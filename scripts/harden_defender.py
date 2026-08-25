"""Blue Hardening Round 1: promote prior Red-Team false negatives, retrain, compare.

Implements the retrain half of the loop `docs/ARCHITECTURE.md` describes as
``RETRAIN | defend/ | promoted hard positives | new model_version`` and the
rules in `docs/EVALUATION_RULES.md` SS2/SS3:

1. **Promote** every scenario transaction (warm-up + fraud) from the frozen
   Round-0 confrontation and the selected Adaptive-Round-1 candidate into a
   hard-positive training set (`aegis.defend.hard_positives`), re-stamped
   `split=train`, with ground truth unchanged and provenance preserved.
2. **Validate** the promotion cannot leak: no promoted `transaction_id`
   collides with validation or test, no duplicate IDs, every fraud row
   carries attack-family/blueprint/generation provenance.
3. **Retrain** Defender v2 via the existing, tested low-memory baseline
   pipeline (`scripts/train_baseline_detector.py`), with the hard positives
   appended to train only. Validation-only threshold tuning and the
   untouched PaySim test split are otherwise identical to the baseline run.
4. **Compare** Defender v2 against the frozen baseline v1 on the untouched
   PaySim test split - never on the hard positives themselves
   (`docs/EVALUATION_RULES.md` SS3: scoring a model on its own just-promoted
   training rows is meaningless and must not be reported as a win).
5. **Hand off** a small, explicit interface for the next Red generation: this
   script does not generate or mutate any attack. See
   `generation2_handoff.json` in the written model artifact.

This script orchestrates; the promotion, streaming-materialization, and
metrics logic it calls all live in `src/aegis/` (`aegis.defend.hard_positives`,
`aegis.features.streaming`, `aegis.defend.metrics`), per `scripts/README.md`.
"""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from aegis.defend.hard_positives import (
    HardPositiveArtifact,
    HardPositivePromotion,
    HardPositiveSource,
    assert_no_duplicate_transaction_ids,
    assert_no_id_overlap_with_jsonl,
    promote_hard_positives,
    write_hard_positive_artifact,
)
from aegis.shared.contracts import EvaluationResult

if TYPE_CHECKING:  # pragma: no cover - static typing only, see the runtime import below
    from scripts.train_baseline_detector import BaselinePipelineConfig, BaselinePipelineResult

# Direct ``python scripts/harden_defender.py`` execution places scripts/, not
# the repository root, on sys.path - same import-by-runtime-name workaround
# `scripts/run_bustout_confrontation.py` already uses.
_training_module = importlib.import_module(
    "scripts.train_baseline_detector" if __package__ else "train_baseline_detector"
)
if not TYPE_CHECKING:
    BaselinePipelineConfig = _training_module.BaselinePipelineConfig
    BaselinePipelineResult = _training_module.BaselinePipelineResult
run_baseline_pipeline = _training_module.run_baseline_pipeline
_is_valid_feature_artifact = _training_module._is_valid_feature_artifact
_DEFAULT_CHUNK_SIZE = _training_module.DEFAULT_CHUNK_SIZE
_LOW_MEMORY_DEFAULT_NTHREAD = _training_module.LOW_MEMORY_DEFAULT_NTHREAD

DEFAULT_ROUND0_CONFRONTATION_DIR = Path(
    "data/synthetic/confrontations/confrontation-416e606888de1ffa"
)
DEFAULT_ADAPTIVE_CANDIDATE_DIR = Path(
    "data/synthetic/adaptive_rounds/adaptive-round-1-864e34ee0950e8bc/candidates/"
    "synthetic-identity-bustout-v1-g1-93aad9875685"
)
DEFAULT_BASELINE_MODEL_DIR = Path("models/xgboost-baseline-20260101")
DEFAULT_MODEL_VERSION_PREFIX = "xgboost-hardened-r1"
DEFAULT_HARDENING_SEED = 20260201
"""Distinct from the baseline's 20260101 seed - a hardening run must never be
mistaken for, or overwrite, the frozen baseline artifact."""


