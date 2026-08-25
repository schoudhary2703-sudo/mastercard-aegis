"""End-to-end proof for the LOAFO generalization benchmark
(`scripts/run_loafo_benchmark.py`).

Builds a small fixture standing in for the real artifacts: a tiny processed
PaySim run, a stand-in "Defender v3" trained over it, and small
hand-built scenarios standing in for the mule and adaptive-evasion prior
confrontations (the two *training* families for the fold under test). The
held-out family's *fresh* evaluation scenario is generated for real via the
existing `run_bustout_confrontation` machinery (the same low-memory,
`reuse_model_dir` path `tests/test_bustout_confrontation_low_memory.py`
already proves works against a tiny fixture PaySim directory), so this test
exercises the genuine generation + scoring + freshness-check code path, not
a stub.

Runs one full LOAFO fold (train on mule + adaptive-evasion, hold out
synthetic_identity_bustout) end to end and checks every safety property the
task's verification requirements demand, plus targeted unit tests for the
freshness/overlap and generalization-verdict helpers in isolation.
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
from scripts.run_loafo_benchmark import (
    FAMILY_ADAPTIVE,
    FAMILY_MULE,
    FAMILY_SYNTHETIC,
    LoafoBenchmarkConfig,
    LoafoFoldSpec,
    _generalization_verdict,
    assert_fresh_scenario_has_no_overlap,
    build_summary,
    run_loafo_fold,
    snapshot_prior_artifact_ids,
)
from scripts.train_baseline_detector import BaselinePipelineConfig, run_baseline_pipeline

from aegis.defend.hard_positives import HardPositiveSource
from aegis.shared.contracts import Transaction, TransactionBatch
from aegis.shared.enums import AttackFamily, DataSplit, FraudLabel, TransactionType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
PROMOTED_AT = datetime(2026, 9, 10, tzinfo=timezone.utc)


@pytest.fixture
def work_dir() -> Iterator[Path]:
    path = (Path("data/interim") / f"loafo-test-{uuid.uuid4().hex}").resolve()
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# --- PaySim-shaped fixture (mirrors tests/test_bustout_confrontation_low_memory.py) ---


def _paysim_txn(i: int, day: int, split: DataSplit) -> Transaction:
    fraud = i % 10 == 0
    return Transaction(
        transaction_id=f"{split.value}-{i}",
        timestamp=T0 + timedelta(days=day, minutes=i * 5),
        source_account_id=f"src-{i % 7}",
        destination_account_id=f"dst-{i % 5}",
        amount=(700.0 + i) if fraud else (30.0 + i % 25),
        transaction_type=TransactionType.CASH_OUT if fraud else TransactionType.PAYMENT,
        label=FraudLabel.FRAUD if fraud else FraudLabel.LEGITIMATE,
        split=split,
    )


def _make_split(n: int, day: int, split: DataSplit) -> list[Transaction]:
    return [_paysim_txn(i, day, split) for i in range(n)]


def _write_jsonl(path: Path, transactions: list[Transaction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for txn in transactions:
            fh.write(txn.to_json())
            fh.write("\n")


@pytest.fixture
def processed_dir(work_dir: Path) -> Path:
    root = work_dir / "processed"
    _write_jsonl(root / "train.jsonl", _make_split(120, 0, DataSplit.TRAIN))
    _write_jsonl(root / "validation.jsonl", _make_split(40, 10, DataSplit.VALIDATION))
    _write_jsonl(root / "test.jsonl", _make_split(40, 20, DataSplit.TEST))
    return root


@pytest.fixture
def defender_v3_standin(work_dir: Path, processed_dir: Path):
    """Stand-in for the real Defender v3 - just needs to be *a* trained
    21-column model with its own threshold, for the memorization comparison."""
    return run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_dir,
            output_dir=work_dir / "models",
            seed=999,
            num_boost_round=8,
            latency_sample_size=5,
            low_memory=True,
            chunk_size=7,
            model_version_prefix="standin-defender-v3",
        )
    )


# --- hand-built hard-positive source scenarios (training families only) ---


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
    warmup: int = 3,
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
def fold_c_family_sources(work_dir: Path) -> dict[str, list[HardPositiveSource]]:
    """Sources for Fold C: train on mule + adaptive-evasion, hold out synthetic."""
    mule_dir = work_dir / "sources" / "mule"
    adaptive_dir = work_dir / "sources" / "adaptive-evasion"
    _write_jsonl(
        mule_dir / "transactions.jsonl",
        _scenario(
            "mule-fixture-1",
            day_offset=7,
            attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
            blueprint_id="mule-network-structuring-v1",
        ),
    )
    _write_jsonl(
        adaptive_dir / "transactions.jsonl",
        _scenario(
            "adaptive-fixture-1",
            day_offset=8,
            attack_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
            blueprint_id="adaptive-detector-evasion-v1-g1-x",
        ),
    )
    return {
        FAMILY_SYNTHETIC: [],  # held out in Fold C - deliberately no sources
        FAMILY_MULE: [
            HardPositiveSource(artifact_dir=mule_dir, source_round="mule-confrontation-1")
        ],
        FAMILY_ADAPTIVE: [
            HardPositiveSource(
                artifact_dir=adaptive_dir, source_round="adaptive-evasion-confrontation-1"
            )
        ],
    }


def _fold_c_config(
    work_dir: Path,
    processed_dir: Path,
    defender_v3_model_dir: Path,
    family_sources: dict[str, list[HardPositiveSource]],
    **overrides: Any,
) -> LoafoBenchmarkConfig:
    spec = LoafoFoldSpec(
        fold_id="fold-c-test",
        held_out_family=FAMILY_SYNTHETIC,
        training_families=(FAMILY_MULE, FAMILY_ADAPTIVE),
        model_version_prefix="loafo-test-mule-adaptive",
        training_seed=555,
        fresh_eval_seed=556,
    )
    base: dict[str, Any] = {
        "processed_dir": processed_dir,
        "folds": (spec,),
        "defender_v3_model_dir": defender_v3_model_dir,
        "synthetic_root": work_dir / "synthetic",
        "hardening_data_dir": work_dir / "hardening",
        "model_output_dir": work_dir / "models",
        "fresh_eval_output_dir": work_dir / "synthetic" / "loafo_evaluations",
        "num_boost_round": 8,
        "latency_sample_size": 5,
        "low_memory": True,
        "chunk_size": 7,
        "promoted_at": PROMOTED_AT,
        "family_sources": family_sources,
    }
    base.update(overrides)
    return LoafoBenchmarkConfig(**base)


# --- full fold, end to end ---------------------------------------------------


def test_fold_trains_only_on_the_two_included_families(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    config = _fold_c_config(
        work_dir, processed_dir, defender_v3_standin.artifact_dir, fold_c_family_sources
    )
    result = run_loafo_fold(config.folds[0], config)

    promoted_families = {p.attack_family for p in result.promotion.provenance}
    assert promoted_families == {"mule_network_structuring", "adaptive_detector_evasion"}
    assert "synthetic_identity_bustout" not in promoted_families
    assert set(result.family_counts) == {"mule_network_structuring", "adaptive_detector_evasion"}


def test_held_out_family_contributes_zero_training_rows(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    """The structural guarantee (empty source list) plus the script's own
    runtime assertion both hold - proven by inspecting actual promoted rows,
    not just trusting the empty source list."""
    config = _fold_c_config(
        work_dir, processed_dir, defender_v3_standin.artifact_dir, fold_c_family_sources
    )
    result = run_loafo_fold(config.folds[0], config)

    for txn in result.promotion.transactions:
        assert str(txn.attack_family) != "synthetic_identity_bustout" or txn.attack_family is None


def test_fresh_held_out_scenario_is_a_real_bustout_scenario_never_in_training(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    config = _fold_c_config(
        work_dir, processed_dir, defender_v3_standin.artifact_dir, fold_c_family_sources
    )
    result = run_loafo_fold(config.folds[0], config)

    fresh = result.fresh_eval
    assert fresh.fraud_count > 0
    assert fresh.caught_count + fresh.evaded_count == fresh.fraud_count
    # The fresh scenario's own report id is real (bustout confrontation dir naming).
    assert "confrontation" in str(fresh.source_artifact)
    # The fresh bust-out scenario's ids must never appear among the (mule +
    # adaptive-evasion) rows this fold actually trained on.
    trained_ids = {t.transaction_id for t in result.promotion.transactions}
    fresh_ids = {e["transaction_id"] for e in fresh.hardest_evasions}
    assert not (trained_ids & fresh_ids)


def test_paysim_native_metrics_use_untouched_test_split(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    config = _fold_c_config(
        work_dir, processed_dir, defender_v3_standin.artifact_dir, fold_c_family_sources
    )
    result = run_loafo_fold(config.folds[0], config)
    assert result.training_result.test_evaluation.overall.support == 40
    assert result.training_result.validation_evaluation.overall.support == 40


def test_fold_and_defender_v3_evaluations_are_leave_one_attack_family_out(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    config = _fold_c_config(
        work_dir, processed_dir, defender_v3_standin.artifact_dir, fold_c_family_sources
    )
    result = run_loafo_fold(config.folds[0], config)

    fresh = result.fresh_eval
    assert fresh.fold_evaluation.protocol.value == "leave_one_attack_family_out"
    assert fresh.fold_evaluation.held_out_family is AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT
    assert fresh.defender_v3_evaluation.protocol.value == "leave_one_attack_family_out"
    assert fresh.defender_v3_evaluation.held_out_family is AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT
    # Both scored on the identical scenario id.
    assert fresh.fold_evaluation.dataset_id == fresh.defender_v3_evaluation.dataset_id


def test_model_hashes_are_stable_after_evaluation(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    v3_model_json = defender_v3_standin.artifact_dir / "model.json"
    v3_before = v3_model_json.read_bytes()

    config = _fold_c_config(
        work_dir, processed_dir, defender_v3_standin.artifact_dir, fold_c_family_sources
    )
    result = run_loafo_fold(config.folds[0], config)

    assert v3_model_json.read_bytes() == v3_before
    assert result.model_hash_before == result.model_hash_after
    fold_model_json = result.training_result.artifact_dir / "model.json"
    assert (
        result.model_hash_after[0]
        == __import__("hashlib").sha256(fold_model_json.read_bytes()).hexdigest()
    )


def test_fold_report_is_written_with_expected_fields(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    config = _fold_c_config(
        work_dir, processed_dir, defender_v3_standin.artifact_dir, fold_c_family_sources
    )
    result = run_loafo_fold(config.folds[0], config)

    report = json.loads(result.fold_report_path.read_text(encoding="utf-8"))
    assert report["held_out_family"] == "synthetic_identity_bustout"
    assert set(report["training_families"]) == {
        "mule_network_structuring",
        "adaptive_detector_evasion",
    }
    assert report["tuned_threshold"] == pytest.approx(result.training_result.tuned_threshold)
    fresh = report["fresh_held_out_evaluation"]
    assert fresh["fraud_count"] == result.fresh_eval.fraud_count
    assert "fold_model_evaluation" in fresh
    assert "defender_v3_evaluation" in fresh
    assert "hardest_evasions" in fresh


def test_duplicate_transaction_id_across_training_sources_is_rejected(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    mule_dir = work_dir / "sources" / "mule-dup"
    mule_rows = _scenario(
        "mule-dup",
        day_offset=7,
        attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
        blueprint_id="mule-network-structuring-v1",
    )
    adaptive_dir = work_dir / "sources" / "adaptive-dup"
    adaptive_rows = _scenario(
        "adaptive-dup",
        day_offset=8,
        attack_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
        blueprint_id="adaptive-detector-evasion-v1-g1-x",
    )
    adaptive_rows[0] = adaptive_rows[0].model_copy(
        update={"transaction_id": mule_rows[0].transaction_id}
    )
    _write_jsonl(mule_dir / "transactions.jsonl", mule_rows)
    _write_jsonl(adaptive_dir / "transactions.jsonl", adaptive_rows)

    sources = {
        FAMILY_SYNTHETIC: [],
        FAMILY_MULE: [
            HardPositiveSource(artifact_dir=mule_dir, source_round="mule-confrontation-1")
        ],
        FAMILY_ADAPTIVE: [
            HardPositiveSource(
                artifact_dir=adaptive_dir, source_round="adaptive-evasion-confrontation-1"
            )
        ],
    }
    config = _fold_c_config(work_dir, processed_dir, defender_v3_standin.artifact_dir, sources)
    with pytest.raises(Exception, match="duplicate transaction_id"):
        run_loafo_fold(config.folds[0], config)


def test_hard_positive_id_colliding_with_validation_is_rejected(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    mule_dir = work_dir / "sources" / "mule-collide"
    rows = _scenario(
        "mule-collide",
        day_offset=7,
        attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
        blueprint_id="mule-network-structuring-v1",
    )
    rows[0] = rows[0].model_copy(update={"transaction_id": "validation-0"})
    _write_jsonl(mule_dir / "transactions.jsonl", rows)

    sources = dict(fold_c_family_sources)
    sources[FAMILY_MULE] = [
        HardPositiveSource(artifact_dir=mule_dir, source_round="mule-confrontation-1")
    ]
    config = _fold_c_config(work_dir, processed_dir, defender_v3_standin.artifact_dir, sources)
    with pytest.raises(Exception, match="already present in validation"):
        run_loafo_fold(config.folds[0], config)


def test_low_memory_execution_completes_and_writes_expected_files(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    config = _fold_c_config(
        work_dir, processed_dir, defender_v3_standin.artifact_dir, fold_c_family_sources
    )
    result = run_loafo_fold(config.folds[0], config)

    artifact_dir = result.training_result.artifact_dir
    assert (artifact_dir / "model.json").exists()
    assert (artifact_dir / "metadata.json").exists()
    assert (artifact_dir / "loafo_fold_report.json").exists()


# --- freshness / overlap helpers, in isolation --------------------------------


def test_snapshot_prior_artifact_ids_reads_transaction_and_scenario_ids(work_dir):
    synthetic_root = work_dir / "synthetic"
    _write_jsonl(
        synthetic_root / "some_confrontation" / "transactions.jsonl",
        [
            Transaction(
                transaction_id="prior-txn-1",
                timestamp=T0,
                source_account_id="a",
                destination_account_id="b",
                amount=10.0,
                transaction_type=TransactionType.TRANSFER,
                scenario_id="prior-scenario-1",
            )
        ],
    )
    txn_ids, scenario_ids = snapshot_prior_artifact_ids(
        synthetic_root=synthetic_root, hardening_root=work_dir / "hardening-missing"
    )
    assert "prior-txn-1" in txn_ids
    assert "prior-scenario-1" in scenario_ids


def test_snapshot_prior_artifact_ids_tolerates_missing_roots(work_dir):
    txn_ids, scenario_ids = snapshot_prior_artifact_ids(
        synthetic_root=work_dir / "does-not-exist",
        hardening_root=work_dir / "also-missing",
    )
    assert txn_ids == set()
    assert scenario_ids == set()


def _tiny_batch(transaction_ids: list[str], scenario_id: str | None = None) -> TransactionBatch:
    return TransactionBatch(
        batch_id="fixture-batch",
        seed=1,
        generator_name="fixture",
        generator_version="1.0.0",
        transactions=[
            Transaction(
                transaction_id=tid,
                timestamp=T0,
                source_account_id="a",
                destination_account_id="b",
                amount=10.0,
                transaction_type=TransactionType.TRANSFER,
                scenario_id=scenario_id,
            )
            for tid in transaction_ids
        ],
    )


def test_assert_fresh_scenario_has_no_overlap_passes_when_disjoint():
    batch = _tiny_batch(["fresh-1", "fresh-2"], scenario_id="fresh-scenario")
    assert_fresh_scenario_has_no_overlap(
        batch=batch,
        prior_transaction_ids={"old-1"},
        prior_scenario_ids={"old-scenario"},
        fold_id="fold-x",
        family="mule_network_structuring",
    )  # does not raise


def test_assert_fresh_scenario_has_no_overlap_raises_on_transaction_id_collision():
    batch = _tiny_batch(["collide-1"], scenario_id="fresh-scenario")
    with pytest.raises(ValueError, match="transaction_id"):
        assert_fresh_scenario_has_no_overlap(
            batch=batch,
            prior_transaction_ids={"collide-1"},
            prior_scenario_ids=set(),
            fold_id="fold-x",
            family="mule_network_structuring",
        )


def test_assert_fresh_scenario_has_no_overlap_raises_on_scenario_id_collision():
    batch = _tiny_batch(["fresh-1"], scenario_id="collide-scenario")
    with pytest.raises(ValueError, match="scenario_id"):
        assert_fresh_scenario_has_no_overlap(
            batch=batch,
            prior_transaction_ids=set(),
            prior_scenario_ids={"collide-scenario"},
            fold_id="fold-x",
            family="mule_network_structuring",
        )


# --- generalization verdict + summary ----------------------------------------


def test_generalization_verdict_weak_when_loafo_recall_is_zero():
    assert _generalization_verdict(0.0, 0.8) == "weak"


def test_generalization_verdict_strong_when_at_least_half_of_v3():
    assert _generalization_verdict(0.5, 1.0) == "strong"
    assert _generalization_verdict(0.6, 1.0) == "strong"


def test_generalization_verdict_partial_when_below_half_of_v3():
    assert _generalization_verdict(0.2, 1.0) == "partial"


def test_generalization_verdict_strong_when_v3_itself_caught_nothing():
    assert _generalization_verdict(0.3, 0.0) == "strong"


def test_build_summary_aggregates_fold_results(
    work_dir, processed_dir, defender_v3_standin, fold_c_family_sources
):
    config = _fold_c_config(
        work_dir, processed_dir, defender_v3_standin.artifact_dir, fold_c_family_sources
    )
    result = run_loafo_fold(config.folds[0], config)

    summary = build_summary([result])
    assert "synthetic_identity_bustout" in summary["held_out_recall_per_family"]
    assert summary["mean_loafo_recall"] == pytest.approx(
        summary["held_out_recall_per_family"]["synthetic_identity_bustout"]
    )
    assert summary["per_family"]["synthetic_identity_bustout"]["fold_id"] == "fold-c-test"
    assert summary["per_family"]["synthetic_identity_bustout"]["verdict"] in (
        "strong",
        "partial",
        "weak",
    )
