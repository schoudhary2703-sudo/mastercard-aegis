"""End-to-end proof for Defender v3 cross-family hardening
(`scripts/harden_defender_crossfamily.py`).

Builds a small fixture standing in for the real artifacts: a tiny processed
PaySim run, a freshly-trained "baseline v1" over it, a stand-in "Defender
v2" evaluation record (only its `evaluation_test.json` is needed - v2 is
never retrained here), and one small scenario per attack family standing in
for the real mule and adaptive-evasion confrontations plus the bust-out
round-0/adaptive-round-1 sources. Then runs the actual cross-family
hardening pipeline end-to-end and checks every safety property
`docs/EVALUATION_RULES.md` SS2/SS3/SS4 and the task's verification
requirements demand.
"""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from scripts.harden_defender_crossfamily import (
    CrossFamilyHardenConfig,
    run_crossfamily_hardening,
)
from scripts.train_baseline_detector import BaselinePipelineConfig, run_baseline_pipeline

from aegis.features.streaming import FeatureArtifact
from aegis.features.temporal import feature_columns
from aegis.shared.contracts import Transaction
from aegis.shared.enums import AttackFamily, DataSplit, FraudLabel, TransactionType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
PROMOTED_AT = datetime(2026, 9, 1, tzinfo=timezone.utc)


@pytest.fixture
def work_dir() -> Iterator[Path]:
    path = (Path("data/interim") / f"harden-crossfamily-test-{uuid.uuid4().hex}").resolve()
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _paysim_txn(i: int, day_offset: int, split: DataSplit) -> Transaction:
    label = FraudLabel.FRAUD if i % 8 == 0 else FraudLabel.LEGITIMATE
    return Transaction(
        transaction_id=f"{split.value}-{i}",
        timestamp=T0 + timedelta(days=day_offset, minutes=i * 6),
        source_account_id=f"src{i % 9}",
        destination_account_id=f"dst{i % 6}",
        amount=75.0 + (i % 17) * 31.0,
        transaction_type=TransactionType.TRANSFER,
        source_balance_before=1200.0,
        source_balance_after=1100.0,
        destination_balance_before=250.0,
        destination_balance_after=350.0,
        label=label,
        split=split,
        metadata={"isFlaggedFraud": 0},
    )


def _make_split(n: int, day_offset: int, split: DataSplit) -> list[Transaction]:
    return [_paysim_txn(i, day_offset, split) for i in range(n)]