@dataclass(frozen=True)
class HardenDefenderConfig:
    """Everything needed to reproduce one Blue hardening round."""

    processed_dir: Path
    round0_confrontation_dir: Path = DEFAULT_ROUND0_CONFRONTATION_DIR
    adaptive_candidate_dir: Path = DEFAULT_ADAPTIVE_CANDIDATE_DIR
    baseline_model_dir: Path = DEFAULT_BASELINE_MODEL_DIR
    hardening_data_dir: Path = Path("data/hardening")
    model_output_dir: Path = Path("models")
    model_version_prefix: str = DEFAULT_MODEL_VERSION_PREFIX
    seed: int = DEFAULT_HARDENING_SEED
    num_boost_round: int = 300
    latency_sample_size: int = 200
    low_memory: bool = True
    chunk_size: int = _DEFAULT_CHUNK_SIZE
    nthread: int | None = None
    reuse_baseline_validation_test_features: bool = True
    """When `low_memory` and the baseline artifact has cached
    `features/validation` and `features/test` (byte-identical either way,
    since hard positives only ever touch train), copy them into this run's
    feature directory instead of re-streaming ~1.9M unchanged rows."""
    promoted_at: datetime | None = None
    """Fixed timestamp for `metadata.hardening.promoted_at` on every promoted
    row. `None` uses the wall clock (default for a real run); tests pass a
    fixed value so the written hard-positive artifact is byte-for-byte
    reproducible, per AGENTS.md SS6 ("never seed from wall-clock time")."""


@dataclass(frozen=True)
class HardenDefenderResult:
    promotion: HardPositivePromotion
    hard_positive_artifact: HardPositiveArtifact
    training_result: BaselinePipelineResult
    baseline_evaluation: EvaluationResult
    regression_report: dict[str, object]
    regression_report_path: Path
    handoff_path: Path


