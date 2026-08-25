"""Streaming feature materialization must exactly match the in-memory extractor.

`materialize_split_features` exists purely for memory bounds - it must never
produce a different feature value, a different row order, or a different
label than `TemporalBaselineFeatureExtractor.fit_transform` on the same
(filtered) input. Every test here is a semantic-equivalence proof, not a
smoke test.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from aegis.features.streaming import (
    FeatureArtifact,
    materialize_split_features,
    materialize_split_features_with_extra,
)
from aegis.features.temporal import TemporalBaselineFeatureExtractor, feature_columns
from aegis.shared.contracts import Transaction
from aegis.shared.enums import FraudLabel, TransactionType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def work_dir() -> Iterator[Path]:
    """Windows-sandbox-friendly scratch directory, matching tests/test_paysim.py."""
    path = (Path("data/interim") / f"streaming-test-{uuid.uuid4().hex}").resolve()
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _txn(i: int, **overrides: Any) -> Transaction:
    base: dict[str, Any] = {
        "transaction_id": f"t{i}",
        "timestamp": T0 + timedelta(minutes=i * 7),
        "source_account_id": f"src{i % 5}",
        "destination_account_id": f"dst{i % 3}",
        "amount": 80.0 + (i % 11) * 23.5,
        "transaction_type": TransactionType.TRANSFER,
        "source_balance_before": 1000.0,
        "source_balance_after": 900.0,
        "destination_balance_before": 200.0,
        "destination_balance_after": 300.0,
        "label": FraudLabel.FRAUD if i % 9 == 0 else FraudLabel.LEGITIMATE,
    }
    base.update(overrides)
    return Transaction(**base)


def _sequence(n: int, *, unknown_every: int | None = None) -> list[Transaction]:
    out = []
    for i in range(n):
        label = FraudLabel.UNKNOWN if unknown_every and i % unknown_every == 0 else None
        overrides = {"label": label} if label is not None else {}
        out.append(_txn(i, **overrides))
    return out


def _write_jsonl(path: Path, transactions: list[Transaction]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for txn in transactions:
            handle.write(txn.to_json())
            handle.write("\n")


def _labelled_only(transactions: list[Transaction]) -> list[Transaction]:
    return [t for t in transactions if t.label is not FraudLabel.UNKNOWN]


def _in_memory_frame(transactions: list[Transaction]):
    return TemporalBaselineFeatureExtractor().fit_transform(_labelled_only(transactions))


@pytest.mark.parametrize("chunk_size", [1, 3, 7, 1000])
def test_streaming_matches_in_memory_extraction(work_dir, chunk_size):
    txns = _sequence(40)
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)

    expected = _in_memory_frame(txns)
    artifact = materialize_split_features(
        source, work_dir / f"features-{chunk_size}", chunk_size=chunk_size
    )

    actual = artifact.load_features(mmap=False)
    np.testing.assert_allclose(actual, expected.to_numpy(dtype=np.float32), rtol=1e-5, atol=1e-6)


def test_chunk_size_does_not_change_feature_values(work_dir):
    txns = _sequence(53)
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)

    small = materialize_split_features(source, work_dir / "small", chunk_size=2)
    large = materialize_split_features(source, work_dir / "large", chunk_size=10_000)

    np.testing.assert_array_equal(small.load_features(mmap=False), large.load_features(mmap=False))
    np.testing.assert_array_equal(small.load_labels(), large.load_labels())
    assert small.load_transaction_ids() == large.load_transaction_ids()


def test_chunk_boundary_does_not_reset_causal_history(work_dir):
    """An account's second transaction, artificially split across a chunk boundary,
    must still see its first transaction's history."""
    txns = [
        _txn(0, source_account_id="acct-x", timestamp=T0, amount=100.0),
        _txn(1, source_account_id="other", timestamp=T0 + timedelta(minutes=1)),
        _txn(
            2,
            source_account_id="acct-x",
            timestamp=T0 + timedelta(minutes=30),
            amount=300.0,
        ),
    ]
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)

    # chunk_size=1 forces the boundary to fall exactly between every row,
    # including between the two acct-x transactions.
    artifact = materialize_split_features(source, work_dir / "chunked", chunk_size=1)
    features = artifact.load_features(mmap=False)
    names = feature_columns("temporal")

    count_before = features[2, names.index("temporal.source_txn_count_before")]
    avg_before = features[2, names.index("temporal.source_avg_amount_before")]
    seconds_since = features[2, names.index("temporal.seconds_since_source_previous_txn")]

    assert count_before == 1.0
    assert avg_before == 100.0
    assert seconds_since == pytest.approx(1800.0)  # 30 minutes after acct-x's first row