def _write_jsonl(path: Path, transactions: list[Transaction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for txn in transactions:
            fh.write(txn.to_json())
            fh.write("\n")


def _context_txn(
    i: int, scenario_id: str, day_offset: int, *, blueprint_id: str, **overrides: Any
) -> Transaction:
    base: dict[str, Any] = {
        "transaction_id": f"{scenario_id}-context-{i:03d}",
        "timestamp": T0 + timedelta(days=day_offset + i),
        "source_account_id": f"C-SRC-{scenario_id}",
        "destination_account_id": f"C-CTX-{scenario_id}-{i}",
        "amount": 400.0 + i * 10,
        "transaction_type": TransactionType.CASH_OUT,
        "label": FraudLabel.LEGITIMATE,
        "is_synthetic": True,
        "scenario_id": scenario_id,
        "blueprint_id": blueprint_id,
        "sequence_index": i,
        "generation": 0,
        "split": DataSplit.TEST,
    }
    base.update(overrides)
    return Transaction(**base)


def _fraud_txn(
    i: int,
    scenario_id: str,
    *,
    warmup_count: int,
    day_offset: int,
    attack_family: AttackFamily,
    blueprint_id: str,
    **overrides: Any,
) -> Transaction:
    base: dict[str, Any] = {
        "transaction_id": f"{scenario_id}-fraud-{i:03d}",
        "timestamp": T0 + timedelta(days=day_offset + warmup_count + i),
        "source_account_id": f"C-SRC-{scenario_id}",
        "destination_account_id": f"C-FRAUD-{scenario_id}-{i}",
        "amount": 4000.0 + i * 100,
        "transaction_type": TransactionType.CASH_OUT,
        "label": FraudLabel.FRAUD,
        "attack_family": attack_family,
        "is_synthetic": True,
        "scenario_id": scenario_id,
        "blueprint_id": blueprint_id,
        "sequence_index": warmup_count + i,
        "generation": 0,
        "split": DataSplit.TEST,
    }
    base.update(overrides)
    return Transaction(**base)


def _scenario(
    scenario_id: str,
    day_offset: int,
    *,
    attack_family: AttackFamily,
    blueprint_id: str,
    warmup: int = 4,
    fraud: int = 2,
) -> list[Transaction]:
    rows = [
        _context_txn(i, scenario_id, day_offset, blueprint_id=blueprint_id) for i in range(warmup)
    ]
    rows.extend(
        _fraud_txn(
            i,
            scenario_id,
            warmup_count=warmup,
            day_offset=day_offset,
            attack_family=attack_family,
            blueprint_id=blueprint_id,
        )
        for i in range(fraud)
    )
    return rows


@pytest.fixture
def processed_dir(work_dir: Path) -> Path:
    root = work_dir / "processed"
    _write_jsonl(root / "train.jsonl", _make_split(180, 0, DataSplit.TRAIN))
    _write_jsonl(root / "validation.jsonl", _make_split(50, 10, DataSplit.VALIDATION))
    _write_jsonl(root / "test.jsonl", _make_split(50, 20, DataSplit.TEST))
    return root


@pytest.fixture
def baseline_v1_result(work_dir: Path, processed_dir: Path):
    return run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_dir,
            output_dir=work_dir / "models",
            seed=111,
            num_boost_round=10,
            latency_sample_size=5,
            low_memory=True,
            chunk_size=7,
        )
    )


@pytest.fixture
def defender_v2_model_dir(work_dir: Path, baseline_v1_result) -> Path:
    """Only `evaluation_test.json` is needed - v3's script never retrains v2,
    only reads its frozen test evaluation for the 3-way comparison."""
    v2_dir = work_dir / "models" / "stand-in-v2"
    v2_dir.mkdir(parents=True)
    v2_eval = baseline_v1_result.test_evaluation.model_copy(
        update={
            "model_version": "stand-in-defender-v2",
            "evaluation_id": "stand-in-defender-v2-test",
        }
    )
    (v2_dir / "evaluation_test.json").write_text(v2_eval.to_json(indent=2), encoding="utf-8")
    return v2_dir


def _crossfamily_config(
    work_dir: Path,
    processed_dir: Path,
    baseline_v1_artifact_dir: Path,
    defender_v2_model_dir: Path,
    **overrides: Any,
) -> CrossFamilyHardenConfig:
    bustout_round0_dir = work_dir / "sources" / "bustout-round0"
    bustout_adaptive_dir = work_dir / "sources" / "bustout-adaptive"
    mule_dir = work_dir / "sources" / "mule"
    adaptive_evasion_dir = work_dir / "sources" / "adaptive-evasion"

    _write_jsonl(
        bustout_round0_dir / "transactions.jsonl",
        _scenario(
            "bustout-r0",
            day_offset=5,
            attack_family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
            blueprint_id="synthetic-identity-bustout-v1",
        ),
    )
    _write_jsonl(
        bustout_adaptive_dir / "transactions.jsonl",
        _scenario(
            "bustout-r1",
            day_offset=6,
            attack_family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
            blueprint_id="synthetic-identity-bustout-v1-g1-x",
        ),
    )
    _write_jsonl(
        mule_dir / "transactions.jsonl",
        _scenario(
            "mule-1",
            day_offset=7,
            attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
            blueprint_id="mule-network-structuring-v1",
            warmup=3,
            fraud=3,
        ),
    )
    _write_jsonl(
        adaptive_evasion_dir / "transactions.jsonl",
        _scenario(
            "adaptive-evasion-1",
            day_offset=8,
            attack_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
            blueprint_id="adaptive-detector-evasion-v1-g1-x",
            warmup=2,
            fraud=2,
        ),
    )

    base: dict[str, Any] = {
        "processed_dir": processed_dir,
        "bustout_round0_dir": bustout_round0_dir,
        "bustout_adaptive_dir": bustout_adaptive_dir,
        "mule_confrontation_dir": mule_dir,
        "adaptive_evasion_confrontation_dir": adaptive_evasion_dir,
        "baseline_v1_model_dir": baseline_v1_artifact_dir,
        "defender_v2_model_dir": defender_v2_model_dir,
        "hardening_data_dir": work_dir / "hardening",
        "model_output_dir": work_dir / "models",
        "model_version_prefix": "xgboost-hardened-crossfamily",
        "seed": 777,
        "num_boost_round": 10,
        "latency_sample_size": 5,
        "low_memory": True,
        "chunk_size": 7,
        "promoted_at": PROMOTED_AT,
    }
    base.update(overrides)
    return CrossFamilyHardenConfig(**base)


