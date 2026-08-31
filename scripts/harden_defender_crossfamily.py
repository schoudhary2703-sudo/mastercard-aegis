"""Defender v3: cross-family hardening.

Extends `scripts/harden_defender.py`'s single-family (synthetic-identity
bust-out) pattern to all three attack families implemented so far:

1. `synthetic_identity_bustout` - the Round-0 confrontation and the selected
   Adaptive-Round-1 candidate (the same sources `harden_defender.py` used for
   Defender v2).
2. `mule_network_structuring` - the one real confrontation run against
   Defender v2 (`data/synthetic/mule_confrontations/`).
3. `adaptive_detector_evasion` - the one real confrontation run against
   Defender v2 (`data/synthetic/adaptive_evasion_confrontations/`).

Deliberately **not** promoted: the bust-out "fresh confrontation" and
"generation-2" artifacts generated *against Defender v2* per its own
`generation2_handoff.json`
(`data/synthetic/confrontations/confrontation-9ad4e08145771e39`,
`data/synthetic/adaptive_rounds/adaptive-round-1-10758c69cc2b51d5`). Those
are reserved as held-out material for the fresh, post-v3 Red evaluation this
script does not perform (`docs/EVALUATION_RULES.md` SS4) - promoting them
now would consume the only genuinely fresh bust-out evaluation available for
that later step.

Same five phases as `harden_defender.py`, generalized to N sources and a
three-way (v1/v2/v3) comparison instead of two-way:

1. **Promote** every scenario transaction (context/warm-up + fraud) from all
   four sources above into one combined hard-positive training set
   (`aegis.defend.hard_positives`, entirely reused, unmodified - it already
   reads `attack_family`/`blueprint_id`/`generation`/`scenario_id` off the
   `Transaction` rows themselves and does not care which family they came
   from).
2. **Validate** no duplicate `transaction_id` across sources, and no overlap
   with the untouched PaySim train/validation/test split.
3. **Retrain** Defender v3 via the existing, tested low-memory pipeline
   (`scripts/train_baseline_detector.py`), validation-only threshold tuning,
   untouched-test evaluation - identical machinery to v1/v2. The feature
   extractor changed for v3 (`aegis.features.temporal` 0.1.0 -> 0.2.0, see
   `docs/BASELINE_DETECTOR.md` "Cross-family hardening (Defender v3)"), so
   v3's validation/test features are always materialized fresh - v1/v2's
   cached feature arrays are 19-column and would silently be the wrong shape
   if reused.
4. **Compare** v1, v2, and v3 on the untouched PaySim test split only - never
   on the hard positives themselves (`docs/EVALUATION_RULES.md` SS3), and
   never claiming a cross-family *attack* improvement, which requires a
   fresh Red confrontation this script does not run (SS4).
5. **Hand off** a machine-readable interface for the next Red round, listing
   every excluded scenario/transaction id across all three families and the
   fresh-seed requirement.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from aegis.defend.acceptance import (
    DEFAULT_OPERATING_FPR_BUDGET,
    DEFAULT_TOLERANCE,
    AcceptanceCriteria,
    AcceptanceDecision,
    evaluate_acceptance,
)
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

# Direct ``python scripts/harden_defender_crossfamily.py`` execution places
# scripts/, not the repository root, on sys.path - same import-by-runtime-name
# workaround `scripts/harden_defender.py` already uses.
_training_module = importlib.import_module(
    "scripts.train_baseline_detector" if __package__ else "train_baseline_detector"
)
if not TYPE_CHECKING:
    BaselinePipelineConfig = _training_module.BaselinePipelineConfig
    BaselinePipelineResult = _training_module.BaselinePipelineResult
run_baseline_pipeline = _training_module.run_baseline_pipeline
_DEFAULT_CHUNK_SIZE = _training_module.DEFAULT_CHUNK_SIZE
_LOW_MEMORY_DEFAULT_NTHREAD = _training_module.LOW_MEMORY_DEFAULT_NTHREAD

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
DEFAULT_BASELINE_V1_MODEL_DIR = Path("models/xgboost-baseline-20260101")
DEFAULT_DEFENDER_V2_MODEL_DIR = Path("models/xgboost-hardened-r1-20260201")
DEFAULT_MODEL_VERSION_PREFIX = "xgboost-hardened-crossfamily"
DEFAULT_SEED = 20260301
"""Distinct from baseline v1's 20260101 and Defender v2's 20260201 - a
cross-family hardening run must never be mistaken for, or overwrite, either
frozen artifact."""

FEATURE_EXTRACTOR_VERSION_NOTE = (
    "aegis.features.temporal.TemporalBaselineFeatureExtractor 0.2.0 (21 columns: the "
    "same 19 decision-time-safe columns v1/v2 used, plus "
    "source_distinct_destinations_before / destination_distinct_sources_before)"
)


@dataclass(frozen=True)
class CrossFamilyHardenConfig:
    """Everything needed to reproduce one Defender-v3 cross-family run."""

    processed_dir: Path
    bustout_round0_dir: Path = DEFAULT_BUSTOUT_ROUND0_DIR
    bustout_adaptive_dir: Path = DEFAULT_BUSTOUT_ADAPTIVE_DIR
    mule_confrontation_dir: Path = DEFAULT_MULE_CONFRONTATION_DIR
    adaptive_evasion_confrontation_dir: Path = DEFAULT_ADAPTIVE_EVASION_CONFRONTATION_DIR
    baseline_v1_model_dir: Path = DEFAULT_BASELINE_V1_MODEL_DIR
    defender_v2_model_dir: Path = DEFAULT_DEFENDER_V2_MODEL_DIR
    hardening_data_dir: Path = Path("data/hardening")
    model_output_dir: Path = Path("models")
    model_version_prefix: str = DEFAULT_MODEL_VERSION_PREFIX
    seed: int = DEFAULT_SEED
    num_boost_round: int = 300
    latency_sample_size: int = 200
    low_memory: bool = True
    chunk_size: int = _DEFAULT_CHUNK_SIZE
    nthread: int | None = None
    promoted_at: datetime | None = None
    """Fixed timestamp for `metadata.hardening.promoted_at` on every promoted
    row. `None` uses the wall clock (default for a real run); tests pass a
    fixed value so the written hard-positive artifact is byte-for-byte
    reproducible, per AGENTS.md SS6."""
    acceptance_criteria: AcceptanceCriteria | None = None
    """What v3 must satisfy against *both* v2 and v1 to count as a promotion.
    `None` uses `AcceptanceCriteria()` defaults."""

    def sources(self) -> list[HardPositiveSource]:
        return [
            HardPositiveSource(artifact_dir=Path(self.bustout_round0_dir), source_round="round-0"),
            HardPositiveSource(
                artifact_dir=Path(self.bustout_adaptive_dir), source_round="adaptive-round-1"
            ),
            HardPositiveSource(
                artifact_dir=Path(self.mule_confrontation_dir),
                source_round="mule-confrontation-1",
            ),
            HardPositiveSource(
                artifact_dir=Path(self.adaptive_evasion_confrontation_dir),
                source_round="adaptive-evasion-confrontation-1",
            ),
        ]


@dataclass(frozen=True)
class CrossFamilyHardenResult:
    promotion: HardPositivePromotion
    hard_positive_artifact: HardPositiveArtifact
    training_result: BaselinePipelineResult
    baseline_v1_evaluation: EvaluationResult
    defender_v2_evaluation: EvaluationResult
    family_counts: dict[str, dict[str, int]]
    regression_report: dict[str, object]
    regression_report_path: Path
    handoff_path: Path
    acceptance_vs_v1: AcceptanceDecision
    acceptance_vs_v2: AcceptanceDecision
    acceptance_path: Path

    @property
    def accepted(self) -> bool:
        """Cleared only if it regresses neither the predecessor nor the baseline.

        Gating on v2 alone is what let v3 ship while sitting below the untouched
        v1 on PR-AUC and recall: each round only ever had to beat the round
        before it, so the loop could drift away from the baseline one tolerable
        step at a time.
        """
        return self.acceptance_vs_v1.accepted and self.acceptance_vs_v2.accepted


def run_crossfamily_hardening(config: CrossFamilyHardenConfig) -> CrossFamilyHardenResult:
    processed_dir = Path(config.processed_dir)
    validation_path = processed_dir / "validation.jsonl"
    test_path = processed_dir / "test.jsonl"
    train_path = processed_dir / "train.jsonl"
    for path in (train_path, validation_path, test_path):
        if not path.is_file():
            raise ValueError(f"prepared PaySim artifact not found: {path}")

    # -- Phase A: promote hard positives from all 3 attack families ---------
    sources = config.sources()
    print(f"Promoting hard positives from {len(sources)} source(s) across 3 attack families:")
    for source in sources:
        print(f"  {source.source_round}: {source.artifact_dir}")
    promotion = promote_hard_positives(sources, promoted_at=config.promoted_at)
    family_counts = summarize_by_family(promotion)
    print(
        f"  promoted {len(promotion.transactions)} rows total "
        f"({promotion.fraud_count} fraud, "
        f"{len(promotion.transactions) - promotion.fraud_count} legitimate)"
    )
    print("Counts per family:")
    for family in sorted(family_counts):
        c = family_counts[family]
        print(
            f"  {family}: {c['rows']} rows ({c['fraud']} fraud, {c['legitimate']} legitimate) "
            f"across {c['scenarios']} scenario(s)"
        )

    # -- Phase A: leakage checks ----------------------------------------------
    assert_no_duplicate_transaction_ids(promotion.transactions)
    candidate_ids = set(promotion.transaction_ids)
    print("Checking for transaction-ID overlap with validation/test/train...")
    assert_no_id_overlap_with_jsonl(candidate_ids, validation_path, label="validation")
    assert_no_id_overlap_with_jsonl(candidate_ids, test_path, label="test")
    assert_no_id_overlap_with_jsonl(candidate_ids, train_path, label="train")
    print("  no overlap found")

    hardening_run_dir = (
        Path(config.hardening_data_dir) / f"hard-positives-crossfamily-{config.seed}"
    )
    hard_positive_artifact = write_hard_positive_artifact(promotion, hardening_run_dir)
    print(f"  hard-positive artifact: {hard_positive_artifact.jsonl_path}")

    # -- Phase B: retrain -------------------------------------------------------
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
    # No feature reuse from v1/v2 here (unlike harden_defender.py's
    # `_maybe_reuse_baseline_features`): the feature extractor's column set
    # changed for v3 (see FEATURE_EXTRACTOR_VERSION_NOTE), so v1/v2's cached
    # validation/test feature arrays are the wrong shape and must not be
    # copied in - v3 always materializes its own.
    print(f"Training {training_config.model_version} (low_memory={config.low_memory})...")
    print(f"  features: {FEATURE_EXTRACTOR_VERSION_NOTE}")
    training_result = run_baseline_pipeline(training_config)
    print(f"  artifact: {training_result.artifact_dir}")
    print(
        f"  train={training_result.train_size} validation={training_result.validation_size} "
        f"test={training_result.test_size} threshold={training_result.tuned_threshold:.4f}"
    )

    # -- Phase C: 3-way regression check vs. frozen v1 and v2 ------------------
    baseline_v1_evaluation = EvaluationResult.model_validate_json(
        (Path(config.baseline_v1_model_dir) / "evaluation_test.json").read_text(encoding="utf-8")
    )
    defender_v2_evaluation = EvaluationResult.model_validate_json(
        (Path(config.defender_v2_model_dir) / "evaluation_test.json").read_text(encoding="utf-8")
    )
    regression_report = build_threeway_regression_report(
        v1=baseline_v1_evaluation,
        v2=defender_v2_evaluation,
        v3=training_result.test_evaluation,
    )
    regression_report_path = training_result.artifact_dir / "regression_vs_v1_v2.json"
    regression_report_path.write_text(
        json.dumps(regression_report, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Gate against both prior generations. v2 is the model this replaces; v1 is
    # the untouched baseline the whole loop is measured against, and skipping it
    # is precisely how a chain of individually-tolerable rounds ends up below
    # where it started.
    acceptance_vs_v2 = evaluate_acceptance(
        incumbent=defender_v2_evaluation,
        candidate=training_result.test_evaluation,
        criteria=config.acceptance_criteria,
    )
    acceptance_vs_v1 = evaluate_acceptance(
        incumbent=baseline_v1_evaluation,
        candidate=training_result.test_evaluation,
        criteria=config.acceptance_criteria,
    )
    accepted = acceptance_vs_v1.accepted and acceptance_vs_v2.accepted
    acceptance_path = training_result.artifact_dir / "acceptance.json"
    acceptance_path.write_text(
        json.dumps(
            {
                "accepted": accepted,
                "policy": (
                    "a candidate must regress neither the generation it replaces "
                    "nor the untouched baseline"
                ),
                "vs_defender_v2": acceptance_vs_v2.to_dict(),
                "vs_baseline_v1": acceptance_vs_v1.to_dict(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"vs defender_v2 -> {acceptance_vs_v2.summary}")
    print(f"vs baseline_v1 -> {acceptance_vs_v1.summary}")

    # -- Phase D: Codex handoff ---------------------------------------------
    handoff_path = training_result.artifact_dir / "codex_handoff.json"
    handoff_path.write_text(
        json.dumps(
            build_codex_handoff(
                training_result=training_result,
                promotion=promotion,
                sources=sources,
                processed_dir=processed_dir,
                family_counts=family_counts,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    return CrossFamilyHardenResult(
        promotion=promotion,
        hard_positive_artifact=hard_positive_artifact,
        training_result=training_result,
        baseline_v1_evaluation=baseline_v1_evaluation,
        defender_v2_evaluation=defender_v2_evaluation,
        family_counts=family_counts,
        regression_report=regression_report,
        regression_report_path=regression_report_path,
        handoff_path=handoff_path,
        acceptance_vs_v1=acceptance_vs_v1,
        acceptance_vs_v2=acceptance_vs_v2,
        acceptance_path=acceptance_path,
    )


def summarize_by_family(promotion: HardPositivePromotion) -> dict[str, dict[str, int]]:
    """Row/fraud/legitimate/scenario counts per `attack_family`, from provenance alone."""
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"rows": 0, "fraud": 0, "legitimate": 0, "scenarios": 0}
    )
    scenarios_by_family: dict[str, set[str]] = defaultdict(set)
    for p in promotion.provenance:
        bucket = counts[p.attack_family]
        bucket["rows"] += p.warmup_transaction_count + p.fraud_transaction_count
        bucket["fraud"] += p.fraud_transaction_count
        bucket["legitimate"] += p.warmup_transaction_count
        scenarios_by_family[p.attack_family].add(p.scenario_id)
    for family, scenario_ids in scenarios_by_family.items():
        counts[family]["scenarios"] = len(scenario_ids)
    return {family: dict(bucket) for family, bucket in counts.items()}


def build_threeway_regression_report(
    *, v1: EvaluationResult, v2: EvaluationResult, v3: EvaluationResult
) -> dict[str, object]:
    """Baseline v1 vs. Defender v2 vs. Defender v3, all on the untouched PaySim test split.

    Never compares against the hard positives themselves
    (`docs/EVALUATION_RULES.md` SS3). Does not, and cannot, measure
    cross-family attack improvement - that requires a fresh Red confrontation
    against v3, which is a separate, later step (SS4).
    """
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
        v1_value = getattr(v1.overall, field)
        v2_value = getattr(v2.overall, field)
        v3_value = getattr(v3.overall, field)
        metrics[field] = {
            "baseline_v1": v1_value,
            "defender_v2": v2_value,
            "defender_v3_crossfamily": v3_value,
            "delta_v3_vs_v1": _delta(v1_value, v3_value),
            "delta_v3_vs_v2": _delta(v2_value, v3_value),
        }

    fpr_budgets = sorted(
        set(v1.overall.recall_at_fixed_fpr)
        | set(v2.overall.recall_at_fixed_fpr)
        | set(v3.overall.recall_at_fixed_fpr)
    )
    recall_at_fpr = {
        budget: {
            "baseline_v1": v1.overall.recall_at_fixed_fpr.get(budget),
            "defender_v2": v2.overall.recall_at_fixed_fpr.get(budget),
            "defender_v3_crossfamily": v3.overall.recall_at_fixed_fpr.get(budget),
        }
        for budget in fpr_budgets
    }

    def _confusion(counts: object) -> dict[str, int]:
        return {
            "true_positives": counts.true_positives,  # type: ignore[attr-defined]
            "false_positives": counts.false_positives,  # type: ignore[attr-defined]
            "true_negatives": counts.true_negatives,  # type: ignore[attr-defined]
            "false_negatives": counts.false_negatives,  # type: ignore[attr-defined]
        }

    def _latency(evaluation: EvaluationResult) -> dict[str, object] | None:
        return evaluation.latency.model_dump(mode="json") if evaluation.latency else None

    return {
        "dataset_id": v3.dataset_id,
        "split": str(v3.split),
        "baseline_v1_model_version": v1.model_version,
        "defender_v2_model_version": v2.model_version,
        "defender_v3_model_version": v3.model_version,
        "feature_extractor": FEATURE_EXTRACTOR_VERSION_NOTE,
        "metrics": metrics,
        "recall_at_fixed_fpr": recall_at_fpr,
        "confusion_matrix": {
            "baseline_v1": _confusion(v1.overall.counts),
            "defender_v2": _confusion(v2.overall.counts),
            "defender_v3_crossfamily": _confusion(v3.overall.counts),
        },
        "support": {
            "baseline_v1": v1.overall.support,
            "defender_v2": v2.overall.support,
            "defender_v3_crossfamily": v3.overall.support,
        },
        "latency_ms": {
            "baseline_v1": _latency(v1),
            "defender_v2": _latency(v2),
            "defender_v3_crossfamily": _latency(v3),
        },
        "notes": (
            "Computed on the untouched PaySim test split only, for all three models - never "
            "on the hard positives used to retrain v2 or v3 (docs/EVALUATION_RULES.md SS3). "
            "This is a static-holdout regression check only; it does not evaluate cross-family "
            "attack improvement, which requires a fresh Red confrontation against Defender v3 "
            "after it is frozen (docs/EVALUATION_RULES.md SS4)."
        ),
    }


def _delta(before: object, after: object) -> float | None:
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return after - before
    return None


def build_codex_handoff(
    *,
    training_result: BaselinePipelineResult,
    promotion: HardPositivePromotion,
    sources: Sequence[HardPositiveSource],
    processed_dir: Path,
    family_counts: dict[str, dict[str, int]],
) -> dict[str, object]:
    """The interface a fresh, post-v3 Red round should use.

    Deliberately reuses the existing, unmodified confrontation scripts for
    all three families - Defender v3 is a normal `XGBoostDetector.save()`
    artifact, so no new Red-facing interface is required. `excluded_*_ids`
    covers every scenario/transaction promoted across all three families;
    Generation-3 candidates in any family must not reuse them, and must use
    a seed that was not used for any prior round in any family
    (`docs/EVALUATION_RULES.md` SS2-4).
    """
    scenario_ids = sorted({p.scenario_id for p in promotion.provenance})
    families = sorted({p.attack_family for p in promotion.provenance})
    return {
        "defender_version": training_result.model_version,
        "model_dir": str(training_result.artifact_dir),
        "tuned_threshold": training_result.tuned_threshold,
        "feature_extractor": FEATURE_EXTRACTOR_VERSION_NOTE,
        "hard_positive_source_families": families,
        "hard_positive_counts_by_family": family_counts,
        "trained_on": {
            "processed_dir": str(processed_dir),
            "hard_positive_sources": [
                {"source_round": s.source_round, "artifact_dir": str(s.artifact_dir)}
                for s in sources
            ],
        },
        "excluded_transaction_ids": promotion.fraud_transaction_ids,
        "excluded_scenario_ids": scenario_ids,
        "fresh_seed_requirement": (
            "Any fresh Red confrontation against Defender v3, in any of the three families, "
            "must use a seed that was not previously used for any promoted source above, and "
            "must not reuse excluded_transaction_ids or excluded_scenario_ids. This fresh-Red "
            "evaluation is a separate, later step - not performed by this script "
            "(docs/EVALUATION_RULES.md SS4)."
        ),
        "instructions": (
            "Confront Defender v3 with genuinely fresh attacks in each family, not a re-score "
            "of what it was hardened against: "
            "(1) synthetic_identity_bustout: python scripts/run_bustout_confrontation.py "
            f"<processed_dir> --reuse-model-dir {training_result.artifact_dir} "
            "--output-dir data/synthetic/confrontations --seed <fresh-seed>; "
            "(2) mule_network_structuring: python scripts/run_mule_network_confrontation.py "
            f"<processed_dir> {training_result.artifact_dir} --seed <fresh-seed> "
            "--output-dir data/synthetic/mule_confrontations; "
            "(3) adaptive_detector_evasion: python scripts/run_adaptive_evasion_confrontation.py "
            f"<processed_dir> {training_result.artifact_dir} --seed <fresh-seed> "
            "--output-dir data/synthetic/adaptive_evasion_confrontations. "
            "Do not run Leave-One-Attack-Family-Out (LOAFO) yet."
        ),
        "rules": "docs/EVALUATION_RULES.md SS2-4, SS6",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Defender v3: promote prior real hard positives from all three attack families "
            "(synthetic_identity_bustout, mule_network_structuring, adaptive_detector_evasion) "
            "into training-only rows, retrain via the low-memory pipeline, and compare v1/v2/v3 "
            "on untouched PaySim test."
        )
    )
    parser.add_argument(
        "processed_dir",
        type=Path,
        help="prepared PaySim run directory (train/validation/test.jsonl)",
    )
    parser.add_argument("--bustout-round0-dir", type=Path, default=DEFAULT_BUSTOUT_ROUND0_DIR)
    parser.add_argument("--bustout-adaptive-dir", type=Path, default=DEFAULT_BUSTOUT_ADAPTIVE_DIR)
    parser.add_argument(
        "--mule-confrontation-dir", type=Path, default=DEFAULT_MULE_CONFRONTATION_DIR
    )
    parser.add_argument(
        "--adaptive-evasion-confrontation-dir",
        type=Path,
        default=DEFAULT_ADAPTIVE_EVASION_CONFRONTATION_DIR,
    )
    parser.add_argument("--baseline-v1-model-dir", type=Path, default=DEFAULT_BASELINE_V1_MODEL_DIR)
    parser.add_argument("--defender-v2-model-dir", type=Path, default=DEFAULT_DEFENDER_V2_MODEL_DIR)
    parser.add_argument("--hardening-data-dir", type=Path, default=Path("data/hardening"))
    parser.add_argument("--model-output-dir", type=Path, default=Path("models"))
    parser.add_argument("--model-version-prefix", type=str, default=DEFAULT_MODEL_VERSION_PREFIX)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--num-boost-round", type=int, default=300)
    parser.add_argument("--latency-sample-size", type=int, default=200)
    parser.add_argument("--low-memory", action="store_true", default=True)
    parser.add_argument(
        "--no-low-memory", dest="low_memory", action="store_false", help="use the in-memory path"
    )
    parser.add_argument("--chunk-size", type=int, default=_DEFAULT_CHUNK_SIZE)
    parser.add_argument("--nthread", type=int, default=None)
    parser.add_argument(
        "--acceptance-tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help=(
            "absolute regression allowed per gated metric before v3 is rejected "
            f"(default {DEFAULT_TOLERANCE})"
        ),
    )
    parser.add_argument(
        "--operating-fpr-budget",
        type=float,
        default=DEFAULT_OPERATING_FPR_BUDGET,
        help=(
            "false-positive budget whose recall the gate compares "
            f"(default {DEFAULT_OPERATING_FPR_BUDGET})"
        ),
    )
    parser.add_argument(
        "--allow-regression",
        action="store_true",
        help=(
            "exit 0 even when the acceptance gate rejects v3. The rejection is still "
            "recorded in acceptance.json -- this only stops it failing the process."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = CrossFamilyHardenConfig(
        processed_dir=args.processed_dir,
        bustout_round0_dir=args.bustout_round0_dir,
        bustout_adaptive_dir=args.bustout_adaptive_dir,
        mule_confrontation_dir=args.mule_confrontation_dir,
        adaptive_evasion_confrontation_dir=args.adaptive_evasion_confrontation_dir,
        baseline_v1_model_dir=args.baseline_v1_model_dir,
        defender_v2_model_dir=args.defender_v2_model_dir,
        hardening_data_dir=args.hardening_data_dir,
        model_output_dir=args.model_output_dir,
        model_version_prefix=args.model_version_prefix,
        seed=args.seed,
        num_boost_round=args.num_boost_round,
        latency_sample_size=args.latency_sample_size,
        low_memory=args.low_memory,
        chunk_size=args.chunk_size,
        nthread=args.nthread,
        acceptance_criteria=AcceptanceCriteria(
            tolerance=args.acceptance_tolerance,
            operating_fpr_budget=args.operating_fpr_budget,
        ),
    )
    result = run_crossfamily_hardening(config)

    print()
    print(f"Defender v3: {result.training_result.model_version}")
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
    print(f"v1 vs v2 vs v3 regression: {result.regression_report_path}")
    print(f"Codex handoff: {result.handoff_path}")
    print(f"Acceptance gate: {result.acceptance_path}")
    print(f"  vs defender_v2 -> {result.acceptance_vs_v2.summary}")
    print(f"  vs baseline_v1 -> {result.acceptance_vs_v1.summary}")

    if not result.accepted and not args.allow_regression:
        print()
        print(
            "Rejected by the acceptance gate. Artifacts were written for inspection; "
            "re-run with --allow-regression to ship anyway."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