def test_chunk_boundary_does_not_reset_distinct_counterparty_history(work_dir):
    """Cross-family (Defender v3) columns must survive a chunk boundary too -
    same equivalence proof as `test_chunk_boundary_does_not_reset_causal_history`,
    for `source_distinct_destinations_before` specifically."""
    txns = [
        _txn(0, source_account_id="coordinator", destination_account_id="mule-1", timestamp=T0),
        _txn(1, source_account_id="other", timestamp=T0 + timedelta(minutes=1)),
        _txn(
            2,
            source_account_id="coordinator",
            destination_account_id="mule-2",
            timestamp=T0 + timedelta(minutes=2),
        ),
    ]
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)

    # chunk_size=1 forces the boundary between every row, including between
    # the coordinator's two transactions.
    artifact = materialize_split_features(source, work_dir / "chunked", chunk_size=1)
    features = artifact.load_features(mmap=False)
    names = feature_columns("temporal")

    distinct_before = features[2, names.index("temporal.source_distinct_destinations_before")]
    assert distinct_before == 1.0  # saw mule-1 in an earlier chunk


def test_row_order_and_label_alignment_preserved(work_dir):
    txns = _sequence(25)
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)

    artifact = materialize_split_features(source, work_dir / "features", chunk_size=4)
    ids = artifact.load_transaction_ids()
    labels = artifact.load_labels()

    expected_ids = [t.transaction_id for t in _labelled_only(txns)]
    expected_labels = [1 if t.is_fraud else 0 for t in _labelled_only(txns)]
    assert ids == expected_ids
    assert labels.tolist() == expected_labels


def test_unknown_labelled_rows_are_dropped_and_excluded_from_history(work_dir):
    txns = _sequence(30, unknown_every=5)
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)

    artifact = materialize_split_features(source, work_dir / "features", chunk_size=6)
    assert artifact.row_count == len(_labelled_only(txns))
    written_ids = set(artifact.load_transaction_ids())
    assert all(t.label is not FraudLabel.UNKNOWN for t in txns if t.transaction_id in written_ids)

    expected = _in_memory_frame(txns)  # already filters UNKNOWN via _labelled_only
    actual = artifact.load_features(mmap=False)
    np.testing.assert_allclose(actual, expected.to_numpy(dtype=np.float32), rtol=1e-5, atol=1e-6)


def test_forbidden_fields_never_appear_in_schema(work_dir):
    txns = _sequence(10)
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)
    artifact = materialize_split_features(source, work_dir / "features", chunk_size=3)

    forbidden = (
        "label",
        "is_fraud",
        "attack_family",
        "blueprint_id",
        "scenario_id",
        "balance_after",
    )
    for name in artifact.feature_names:
        for token in forbidden:
            assert token not in name


def test_out_of_order_timestamps_raise(work_dir):
    txns = [
        _txn(0, timestamp=T0 + timedelta(minutes=10)),
        _txn(1, timestamp=T0),  # goes backwards
    ]
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)

    with pytest.raises(ValueError, match="not chronologically ordered"):
        materialize_split_features(source, work_dir / "features", chunk_size=10)


def test_refuses_to_overwrite_existing_artifact(work_dir):
    txns = _sequence(5)
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)
    materialize_split_features(source, work_dir / "features", chunk_size=2)

    with pytest.raises(FileExistsError):
        materialize_split_features(source, work_dir / "features", chunk_size=2)


