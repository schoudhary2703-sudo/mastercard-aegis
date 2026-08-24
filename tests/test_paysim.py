"""PaySim preparation uses source-schema fixtures, never a fabricated production corpus."""

from __future__ import annotations

import csv
import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from aegis.generate import (
    PAYSIM_REQUIRED_COLUMNS,
    PaySimPreparationConfig,
    PaySimSchemaError,
    map_paysim_row,
    prepare_paysim,
    validate_paysim_schema,
)
from aegis.shared.contracts import Transaction
from aegis.shared.enums import Channel, DataSplit, FraudLabel, TransactionType


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Keep Windows sandbox test artifacts in the repository's ignored data area."""
    path = (Path("data/interim") / f"paysim-test-{uuid.uuid4().hex}").resolve()
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _source_row(
    step: int,
    source: str,
    destination: str,
    *,
    is_fraud: int = 0,
    transaction_type: str = "TRANSFER",
) -> dict[str, str | int | float]:
    return {
        "step": step,
        "type": transaction_type,
        "amount": 100.0 + step,
        "nameOrig": source,
        "oldbalanceOrg": 1000.0,
        "newbalanceOrig": 900.0 - step,
        "nameDest": destination,
        "oldbalanceDest": 50.0,
        "newbalanceDest": 150.0 + step,
        "isFraud": is_fraud,
        "isFlaggedFraud": int(is_fraud and step % 2 == 0),
    }


