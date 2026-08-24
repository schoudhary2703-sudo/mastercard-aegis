"""Train and evaluate the Blue Team baseline fraud detector.

This script is the one place allowed to depend on both `aegis.features` and
`aegis.defend`: `docs/ARCHITECTURE.md` restricts every package under
`src/aegis/` to `shared` only (`loop/` aside, which is out of scope for this
phase), so the feature-extraction -> training -> evaluation sequencing lives
here rather than inside either package. All actual logic - feature
computation, model training, metric math - stays in `src/aegis/`; this file
only sequences calls and handles paths/CLI, per scripts/README.md.

Command (after `python scripts/prepare_paysim.py ...` has produced a
processed run directory)::

    python scripts/train_baseline_detector.py \\
        data/processed/paysim/<run-dir> --seed 20260101

Writes the trained model, its metadata, and both evaluation results under
`models/<model_version>/` (default; override with --output-dir).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from aegis.defend import ActionPolicy, XGBoostDetector
from aegis.defend.metrics import (
    DEFAULT_FPR_BUDGETS,
    build_evaluation_result,
    measure_scoring_latency,
    tune_threshold_for_f1,
)
from aegis.defend.xgboost_detector import DEFAULT_NUM_BOOST_ROUND
from aegis.features import TemporalBaselineFeatureExtractor, load_transactions_jsonl
from aegis.shared.contracts import EvaluationResult, Transaction
from aegis.shared.enums import DataSplit, EvaluationProtocol, FraudLabel

TRAIN_FILENAME = "train.jsonl"
VALIDATION_FILENAME = "validation.jsonl"
TEST_FILENAME = "test.jsonl"


@dataclass(frozen=True)
class BaselinePipelineConfig:
    """Everything needed to reproduce one training/evaluation run."""

    processed_dir: Path
    output_dir: Path
    seed: int = 20260101
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND
    fpr_budgets: tuple[float, ...] = field(default_factory=lambda: DEFAULT_FPR_BUDGETS)
    latency_sample_size: int = 200

    @property
    def dataset_id(self) -> str:
        return Path(self.processed_dir).name


@dataclass(frozen=True)
class BaselinePipelineResult:
    """What one pipeline run produced, for the CLI to print and tests to assert on."""

    model_version: str
    artifact_dir: Path
    tuned_threshold: float
    scale_pos_weight: float
    train_size: int
    validation_size: int
    test_size: int
    validation_evaluation: EvaluationResult
    test_evaluation: EvaluationResult


def _labelled_only(transactions: list[Transaction]) -> list[Transaction]:
    """Drop `FraudLabel.UNKNOWN` rows. Unknown is not legitimate; it is unusable."""
    return [t for t in transactions if t.label is not FraudLabel.UNKNOWN]


def run_baseline_pipeline(config: BaselinePipelineConfig) -> BaselinePipelineResult:
    """Train, tune, evaluate, and persist the baseline XGBoost detector."""
    processed_dir = Path(config.processed_dir)
    train = _labelled_only(load_transactions_jsonl(processed_dir / TRAIN_FILENAME))
    validation = _labelled_only(load_transactions_jsonl(processed_dir / VALIDATION_FILENAME))
    test = _labelled_only(load_transactions_jsonl(processed_dir / TEST_FILENAME))

    extractor = TemporalBaselineFeatureExtractor()
    X_train = extractor.fit_transform(train)
    y_train = np.array([int(t.is_fraud) for t in train])
    X_validation = extractor.transform(validation)
    y_validation = np.array([int(t.is_fraud) for t in validation])
    X_test = extractor.transform(test)
    y_test = np.array([int(t.is_fraud) for t in test])

    model_version = f"xgboost-baseline-{config.seed}"
    detector = XGBoostDetector(
        seed=config.seed,
        num_boost_round=config.num_boost_round,
        model_version=model_version,
    )
    detector.fit(X_train, y_train)
    resolved_spw = detector.scale_pos_weight or 1.0

    # -- threshold tuning: validation only, never test -----------------------
    validation_scores = detector.score(X_validation)
    threshold = tune_threshold_for_f1(y_validation, validation_scores)
    detector.action_policy = ActionPolicy(
        step_up_at=threshold,
        review_at=min(1.0, threshold + (1.0 - threshold) * 0.4),
        decline_at=min(1.0, threshold + (1.0 - threshold) * 0.7),
        label_threshold=threshold,
    )

    validation_outputs = detector.predict(
        X_validation, [t.transaction_id for t in validation], explain=False
    )
    validation_output_scores = np.array([o.risk_score for o in validation_outputs])
    validation_latency = measure_scoring_latency(
        detector, X_validation, sample_size=config.latency_sample_size
    )
    validation_evaluation = build_evaluation_result(
        evaluation_id=f"{model_version}-validation",
        y_true=y_validation,
        scores=validation_output_scores,
        threshold=threshold,
        model_version=model_version,
        dataset_id=config.dataset_id,
        split=DataSplit.VALIDATION,
        protocol=EvaluationProtocol.STATIC_HOLDOUT,
        latency=validation_latency,
        fpr_budgets=config.fpr_budgets,
        seed=config.seed,
        notes="Threshold tuned on this split (maximize F1).",
    )

    # -- test: touched once, after the threshold is fixed --------------------
    test_outputs = detector.predict(X_test, [t.transaction_id for t in test], explain=False)
    test_output_scores = np.array([o.risk_score for o in test_outputs])
    test_latency = measure_scoring_latency(detector, X_test, sample_size=config.latency_sample_size)
    test_evaluation = build_evaluation_result(
        evaluation_id=f"{model_version}-test",
        y_true=y_test,
        scores=test_output_scores,
        threshold=threshold,
        model_version=model_version,
        dataset_id=config.dataset_id,
        split=DataSplit.TEST,
        protocol=EvaluationProtocol.STATIC_HOLDOUT,
        latency=test_latency,
        fpr_budgets=config.fpr_budgets,
        seed=config.seed,
        notes="Final reported figure; threshold fixed from validation only.",
    )

    artifact_dir = Path(config.output_dir) / model_version
    detector.save(str(artifact_dir))
    (artifact_dir / "evaluation_validation.json").write_text(
        validation_evaluation.to_json(indent=2), encoding="utf-8"
    )
    (artifact_dir / "evaluation_test.json").write_text(
        test_evaluation.to_json(indent=2), encoding="utf-8"
    )

    return BaselinePipelineResult(
        model_version=model_version,
        artifact_dir=artifact_dir,
        tuned_threshold=threshold,
        scale_pos_weight=resolved_spw,
        train_size=len(train),
        validation_size=len(validation),
        test_size=len(test),
        validation_evaluation=validation_evaluation,
        test_evaluation=test_evaluation,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train the XGBoost baseline detector on a processed PaySim run directory "
            "(train/validation/test.jsonl), tune its threshold on validation, and "
            "evaluate once on validation and once on test."
        )
    )
    parser.add_argument(
        "processed_dir",
        type=Path,
        help="processed PaySim run directory, e.g. data/processed/paysim/<run>",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("models"),
        help="directory the trained model artifact is written under (default: models)",
    )
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--num-boost-round", type=int, default=DEFAULT_NUM_BOOST_ROUND)
    parser.add_argument("--latency-sample-size", type=int, default=200)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = BaselinePipelineConfig(
        processed_dir=args.processed_dir,
        output_dir=args.output_dir,
        seed=args.seed,
        num_boost_round=args.num_boost_round,
        latency_sample_size=args.latency_sample_size,
    )
    result = run_baseline_pipeline(config)

    print(f"Trained {result.model_version}")
    print(
        f"  train={result.train_size} validation={result.validation_size} test={result.test_size}"
    )
    print(
        f"  scale_pos_weight={result.scale_pos_weight:.3f} "
        f"tuned_threshold={result.tuned_threshold:.4f}"
    )
    print(f"  artifact: {result.artifact_dir}")
    print("Validation metrics:")
    validation_summary = result.validation_evaluation.overall.model_dump(mode="json")
    print(json.dumps(validation_summary, indent=2, sort_keys=True))
    print("Test metrics:")
    test_summary = result.test_evaluation.overall.model_dump(mode="json")
    print(json.dumps(test_summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
