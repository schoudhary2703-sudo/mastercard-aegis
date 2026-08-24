"""End-to-end baseline pipeline on small fixtures - no real PaySim data required.

Per the task brief: "If no real processed PaySim dataset exists locally, do
not fabricate production results. Use small fixtures for tests." These
fixtures are synthetic and only prove the pipeline wiring is correct; they
are not evidence of real-world detector quality.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from scripts.train_baseline_detector import BaselinePipelineConfig, run_baseline_pipeline

from aegis.shared.contracts import Transaction
from aegis.shared.enums import DataSplit, FraudLabel, TransactionType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def processed_run_dir() -> Iterator[Path]:
    root = Path("data/interim") / f"pipeline-test-{uuid.uuid4().hex}" / "run"
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


@pytest.fixture
def output_dir() -> Iterator[Path]:
    path = Path("data/interim") / f"pipeline-models-{uuid.uuid4().hex}"
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _make_split(
    n: int, day_offset: int, split: DataSplit, *, unknown_every: int | None = None
) -> list[Transaction]:
    out = []
    for i in range(n):
        if unknown_every and i % unknown_every == 0:
            label = FraudLabel.UNKNOWN
        elif i % 8 == 0:
            label = FraudLabel.FRAUD
        else:
            label = FraudLabel.LEGITIMATE
        out.append(
            Transaction(
                transaction_id=f"{split.value}-{i}",
                timestamp=T0 + timedelta(days=day_offset, minutes=i * 6),
                source_account_id=f"src{i % 8}",
                destination_account_id=f"dst{i % 5}",
                amount=90.0 + (i % 15) * 42.0,
                transaction_type=TransactionType.TRANSFER,
                source_balance_before=1500.0,
                source_balance_after=1400.0,
                destination_balance_before=300.0,
                destination_balance_after=400.0,
                label=label,
                split=split,
                metadata={"isFlaggedFraud": 0, "step": i},
            )
        )
    return out


def _write_jsonl(path: Path, transactions: list[Transaction]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for txn in transactions:
            fh.write(txn.to_json())
            fh.write("\n")


def test_pipeline_trains_evaluates_and_saves(processed_run_dir, output_dir):
    _write_jsonl(
        processed_run_dir / "train.jsonl", _make_split(200, 0, DataSplit.TRAIN, unknown_every=17)
    )
    _write_jsonl(processed_run_dir / "validation.jsonl", _make_split(60, 10, DataSplit.VALIDATION))
    _write_jsonl(processed_run_dir / "test.jsonl", _make_split(60, 20, DataSplit.TEST))

    config = BaselinePipelineConfig(
        processed_dir=processed_run_dir,
        output_dir=output_dir,
        seed=123,
        num_boost_round=15,
        latency_sample_size=10,
    )
    result = run_baseline_pipeline(config)

    assert result.model_version == "xgboost-baseline-123"
    assert result.train_size == 200 - len(range(0, 200, 17))  # UNKNOWN rows dropped
    assert result.validation_size == 60
    assert result.test_size == 60
    assert 0.0 <= result.tuned_threshold <= 1.0
    assert result.scale_pos_weight > 1.0  # fraud is the minority class

    assert result.validation_evaluation.split is DataSplit.VALIDATION
    assert result.test_evaluation.split is DataSplit.TEST
    assert result.validation_evaluation.model_version == result.model_version
    assert result.test_evaluation.model_version == result.model_version

    artifact_dir = result.artifact_dir
    assert (artifact_dir / "model.json").exists()
    assert (artifact_dir / "metadata.json").exists()
    assert (artifact_dir / "evaluation_validation.json").exists()
    assert (artifact_dir / "evaluation_test.json").exists()


def test_pipeline_is_reproducible_for_a_fixed_seed(processed_run_dir, output_dir):
    _write_jsonl(processed_run_dir / "train.jsonl", _make_split(150, 0, DataSplit.TRAIN))
    _write_jsonl(processed_run_dir / "validation.jsonl", _make_split(40, 10, DataSplit.VALIDATION))
    _write_jsonl(processed_run_dir / "test.jsonl", _make_split(40, 20, DataSplit.TEST))

    config = BaselinePipelineConfig(
        processed_dir=processed_run_dir, output_dir=output_dir, seed=999, num_boost_round=12
    )
    first = run_baseline_pipeline(config)
    second = run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_run_dir,
            output_dir=output_dir / "rerun",
            seed=999,
            num_boost_round=12,
        )
    )

    assert first.tuned_threshold == pytest.approx(second.tuned_threshold)
    assert first.test_evaluation.overall.model_dump() == second.test_evaluation.overall.model_dump()


def test_pipeline_never_tunes_on_test(processed_run_dir, output_dir):
    """Test evaluation notes must say the threshold came from validation, not test."""
    _write_jsonl(processed_run_dir / "train.jsonl", _make_split(120, 0, DataSplit.TRAIN))
    _write_jsonl(processed_run_dir / "validation.jsonl", _make_split(30, 10, DataSplit.VALIDATION))
    _write_jsonl(processed_run_dir / "test.jsonl", _make_split(30, 20, DataSplit.TEST))

    result = run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_run_dir, output_dir=output_dir, seed=5, num_boost_round=10
        )
    )
    validation_threshold = result.validation_evaluation.overall.threshold
    test_threshold = result.test_evaluation.overall.threshold
    assert validation_threshold == test_threshold
    assert "validation" in result.test_evaluation.notes.lower()
