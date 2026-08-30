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

Memory-safe mode
-----------------
`--low-memory` replaces the default in-memory path (load every split as
`Transaction` objects, extract features into one `float64` DataFrame per
split, hold train/validation/test simultaneously) with a streaming one: each
split is materialized to compact on-disk `float32` feature arrays one at a
time (`aegis.features.streaming`), the raw split is released before the next
one is touched, and training reads the resulting small arrays. Feature
values, labels, row order, and thresholding logic are unchanged - this is an
execution-level optimization, not a model or feature change. See
`docs/BASELINE_DETECTOR.md` "Memory-safe materialization" for the full
diagnosis and design, and `tests/test_features_streaming.py` for the
semantic-equivalence proof.

Hard-positive hardening
------------------------
`--hard-positives-jsonl` (paired with `--model-version-prefix` so a hardened
run never collides with `models/xgboost-baseline-*`) folds promoted prior
false negatives (`aegis.defend.hard_positives`) into train only - validation
and test are read and scored exactly as in the plain baseline run. See
`scripts/harden_defender.py` for the end-to-end promotion + retrain +
regression-check orchestration, and `docs/EVALUATION_RULES.md` SS2/SS3 for
the rules this exists to satisfy.
"""

from __future__ import annotations

import argparse
import gc
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from aegis.defend import ActionPolicy, XGBoostDetector
from aegis.defend.hard_positives import (
    DEFAULT_PROMOTED_POSITIVE_MASS_SHARE,
    promoted_sample_weights,
)
from aegis.defend.metrics import (
    DEFAULT_FPR_BUDGETS,
    build_evaluation_result,
    measure_scoring_latency,
    threshold_at_fpr_budget,
    tune_threshold_for_f1,
)
from aegis.defend.xgboost_detector import DEFAULT_HYPERPARAMETERS, DEFAULT_NUM_BOOST_ROUND
from aegis.features import TemporalBaselineFeatureExtractor, load_transactions_jsonl
from aegis.features.io import count_labelled_jsonl_lines
from aegis.features.streaming import (
    DEFAULT_CHUNK_SIZE,
    FEATURES_FILENAME,
    LABELS_FILENAME,
    SCHEMA_FILENAME,
    TRANSACTION_IDS_FILENAME,
    FeatureArtifact,
    materialize_split_features,
    materialize_split_features_with_extra,
)
from aegis.shared.contracts import EvaluationResult, Transaction
from aegis.shared.enums import DataSplit, EvaluationProtocol, FraudLabel

TRAIN_FILENAME = "train.jsonl"
VALIDATION_FILENAME = "validation.jsonl"
TEST_FILENAME = "test.jsonl"
LOW_MEMORY_DEFAULT_NTHREAD = 2
"""Conservative default thread count for --low-memory on an ~8GB machine."""

THRESHOLD_RULE_F1 = "f1"
THRESHOLD_RULE_FPR_BUDGET = "fpr_budget"
THRESHOLD_RULES = (THRESHOLD_RULE_FPR_BUDGET, THRESHOLD_RULE_F1)
DEFAULT_THRESHOLD_FPR_BUDGET = 0.005
"""Default false-positive budget for the operating point, one of the agreed
`DEFAULT_FPR_BUDGETS` the project already reports `recall_at_fixed_fpr` at.