def _write_source(path: Path, rows: list[dict[str, str | int | float]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAYSIM_REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def paysim_rows() -> list[dict[str, str | int | float]]:
    rows = [
        _source_row(
            step,
            "C-CROSS" if step in (1, 9) else f"C{step}",
            "D-CROSS" if step in (2, 8) else f"D{step}",
            is_fraud=int(step in (2, 8, 9)),
            transaction_type=("PAYMENT" if step % 2 else "TRANSFER"),
        )
        for step in range(1, 11)
    ]
    return rows


@pytest.fixture
def paysim_csv(tmp_path, paysim_rows) -> Path:
    return _write_source(tmp_path / "paysim.csv", paysim_rows)


def _read_transactions(path: Path) -> list[Transaction]:
    return [
        Transaction.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_valid_paysim_schema_is_accepted(paysim_csv):
    assert validate_paysim_schema(paysim_csv) == PAYSIM_REQUIRED_COLUMNS


def test_missing_required_column_is_rejected(tmp_path):
    path = tmp_path / "missing.csv"
    columns = [column for column in PAYSIM_REQUIRED_COLUMNS if column != "isFraud"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
    with pytest.raises(PaySimSchemaError, match="isFraud"):
        validate_paysim_schema(path)


def test_canonical_mapping_and_label_preservation():
    row = _source_row(2, "C100", "M200", is_fraud=1, transaction_type="PAYMENT")
    transaction = map_paysim_row(
        {key: str(value) for key, value in row.items()},
        source_row_number=7,
        split=DataSplit.TEST,
    )

    assert transaction.transaction_id.startswith("paysim-0000000007-")
    assert transaction.timestamp.isoformat() == "2017-01-01T01:00:00+00:00"
    assert transaction.source_account_id == "C100"
    assert transaction.destination_account_id == "M200"
    assert transaction.merchant_id == "M200"
    assert transaction.transaction_type is TransactionType.PAYMENT
    assert transaction.channel is Channel.UNKNOWN
    assert transaction.currency == "XXX"
    assert transaction.label is FraudLabel.FRAUD
    assert transaction.attack_family is None
    assert transaction.is_synthetic is False
    assert transaction.split is DataSplit.TEST
    assert transaction.metadata["paysim.is_flagged_fraud"] == 1


def test_preparation_is_reproducible_with_fixed_seed(paysim_csv, tmp_path):
    first = prepare_paysim(
        paysim_csv,
        PaySimPreparationConfig(
            data_root=tmp_path / "run-one" / "data",
            seed=17,
            train_ratio=0.6,
            validation_ratio=0.2,
            test_ratio=0.2,
        ),
    )
    second = prepare_paysim(
        paysim_csv,
        PaySimPreparationConfig(
            data_root=tmp_path / "run-two" / "data",
            seed=17,
            train_ratio=0.6,
            validation_ratio=0.2,
            test_ratio=0.2,
        ),
    )

    assert first.output_dir.name == second.output_dir.name
    for artifact in ("train", "validation", "test", "quarantine"):
        assert first.artifacts[artifact].read_bytes() == second.artifacts[artifact].read_bytes()
    assert first.summary == second.summary


def test_temporal_mode_is_default_and_preserves_chronological_separation(paysim_csv, tmp_path):
    result = prepare_paysim(
        paysim_csv,
        PaySimPreparationConfig(
            data_root=tmp_path / "data",
            seed=99,
            train_ratio=0.6,
            validation_ratio=0.2,
            test_ratio=0.2,
        ),
    )
    split_transactions = {
        split: _read_transactions(result.artifacts[split])
        for split in ("train", "validation", "test")
    }

    transaction_ids = {
        split: {transaction.transaction_id for transaction in transactions}
        for split, transactions in split_transactions.items()
    }
    split_names = list(split_transactions)
    for index, left in enumerate(split_names):
        for right in split_names[index + 1 :]:
            assert transaction_ids[left].isdisjoint(transaction_ids[right])

    assert PaySimPreparationConfig().split_mode == "temporal"
    assert result.summary["splitting"]["mode"] == "temporal"
    assert result.summary["splitting"]["train_end_step"] == 6
    assert result.summary["splitting"]["validation_end_step"] == 8
    assert max(transaction.timestamp for transaction in split_transactions["train"]) < min(
        transaction.timestamp for transaction in split_transactions["validation"]
    )
    assert max(transaction.timestamp for transaction in split_transactions["validation"]) < min(
        transaction.timestamp for transaction in split_transactions["test"]
    )
    assert [transaction.split for transaction in split_transactions["train"]] == [
        DataSplit.TRAIN
    ] * 6


def test_temporal_mode_reports_overlap_without_quarantining_spanning_entities(paysim_csv, tmp_path):
    result = prepare_paysim(
        paysim_csv,
        PaySimPreparationConfig(
            data_root=tmp_path / "data",
            train_ratio=0.6,
            validation_ratio=0.2,
            test_ratio=0.2,
        ),
    )
    quarantined = _read_transactions(result.artifacts["quarantine"])

    assert quarantined == []
    assert result.summary["splitting"]["quarantine"] == {"count": 0, "percentage": 0.0}
    assert result.summary["splitting"]["entity_overlap"] == {
        "source_accounts": {
            "train_vs_validation": 0,
            "train_vs_test": 1,
            "validation_vs_test": 0,
        },
        "destination_accounts": {
            "train_vs_validation": 1,
            "train_vs_test": 0,
            "validation_vs_test": 0,
        },
    }


def test_entity_isolated_mode_quarantines_spanning_entities(paysim_csv, tmp_path):
    result = prepare_paysim(
        paysim_csv,
        PaySimPreparationConfig(
            data_root=tmp_path / "data",
            split_mode="entity_isolated",
            train_ratio=0.6,
            validation_ratio=0.2,
            test_ratio=0.2,
        ),
    )
    quarantined = _read_transactions(result.artifacts["quarantine"])

    assert result.summary["splitting"]["mode"] == "entity_isolated"
    assert len(quarantined) == 4
    assert {transaction.source_account_id for transaction in quarantined} >= {"C-CROSS"}
    assert all(transaction.split is DataSplit.UNASSIGNED for transaction in quarantined)
    assert all(transaction.metadata["preparation.exclusion_reasons"] for transaction in quarantined)
    assert result.summary["splitting"]["entity_overlap"] == {
        "source_accounts": {
            "train_vs_validation": 0,
            "train_vs_test": 0,
            "validation_vs_test": 0,
        },
        "destination_accounts": {
            "train_vs_validation": 0,
            "train_vs_test": 0,
            "validation_vs_test": 0,
        },
    }


def test_dataset_summary_statistics_are_complete(paysim_csv, tmp_path):
    result = prepare_paysim(
        paysim_csv,
        PaySimPreparationConfig(
            data_root=tmp_path / "data",
            train_ratio=0.6,
            validation_ratio=0.2,
            test_ratio=0.2,
        ),
    )
    source = result.summary["source_statistics"]
    splitting = result.summary["splitting"]

    assert source["total_transactions"] == 10
    assert source["legitimate_count"] == 7
    assert source["fraud_count"] == 3
    assert source["fraud_prevalence"] == pytest.approx(0.3)
    assert source["transaction_type_distribution"] == {"payment": 5, "transfer": 5}
    assert source["step_range"] == {"minimum": 1, "maximum": 10}
    assert source["entity_counts"] == {"source": 9, "destination": 9, "all": 18}
    assert splitting["split_sizes"] == {
        "train": 6,
        "validation": 2,
        "test": 2,
        "quarantine": 0,
    }
    assert splitting["split_statistics"]["train"] == {
        "transaction_count": 6,
        "legitimate_count": 5,
        "fraud_count": 1,
        "fraud_prevalence": pytest.approx(1 / 6),
        "transaction_type_distribution": {"payment": 3, "transfer": 3},
        "step_range": {"minimum": 1, "maximum": 6},
        "timestamp_range_utc": {
            "minimum": "2017-01-01T00:00:00+00:00",
            "maximum": "2017-01-01T05:00:00+00:00",
        },
    }
    assert json.loads(result.artifacts["summary"].read_text(encoding="utf-8")) == result.summary


def test_currency_default_and_override_are_explicit_and_deterministic(paysim_csv, tmp_path):
    neutral = prepare_paysim(
        paysim_csv,
        PaySimPreparationConfig(
            data_root=tmp_path / "neutral" / "data",
            train_ratio=0.6,
            validation_ratio=0.2,
            test_ratio=0.2,
        ),
    )
    override_one = prepare_paysim(
        paysim_csv,
        PaySimPreparationConfig(
            data_root=tmp_path / "override-one" / "data",
            currency="inr",
            train_ratio=0.6,
            validation_ratio=0.2,
            test_ratio=0.2,
        ),
    )
    override_two = prepare_paysim(
        paysim_csv,
        PaySimPreparationConfig(
            data_root=tmp_path / "override-two" / "data",
            currency="INR",
            train_ratio=0.6,
            validation_ratio=0.2,
            test_ratio=0.2,
        ),
    )

    assert neutral.summary["configuration"]["currency"] == {
        "value": "XXX",
        "basis": "neutral_default",
    }
    assert all(
        transaction.currency == "XXX"
        for transaction in _read_transactions(neutral.artifacts["train"])
    )
    assert override_one.summary["configuration"]["currency"] == {
        "value": "INR",
        "basis": "explicit_override",
    }
    assert override_one.output_dir.name == override_two.output_dir.name
    assert (
        override_one.artifacts["train"].read_bytes() == override_two.artifacts["train"].read_bytes()
    )