def test_schema_file_records_metadata(work_dir):
    txns = _sequence(12)
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)
    artifact = materialize_split_features(source, work_dir / "features", chunk_size=5)

    schema = FeatureArtifact.load_schema(artifact.directory)
    assert schema["row_count"] == artifact.row_count
    assert schema["feature_names"] == artifact.feature_names
    assert schema["chunk_size"] == 5
    assert schema["dtype"] == "float32"


def test_invalid_chunk_size_rejected(work_dir):
    txns = _sequence(3)
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        materialize_split_features(source, work_dir / "features", chunk_size=0)


def test_materialize_with_extra_matches_concatenated_in_memory(work_dir):
    """`materialize_split_features_with_extra` must equal the in-memory extractor
    run over base+extra concatenated - this is the hard-positive hardening path,
    so it needs the same equivalence proof `materialize_split_features` has."""
    base_txns = _sequence(20)
    extra_txns = [_txn(100 + i, timestamp=T0 + timedelta(days=1, minutes=i * 7)) for i in range(5)]
    base_source = work_dir / "base.jsonl"
    extra_source = work_dir / "extra.jsonl"
    _write_jsonl(base_source, base_txns)
    _write_jsonl(extra_source, extra_txns)

    expected = _in_memory_frame(base_txns + extra_txns)
    artifact = materialize_split_features_with_extra(
        base_source, [extra_source], work_dir / "features", chunk_size=3
    )

    actual = artifact.load_features(mmap=False)
    np.testing.assert_allclose(actual, expected.to_numpy(dtype=np.float32), rtol=1e-5, atol=1e-6)
    assert artifact.row_count == len(_labelled_only(base_txns)) + len(_labelled_only(extra_txns))
    expected_ids = [t.transaction_id for t in _labelled_only(base_txns + extra_txns)]
    assert artifact.load_transaction_ids() == expected_ids


def test_materialize_with_extra_chains_multiple_sources(work_dir):
    base_txns = _sequence(10)
    extra_a = [_txn(200 + i, timestamp=T0 + timedelta(days=1, minutes=i * 5)) for i in range(4)]
    extra_b = [_txn(300 + i, timestamp=T0 + timedelta(days=2, minutes=i * 5)) for i in range(4)]
    base_source = work_dir / "base.jsonl"
    extra_a_source = work_dir / "extra_a.jsonl"
    extra_b_source = work_dir / "extra_b.jsonl"
    _write_jsonl(base_source, base_txns)
    _write_jsonl(extra_a_source, extra_a)
    _write_jsonl(extra_b_source, extra_b)

    expected = _in_memory_frame(base_txns + extra_a + extra_b)
    artifact = materialize_split_features_with_extra(
        base_source, [extra_a_source, extra_b_source], work_dir / "features", chunk_size=3
    )

    actual = artifact.load_features(mmap=False)
    np.testing.assert_allclose(actual, expected.to_numpy(dtype=np.float32), rtol=1e-5, atol=1e-6)


def test_materialize_with_extra_enforces_cross_source_chronology(work_dir):
    """An extra source dated *before* the base split's last row must raise, not
    silently compute wrong causal history across the join."""
    base_txns = [_txn(0, timestamp=T0 + timedelta(days=1))]
    extra_txns = [_txn(1, timestamp=T0)]  # earlier than the base split's only row
    base_source = work_dir / "base.jsonl"
    extra_source = work_dir / "extra.jsonl"
    _write_jsonl(base_source, base_txns)
    _write_jsonl(extra_source, extra_txns)

    with pytest.raises(ValueError, match="not chronologically ordered"):
        materialize_split_features_with_extra(
            base_source, [extra_source], work_dir / "features", chunk_size=10
        )


def test_no_temp_directory_survives_a_failed_materialization(work_dir):
    txns = [
        _txn(0, timestamp=T0 + timedelta(minutes=10)),
        _txn(1, timestamp=T0),
    ]
    source = work_dir / "split.jsonl"
    _write_jsonl(source, txns)

    destination = work_dir / "features"
    with pytest.raises(ValueError):
        materialize_split_features(source, destination, chunk_size=10)

    assert not destination.exists()
    leftovers = list(work_dir.glob(".features.tmp-*"))
    assert leftovers == []