def run_harden_defender(config: HardenDefenderConfig) -> HardenDefenderResult:
    processed_dir = Path(config.processed_dir)
    validation_path = processed_dir / "validation.jsonl"
    test_path = processed_dir / "test.jsonl"
    train_path = processed_dir / "train.jsonl"
    for path in (train_path, validation_path, test_path):
        if not path.is_file():
            raise ValueError(f"prepared PaySim artifact not found: {path}")

    # -- Phase A: promote ---------------------------------------------------
    sources = [
        HardPositiveSource(
            artifact_dir=Path(config.round0_confrontation_dir), source_round="round-0"
        ),
        HardPositiveSource(
            artifact_dir=Path(config.adaptive_candidate_dir), source_round="adaptive-round-1"
        ),
    ]
    print(f"Promoting hard positives from {len(sources)} source(s):")
    for source in sources:
        print(f"  {source.source_round}: {source.artifact_dir}")
    promotion = promote_hard_positives(sources, promoted_at=config.promoted_at)
    print(
        f"  promoted {len(promotion.transactions)} rows "
        f"({promotion.fraud_count} fraud, {len(promotion.transactions) - promotion.fraud_count} "
        "legitimate warm-up)"
    )

    # -- Phase A: leakage checks ---------------------------------------------
    assert_no_duplicate_transaction_ids(promotion.transactions)
    candidate_ids = set(promotion.transaction_ids)
    print("Checking for transaction-ID overlap with validation/test...")
    assert_no_id_overlap_with_jsonl(candidate_ids, validation_path, label="validation")
    assert_no_id_overlap_with_jsonl(candidate_ids, test_path, label="test")
    assert_no_id_overlap_with_jsonl(candidate_ids, train_path, label="train")
    print("  no overlap found")

    hardening_run_dir = (
        Path(config.hardening_data_dir) / f"hard-positives-r1-{config.seed}"
    )
    hard_positive_artifact = write_hard_positive_artifact(promotion, hardening_run_dir)
    print(f"  hard-positive artifact: {hard_positive_artifact.jsonl_path}")

    # -- Phase B: retrain -----------------------------------------------------
    nthread = config.nthread
    if config.low_memory and nthread is None:
        nthread = _LOW_MEMORY_DEFAULT_NTHREAD

    training_config = BaselinePipelineConfig(
        processed_dir=processed_dir,
        output_dir=config.model_output_dir,
        seed=config.seed,
        num_boost_round=config.num_boost_round,
        latency_sample_size=config.latency_sample_size,
        low_memory=config.low_memory,
        chunk_size=config.chunk_size,
        nthread=nthread,
        model_version_prefix=config.model_version_prefix,
        hard_positive_jsonl=hard_positive_artifact.jsonl_path,
    )

    if config.low_memory and config.reuse_baseline_validation_test_features:
        _maybe_reuse_baseline_features(
            baseline_model_dir=Path(config.baseline_model_dir),
            target_feature_dir=training_config.resolved_feature_artifact_dir(),
        )

    print(f"Training {training_config.model_version} (low_memory={config.low_memory})...")
    training_result = run_baseline_pipeline(training_config)
    print(f"  artifact: {training_result.artifact_dir}")
    print(
        f"  train={training_result.train_size} validation={training_result.validation_size} "
        f"test={training_result.test_size} threshold={training_result.tuned_threshold:.4f}"
    )

    # -- Phase C: regression check vs. frozen baseline v1 ----------------------
    baseline_evaluation_path = Path(config.baseline_model_dir) / "evaluation_test.json"
    baseline_evaluation = EvaluationResult.model_validate_json(
        baseline_evaluation_path.read_text(encoding="utf-8")
    )
    regression_report = _build_regression_report(
        baseline=baseline_evaluation,
        hardened=training_result.test_evaluation,
    )
    regression_report_path = training_result.artifact_dir / "regression_vs_baseline.json"
    regression_report_path.write_text(
        json.dumps(regression_report, indent=2, sort_keys=True), encoding="utf-8"
    )

    # -- Phase D: handoff for a fresh generation-2 Red round -------------------
    handoff_path = training_result.artifact_dir / "generation2_handoff.json"
    handoff_path.write_text(
        json.dumps(
            _build_generation2_handoff(
                training_result=training_result,
                promotion=promotion,
                sources=sources,
                processed_dir=processed_dir,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    return HardenDefenderResult(
        promotion=promotion,
        hard_positive_artifact=hard_positive_artifact,
        training_result=training_result,
        baseline_evaluation=baseline_evaluation,
        regression_report=regression_report,
        regression_report_path=regression_report_path,
        handoff_path=handoff_path,
    )


def _maybe_reuse_baseline_features(*, baseline_model_dir: Path, target_feature_dir: Path) -> None:
    """Copy baseline's cached validation/test feature artifacts, if valid and present.

    Hard positives are appended to train only, so validation and test
    features are byte-identical to the baseline run - re-streaming ~1.9M
    already-materialized rows would be wasted work. Train is deliberately
    never reused here: its content differs (it gains the hard positives).
    """
    for split_name in ("validation", "test"):
        source_dir = baseline_model_dir / "features" / split_name
        target_dir = target_feature_dir / split_name
        if target_dir.exists():
            continue
        if not _is_valid_feature_artifact(source_dir):
            continue
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target_dir)
        print(f"  reusing baseline {split_name} features: {source_dir} -> {target_dir}")


def _build_regression_report(
    *, baseline: EvaluationResult, hardened: EvaluationResult
) -> dict[str, object]:
    """Baseline v1 vs. Defender v2, both on the untouched PaySim test split.

    Never compares against the hard positives themselves
    (`docs/EVALUATION_RULES.md` SS3) - both `EvaluationResult`s here are the
    `evaluation_test.json` each pipeline run wrote from the same, unmodified
    `processed_dir/test.jsonl`.
    """
    b, h = baseline.overall, hardened.overall
    fields = (
        "precision",
        "recall",
        "f1",
        "pr_auc",
        "roc_auc",
        "false_positive_rate",
        "false_negative_rate",
        "alert_rate",
        "threshold",
    )
    metrics: dict[str, dict[str, float | None]] = {}
    for field in fields:
        baseline_value = getattr(b, field)
        hardened_value = getattr(h, field)
        delta = (
            hardened_value - baseline_value
            if isinstance(baseline_value, (int, float)) and isinstance(hardened_value, (int, float))
            else None
        )
        metrics[field] = {
            "baseline_v1": baseline_value,
            "defender_v2": hardened_value,
            "delta": delta,
        }

    recall_at_fpr = {
        budget: {
            "baseline_v1": b.recall_at_fixed_fpr.get(budget),
            "defender_v2": h.recall_at_fixed_fpr.get(budget),
        }
        for budget in sorted(set(b.recall_at_fixed_fpr) | set(h.recall_at_fixed_fpr))
    }

    def _confusion(counts: object) -> dict[str, int]:
        return {
            "true_positives": counts.true_positives,  # type: ignore[attr-defined]
            "false_positives": counts.false_positives,  # type: ignore[attr-defined]
            "true_negatives": counts.true_negatives,  # type: ignore[attr-defined]
            "false_negatives": counts.false_negatives,  # type: ignore[attr-defined]
        }

    latency = {
        "baseline_v1": baseline.latency.model_dump(mode="json") if baseline.latency else None,
        "defender_v2": hardened.latency.model_dump(mode="json") if hardened.latency else None,
    }

    return {
        "dataset_id": hardened.dataset_id,
        "split": str(hardened.split),
        "baseline_model_version": baseline.model_version,
        "defender_v2_model_version": hardened.model_version,
        "metrics": metrics,
        "recall_at_fixed_fpr": recall_at_fpr,
        "confusion_matrix": {
            "baseline_v1": _confusion(b.counts),
            "defender_v2": _confusion(h.counts),
        },
        "support": {"baseline_v1": b.support, "defender_v2": h.support},
        "latency_ms": latency,
        "notes": (
            "Computed on the untouched PaySim test split only - never on the hard "
            "positives used to retrain Defender v2 (docs/EVALUATION_RULES.md SS3)."
        ),
    }


def _build_generation2_handoff(
    *,
    training_result: BaselinePipelineResult,
    promotion: HardPositivePromotion,
    sources: Sequence[HardPositiveSource],
    processed_dir: Path,
) -> dict[str, object]:
    """The interface a fresh Red generation-2 round should use against Defender v2.

    Deliberately reuses the existing, unmodified confrontation/adaptive-round
    scripts - Defender v2 is a normal `XGBoostDetector.save()` artifact, so
    no new Red-facing interface is required:

        python scripts/run_bustout_confrontation.py <processed_dir> \\
            --reuse-model-dir {model_dir} --output-dir data/synthetic/confrontations

        python scripts/run_adaptive_bustout_round.py <processed_dir> \\
            <new_confrontation_dir> {model_dir} --seed <fresh-seed>

    `excluded_transaction_ids` / `excluded_scenario_ids` are the promoted
    hard positives Defender v2 was trained on - generation-2 candidates must
    not reuse them (`docs/EVALUATION_RULES.md` SS4: closed-loop evaluation
    uses attacks generated *after* the retrain, with a fresh seed, never
    round-n samples re-scored against the round-n+1 model).
    """
    scenario_ids = sorted({p.scenario_id for p in promotion.provenance})
    return {
        "defender_version": training_result.model_version,
        "model_dir": str(training_result.artifact_dir),
        "tuned_threshold": training_result.tuned_threshold,
        "trained_on": {
            "processed_dir": str(processed_dir),
            "hard_positive_sources": [
                {"source_round": s.source_round, "artifact_dir": str(s.artifact_dir)}
                for s in sources
            ],
        },
        "excluded_transaction_ids": promotion.fraud_transaction_ids,
        "excluded_scenario_ids": scenario_ids,
        "instructions": (
            "Confront Defender v2 with a genuinely fresh attack, not a re-score of what "
            "it was hardened against: "
            "(1) python scripts/run_bustout_confrontation.py <processed_dir> "
            f"--reuse-model-dir {training_result.artifact_dir} "
            "--output-dir data/synthetic/confrontations --seed <fresh-seed>; "
            "(2) python scripts/run_adaptive_bustout_round.py <processed_dir> "
            f"<new_confrontation_dir> {training_result.artifact_dir} --seed <fresh-seed>. "
            "Generation-2 candidates must not reuse excluded_transaction_ids or "
            "excluded_scenario_ids above, and must use a seed that was not used for "
            "round-0 or adaptive-round-1."
        ),
        "rules": "docs/EVALUATION_RULES.md SS2-4",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Blue Hardening Round 1: promote Round-0 + Adaptive-Round-1 bust-out false "
            "negatives into training-only hard positives, retrain Defender v2, and compare "
            "it against the frozen baseline on untouched PaySim test."
        )
    )
    parser.add_argument(
        "processed_dir",
        type=Path,
        help="prepared PaySim run directory (train/validation/test.jsonl)",
    )
    parser.add_argument(
        "--round0-confrontation-dir", type=Path, default=DEFAULT_ROUND0_CONFRONTATION_DIR
    )
    parser.add_argument(
        "--adaptive-candidate-dir", type=Path, default=DEFAULT_ADAPTIVE_CANDIDATE_DIR
    )
    parser.add_argument("--baseline-model-dir", type=Path, default=DEFAULT_BASELINE_MODEL_DIR)
    parser.add_argument("--hardening-data-dir", type=Path, default=Path("data/hardening"))
    parser.add_argument("--model-output-dir", type=Path, default=Path("models"))
    parser.add_argument("--model-version-prefix", type=str, default=DEFAULT_MODEL_VERSION_PREFIX)
    parser.add_argument("--seed", type=int, default=DEFAULT_HARDENING_SEED)
    parser.add_argument("--num-boost-round", type=int, default=300)
    parser.add_argument("--latency-sample-size", type=int, default=200)
    parser.add_argument("--low-memory", action="store_true", default=True)
    parser.add_argument(
        "--no-low-memory", dest="low_memory", action="store_false", help="use the in-memory path"
    )
    parser.add_argument("--chunk-size", type=int, default=_DEFAULT_CHUNK_SIZE)
    parser.add_argument("--nthread", type=int, default=None)
    parser.add_argument(
        "--no-reuse-baseline-features",
        dest="reuse_baseline_features",
        action="store_false",
        default=True,
        help="always re-materialize validation/test features instead of copying the baseline's",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = HardenDefenderConfig(
        processed_dir=args.processed_dir,
        round0_confrontation_dir=args.round0_confrontation_dir,
        adaptive_candidate_dir=args.adaptive_candidate_dir,
        baseline_model_dir=args.baseline_model_dir,
        hardening_data_dir=args.hardening_data_dir,
        model_output_dir=args.model_output_dir,
        model_version_prefix=args.model_version_prefix,
        seed=args.seed,
        num_boost_round=args.num_boost_round,
        latency_sample_size=args.latency_sample_size,
        low_memory=args.low_memory,
        chunk_size=args.chunk_size,
        nthread=args.nthread,
        reuse_baseline_validation_test_features=args.reuse_baseline_features,
    )
    result = run_harden_defender(config)

    print()
    print(f"Defender v2: {result.training_result.model_version}")
    print(f"  artifact: {result.training_result.artifact_dir}")
    print(f"  hard positives: {result.hard_positive_artifact.jsonl_path}")
    print("Validation metrics (threshold tuned here, never on test):")
    print(
        json.dumps(
            result.training_result.validation_evaluation.overall.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
    )
    print("Test metrics (untouched PaySim test):")
    print(
        json.dumps(
            result.training_result.test_evaluation.overall.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
    )
    print(f"Baseline v1 vs Defender v2: {result.regression_report_path}")
    print(f"Generation-2 handoff: {result.handoff_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