# --- A: hard-positive dataset -----------------------------------------------


def test_hardening_appends_hard_positives_from_all_three_families_to_train_only(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    # bustout: 2 scenarios * (4+2) = 12; mule: 1 * (3+3) = 6; adaptive-evasion: 1 * (2+2) = 4.
    assert result.hard_positive_artifact.row_count == 22
    assert result.hard_positive_artifact.fraud_count == 2 + 2 + 3 + 2
    assert result.training_result.train_size == baseline_v1_result.train_size + 22
    assert result.training_result.validation_size == baseline_v1_result.validation_size
    assert result.training_result.test_size == baseline_v1_result.test_size


def test_hard_positive_counts_reported_per_family(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    assert set(result.family_counts) == {
        "synthetic_identity_bustout",
        "mule_network_structuring",
        "adaptive_detector_evasion",
    }
    bustout = result.family_counts["synthetic_identity_bustout"]
    assert bustout == {"rows": 12, "fraud": 4, "legitimate": 8, "scenarios": 2}
    mule = result.family_counts["mule_network_structuring"]
    assert mule == {"rows": 6, "fraud": 3, "legitimate": 3, "scenarios": 1}
    adaptive_evasion = result.family_counts["adaptive_detector_evasion"]
    assert adaptive_evasion == {"rows": 4, "fraud": 2, "legitimate": 2, "scenarios": 1}


def test_provenance_preserves_family_blueprint_scenario_and_source_round(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    by_scenario = {p.scenario_id: p for p in result.promotion.provenance}
    assert by_scenario["bustout-r0"].source_round == "round-0"
    assert by_scenario["bustout-r1"].source_round == "adaptive-round-1"
    assert by_scenario["mule-1"].source_round == "mule-confrontation-1"
    assert by_scenario["mule-1"].attack_family == "mule_network_structuring"
    assert by_scenario["mule-1"].blueprint_id == "mule-network-structuring-v1"
    assert by_scenario["adaptive-evasion-1"].source_round == "adaptive-evasion-confrontation-1"
    assert by_scenario["adaptive-evasion-1"].attack_family == "adaptive_detector_evasion"

    hardened_txn = next(t for t in result.promotion.transactions if t.scenario_id == "mule-1")
    assert hardened_txn.split == DataSplit.TRAIN
    assert hardened_txn.metadata["hardening"]["source_round"] == "mule-confrontation-1"
    assert hardened_txn.metadata["hardening"]["promoted_at"] == PROMOTED_AT.isoformat()


def test_hardening_rejects_duplicate_transaction_id_across_families(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    mule_dir = work_dir / "sources" / "mule-dup"
    rows = _scenario(
        "mule-dup",
        day_offset=7,
        attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
        blueprint_id="mule-network-structuring-v1",
    )
    adaptive_evasion_dir = work_dir / "sources" / "adaptive-evasion-dup"
    other_rows = _scenario(
        "adaptive-evasion-dup",
        day_offset=8,
        attack_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
        blueprint_id="adaptive-detector-evasion-v1-g1-x",
    )
    # Force a cross-family transaction_id collision.
    other_rows[0] = other_rows[0].model_copy(update={"transaction_id": rows[0].transaction_id})
    _write_jsonl(mule_dir / "transactions.jsonl", rows)
    _write_jsonl(adaptive_evasion_dir / "transactions.jsonl", other_rows)

    config = _crossfamily_config(
        work_dir,
        processed_dir,
        baseline_v1_result.artifact_dir,
        defender_v2_model_dir,
        mule_confrontation_dir=mule_dir,
        adaptive_evasion_confrontation_dir=adaptive_evasion_dir,
    )
    with pytest.raises(Exception, match="duplicate transaction_id"):
        run_crossfamily_hardening(config)


def test_hardening_rejects_a_hard_positive_id_that_collides_with_validation(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    mule_dir = work_dir / "sources" / "mule-collide"
    colliding_rows = _scenario(
        "mule-collide",
        day_offset=7,
        attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
        blueprint_id="mule-network-structuring-v1",
    )
    colliding_rows[0] = colliding_rows[0].model_copy(update={"transaction_id": "validation-0"})
    _write_jsonl(mule_dir / "transactions.jsonl", colliding_rows)

    config = _crossfamily_config(
        work_dir,
        processed_dir,
        baseline_v1_result.artifact_dir,
        defender_v2_model_dir,
        mule_confrontation_dir=mule_dir,
    )
    with pytest.raises(Exception, match="already present in validation"):
        run_crossfamily_hardening(config)


# --- B: feature leakage safety (integration-level) --------------------------


def test_feature_matrix_has_21_columns_including_distinct_counterparty_features(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    schema = FeatureArtifact.load_schema(result.training_result.artifact_dir / "features" / "train")
    feature_names = schema["feature_names"]
    assert isinstance(feature_names, list)
    assert len(feature_names) == 21
    assert "temporal.source_distinct_destinations_before" in feature_names
    assert "temporal.destination_distinct_sources_before" in feature_names


def test_v3_materializes_its_own_features_independent_of_v1(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    """v3's crossfamily script has no feature-reuse-from-baseline shortcut
    (unlike `harden_defender.py`'s `_maybe_reuse_baseline_features`, which
    would be wrong here since the feature extractor's column set changed for
    v3): v3's validation features must live under its own artifact directory
    and exactly match the current extractor's schema, not a copy of v1's."""
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    v3_feature_dir = result.training_result.artifact_dir / "features" / "validation"
    assert v3_feature_dir != baseline_v1_result.artifact_dir / "features" / "validation"
    v3_schema = FeatureArtifact.load_schema(v3_feature_dir)
    assert v3_schema["feature_names"] == feature_columns("temporal")


# --- C: train-only augmentation / evaluation isolation ----------------------


def test_defender_v3_model_version_and_artifact_dir_are_distinct(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    assert result.training_result.model_version == "xgboost-hardened-crossfamily-777"
    assert result.training_result.model_version != baseline_v1_result.model_version
    assert result.training_result.artifact_dir != baseline_v1_result.artifact_dir


def test_baseline_v1_and_v2_artifacts_are_never_modified(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    v1_model_json = baseline_v1_result.artifact_dir / "model.json"
    v1_before = v1_model_json.read_bytes()
    v2_eval_json = defender_v2_model_dir / "evaluation_test.json"
    v2_before = v2_eval_json.read_bytes()

    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    run_crossfamily_hardening(config)

    assert v1_model_json.read_bytes() == v1_before
    assert v2_eval_json.read_bytes() == v2_before


def test_test_evaluation_is_computed_only_on_untouched_test_split(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    assert (
        result.training_result.test_evaluation.overall.support
        == baseline_v1_result.test_evaluation.overall.support
        == 50
    )


def test_threshold_tuned_on_validation_only(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    assert (
        result.training_result.validation_evaluation.overall.support
        == baseline_v1_result.validation_size
        == 50
    )


# --- D: three-way regression benchmark --------------------------------------


def test_regression_report_compares_v1_v2_and_v3(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    report = json.loads(result.regression_report_path.read_text(encoding="utf-8"))
    assert report["baseline_v1_model_version"] == baseline_v1_result.model_version
    assert report["defender_v2_model_version"] == "stand-in-defender-v2"
    assert report["defender_v3_model_version"] == result.training_result.model_version
    for field in (
        "precision",
        "recall",
        "f1",
        "pr_auc",
        "roc_auc",
        "false_positive_rate",
        "threshold",
    ):
        assert field in report["metrics"]
        row = report["metrics"][field]
        assert {"baseline_v1", "defender_v2", "defender_v3_crossfamily"} <= row.keys()
    for model_key in ("baseline_v1", "defender_v2", "defender_v3_crossfamily"):
        assert report["confusion_matrix"][model_key]["true_positives"] >= 0
        assert report["latency_ms"][model_key] is not None
    assert "fresh Red confrontation" in report["notes"]


# --- E: Codex handoff --------------------------------------------------------


def test_codex_handoff_contains_required_fields(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    handoff = json.loads(result.handoff_path.read_text(encoding="utf-8"))
    assert handoff["defender_version"] == result.training_result.model_version
    assert handoff["model_dir"] == str(result.training_result.artifact_dir)
    assert handoff["tuned_threshold"] == pytest.approx(result.training_result.tuned_threshold)
    assert set(handoff["hard_positive_source_families"]) == {
        "synthetic_identity_bustout",
        "mule_network_structuring",
        "adaptive_detector_evasion",
    }
    assert set(handoff["excluded_scenario_ids"]) == {
        "bustout-r0",
        "bustout-r1",
        "mule-1",
        "adaptive-evasion-1",
    }
    assert len(handoff["excluded_transaction_ids"]) == 2 + 2 + 3 + 2
    assert "fresh" in handoff["fresh_seed_requirement"].lower()
    assert "run_bustout_confrontation.py" in handoff["instructions"]
    assert "run_mule_network_confrontation.py" in handoff["instructions"]
    assert "run_adaptive_evasion_confrontation.py" in handoff["instructions"]
    assert "LOAFO" in handoff["instructions"]


# --- F: determinism / low-memory ---------------------------------------------


def test_hardening_is_deterministic_with_a_fixed_seed(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config_a = _crossfamily_config(
        work_dir,
        processed_dir,
        baseline_v1_result.artifact_dir,
        defender_v2_model_dir,
        hardening_data_dir=work_dir / "hardening-a",
        model_output_dir=work_dir / "models-a",
    )
    result_a = run_crossfamily_hardening(config_a)

    config_b = _crossfamily_config(
        work_dir,
        processed_dir,
        baseline_v1_result.artifact_dir,
        defender_v2_model_dir,
        hardening_data_dir=work_dir / "hardening-b",
        model_output_dir=work_dir / "models-b",
    )
    result_b = run_crossfamily_hardening(config_b)

    assert (
        result_a.hard_positive_artifact.jsonl_path.read_text()
        == result_b.hard_positive_artifact.jsonl_path.read_text()
    )
    assert result_a.training_result.tuned_threshold == pytest.approx(
        result_b.training_result.tuned_threshold
    )
    metrics_a = result_a.training_result.test_evaluation.overall.model_dump()
    metrics_b = result_b.training_result.test_evaluation.overall.model_dump()
    assert metrics_a == metrics_b


def test_low_memory_execution_completes_and_writes_expected_files(
    work_dir, processed_dir, baseline_v1_result, defender_v2_model_dir
):
    config = _crossfamily_config(
        work_dir, processed_dir, baseline_v1_result.artifact_dir, defender_v2_model_dir
    )
    result = run_crossfamily_hardening(config)

    artifact_dir = result.training_result.artifact_dir
    assert (artifact_dir / "model.json").exists()
    assert (artifact_dir / "metadata.json").exists()
    assert (artifact_dir / "evaluation_validation.json").exists()
    assert (artifact_dir / "evaluation_test.json").exists()
    assert (artifact_dir / "regression_vs_v1_v2.json").exists()
    assert (artifact_dir / "codex_handoff.json").exists()
