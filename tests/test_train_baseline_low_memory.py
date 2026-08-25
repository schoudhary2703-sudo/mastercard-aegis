"""`--low-memory` must reproduce the in-memory pipeline's results exactly.

This is the end-to-end semantic-equivalence proof: same fixture, same seed,
run once through `_run_in_memory_pipeline` and once through
`_run_low_memory_pipeline`, and every reported metric must match.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from scripts.train_baseline_detector import (
    LOW_MEMORY_DEFAULT_NTHREAD,
    BaselinePipelineConfig,
    _is_valid_feature_artifact,
    _materialize_or_reuse,
    run_baseline_pipeline,
)

from aegis.features.streaming import materialize_split_features
from aegis.shared.contracts import Transaction
from aegis.shared.enums import DataSplit, FraudLabel, TransactionType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def processed_run_dir() -> Iterator[Path]:
    root = Path("data/interim") / f"low-memory-test-{uuid.uuid4().hex}" / "run"
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


@pytest.fixture
def output_dirs() -> Iterator[tuple[Path, Path]]:
    base = Path("data/interim") / f"low-memory-models-{uuid.uuid4().hex}"
    try:
        yield base / "in_memory", base / "low_memory"
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _make_split(n: int, day_offset: int, split: DataSplit) -> list[Transaction]:
    out = []
    for i in range(n):
        label = FraudLabel.FRAUD if i % 8 == 0 else FraudLabel.LEGITIMATE
        out.append(
            Transaction(
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
        )
    return out


def _write_jsonl(path: Path, transactions: list[Transaction]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for txn in transactions:
            fh.write(txn.to_json())
            fh.write("\n")


def test_low_memory_matches_in_memory_pipeline(processed_run_dir, output_dirs):
    _write_jsonl(processed_run_dir / "train.jsonl", _make_split(180, 0, DataSplit.TRAIN))
    _write_jsonl(processed_run_dir / "validation.jsonl", _make_split(50, 10, DataSplit.VALIDATION))
    _write_jsonl(processed_run_dir / "test.jsonl", _make_split(50, 20, DataSplit.TEST))

    in_memory_dir, low_memory_dir = output_dirs

    in_memory_result = run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_run_dir,
            output_dir=in_memory_dir,
            seed=321,
            num_boost_round=15,
            latency_sample_size=10,
            low_memory=False,
        )
    )
    low_memory_result = run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_run_dir,
            output_dir=low_memory_dir,
            seed=321,
            num_boost_round=15,
            latency_sample_size=10,
            low_memory=True,
            chunk_size=7,  # deliberately small to force many chunk boundaries
        )
    )

    assert low_memory_result.model_version == in_memory_result.model_version
    assert low_memory_result.train_size == in_memory_result.train_size
    assert low_memory_result.validation_size == in_memory_result.validation_size
    assert low_memory_result.test_size == in_memory_result.test_size
    assert low_memory_result.tuned_threshold == pytest.approx(in_memory_result.tuned_threshold)
    assert low_memory_result.scale_pos_weight == pytest.approx(in_memory_result.scale_pos_weight)

    in_memory_metrics = in_memory_result.test_evaluation.overall.model_dump()
    low_memory_metrics = low_memory_result.test_evaluation.overall.model_dump()
    # Latency is a wall-clock measurement, not a semantic value.
    in_memory_metrics.pop("threshold", None)
    low_memory_metrics.pop("threshold", None)
    assert low_memory_result.test_evaluation.overall.threshold == pytest.approx(
        in_memory_result.test_evaluation.overall.threshold
    )
    assert low_memory_metrics == in_memory_metrics

    in_memory_val_metrics = in_memory_result.validation_evaluation.overall.model_dump()
    low_memory_val_metrics = low_memory_result.validation_evaluation.overall.model_dump()
    assert low_memory_val_metrics == in_memory_val_metrics


def test_low_memory_writes_feature_artifacts_and_model(processed_run_dir, output_dirs):
    _write_jsonl(processed_run_dir / "train.jsonl", _make_split(60, 0, DataSplit.TRAIN))
    _write_jsonl(processed_run_dir / "validation.jsonl", _make_split(20, 10, DataSplit.VALIDATION))
    _write_jsonl(processed_run_dir / "test.jsonl", _make_split(20, 20, DataSplit.TEST))

    _, low_memory_dir = output_dirs
    result = run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_run_dir,
            output_dir=low_memory_dir,
            seed=7,
            num_boost_round=10,
            low_memory=True,
            chunk_size=5,
        )
    )

    assert (result.artifact_dir / "model.json").exists()
    assert (result.artifact_dir / "metadata.json").exists()
    assert (result.artifact_dir / "evaluation_validation.json").exists()
    assert (result.artifact_dir / "evaluation_test.json").exists()

    feature_dir = result.artifact_dir / "features"
    for split_name in ("train", "validation", "test"):
        split_dir = feature_dir / split_name
        assert (split_dir / "features.npy").exists()
        assert (split_dir / "labels.npy").exists()
        assert (split_dir / "transaction_ids.txt").exists()
        assert (split_dir / "schema.json").exists()


def test_low_memory_default_nthread_applied_when_unset(processed_run_dir, output_dirs):
    _write_jsonl(processed_run_dir / "train.jsonl", _make_split(40, 0, DataSplit.TRAIN))
    _write_jsonl(processed_run_dir / "validation.jsonl", _make_split(15, 10, DataSplit.VALIDATION))
    _write_jsonl(processed_run_dir / "test.jsonl", _make_split(15, 20, DataSplit.TEST))

    config = BaselinePipelineConfig(
        processed_dir=processed_run_dir,
        output_dir=output_dirs[1],
        seed=11,
        num_boost_round=8,
        low_memory=True,
        chunk_size=6,
    )
    # The CLI applies LOW_MEMORY_DEFAULT_NTHREAD when --nthread is omitted;
    # the config/pipeline layer itself leaves nthread=None alone (explicit is
    # better than a hidden default two layers down).
    assert config.nthread is None
    params = config.resolved_hyperparameters()
    assert "nthread" not in params

    explicit_config = BaselinePipelineConfig(
        processed_dir=processed_run_dir,
        output_dir=output_dirs[0],
        seed=11,
        num_boost_round=8,
        low_memory=True,
        chunk_size=6,
        nthread=LOW_MEMORY_DEFAULT_NTHREAD,
    )
    assert explicit_config.resolved_hyperparameters()["nthread"] == LOW_MEMORY_DEFAULT_NTHREAD
    run_baseline_pipeline(explicit_config)  # exercises the nthread-set path end-to-end


# --- checkpoint resume: the actual incident this repairs -------------------
def test_materialize_or_reuse_skips_a_complete_existing_artifact(processed_run_dir, output_dirs):
    _write_jsonl(processed_run_dir / "train.jsonl", _make_split(30, 0, DataSplit.TRAIN))
    source = processed_run_dir / "train.jsonl"
    target = output_dirs[0] / "train"

    first = materialize_split_features(source, target, chunk_size=5)
    features_mtime = (target / "features.npy").stat().st_mtime
    schema_mtime = (target / "schema.json").stat().st_mtime

    reused = _materialize_or_reuse(source, target, chunk_size=5, label="train")

    assert reused.row_count == first.row_count
    assert reused.feature_names == first.feature_names
    # Nothing was rewritten - same files, same mtimes, not just equal content.
    assert (target / "features.npy").stat().st_mtime == features_mtime
    assert (target / "schema.json").stat().st_mtime == schema_mtime


def test_materialize_or_reuse_rejects_an_incomplete_directory(processed_run_dir, output_dirs):
    target = output_dirs[0] / "train"
    target.mkdir(parents=True)
    (target / "features.npy").write_bytes(b"not a real npy file")  # partial/corrupt, no schema.json

    with pytest.raises(FileExistsError, match="not a complete, valid feature artifact"):
        _materialize_or_reuse(
            processed_run_dir / "train.jsonl", target, chunk_size=5, label="train"
        )


def test_is_valid_feature_artifact_false_for_missing_directory(output_dirs):
    assert _is_valid_feature_artifact(output_dirs[0] / "does-not-exist") is False


def test_resumed_pipeline_reuses_train_and_validation_but_redoes_test(
    processed_run_dir, output_dirs
):
    """Simulates exactly the production incident: train + validation feature
    materialization completed, but the process was stopped before test
    materialization ever started. Re-running must reuse the first two and
    only materialize test, ending with the same result a clean run would
    produce.
    """
    _write_jsonl(processed_run_dir / "train.jsonl", _make_split(80, 0, DataSplit.TRAIN))
    _write_jsonl(processed_run_dir / "validation.jsonl", _make_split(25, 10, DataSplit.VALIDATION))
    _write_jsonl(processed_run_dir / "test.jsonl", _make_split(25, 20, DataSplit.TEST))

    low_memory_dir = output_dirs[1]
    config = BaselinePipelineConfig(
        processed_dir=processed_run_dir,
        output_dir=low_memory_dir,
        seed=42,
        num_boost_round=10,
        low_memory=True,
        chunk_size=4,
    )
    feature_root = config.resolved_feature_artifact_dir()

    # Pre-materialize train and validation directly, as if an earlier,
    # interrupted run had already completed exactly those two stages.
    materialize_split_features(
        processed_run_dir / "train.jsonl", feature_root / "train", chunk_size=4
    )
    materialize_split_features(
        processed_run_dir / "validation.jsonl", feature_root / "validation", chunk_size=4
    )
    train_mtime = (feature_root / "train" / "schema.json").stat().st_mtime
    validation_mtime = (feature_root / "validation" / "schema.json").stat().st_mtime
    assert not (feature_root / "test").exists()

    result = run_baseline_pipeline(config)

    assert (feature_root / "test").exists()
    assert (feature_root / "train" / "schema.json").stat().st_mtime == train_mtime
    assert (feature_root / "validation" / "schema.json").stat().st_mtime == validation_mtime
    assert result.train_size == 80
    assert result.validation_size == 25
    assert result.test_size == 25

    # Cross-check against a clean run with no pre-existing artifacts.
    clean_result = run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_run_dir,
            output_dir=output_dirs[0],
            seed=42,
            num_boost_round=10,
            low_memory=True,
            chunk_size=4,
        )
    )
    assert result.tuned_threshold == pytest.approx(clean_result.tuned_threshold)
    assert (
        result.test_evaluation.overall.model_dump()
        == clean_result.test_evaluation.overall.model_dump()
    )
