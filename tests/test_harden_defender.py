"""End-to-end proof for Blue Hardening Round 1 (`scripts/harden_defender.py`).

Builds a small fixture standing in for the real artifacts: a tiny processed
PaySim run, a freshly-trained "baseline v1" over it, and two small bust-out
scenarios standing in for the real Round-0 confrontation and the selected
Adaptive-Round-1 candidate. Then runs the actual hardening pipeline
end-to-end and checks every safety property `docs/EVALUATION_RULES.md`
SS2/SS3 and the task's Phase E requirements demand.
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
from scripts.harden_defender import HardenDefenderConfig, run_harden_defender
from scripts.train_baseline_detector import BaselinePipelineConfig, run_baseline_pipeline

from aegis.shared.contracts import Transaction
from aegis.shared.enums import AttackFamily, DataSplit, FraudLabel, TransactionType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
PROMOTED_AT = datetime(2026, 8, 25, tzinfo=timezone.utc)


@pytest.fixture
def work_dir() -> Iterator[Path]:
    path = (Path("data/interim") / f"harden-defender-test-{uuid.uuid4().hex}").resolve()
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


def _warmup_txn(i: int, scenario_id: str, day_offset: int, **overrides: Any) -> Transaction:
    base: dict[str, Any] = {
        "transaction_id": f"{scenario_id}-warmup-{i:03d}",
        "timestamp": T0 + timedelta(days=day_offset + i),
        "source_account_id": f"C-SYN-{scenario_id}",
        "destination_account_id": f"C-WARM-{scenario_id}-{i}",
        "amount": 400.0 + i * 10,
        "transaction_type": TransactionType.CASH_OUT,
        "label": FraudLabel.LEGITIMATE,
        "is_synthetic": True,
        "scenario_id": scenario_id,
        "blueprint_id": "synthetic-identity-bustout-v1",
        "sequence_index": i,
        "generation": 0,
        "split": DataSplit.TEST,
    }
    base.update(overrides)
    return Transaction(**base)


def _fraud_txn(
    i: int, scenario_id: str, *, warmup_count: int, day_offset: int, **overrides: Any
) -> Transaction:
    base: dict[str, Any] = {
        "transaction_id": f"{scenario_id}-bustout-{i:03d}",
        "timestamp": T0 + timedelta(days=day_offset + warmup_count + i),
        "source_account_id": f"C-SYN-{scenario_id}",
        "destination_account_id": f"C-BUST-{scenario_id}-{i}",
        "amount": 4000.0 + i * 100,
        "transaction_type": TransactionType.CASH_OUT,
        "label": FraudLabel.FRAUD,
        "attack_family": AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
        "is_synthetic": True,
        "scenario_id": scenario_id,
        "blueprint_id": "synthetic-identity-bustout-v1",
        "sequence_index": warmup_count + i,
        "generation": 0,
        "split": DataSplit.TEST,
    }
    base.update(overrides)
    return Transaction(**base)


def _scenario(
    scenario_id: str, day_offset: int, *, warmup: int = 4, fraud: int = 2
) -> list[Transaction]:
    rows = [_warmup_txn(i, scenario_id, day_offset) for i in range(warmup)]
    rows.extend(
        _fraud_txn(i, scenario_id, warmup_count=warmup, day_offset=day_offset)
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
def baseline_result(work_dir: Path, processed_dir: Path):
    return run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_dir,
            output_dir=work_dir / "models",
            seed=321,
            num_boost_round=10,
            latency_sample_size=5,
            low_memory=True,
            chunk_size=7,
        )
    )


def _harden_config(
    work_dir: Path, processed_dir: Path, baseline_artifact_dir: Path, **overrides: Any
) -> HardenDefenderConfig:
    round0_dir = work_dir / "sources" / "round0"
    round1_dir = work_dir / "sources" / "round1"
    _write_jsonl(round0_dir / "transactions.jsonl", _scenario("bustout-h0", day_offset=5))
    _write_jsonl(round1_dir / "transactions.jsonl", _scenario("bustout-h1", day_offset=6))

    base: dict[str, Any] = {
        "processed_dir": processed_dir,
        "round0_confrontation_dir": round0_dir,
        "adaptive_candidate_dir": round1_dir,
        "baseline_model_dir": baseline_artifact_dir,
        "hardening_data_dir": work_dir / "hardening",
        "model_output_dir": work_dir / "models",
        "model_version_prefix": "xgboost-hardened-r1",
        "seed": 999,
        "num_boost_round": 10,
        "latency_sample_size": 5,
        "low_memory": True,
        "chunk_size": 7,
        "promoted_at": PROMOTED_AT,
    }
    base.update(overrides)
    return HardenDefenderConfig(**base)


def test_hardening_appends_hard_positives_to_train_only(work_dir, processed_dir, baseline_result):
    config = _harden_config(work_dir, processed_dir, baseline_result.artifact_dir)
    result = run_harden_defender(config)

    # 2 scenarios * (4 warmup + 2 fraud) = 12 promoted rows, train-only.
    assert result.training_result.train_size == baseline_result.train_size + 12
    assert result.training_result.validation_size == baseline_result.validation_size
    assert result.training_result.test_size == baseline_result.test_size
    assert result.hard_positive_artifact.row_count == 12
    assert result.hard_positive_artifact.fraud_count == 4


def test_hardened_model_version_and_artifact_dir_are_distinct(
    work_dir, processed_dir, baseline_result
):
    config = _harden_config(work_dir, processed_dir, baseline_result.artifact_dir)
    result = run_harden_defender(config)

    assert result.training_result.model_version == "xgboost-hardened-r1-999"
    assert result.training_result.model_version != baseline_result.model_version
    assert result.training_result.artifact_dir != baseline_result.artifact_dir
    assert result.training_result.artifact_dir.exists()


def test_baseline_artifact_is_never_modified(work_dir, processed_dir, baseline_result):
    baseline_model_json = baseline_result.artifact_dir / "model.json"
    before_bytes = baseline_model_json.read_bytes()
    before_mtime = baseline_model_json.stat().st_mtime

    config = _harden_config(work_dir, processed_dir, baseline_result.artifact_dir)
    run_harden_defender(config)

    assert baseline_model_json.read_bytes() == before_bytes
    assert baseline_model_json.stat().st_mtime == before_mtime


def test_test_evaluation_is_computed_only_on_untouched_test_split(
    work_dir, processed_dir, baseline_result
):
    config = _harden_config(work_dir, processed_dir, baseline_result.artifact_dir)
    result = run_harden_defender(config)

    hardened_support = result.training_result.test_evaluation.overall.support
    baseline_support = baseline_result.test_evaluation.overall.support
    assert hardened_support == baseline_support == 50  # never grows by the 4 promoted fraud rows


def test_threshold_still_tuned_on_validation_only(work_dir, processed_dir, baseline_result):
    config = _harden_config(work_dir, processed_dir, baseline_result.artifact_dir)
    result = run_harden_defender(config)

    validation_support = result.training_result.validation_evaluation.overall.support
    assert validation_support == baseline_result.validation_size == 50


def test_regression_report_compares_against_baseline_test_metrics(
    work_dir, processed_dir, baseline_result
):
    config = _harden_config(work_dir, processed_dir, baseline_result.artifact_dir)
    result = run_harden_defender(config)

    report = json.loads(result.regression_report_path.read_text(encoding="utf-8"))
    assert report["baseline_model_version"] == baseline_result.model_version
    assert report["defender_v2_model_version"] == result.training_result.model_version
    for field in ("precision", "recall", "f1", "false_positive_rate", "threshold"):
        assert field in report["metrics"]
        assert "baseline_v1" in report["metrics"][field]
        assert "defender_v2" in report["metrics"][field]
    assert report["confusion_matrix"]["baseline_v1"]["true_positives"] >= 0


def test_generation2_handoff_excludes_promoted_scenarios(work_dir, processed_dir, baseline_result):
    config = _harden_config(work_dir, processed_dir, baseline_result.artifact_dir)
    result = run_harden_defender(config)

    handoff = json.loads(result.handoff_path.read_text(encoding="utf-8"))
    assert handoff["defender_version"] == result.training_result.model_version
    assert handoff["model_dir"] == str(result.training_result.artifact_dir)
    assert set(handoff["excluded_scenario_ids"]) == {"bustout-h0", "bustout-h1"}
    assert len(handoff["excluded_transaction_ids"]) == 4
    assert "run_bustout_confrontation.py" in handoff["instructions"]
    assert "run_adaptive_bustout_round.py" in handoff["instructions"]


def test_hardening_is_deterministic_with_a_fixed_seed(work_dir, processed_dir, baseline_result):
    config_a = _harden_config(
        work_dir,
        processed_dir,
        baseline_result.artifact_dir,
        hardening_data_dir=work_dir / "hardening-a",
        model_output_dir=work_dir / "models-a",
    )
    result_a = run_harden_defender(config_a)

    config_b = _harden_config(
        work_dir,
        processed_dir,
        baseline_result.artifact_dir,
        hardening_data_dir=work_dir / "hardening-b",
        model_output_dir=work_dir / "models-b",
    )
    result_b = run_harden_defender(config_b)

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


def test_hardening_rejects_a_hard_positive_id_that_collides_with_validation(
    work_dir, processed_dir, baseline_result
):
    round0_dir = work_dir / "sources" / "round0-collide"
    colliding_rows = _scenario("bustout-collide", day_offset=5)
    # Force a collision: reuse an ID that also appears in validation.jsonl.
    colliding_rows[0] = colliding_rows[0].model_copy(update={"transaction_id": "validation-0"})
    _write_jsonl(round0_dir / "transactions.jsonl", colliding_rows)
    round1_dir = work_dir / "sources" / "round1-collide"
    _write_jsonl(round1_dir / "transactions.jsonl", _scenario("bustout-h1c", day_offset=6))

    config = _harden_config(
        work_dir,
        processed_dir,
        baseline_result.artifact_dir,
        round0_confrontation_dir=round0_dir,
        adaptive_candidate_dir=round1_dir,
    )
    with pytest.raises(Exception, match="already present in validation"):
        run_harden_defender(config)


def test_low_memory_execution_completes_and_writes_expected_files(
    work_dir, processed_dir, baseline_result
):
    config = _harden_config(work_dir, processed_dir, baseline_result.artifact_dir)
    result = run_harden_defender(config)

    artifact_dir = result.training_result.artifact_dir
    assert (artifact_dir / "model.json").exists()
    assert (artifact_dir / "metadata.json").exists()
    assert (artifact_dir / "evaluation_validation.json").exists()
    assert (artifact_dir / "evaluation_test.json").exists()
    assert (artifact_dir / "regression_vs_baseline.json").exists()
    assert (artifact_dir / "generation2_handoff.json").exists()