0.005 means roughly one review per 200 legitimate payments - a review load a
real issuer can staff, and the middle of the three budgets
`docs/EVALUATION_RULES.md` already requires reporting."""


@dataclass(frozen=True)
class BaselinePipelineConfig:
    """Everything needed to reproduce one training/evaluation run."""

    processed_dir: Path
    output_dir: Path
    seed: int = 20260101
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND
    fpr_budgets: tuple[float, ...] = field(default_factory=lambda: DEFAULT_FPR_BUDGETS)
    latency_sample_size: int = 200
    low_memory: bool = False
    chunk_size: int = DEFAULT_CHUNK_SIZE
    nthread: int | None = None
    feature_artifact_dir: Path | None = None
    model_version_prefix: str = "xgboost-baseline"
    hard_positive_jsonl: Path | None = None
    """Promoted hard-positive rows (see `aegis.defend.hard_positives`),
    already re-stamped `split=train` and chronologically sorted, appended to
    train only - validation and test are untouched either way. `None`
    reproduces the plain baseline pipeline exactly."""
    threshold_rule: str = THRESHOLD_RULE_FPR_BUDGET
    """How the operating point is chosen on validation - see
    `_select_threshold`. `"fpr_budget"` (default) maximizes recall inside
    `threshold_fpr_budget`; `"f1"` reproduces the original F1-maximizing
    behavior for regression comparisons against the frozen v1/v2 artifacts."""
    threshold_fpr_budget: float = DEFAULT_THRESHOLD_FPR_BUDGET
    """False-positive budget the operating point must respect under
    `threshold_rule="fpr_budget"`. Ignored under `"f1"`."""
    hard_positive_mass_share: float = DEFAULT_PROMOTED_POSITIVE_MASS_SHARE
    """Share of total positive gradient mass the promoted hard positives carry.

    Only meaningful with `hard_positive_jsonl` set. 0.0 reproduces the
    previous unweighted behavior, under which a 22-row promotion into a
    training split holding thousands of positives had no measurable effect -
    see `aegis.defend.hard_positives.promoted_sample_weights`."""
    early_stopping: bool = True
    """Stop boosting once validation `aucpr` stops improving, instead of always
    running the full `num_boost_round`. Uses validation labels to choose *when
    to stop*, the same split and the same way the threshold is tuned - test is
    never involved. Set `False` to reproduce the fixed-300-round v1/v2 fits."""

    @property
    def dataset_id(self) -> str:
        return Path(self.processed_dir).name

    @property
    def model_version(self) -> str:
        return f"{self.model_version_prefix}-{self.seed}"

    @property
    def artifact_dir(self) -> Path:
        return Path(self.output_dir) / self.model_version

    def resolved_feature_artifact_dir(self) -> Path:
        return self.feature_artifact_dir or (self.artifact_dir / "features")

    def resolved_hyperparameters(self) -> dict[str, object]:
        params = dict(DEFAULT_HYPERPARAMETERS)
        if self.nthread is not None:
            params["nthread"] = self.nthread
        return params


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


def _schema_int(schema: dict[str, object], key: str) -> int:
    value = schema[key]
    if not isinstance(value, int):
        msg = f"schema field {key!r} is not an int: {value!r}"
        raise ValueError(msg)
    return value


def _schema_str_list(schema: dict[str, object], key: str) -> list[str]:
    value = schema[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"schema field {key!r} is not a list of strings: {value!r}"
        raise ValueError(msg)
    return value


def _is_valid_feature_artifact(directory: Path) -> bool:
    """Whether `directory` holds a complete, previously materialized artifact.

    `materialize_split_features` only writes `schema.json` - the last file it
    writes - after `features.npy`/`labels.npy`/`transaction_ids.txt` are
    already flushed, and only ever publishes a directory by atomically
    renaming a temp directory once every file is in place. So an existing
    directory (not a `.tmp-*` one, which is never renamed to its final name
    until complete) containing all four files, with the transaction-id count
    matching the row count the schema claims, is complete by construction -
    this is a cheap sanity check, not a full re-validation.
    """
    if not directory.is_dir():
        return False
    required = (FEATURES_FILENAME, LABELS_FILENAME, TRANSACTION_IDS_FILENAME, SCHEMA_FILENAME)
    if not all((directory / name).exists() for name in required):
        return False
    try:
        schema = FeatureArtifact.load_schema(directory)
        expected_rows = _schema_int(schema, "row_count")
        with (directory / TRANSACTION_IDS_FILENAME).open("r", encoding="utf-8") as handle:
            actual_rows = sum(1 for line in handle if line.strip())
    except (OSError, ValueError, KeyError):
        return False
    return actual_rows == expected_rows


def _materialize_or_reuse(
    jsonl_path: Path,
    output_dir: Path,
    *,
    chunk_size: int,
    label: str,
    extra_jsonl_path: Path | None = None,
) -> FeatureArtifact:
    """Reuse a complete prior materialization; only redo genuinely missing/invalid work.

    `extra_jsonl_path`, when given, is appended after `jsonl_path` as one
    logical chronological stream (see
    `aegis.features.streaming.materialize_split_features_with_extra`) - used
    only for the train split, to fold in promoted hard positives.
    """
    if _is_valid_feature_artifact(output_dir):
        schema = FeatureArtifact.load_schema(output_dir)
        print(f"  reusing existing {label} feature artifact: {output_dir}")
        return FeatureArtifact(
            directory=output_dir,
            row_count=_schema_int(schema, "row_count"),
            feature_names=_schema_str_list(schema, "feature_names"),
            namespace=str(schema["namespace"]),
            chunk_size=_schema_int(schema, "chunk_size"),
            source_path=Path(str(schema["source_path"]).split(" + ", 1)[0]),
        )
    if output_dir.exists():
        # Exists but failed validation: something other than a completed
        # `materialize_split_features` run produced it. Do not silently
        # trust or delete it - fail loudly so a human decides.
        msg = (
            f"{output_dir} exists but is not a complete, valid feature artifact; "
            "remove it manually if it is safe to discard, then retry"
        )
        raise FileExistsError(msg)
    if extra_jsonl_path is not None:
        print(f"  materializing {label} features (+ hard positives) -> {output_dir}")
        return materialize_split_features_with_extra(
            jsonl_path, [extra_jsonl_path], output_dir, chunk_size=chunk_size
        )
    print(f"  materializing {label} features -> {output_dir}")
    return materialize_split_features(jsonl_path, output_dir, chunk_size=chunk_size)


def run_baseline_pipeline(config: BaselinePipelineConfig) -> BaselinePipelineResult:
    """Train, tune, evaluate, and persist the baseline XGBoost detector.

    Dispatches to the streaming, bounded-memory implementation when
    `config.low_memory` is set; otherwise uses the original in-memory
    implementation. Both produce the same feature values, labels, threshold
    logic, and `EvaluationResult` shape - see
    `tests/test_features_streaming.py` and `docs/BASELINE_DETECTOR.md`.
    """
    if config.low_memory:
        return _run_low_memory_pipeline(config)
    return _run_in_memory_pipeline(config)


def _finish_and_save(
    config: BaselinePipelineConfig,
    detector: XGBoostDetector,
    resolved_spw: float,
    threshold: float,
    train_size: int,
    validation_size: int,
    test_size: int,
    validation_evaluation: EvaluationResult,
    test_evaluation: EvaluationResult,
) -> BaselinePipelineResult:
    artifact_dir = config.artifact_dir
    detector.save(str(artifact_dir))
    # The operating-point rule is not part of the detector's own metadata -
    # it is a pipeline decision, not a model parameter - but reproducing a
    # reported figure requires knowing which rule produced the threshold, so
    # record it beside the model rather than only in the evaluation notes.
    (artifact_dir / "threshold_selection.json").write_text(
        json.dumps(
            {
                "threshold_rule": config.threshold_rule,
                "threshold_fpr_budget": (
                    config.threshold_fpr_budget
                    if config.threshold_rule == THRESHOLD_RULE_FPR_BUDGET
                    else None
                ),
                "selected_threshold": threshold,
                "tuned_on": "validation",
                "description": _threshold_note(config),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (artifact_dir / "evaluation_validation.json").write_text(
        validation_evaluation.to_json(indent=2), encoding="utf-8"
    )
    (artifact_dir / "evaluation_test.json").write_text(
        test_evaluation.to_json(indent=2), encoding="utf-8"
    )
    return BaselinePipelineResult(
        model_version=config.model_version,
        artifact_dir=artifact_dir,
        tuned_threshold=threshold,
        scale_pos_weight=resolved_spw,
        train_size=train_size,
        validation_size=validation_size,
        test_size=test_size,
        validation_evaluation=validation_evaluation,
        test_evaluation=test_evaluation,
    )


def _run_in_memory_pipeline(config: BaselinePipelineConfig) -> BaselinePipelineResult:
    processed_dir = Path(config.processed_dir)
    train = _labelled_only(load_transactions_jsonl(processed_dir / TRAIN_FILENAME))
    promoted_row_count = 0
    if config.hard_positive_jsonl is not None:
        # Order doesn't affect the in-memory extractor, which re-sorts by
        # timestamp internally (`TemporalBaselineFeatureExtractor._compute_rows`) -
        # unlike the streaming path, which requires a pre-sorted concatenation.
        promoted = _labelled_only(load_transactions_jsonl(config.hard_positive_jsonl))
        promoted_row_count = len(promoted)
        train = train + promoted
    validation = _labelled_only(load_transactions_jsonl(processed_dir / VALIDATION_FILENAME))
    test = _labelled_only(load_transactions_jsonl(processed_dir / TEST_FILENAME))

    extractor = TemporalBaselineFeatureExtractor()
    X_train = extractor.fit_transform(train)
    y_train = np.array([int(t.is_fraud) for t in train])
    X_validation = extractor.transform(validation)
    y_validation = np.array([int(t.is_fraud) for t in validation])
    X_test = extractor.transform(test)
    y_test = np.array([int(t.is_fraud) for t in test])

    model_version = config.model_version
    detector = XGBoostDetector(
        seed=config.seed,
        num_boost_round=config.num_boost_round,
        hyperparameters=config.resolved_hyperparameters(),
        model_version=model_version,
    )
    detector.fit(
        X_train,
        y_train,
        meta=_fit_meta(
            config,
            X_validation,
            y_validation,
            _hard_positive_weights(config, y_train, promoted_row_count),
        ),
    )
    resolved_spw = detector.scale_pos_weight or 1.0

    # -- threshold tuning: validation only, never test -----------------------
    validation_scores = detector.score(X_validation)
    threshold = _select_threshold(config, y_validation, validation_scores)
    detector.action_policy = _policy_for_threshold(threshold)

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
        notes=f"Threshold tuned on this split ({_threshold_note(config)}).",
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

    return _finish_and_save(
        config,
        detector,
        resolved_spw,
        threshold,
        len(train),
        len(validation),
        len(test),
        validation_evaluation,
        test_evaluation,
    )


def _select_threshold(
    config: BaselinePipelineConfig, y_validation: np.ndarray, validation_scores: np.ndarray
) -> float:
    """Choose the operating point on validation, per `config.threshold_rule`.

    Default (`"fpr_budget"`): the lowest threshold whose false-positive rate
    stays inside `config.threshold_fpr_budget`. This is how a payment system
    actually sets a cutoff - review capacity fixes the false-positive budget,
    and the threshold takes as much recall as fits inside it.

    `"f1"` reproduces the original behavior. It is retained because the frozen
    baseline-v1 and defender-v2 artifacts were produced under it, so a
    like-for-like regression comparison against them needs the same rule; it
    is not recommended for new models. On the real PaySim test split F1
    tuning settles at recall 0.779 / FPR 0.0002, well inside every budget the
    project reports against - it spends recall on precision nobody asked for.

    Whichever rule runs, the threshold is still computed on validation only
    and applied unchanged to test (`docs/EVALUATION_RULES.md`).
    """
    if config.threshold_rule == THRESHOLD_RULE_F1:
        return tune_threshold_for_f1(y_validation, validation_scores)
    if config.threshold_rule == THRESHOLD_RULE_FPR_BUDGET:
        return threshold_at_fpr_budget(y_validation, validation_scores, config.threshold_fpr_budget)
    msg = f"unknown threshold_rule {config.threshold_rule!r}; expected one of {THRESHOLD_RULES}"
    raise ValueError(msg)


def _fit_meta(
    config: BaselinePipelineConfig,
    X_validation: pd.DataFrame,
    y_validation: np.ndarray,
    sample_weight: np.ndarray | None = None,
) -> dict[str, object] | None:
    """Side-channel passed to `XGBoostDetector.fit`, per `BaseDetector.fit`'s contract.

    Carries the validation split as an `eval_set` so boosting stops when
    validation `aucpr` stops improving. Without it `num_boost_round` is a
    fixed guess and the `eval_metric` declared in `DEFAULT_HYPERPARAMETERS`
    is never computed at all.

    Also carries `sample_weight` when hard positives were promoted, so those
    rows reach a share of positive gradient mass rather than being lost in a
    multi-million-row split.

    This is the same validation split the threshold is tuned on, used the same
    way - to fix a hyper-parameter of the fitted model. Test remains untouched
    until the single final evaluation (`docs/EVALUATION_RULES.md`).
    """
    meta: dict[str, object] = {}
    if config.early_stopping:
        meta["eval_set"] = (X_validation, y_validation)
    if sample_weight is not None:
        meta["sample_weight"] = sample_weight
    return meta or None


def _hard_positive_weights(
    config: BaselinePipelineConfig, y_train: np.ndarray, promoted_row_count: int
) -> np.ndarray | None:
    """Training weights that give promoted hard positives real gradient mass.

    Returns `None` - meaning unweighted, XGBoost's default - when nothing was
    promoted or weighting is switched off, so a plain baseline run is
    bit-identical to the pre-weighting pipeline.
    """
    if promoted_row_count <= 0 or config.hard_positive_mass_share <= 0.0:
        return None
    return promoted_sample_weights(
        y_train, promoted_row_count, positive_mass_share=config.hard_positive_mass_share
    )


def _threshold_note(config: BaselinePipelineConfig) -> str:
    """Human-readable description of the operating-point rule, for evaluation notes."""
    if config.threshold_rule == THRESHOLD_RULE_F1:
        return "maximize F1"
    return f"maximize recall within FPR <= {config.threshold_fpr_budget}"


def _policy_for_threshold(threshold: float) -> ActionPolicy:
    return ActionPolicy(
        step_up_at=threshold,
        review_at=min(1.0, threshold + (1.0 - threshold) * 0.4),
        decline_at=min(1.0, threshold + (1.0 - threshold) * 0.7),
        label_threshold=threshold,
    )


def _run_low_memory_pipeline(config: BaselinePipelineConfig) -> BaselinePipelineResult:
    """Sequential, one-split-at-a-time version of `_run_in_memory_pipeline`.

    A. materialize train + validation features -> B. train -> C. release train
    D. tune threshold on validation -> E. release validation
    F. materialize test features -> G. evaluate once -> H. release test

    Train, validation, and test raw feature arrays are never resident at the
    same time; only the trained `XGBoostDetector` (a small `Booster`)
    survives from one stage to the next.

    Validation is *materialized* before training (it was materialized after,
    before early stopping existed) so it can serve as the `eval_set`.
    Materialization itself is a bounded-memory streaming write to disk, and
    the array is then memory-mapped, so the only new resident cost is the
    validation `DMatrix` XGBoost builds for evaluation - about 80MB for a
    955k-row, 21-feature float32 split, against the multi-GB peaks this mode
    exists to avoid. Set `early_stopping=False` to skip building it entirely.
    """
    processed_dir = Path(config.processed_dir)
    feature_root = config.resolved_feature_artifact_dir()
    model_version = config.model_version
    hyperparameters = config.resolved_hyperparameters()
    # Promoted rows are appended after the base split by
    # `materialize_split_features_with_extra`, so they occupy the last
    # `promoted_row_count` positions of the materialized array - the ordering
    # `promoted_sample_weights` requires. Counted the same way the streaming
    # materializer counts, so UNKNOWN-label rows are excluded from both.
    promoted_row_count = (
        count_labelled_jsonl_lines(config.hard_positive_jsonl)
        if config.hard_positive_jsonl is not None
        else 0
    )

    # A/B/C -------------------------------------------------------------
    train_artifact = _materialize_or_reuse(
        processed_dir / TRAIN_FILENAME,
        feature_root / "train",
        chunk_size=config.chunk_size,
        label="train",
        extra_jsonl_path=config.hard_positive_jsonl,
    )
    validation_artifact = _materialize_or_reuse(
        processed_dir / VALIDATION_FILENAME,
        feature_root / "validation",
        chunk_size=config.chunk_size,
        label="validation",
    )
    X_train = pd.DataFrame(
        train_artifact.load_features(mmap=True), columns=train_artifact.feature_names, copy=False
    )
    y_train = train_artifact.load_labels()
    train_size = train_artifact.row_count

    detector = XGBoostDetector(
        seed=config.seed,
        num_boost_round=config.num_boost_round,
        hyperparameters=hyperparameters,
        model_version=model_version,
    )
    sample_weight = _hard_positive_weights(config, y_train, promoted_row_count)
    if config.early_stopping:
        # Memory-mapped, so this is a lazy view of the on-disk array rather
        # than a second resident copy of the validation split.
        X_eval = pd.DataFrame(
            validation_artifact.load_features(mmap=True),
            columns=validation_artifact.feature_names,
            copy=False,
        )
        fit_meta = _fit_meta(config, X_eval, validation_artifact.load_labels(), sample_weight)
        detector.fit(X_train, y_train, meta=fit_meta)
        del X_eval, fit_meta
    else:
        detector.fit(
            X_train,
            y_train,
            meta={"sample_weight": sample_weight} if sample_weight is not None else None,
        )
    resolved_spw = detector.scale_pos_weight or 1.0

    del X_train, y_train
    gc.collect()

    # D/E -----------------------------------------------------------------
    X_validation = pd.DataFrame(
        validation_artifact.load_features(mmap=True),
        columns=validation_artifact.feature_names,
        copy=False,
    )
    y_validation = validation_artifact.load_labels()
    validation_ids = validation_artifact.load_transaction_ids()
    validation_size = validation_artifact.row_count

    validation_scores = detector.score(X_validation)
    threshold = _select_threshold(config, y_validation, validation_scores)
    detector.action_policy = _policy_for_threshold(threshold)

    validation_outputs = detector.predict(X_validation, validation_ids, explain=False)
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
        notes=f"Threshold tuned on this split ({_threshold_note(config)}). low_memory=True.",
    )

    del X_validation, y_validation, validation_ids
    gc.collect()

    # F/G/H ---------------------------------------------------------------
    test_artifact = _materialize_or_reuse(
        processed_dir / TEST_FILENAME,
        feature_root / "test",
        chunk_size=config.chunk_size,
        label="test",
    )
    X_test = pd.DataFrame(
        test_artifact.load_features(mmap=True), columns=test_artifact.feature_names, copy=False
    )
    y_test = test_artifact.load_labels()
    test_ids = test_artifact.load_transaction_ids()
    test_size = test_artifact.row_count

    test_outputs = detector.predict(X_test, test_ids, explain=False)
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
        notes="Final reported figure; threshold fixed from validation only. low_memory=True.",
    )

    del X_test, y_test, test_ids
    gc.collect()

    return _finish_and_save(
        config,
        detector,
        resolved_spw,
        threshold,
        train_size,
        validation_size,
        test_size,
        validation_evaluation,
        test_evaluation,
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
    parser.add_argument(
        "--low-memory",
        action="store_true",
        help=(
            "stream each split to compact on-disk float32 feature arrays one at a time "
            "instead of loading train/validation/test simultaneously as Transaction "
            "objects. Same features, labels, and thresholding - execution-only."
        ),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"rows per streaming chunk in --low-memory mode (default: {DEFAULT_CHUNK_SIZE})",
    )
    parser.add_argument(
        "--nthread",
        type=int,
        default=None,
        help=(
            "XGBoost thread count. Defaults to XGBoost's own default normally, or "
            f"{LOW_MEMORY_DEFAULT_NTHREAD} when --low-memory is set and this is omitted."
        ),
    )
    parser.add_argument(
        "--feature-artifact-dir",
        type=Path,
        default=None,
        help="where --low-memory writes feature arrays (default: under the model artifact dir)",
    )
    parser.add_argument(
        "--model-version-prefix",
        type=str,
        default="xgboost-baseline",
        help=(
            "prefix for model_version and the output directory name, e.g. "
            "'xgboost-hardened-r1' -> models/xgboost-hardened-r1-<seed>/ (default: "
            "xgboost-baseline)"
        ),
    )
    parser.add_argument(
        "--threshold-rule",
        choices=THRESHOLD_RULES,
        default=THRESHOLD_RULE_FPR_BUDGET,
        help=(
            "how the validation-tuned operating point is chosen. 'fpr_budget' "
            "(default) maximizes recall inside --threshold-fpr-budget, which is how "
            "a live payment system sets a cutoff. 'f1' maximizes F1 and exists to "
            "reproduce the frozen baseline-v1/defender-v2 artifacts for "
            "like-for-like regression comparison."
        ),
    )
    parser.add_argument(
        "--threshold-fpr-budget",
        type=float,
        default=DEFAULT_THRESHOLD_FPR_BUDGET,
        help=(
            "false-positive budget the operating point must respect under "
            f"--threshold-rule fpr_budget (default: {DEFAULT_THRESHOLD_FPR_BUDGET})"
        ),
    )
    parser.add_argument(
        "--no-early-stopping",
        action="store_true",
        help=(
            "train for the full --num-boost-round instead of stopping when validation "
            "aucpr stops improving. Reproduces the fixed-300-round baseline-v1/"
            "defender-v2 fits."
        ),
    )
    parser.add_argument(
        "--hard-positives-jsonl",
        type=Path,
        default=None,
        help=(
            "promoted hard-positive rows (aegis.defend.hard_positives), already "
            "split=train and chronologically sorted, appended to train only. "
            "Validation and test are never touched. Omit for the plain baseline."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    nthread = args.nthread
    if args.low_memory and nthread is None:
        nthread = LOW_MEMORY_DEFAULT_NTHREAD

    config = BaselinePipelineConfig(
        processed_dir=args.processed_dir,
        output_dir=args.output_dir,
        seed=args.seed,
        num_boost_round=args.num_boost_round,
        latency_sample_size=args.latency_sample_size,
        low_memory=args.low_memory,
        chunk_size=args.chunk_size,
        nthread=nthread,
        feature_artifact_dir=args.feature_artifact_dir,
        model_version_prefix=args.model_version_prefix,
        hard_positive_jsonl=args.hard_positives_jsonl,
        threshold_rule=args.threshold_rule,
        threshold_fpr_budget=args.threshold_fpr_budget,
        early_stopping=not args.no_early_stopping,
    )
    result = run_baseline_pipeline(config)

    print(f"Trained {result.model_version} (low_memory={config.low_memory})")
    print(
        f"  train={result.train_size} validation={result.validation_size} test={result.test_size}"
    )
    print(
        f"  scale_pos_weight={result.scale_pos_weight:.3f} "
        f"tuned_threshold={result.tuned_threshold:.4f} "
        f"({_threshold_note(config)})"
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
