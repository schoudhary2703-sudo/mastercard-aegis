"""Promotion of prior Red-Team false negatives into training-only hard positives.

Covers `docs/EVALUATION_RULES.md` SS2/SS3 directly: re-stamping, provenance
preservation, ground-truth-never-changes, duplicate rejection, and the
validation-split/test-split overlap check that makes "this never leaked into
an evaluation set" a verified fact rather than an assumption.
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

from aegis.defend.hard_positives import (
    HardPositiveSource,
    HardPositiveValidationError,
    assert_no_duplicate_transaction_ids,
    assert_no_id_overlap_with_jsonl,
    promote_hard_positives,
    write_hard_positive_artifact,
)
from aegis.shared.contracts import Transaction
from aegis.shared.enums import AttackFamily, DataSplit, FraudLabel, TransactionType

T0 = datetime(2026, 2, 1, tzinfo=timezone.utc)


@pytest.fixture
def work_dir() -> Iterator[Path]:
    path = (Path("data/interim") / f"hard-positives-test-{uuid.uuid4().hex}").resolve()
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _warmup_txn(i: int, scenario_id: str, **overrides: Any) -> Transaction:
    base: dict[str, Any] = {
        "transaction_id": f"{scenario_id}-warmup-{i:03d}",
        "timestamp": T0 + timedelta(days=i),
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


def _fraud_txn(i: int, scenario_id: str, *, warmup_count: int, **overrides: Any) -> Transaction:
    base: dict[str, Any] = {
        "transaction_id": f"{scenario_id}-bustout-{i:03d}",
        "timestamp": T0 + timedelta(days=warmup_count + i),
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


def _scenario(scenario_id: str, *, warmup: int = 3, fraud: int = 2) -> list[Transaction]:
    rows = [_warmup_txn(i, scenario_id) for i in range(warmup)]
    rows.extend(_fraud_txn(i, scenario_id, warmup_count=warmup) for i in range(fraud))
    return rows


def _write_jsonl(path: Path, transactions: list[Transaction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for txn in transactions:
            handle.write(txn.to_json())
            handle.write("\n")


def _write_source(work_dir: Path, name: str, rows: list[Transaction]) -> HardPositiveSource:
    artifact_dir = work_dir / name
    _write_jsonl(artifact_dir / "transactions.jsonl", rows)
    return HardPositiveSource(artifact_dir=artifact_dir, source_round=name)


def test_promotion_restamps_split_and_preserves_ground_truth(work_dir):
    rows = _scenario("bustout-a")
    source = _write_source(work_dir, "round-0", rows)

    promotion = promote_hard_positives([source])

    assert len(promotion.transactions) == len(rows)
    assert promotion.fraud_count == 2
    for txn in promotion.transactions:
        assert txn.split is DataSplit.TRAIN
    original_by_id = {t.transaction_id: t for t in rows}
    for txn in promotion.transactions:
        original = original_by_id[txn.transaction_id]
        assert txn.label == original.label  # ground truth unchanged, "regardless of prediction"
        assert txn.attack_family == original.attack_family
        assert txn.blueprint_id == original.blueprint_id
        assert txn.scenario_id == original.scenario_id
        assert txn.generation == original.generation


def test_promotion_stamps_provenance_metadata(work_dir):
    rows = _scenario("bustout-b")
    source = _write_source(work_dir, "adaptive-round-1", rows)

    promotion = promote_hard_positives([source])

    for txn in promotion.transactions:
        hardening = txn.metadata["hardening"]
        assert hardening["source_round"] == "adaptive-round-1"
        assert hardening["source_artifact_dir"] == str(source.artifact_dir)
        assert "promoted_at" in hardening

    assert len(promotion.provenance) == 1
    entry = promotion.provenance[0]
    assert entry.source_round == "adaptive-round-1"
    assert entry.scenario_id == "bustout-b"
    assert entry.warmup_transaction_count == 3
    assert entry.fraud_transaction_count == 2
    assert set(entry.fraud_transaction_ids) == {t.transaction_id for t in rows if t.is_fraud}


def test_promotion_combines_and_sorts_multiple_sources(work_dir):
    round0 = _scenario("bustout-early")
    round1 = [
        t.model_copy(update={"timestamp": t.timestamp + timedelta(days=30)})
        for t in _scenario("bustout-late")
    ]
    source0 = _write_source(work_dir, "round-0", round0)
    source1 = _write_source(work_dir, "adaptive-round-1", round1)

    promotion = promote_hard_positives([source0, source1])

    assert len(promotion.transactions) == len(round0) + len(round1)
    timestamps = [t.timestamp for t in promotion.transactions]
    assert timestamps == sorted(timestamps)
    scenario_ids = {p.scenario_id for p in promotion.provenance}
    assert scenario_ids == {"bustout-early", "bustout-late"}


def test_promotion_rejects_scenario_with_no_fraud_rows(work_dir):
    rows = [_warmup_txn(i, "bustout-nofrraud") for i in range(3)]
    source = _write_source(work_dir, "round-0", rows)

    with pytest.raises(HardPositiveValidationError, match="no fraud rows"):
        promote_hard_positives([source])


def test_promotion_rejects_unknown_labels(work_dir):
    rows = _scenario("bustout-unk")
    rows[0] = rows[0].model_copy(update={"label": FraudLabel.UNKNOWN})
    source = _write_source(work_dir, "round-0", rows)

    with pytest.raises(HardPositiveValidationError, match="unlabelled"):
        promote_hard_positives([source])


def test_promotion_rejects_fraud_row_missing_attack_provenance(work_dir):
    rows = _scenario("bustout-noprov")
    # Fraud row with attack_family stripped - contract still allows this since
    # `_check_label_consistency` only forbids attack_family+LEGITIMATE, not a
    # missing attack_family on a FRAUD row.
    stripped = rows[-1].model_copy(update={"attack_family": None, "blueprint_id": None})
    rows[-1] = stripped
    source = _write_source(work_dir, "round-0", rows)

    with pytest.raises(HardPositiveValidationError, match="provenance"):
        promote_hard_positives([source])


def test_promotion_rejects_duplicate_ids_across_sources(work_dir):
    rows = _scenario("bustout-dup")
    source0 = _write_source(work_dir, "round-0", rows)
    source1 = _write_source(work_dir, "adaptive-round-1", rows)  # same IDs, reused verbatim

    with pytest.raises(HardPositiveValidationError, match="duplicate transaction_id"):
        promote_hard_positives([source0, source1])


def test_assert_no_duplicate_transaction_ids_raises_on_duplicate():
    rows = _scenario("bustout-dupcheck")
    with pytest.raises(HardPositiveValidationError, match="duplicate transaction_id"):
        assert_no_duplicate_transaction_ids([*rows, rows[0]])


def test_assert_no_duplicate_transaction_ids_passes_when_unique():
    rows = _scenario("bustout-uniquecheck")
    assert_no_duplicate_transaction_ids(rows)  # must not raise


def test_overlap_check_detects_a_shared_transaction_id(work_dir):
    rows = _scenario("bustout-overlap")
    validation_path = work_dir / "validation.jsonl"
    # validation.jsonl happens to contain one of the same IDs we're about to promote.
    _write_jsonl(validation_path, [rows[0]])
    candidate_ids = {t.transaction_id for t in rows}

    with pytest.raises(HardPositiveValidationError, match="already present in validation"):
        assert_no_id_overlap_with_jsonl(candidate_ids, validation_path, label="validation")


def test_overlap_check_passes_when_disjoint(work_dir):
    rows = _scenario("bustout-disjoint")
    other_rows = _scenario("bustout-other")
    validation_path = work_dir / "validation.jsonl"
    _write_jsonl(validation_path, other_rows)
    candidate_ids = {t.transaction_id for t in rows}

    assert_no_id_overlap_with_jsonl(candidate_ids, validation_path, label="validation")  # no raise


def test_overlap_check_is_a_noop_for_empty_candidates(work_dir):
    validation_path = work_dir / "validation.jsonl"
    _write_jsonl(validation_path, _scenario("bustout-x"))
    assert_no_id_overlap_with_jsonl(set(), validation_path, label="validation")  # no raise


def test_write_hard_positive_artifact_writes_jsonl_and_provenance(work_dir):
    rows = _scenario("bustout-write")
    source = _write_source(work_dir, "round-0", rows)
    promotion = promote_hard_positives([source])

    artifact = write_hard_positive_artifact(promotion, work_dir / "output")

    assert artifact.row_count == len(rows)
    assert artifact.fraud_count == 2
    written_lines = artifact.jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(written_lines) == len(rows)
    for line in written_lines:
        restored = Transaction.model_validate_json(line)
        assert restored.split is DataSplit.TRAIN

    manifest = json.loads(artifact.provenance_path.read_text(encoding="utf-8"))
    assert manifest["row_count"] == len(rows)
    assert manifest["fraud_count"] == 2
    assert len(manifest["scenarios"]) == 1
    assert manifest["scenarios"][0]["source_round"] == "round-0"


def test_write_hard_positive_artifact_refuses_to_overwrite(work_dir):
    rows = _scenario("bustout-overwrite")
    source = _write_source(work_dir, "round-0", rows)
    promotion = promote_hard_positives([source])

    write_hard_positive_artifact(promotion, work_dir / "output")
    with pytest.raises(FileExistsError):
        write_hard_positive_artifact(promotion, work_dir / "output")


def test_promotion_requires_at_least_one_source():
    with pytest.raises(HardPositiveValidationError, match="at least one"):
        promote_hard_positives([])
