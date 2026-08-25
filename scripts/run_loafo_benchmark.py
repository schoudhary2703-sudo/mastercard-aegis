"""LOAFO (Leave-One-Attack-Family-Out) generalization benchmark.

Measures unseen-family generalization, not memorization: for each of the
three implemented attack families, trains a detector on the *other two*
families' prior real hard positives (the held-out family contributes **zero**
training rows), then scores it on one genuinely fresh scenario of the held-out
family - never seen in that fold's training, never reused from any prior
artifact. Defender v3 (`models/xgboost-hardened-crossfamily-*`, trained WITH
all three families) is scored on the identical fresh scenario as a
memorization reference, so the comparison isolates "did this generalize" from
"did this see similar data before".

Three folds, matching `docs/EVALUATION_RULES.md` SS6:

    Fold A: train on synthetic_identity_bustout + mule_network_structuring
            hold out adaptive_detector_evasion entirely
            evaluate on one fresh adaptive-evasion scenario
    Fold B: train on synthetic_identity_bustout + adaptive_detector_evasion
            hold out mule_network_structuring entirely
            evaluate on one fresh mule scenario
    Fold C: train on mule_network_structuring + adaptive_detector_evasion
            hold out synthetic_identity_bustout entirely
            evaluate on one fresh bust-out scenario

Reuses, unmodified: `aegis.defend.hard_positives` (promotion/leakage checks),
`scripts.train_baseline_detector.run_baseline_pipeline` (training), and the
three existing confrontation scripts (`run_bustout_confrontation`,
`run_mule_network_confrontation`, `run_adaptive_evasion_confrontation`) to
generate and score each fold's fresh held-out scenario via their existing
"reuse a frozen model, generate one fresh scenario" path - no Red-side code
is touched, only invoked as already-established black-box entry points.

`aegis.defend.metrics.build_evaluation_result` gained one small, additive
extension for this benchmark: an optional `held_out_family` passthrough, so
each fold's fresh-scenario result is a real, contract-compliant
`EvaluationResult` tagged `LEAVE_ONE_ATTACK_FAMILY_OUT`
(`docs/EVALUATION_RULES.md`: "every reported number must come out of an
`EvaluationResult` carrying the protocol that produced it"), not an ad-hoc
dict. Existing `STATIC_HOLDOUT` callers are unaffected (the parameter
defaults to `None`).

Verification performed for every fold, not just claimed:

* the held-out family contributes zero promoted rows (checked against the
  actual promoted provenance, not just "the sources never included it");
* the promoted hard positives do not collide with PaySim train/validation/test
  (`aegis.defend.hard_positives.assert_no_id_overlap_with_jsonl`, reused);
* the fresh held-out scenario's transaction/scenario ids do not collide with
  *any* prior artifact under `data/synthetic/**/transactions.jsonl` or
  `data/hardening/**/hard_positives.jsonl` (a fresh snapshot taken
  immediately before generation), nor with PaySim validation/test;
* the fold model's and Defender v3's `model.json`/`metadata.json` are
  byte-identical before and after every evaluation step that touches them.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from aegis.defend import XGBoostDetector
from aegis.defend.hard_positives import (
    HardPositiveArtifact,
    HardPositivePromotion,
    HardPositiveSource,
    assert_no_duplicate_transaction_ids,
    assert_no_id_overlap_with_jsonl,
    promote_hard_positives,
    write_hard_positive_artifact,
)
from aegis.defend.metrics import build_evaluation_result
from aegis.features import TemporalBaselineFeatureExtractor
from aegis.features.streaming import FeatureArtifact
from aegis.features.temporal import feature_columns
from aegis.shared.contracts import DetectorOutput, EvaluationResult, TransactionBatch
from aegis.shared.enums import AttackFamily, DataSplit, EvaluationProtocol

if TYPE_CHECKING:  # pragma: no cover - static typing only, see the runtime import below
    from scripts.run_adaptive_evasion_confrontation import (
        AdaptiveEvasionConfrontationConfig,
        AdaptiveEvasionConfrontationResult,
    )
    from scripts.run_bustout_confrontation import (
        ConfrontationPipelineConfig,
        ConfrontationPipelineResult,
    )
    from scripts.run_mule_network_confrontation import (
        MuleConfrontationConfig,
        MuleConfrontationResult,
    )
    from scripts.train_baseline_detector import BaselinePipelineConfig, BaselinePipelineResult


def _import(name: str) -> Any:
    # Direct ``python scripts/run_loafo_benchmark.py`` execution places
    # scripts/, not the repository root, on sys.path - same
    # import-by-runtime-name workaround the other harden_defender* scripts use.
    return importlib.import_module(f"scripts.{name}" if __package__ else name)


_training_module = _import("train_baseline_detector")
_bustout_module = _import("run_bustout_confrontation")
_mule_module = _import("run_mule_network_confrontation")
_adaptive_module = _import("run_adaptive_evasion_confrontation")
_crossfamily_module = _import("harden_defender_crossfamily")

if not TYPE_CHECKING:
    BaselinePipelineConfig = _training_module.BaselinePipelineConfig
    BaselinePipelineResult = _training_module.BaselinePipelineResult
    ConfrontationPipelineConfig = _bustout_module.ConfrontationPipelineConfig
    ConfrontationPipelineResult = _bustout_module.ConfrontationPipelineResult
    MuleConfrontationConfig = _mule_module.MuleConfrontationConfig
    MuleConfrontationResult = _mule_module.MuleConfrontationResult
    AdaptiveEvasionConfrontationConfig = _adaptive_module.AdaptiveEvasionConfrontationConfig
    AdaptiveEvasionConfrontationResult = _adaptive_module.AdaptiveEvasionConfrontationResult

run_baseline_pipeline = _training_module.run_baseline_pipeline
_is_valid_feature_artifact = _training_module._is_valid_feature_artifact
_DEFAULT_CHUNK_SIZE = _training_module.DEFAULT_CHUNK_SIZE
_LOW_MEMORY_DEFAULT_NTHREAD = _training_module.LOW_MEMORY_DEFAULT_NTHREAD
run_bustout_confrontation = _bustout_module.run_bustout_confrontation
run_mule_network_confrontation = _mule_module.run_mule_network_confrontation
run_adaptive_evasion_confrontation = _adaptive_module.run_adaptive_evasion_confrontation
summarize_by_family = _crossfamily_module.summarize_by_family

FAMILY_SYNTHETIC = "synthetic_identity_bustout"
FAMILY_MULE = "mule_network_structuring"
FAMILY_ADAPTIVE = "adaptive_detector_evasion"

DEFAULT_BUSTOUT_ROUND0_DIR = Path("data/synthetic/confrontations/confrontation-416e606888de1ffa")
DEFAULT_BUSTOUT_ADAPTIVE_DIR = Path(
    "data/synthetic/adaptive_rounds/adaptive-round-1-864e34ee0950e8bc/candidates/"
    "synthetic-identity-bustout-v1-g1-93aad9875685"
)
DEFAULT_MULE_CONFRONTATION_DIR = Path(
    "data/synthetic/mule_confrontations/mule-confrontation-fc18c9ba3c66912f"
)
DEFAULT_ADAPTIVE_EVASION_CONFRONTATION_DIR = Path(
    "data/synthetic/adaptive_evasion_confrontations/adaptive-evasion-confrontation-1c0b165066cd2c9b"
)
DEFAULT_DEFENDER_V3_MODEL_DIR = Path("models/xgboost-hardened-crossfamily-20260301")

_TRANSACTION_ID_PATTERN = re.compile(r'"transaction_id":"([^"]+)"')
_SCENARIO_ID_PATTERN = re.compile(r'"scenario_id":"([^"]+)"')


def _family_sources() -> dict[str, list[HardPositiveSource]]:
    return {
        FAMILY_SYNTHETIC: [
            HardPositiveSource(artifact_dir=DEFAULT_BUSTOUT_ROUND0_DIR, source_round="round-0"),
            HardPositiveSource(
                artifact_dir=DEFAULT_BUSTOUT_ADAPTIVE_DIR, source_round="adaptive-round-1"
            ),
        ],
        FAMILY_MULE: [
            HardPositiveSource(
                artifact_dir=DEFAULT_MULE_CONFRONTATION_DIR, source_round="mule-confrontation-1"
            ),
        ],
        FAMILY_ADAPTIVE: [
            HardPositiveSource(
                artifact_dir=DEFAULT_ADAPTIVE_EVASION_CONFRONTATION_DIR,
                source_round="adaptive-evasion-confrontation-1",
            ),
        ],
    }


@dataclass(frozen=True)
class LoafoFoldSpec:
    fold_id: str
    held_out_family: str
    training_families: tuple[str, ...]
    model_version_prefix: str
    training_seed: int
    fresh_eval_seed: int
    """Distinct from every seed already used anywhere in the repo (baseline
    v1: 20260101, Defender v2: 20260201, Defender v3: 20260301, and every
    family's own prior confrontation/adaptive-round seeds) - a LOAFO fresh
    scenario must never be mistaken for, or coincide with, a prior one."""


DEFAULT_FOLDS: tuple[LoafoFoldSpec, ...] = (
    LoafoFoldSpec(
        fold_id="fold-a-synth-mule",
        held_out_family=FAMILY_ADAPTIVE,
        training_families=(FAMILY_SYNTHETIC, FAMILY_MULE),
        model_version_prefix="loafo-synth-mule",
        training_seed=20260401,
        fresh_eval_seed=20270101,
    ),
    LoafoFoldSpec(
        fold_id="fold-b-synth-adaptive",
        held_out_family=FAMILY_MULE,
        training_families=(FAMILY_SYNTHETIC, FAMILY_ADAPTIVE),
        model_version_prefix="loafo-synth-adaptive",
        training_seed=20260402,
        fresh_eval_seed=20270102,
    ),
    LoafoFoldSpec(
        fold_id="fold-c-mule-adaptive",
        held_out_family=FAMILY_SYNTHETIC,
        training_families=(FAMILY_MULE, FAMILY_ADAPTIVE),
        model_version_prefix="loafo-mule-adaptive",
        training_seed=20260403,
        fresh_eval_seed=20270103,
    ),
)


@dataclass(frozen=True)
class LoafoBenchmarkConfig:
    """Everything needed to reproduce all three LOAFO folds."""

    processed_dir: Path
    folds: tuple[LoafoFoldSpec, ...] = DEFAULT_FOLDS
    defender_v3_model_dir: Path = DEFAULT_DEFENDER_V3_MODEL_DIR
    synthetic_root: Path = Path("data/synthetic")
    """Scanned for every `transactions.jsonl` when snapshotting prior
    artifact ids before generating a fresh scenario (`snapshot_prior_artifact_ids`).
    Must be the same tree `fresh_eval_output_dir` and every family source
    directory live under, or the freshness check would miss real prior
    artifacts. Overridden by tests to a fixture root."""
    hardening_data_dir: Path = Path("data/hardening")
    model_output_dir: Path = Path("models")
    fresh_eval_output_dir: Path = Path("data/synthetic/loafo_evaluations")
    num_boost_round: int = 300
    latency_sample_size: int = 200
    low_memory: bool = True
    chunk_size: int = _DEFAULT_CHUNK_SIZE
    nthread: int | None = None
    promoted_at: datetime | None = None
    reuse_v3_validation_test_features: bool = True
    """Defender v3 uses the identical 21-column schema every LOAFO fold does
    (both post-date the cross-family feature addition), and validation/test
    are never touched by hard positives either way - so, unlike
    `harden_defender.py`'s baseline-vs-v2 reuse (blocked in the crossfamily
    script because v3's schema differed from v1/v2's), reusing v3's cached
    validation/test features here is schema-verified safe. See
    `_maybe_reuse_v3_features`, which checks the cached schema's
    `feature_names` against the current extractor before ever copying."""
    family_sources: dict[str, list[HardPositiveSource]] | None = None
    """Override for `_family_sources()`'s real repo defaults - `None` (the
    real-run default) resolves to the actual on-disk confrontation
    artifacts; tests inject a small fixture mapping here instead of writing
    into `data/synthetic/`."""

    def resolved_family_sources(self) -> dict[str, list[HardPositiveSource]]:
        return self.family_sources if self.family_sources is not None else _family_sources()


@dataclass(frozen=True)
class _RawFreshEval:
    report: Any
    batch: TransactionBatch
    output_dir: Path


@dataclass(frozen=True)
class LoafoFreshEvalSummary:
    scenario_id: str
    fraud_count: int
    caught_count: int
    evaded_count: int
    recall: float
    average_fraud_risk_score: float | None
    fidelity_score: float | None
    hardest_evasions: list[dict[str, Any]]
    source_artifact: Path
    fold_evaluation: EvaluationResult
    defender_v3_evaluation: EvaluationResult


@dataclass(frozen=True)
class LoafoFoldResult:
    spec: LoafoFoldSpec
    promotion: HardPositivePromotion
    hard_positive_artifact: HardPositiveArtifact
    family_counts: dict[str, dict[str, int]]
    training_result: BaselinePipelineResult
    fresh_eval: LoafoFreshEvalSummary
    model_hash_before: tuple[str, str]
    model_hash_after: tuple[str, str]
    fold_report_path: Path


@dataclass(frozen=True)
class LoafoBenchmarkResult:
    fold_results: list[LoafoFoldResult]
    summary: dict[str, Any]
    summary_path: Path


# ---------------------------------------------------------------------------
# hashing / freshness helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _model_hashes(model_dir: Path) -> tuple[str, str]:
    directory = Path(model_dir)
    return _sha256(directory / "model.json"), _sha256(directory / "metadata.json")


def _assert_model_unchanged(model_dir: Path, before: tuple[str, str], *, label: str) -> None:
    after = _model_hashes(model_dir)
    if before != after:
        msg = f"{label}: model artifact changed during LOAFO evaluation ({model_dir})"
        raise RuntimeError(msg)


def _read_model_metadata(model_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(
        (Path(model_dir) / "metadata.json").read_text(encoding="utf-8")
    )
    return result


def _read_model_threshold(model_dir: Path) -> float:
    return float(_read_model_metadata(model_dir)["action_policy"]["label_threshold"])


def _read_model_version(model_dir: Path) -> str:
    return str(_read_model_metadata(model_dir)["model_version"])


def _collect_transaction_and_scenario_ids(paths: Iterable[Path]) -> tuple[set[str], set[str]]:
    transaction_ids: set[str] = set()
    scenario_ids: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                txn_match = _TRANSACTION_ID_PATTERN.search(stripped)
                if txn_match:
                    transaction_ids.add(txn_match.group(1))
                scenario_match = _SCENARIO_ID_PATTERN.search(stripped)
                if scenario_match:
                    scenario_ids.add(scenario_match.group(1))
    return transaction_ids, scenario_ids


def snapshot_prior_artifact_ids(
    *,
    synthetic_root: Path = Path("data/synthetic"),
    hardening_root: Path = Path("data/hardening"),
) -> tuple[set[str], set[str]]:
    """Every transaction/scenario id appearing in any real artifact on disk
    right now. Call this *before* generating a fresh scenario - the freshly
    written scenario would otherwise appear in its own "prior" snapshot."""
    transaction_files = (
        sorted(synthetic_root.rglob("transactions.jsonl")) if synthetic_root.is_dir() else []
    )
    hard_positive_files = (
        sorted(hardening_root.rglob("hard_positives.jsonl")) if hardening_root.is_dir() else []
    )
    return _collect_transaction_and_scenario_ids([*transaction_files, *hard_positive_files])


def assert_fresh_scenario_has_no_overlap(
    *,
    batch: TransactionBatch,
    prior_transaction_ids: set[str],
    prior_scenario_ids: set[str],
    fold_id: str,
    family: str,
) -> None:
    batch_transaction_ids = {t.transaction_id for t in batch.transactions}
    transaction_overlap = batch_transaction_ids & prior_transaction_ids
    if transaction_overlap:
        msg = (
            f"{fold_id}: fresh {family} scenario transaction_id(s) collide with a prior "
            f"artifact: {sorted(transaction_overlap)[:5]}"
        )
        raise ValueError(msg)

    batch_scenario_ids = {t.scenario_id for t in batch.transactions if t.scenario_id}
    scenario_overlap = batch_scenario_ids & prior_scenario_ids
    if scenario_overlap:
        msg = (
            f"{fold_id}: fresh {family} scenario_id(s) collide with a prior artifact: "
            f"{sorted(scenario_overlap)}"
        )
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# feature reuse (schema-verified, unlike harden_defender.py's original helper)
# ---------------------------------------------------------------------------


def _maybe_reuse_v3_features(*, v3_model_dir: Path, target_feature_dir: Path) -> None:
    expected = feature_columns("temporal")
    for split_name in ("validation", "test"):
        source_dir = Path(v3_model_dir) / "features" / split_name
        target_dir = target_feature_dir / split_name
        if target_dir.exists():
            continue
        if not _is_valid_feature_artifact(source_dir):
            continue
        schema = FeatureArtifact.load_schema(source_dir)
        if schema.get("feature_names") != expected:
            # Never trust a cache whose column set does not match exactly.
            continue
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target_dir)
        print(f"  reusing Defender v3 {split_name} features (schema-verified): {source_dir}")


# ---------------------------------------------------------------------------
# scoring helpers
# ---------------------------------------------------------------------------


def _score_batch_against(model_dir: Path, batch: TransactionBatch) -> list[DetectorOutput]:
    detector = XGBoostDetector.load(str(model_dir))
    extractor = TemporalBaselineFeatureExtractor().fit([])
    return detector.predict(
        extractor.transform(batch.transactions),
        [t.transaction_id for t in batch.transactions],
        explain=False,
    )


def _aligned_y_true_and_scores(
    batch: TransactionBatch, outputs: Sequence[DetectorOutput]
) -> tuple[np.ndarray, np.ndarray]:
    """Join by `transaction_id`, never by position (docs/EVALUATION_RULES.md)."""
    outputs_by_id = {o.transaction_id: o for o in outputs}
    y_true = np.array([1 if txn.is_fraud else 0 for txn in batch.transactions])
    scores = np.array([outputs_by_id[txn.transaction_id].risk_score for txn in batch.transactions])
    return y_true, scores


def _run_fresh_eval_for_family(
    family: str, *, processed_dir: Path, model_dir: Path, output_dir: Path, seed: int
) -> _RawFreshEval:
    if family == FAMILY_SYNTHETIC:
        bustout_result = run_bustout_confrontation(
            ConfrontationPipelineConfig(
                processed_dir=processed_dir,
                output_dir=output_dir,
                seed=seed,
                reuse_model_dir=model_dir,
            )
        )
        return _RawFreshEval(
            report=bustout_result.report,
            batch=bustout_result.batch,
            output_dir=bustout_result.output_dir,
        )
    if family == FAMILY_MULE:
        mule_result = run_mule_network_confrontation(
            MuleConfrontationConfig(
                processed_dir=processed_dir, model_dir=model_dir, output_dir=output_dir, seed=seed
            )
        )
        return _RawFreshEval(
            report=mule_result.report, batch=mule_result.batch, output_dir=mule_result.output_dir
        )
    if family == FAMILY_ADAPTIVE:
        adaptive_result = run_adaptive_evasion_confrontation(
            AdaptiveEvasionConfrontationConfig(
                processed_dir=processed_dir, model_dir=model_dir, output_dir=output_dir, seed=seed
            )
        )
        return _RawFreshEval(
            report=adaptive_result.report,
            batch=adaptive_result.final_batch,
            output_dir=adaptive_result.output_dir,
        )
    msg = f"unknown attack family: {family!r}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# per-fold orchestration
# ---------------------------------------------------------------------------


def run_loafo_fold(spec: LoafoFoldSpec, config: LoafoBenchmarkConfig) -> LoafoFoldResult:
    processed_dir = Path(config.processed_dir)
    train_path = processed_dir / "train.jsonl"
    validation_path = processed_dir / "validation.jsonl"
    test_path = processed_dir / "test.jsonl"
    for path in (train_path, validation_path, test_path):
        if not path.is_file():
            raise ValueError(f"prepared PaySim artifact not found: {path}")

    # -- A: promote hard positives from the training families ONLY ----------
    family_sources = config.resolved_family_sources()
    sources: list[HardPositiveSource] = []
    for family in spec.training_families:
        sources.extend(family_sources[family])

    print(f"[{spec.fold_id}] train={spec.training_families} hold_out={spec.held_out_family!r}")
    promotion = promote_hard_positives(sources, promoted_at=config.promoted_at)

    promoted_families = {p.attack_family for p in promotion.provenance}
    if spec.held_out_family in promoted_families:
        msg = (
            f"{spec.fold_id}: held-out family {spec.held_out_family!r} leaked into promoted "
            f"training rows (found families: {sorted(promoted_families)})"
        )
        raise ValueError(msg)
    if promoted_families != set(spec.training_families):
        msg = (
            f"{spec.fold_id}: expected promoted families {sorted(spec.training_families)}, "
            f"got {sorted(promoted_families)}"
        )
        raise ValueError(msg)
    print(
        f"  promoted {len(promotion.transactions)} rows ({promotion.fraud_count} fraud) "
        f"from {sorted(promoted_families)}; held-out family contributed 0 rows (verified)"
    )

    assert_no_duplicate_transaction_ids(promotion.transactions)
    candidate_ids = set(promotion.transaction_ids)
    assert_no_id_overlap_with_jsonl(candidate_ids, validation_path, label="validation")
    assert_no_id_overlap_with_jsonl(candidate_ids, test_path, label="test")
    assert_no_id_overlap_with_jsonl(candidate_ids, train_path, label="train")

    hardening_run_dir = (
        Path(config.hardening_data_dir) / f"loafo-{spec.fold_id}-{spec.training_seed}"
    )
    hard_positive_artifact = write_hard_positive_artifact(promotion, hardening_run_dir)
    family_counts = summarize_by_family(promotion)

    # -- B: train (low-memory, schema-verified feature reuse from v3) -------
    nthread = config.nthread
    if config.low_memory and nthread is None:
        nthread = _LOW_MEMORY_DEFAULT_NTHREAD

    training_config = BaselinePipelineConfig(
        processed_dir=processed_dir,
        output_dir=config.model_output_dir,
        seed=spec.training_seed,
        num_boost_round=config.num_boost_round,
        latency_sample_size=config.latency_sample_size,
        low_memory=config.low_memory,
        chunk_size=config.chunk_size,
        nthread=nthread,
        model_version_prefix=spec.model_version_prefix,
        hard_positive_jsonl=hard_positive_artifact.jsonl_path,
    )
    if config.low_memory and config.reuse_v3_validation_test_features:
        _maybe_reuse_v3_features(
            v3_model_dir=Path(config.defender_v3_model_dir),
            target_feature_dir=training_config.resolved_feature_artifact_dir(),
        )
    print(f"  training {training_config.model_version} (low_memory={config.low_memory})...")
    training_result = run_baseline_pipeline(training_config)
    print(
        f"    threshold={training_result.tuned_threshold:.4f} "
        f"native-test-recall={training_result.test_evaluation.overall.recall:.4f}"
    )

    # -- C: fresh held-out evaluation -----------------------------------------
    fold_model_dir = training_result.artifact_dir
    fold_hash_before = _model_hashes(fold_model_dir)
    v3_model_dir = Path(config.defender_v3_model_dir)
    v3_hash_before = _model_hashes(v3_model_dir)

    prior_transaction_ids, prior_scenario_ids = snapshot_prior_artifact_ids(
        synthetic_root=Path(config.synthetic_root), hardening_root=Path(config.hardening_data_dir)
    )

    fresh_eval_output_dir = Path(config.fresh_eval_output_dir) / spec.fold_id
    raw = _run_fresh_eval_for_family(
        spec.held_out_family,
        processed_dir=processed_dir,
        model_dir=fold_model_dir,
        output_dir=fresh_eval_output_dir,
        seed=spec.fresh_eval_seed,
    )
    assert_fresh_scenario_has_no_overlap(
        batch=raw.batch,
        prior_transaction_ids=prior_transaction_ids,
        prior_scenario_ids=prior_scenario_ids,
        fold_id=spec.fold_id,
        family=spec.held_out_family,
    )
    fresh_transaction_ids = {t.transaction_id for t in raw.batch.transactions}
    assert_no_id_overlap_with_jsonl(fresh_transaction_ids, validation_path, label="validation")
    assert_no_id_overlap_with_jsonl(fresh_transaction_ids, test_path, label="test")
    print(f"  fresh {spec.held_out_family} scenario verified disjoint from every prior artifact")

    scenario = raw.report.scenario_reports[0]
    fraud_events = list(scenario.fraudulent_events)
    average_fraud_risk_score = (
        sum(e.risk_score for e in fraud_events) / len(fraud_events) if fraud_events else None
    )
    fidelity_score = (
        scenario.fidelity_summary.get("overall_fidelity_score")
        if scenario.fidelity_summary
        else None
    )

    fold_outputs = _score_batch_against(fold_model_dir, raw.batch)
    fold_y_true, fold_scores = _aligned_y_true_and_scores(raw.batch, fold_outputs)
    fold_evaluation = build_evaluation_result(
        evaluation_id=f"{spec.fold_id}-loafo-{scenario.scenario_id}",
        y_true=fold_y_true,
        scores=fold_scores,
        threshold=training_result.tuned_threshold,
        model_version=training_result.model_version,
        dataset_id=scenario.scenario_id,
        split=DataSplit.TEST,
        protocol=EvaluationProtocol.LEAVE_ONE_ATTACK_FAMILY_OUT,
        held_out_family=AttackFamily(spec.held_out_family),
        seed=spec.fresh_eval_seed,
        notes=(
            f"{spec.fold_id}: trained on {spec.training_families}, scored on one fresh "
            f"{spec.held_out_family} scenario never seen in training."
        ),
    )

    v3_outputs = _score_batch_against(v3_model_dir, raw.batch)
    v3_y_true, v3_scores = _aligned_y_true_and_scores(raw.batch, v3_outputs)
    v3_evaluation = build_evaluation_result(
        evaluation_id=f"defender-v3-on-{scenario.scenario_id}",
        y_true=v3_y_true,
        scores=v3_scores,
        threshold=_read_model_threshold(v3_model_dir),
        model_version=_read_model_version(v3_model_dir),
        dataset_id=scenario.scenario_id,
        split=DataSplit.TEST,
        protocol=EvaluationProtocol.LEAVE_ONE_ATTACK_FAMILY_OUT,
        held_out_family=AttackFamily(spec.held_out_family),
        seed=spec.fresh_eval_seed,
        notes=(
            f"Defender v3 (trained WITH {spec.held_out_family}) scored on the identical fresh "
            f"scenario as a memorization reference for {spec.fold_id}."
        ),
    )

    _assert_model_unchanged(fold_model_dir, fold_hash_before, label=training_result.model_version)
    _assert_model_unchanged(v3_model_dir, v3_hash_before, label="defender-v3-crossfamily")
    fold_hash_after = _model_hashes(fold_model_dir)

    fresh_eval_summary = LoafoFreshEvalSummary(
        scenario_id=scenario.scenario_id,
        fraud_count=len(fraud_events),
        caught_count=scenario.caught_fraud_count,
        evaded_count=scenario.evaded_fraud_count,
        recall=scenario.fraud_recall,
        average_fraud_risk_score=average_fraud_risk_score,
        fidelity_score=fidelity_score,
        hardest_evasions=[e.model_dump(mode="json") for e in raw.report.hardest_evasions],
        source_artifact=raw.output_dir,
        fold_evaluation=fold_evaluation,
        defender_v3_evaluation=v3_evaluation,
    )

    result = LoafoFoldResult(
        spec=spec,
        promotion=promotion,
        hard_positive_artifact=hard_positive_artifact,
        family_counts=family_counts,
        training_result=training_result,
        fresh_eval=fresh_eval_summary,
        model_hash_before=fold_hash_before,
        model_hash_after=fold_hash_after,
        fold_report_path=training_result.artifact_dir / "loafo_fold_report.json",
    )
    _write_fold_report(result)
    return result


def _write_fold_report(result: LoafoFoldResult) -> None:
    fresh = result.fresh_eval
    report: dict[str, Any] = {
        "fold_id": result.spec.fold_id,
        "training_families": list(result.spec.training_families),
        "held_out_family": result.spec.held_out_family,
        "model_version": result.training_result.model_version,
        "model_dir": str(result.training_result.artifact_dir),
        "training_seed": result.spec.training_seed,
        "hard_positive_counts_by_family": result.family_counts,
        "hard_positive_total_rows": len(result.promotion.transactions),
        "hard_positive_total_fraud": result.promotion.fraud_count,
        "tuned_threshold": result.training_result.tuned_threshold,
        "paysim_native_test_metrics": result.training_result.test_evaluation.overall.model_dump(
            mode="json"
        ),
        "paysim_native_validation_metrics": (
            result.training_result.validation_evaluation.overall.model_dump(mode="json")
        ),
        "fresh_held_out_evaluation": {
            "scenario_id": fresh.scenario_id,
            "source_artifact": str(fresh.source_artifact),
            "fraud_count": fresh.fraud_count,
            "caught_count": fresh.caught_count,
            "evaded_count": fresh.evaded_count,
            "recall": fresh.recall,
            "average_fraud_risk_score": fresh.average_fraud_risk_score,
            "fidelity_score": fresh.fidelity_score,
            "hardest_evasions": fresh.hardest_evasions,
            "fold_model_evaluation": fresh.fold_evaluation.model_dump(mode="json"),
            "defender_v3_evaluation": fresh.defender_v3_evaluation.model_dump(mode="json"),
        },
        "model_hash_before": {
            "model_json": result.model_hash_before[0],
            "metadata_json": result.model_hash_before[1],
        },
        "model_hash_after": {
            "model_json": result.model_hash_after[0],
            "metadata_json": result.model_hash_after[1],
        },
        "notes": (
            f"Held-out family {result.spec.held_out_family!r} contributed zero rows to "
            "training (verified against actual promoted provenance). Fresh held-out scenario "
            "verified to have zero id overlap with any prior artifact under data/synthetic/ or "
            "data/hardening/, and with PaySim validation/test. Model hashes verified unchanged "
            "before/after every evaluation step."
        ),
    }
    result.fold_report_path.parent.mkdir(parents=True, exist_ok=True)
    result.fold_report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# cross-fold summary
# ---------------------------------------------------------------------------


def _generalization_verdict(loafo_recall: float, v3_recall: float) -> str:
    """strong: LOAFO recall > 0 and >= half of Defender v3's (memorization
    reference) recall on the identical scenario. partial: LOAFO recall > 0
    but below that. weak: LOAFO recall == 0. This threshold is a disclosed
    methodological choice, not a fact about the data - see the summary's
    own `verdict_rubric` field."""
    if loafo_recall <= 0.0:
        return "weak"
    if v3_recall <= 0.0:
        return "strong"  # caught something v3's memorization did not
    if loafo_recall >= 0.5 * v3_recall:
        return "strong"
    return "partial"


def build_summary(fold_results: Sequence[LoafoFoldResult]) -> dict[str, Any]:
    held_out_recall: dict[str, float] = {}
    v3_recall_same_scenario: dict[str, float] = {}
    per_family: dict[str, dict[str, Any]] = {}

    for result in fold_results:
        family = result.spec.held_out_family
        loafo_recall = result.fresh_eval.fold_evaluation.overall.recall
        v3_recall = result.fresh_eval.defender_v3_evaluation.overall.recall
        held_out_recall[family] = loafo_recall
        v3_recall_same_scenario[family] = v3_recall
        per_family[family] = {
            "fold_id": result.spec.fold_id,
            "training_families": list(result.spec.training_families),
            "loafo_recall": loafo_recall,
            "defender_v3_recall_same_scenario": v3_recall,
            "loafo_precision": result.fresh_eval.fold_evaluation.overall.precision,
            "loafo_caught": result.fresh_eval.caught_count,
            "loafo_evaded": result.fresh_eval.evaded_count,
            "verdict": _generalization_verdict(loafo_recall, v3_recall),
        }

    mean_recall = sum(held_out_recall.values()) / len(held_out_recall) if held_out_recall else 0.0

    return {
        "held_out_recall_per_family": held_out_recall,
        "mean_loafo_recall": mean_recall,
        "defender_v3_recall_on_same_scenarios": v3_recall_same_scenario,
        "per_family": per_family,
        "methodology": (
            "For each family, a LOAFO model trained WITHOUT that family's hard positives is "
            "scored on one fresh scenario of that family, never seen in training. Defender v3 "
            "(trained WITH all three families) is scored on the identical fresh scenario as a "
            "memorization reference. Both use each model's own validation-tuned threshold; "
            "neither evaluation informed any training decision."
        ),
        "verdict_rubric": (
            "strong: LOAFO recall > 0 and >= 50% of Defender v3's recall on the same scenario. "
            "partial: LOAFO recall > 0 but below that. weak: LOAFO recall == 0."
        ),
        "notes": (
            "Every number here comes from a STATIC_HOLDOUT (native PaySim test) or "
            "LEAVE_ONE_ATTACK_FAMILY_OUT (fresh held-out scenario) EvaluationResult "
            "(docs/EVALUATION_RULES.md). Each fold's fresh scenario is one real synthetic "
            "scenario, not a large sample - these numbers are directional, not statistically "
            "powered estimates."
        ),
    }


def run_loafo_benchmark(config: LoafoBenchmarkConfig) -> LoafoBenchmarkResult:
    fold_results = [run_loafo_fold(spec, config) for spec in config.folds]
    summary = build_summary(fold_results)
    summary_path = Path(config.model_output_dir) / "loafo_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return LoafoBenchmarkResult(
        fold_results=fold_results, summary=summary, summary_path=summary_path
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "LOAFO generalization benchmark: three Leave-One-Attack-Family-Out folds, each "
            "trained on two families' prior hard positives and scored on one fresh scenario "
            "of the third, held-out family, compared against Defender v3's memorization."
        )
    )
    parser.add_argument(
        "processed_dir",
        type=Path,
        help="prepared PaySim run directory (train/validation/test.jsonl)",
    )
    parser.add_argument("--defender-v3-model-dir", type=Path, default=DEFAULT_DEFENDER_V3_MODEL_DIR)
    parser.add_argument("--synthetic-root", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--hardening-data-dir", type=Path, default=Path("data/hardening"))
    parser.add_argument("--model-output-dir", type=Path, default=Path("models"))
    parser.add_argument(
        "--fresh-eval-output-dir", type=Path, default=Path("data/synthetic/loafo_evaluations")
    )
    parser.add_argument("--num-boost-round", type=int, default=300)
    parser.add_argument("--latency-sample-size", type=int, default=200)
    parser.add_argument("--low-memory", action="store_true", default=True)
    parser.add_argument(
        "--no-low-memory", dest="low_memory", action="store_false", help="use the in-memory path"
    )
    parser.add_argument("--chunk-size", type=int, default=_DEFAULT_CHUNK_SIZE)
    parser.add_argument("--nthread", type=int, default=None)
    parser.add_argument(
        "--no-reuse-v3-features",
        dest="reuse_v3_features",
        action="store_false",
        default=True,
        help=(
            "always re-materialize validation/test features instead of the schema-verified v3 cache"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = LoafoBenchmarkConfig(
        processed_dir=args.processed_dir,
        defender_v3_model_dir=args.defender_v3_model_dir,
        synthetic_root=args.synthetic_root,
        hardening_data_dir=args.hardening_data_dir,
        model_output_dir=args.model_output_dir,
        fresh_eval_output_dir=args.fresh_eval_output_dir,
        num_boost_round=args.num_boost_round,
        latency_sample_size=args.latency_sample_size,
        low_memory=args.low_memory,
        chunk_size=args.chunk_size,
        nthread=args.nthread,
        reuse_v3_validation_test_features=args.reuse_v3_features,
    )
    result = run_loafo_benchmark(config)

    print()
    print("LOAFO summary:")
    print(json.dumps(result.summary, indent=2, sort_keys=True))
    print(f"Summary written to: {result.summary_path}")
    for fold_result in result.fold_results:
        print(f"  {fold_result.spec.fold_id}: {fold_result.fold_report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
