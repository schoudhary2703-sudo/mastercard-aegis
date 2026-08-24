"""`TemporalBaselineFeatureExtractor` leakage-safety and determinism."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from aegis.features import TemporalBaselineFeatureExtractor
from aegis.shared.contracts import Transaction
from aegis.shared.enums import AttackFamily, FraudLabel, TransactionType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

_FORBIDDEN_TOKENS = (
    "label",
    "is_fraud",
    "attack_family",
    "blueprint_id",
    "scenario_id",
    "isFlaggedFraud",
    "balance_after",
    "balance_delta",
)


def _txn(**overrides: Any) -> Transaction:
    base: dict[str, Any] = {
        "transaction_id": "t0",
        "timestamp": T0,
        "source_account_id": "src-1",
        "destination_account_id": "dst-1",
        "amount": 100.0,
        "transaction_type": TransactionType.TRANSFER,
        "source_balance_before": 500.0,
        "source_balance_after": 400.0,
        "destination_balance_before": 50.0,
        "destination_balance_after": 150.0,
    }
    base.update(overrides)
    return Transaction(**base)


def _sequence(
    n: int, *, minutes_apart: int = 10, fraud_every: int | None = None
) -> list[Transaction]:
    out = []
    for i in range(n):
        out.append(
            _txn(
                transaction_id=f"t{i}",
                timestamp=T0 + timedelta(minutes=i * minutes_apart),
                amount=100.0 + i * 5,
                label=(
                    FraudLabel.FRAUD
                    if fraud_every and i % fraud_every == 0
                    else FraudLabel.LEGITIMATE
                ),
            )
        )
    return out


# --- column contract ---------------------------------------------------
def test_feature_names_available_after_fit():
    extractor = TemporalBaselineFeatureExtractor()
    extractor.fit(_sequence(3))
    assert extractor.is_fitted is True
    assert all(name.startswith("temporal.") for name in extractor.feature_names)
    assert len(extractor.feature_names) == len(set(extractor.feature_names))


def test_transform_before_fit_raises():
    with pytest.raises(RuntimeError, match="before fit"):
        TemporalBaselineFeatureExtractor().transform(_sequence(2))


def test_transform_row_count_and_order_matches_input():
    txns = _sequence(10)
    extractor = TemporalBaselineFeatureExtractor().fit(txns)
    frame = extractor.transform(txns)
    assert len(frame) == 10
    assert list(frame.columns) == extractor.feature_names
    # First row must see amount == its own amount (order-in-input, not sorted-by-time).
    assert frame.iloc[0]["temporal.amount"] == txns[0].amount


# --- leakage safety ------------------------------------------------------
def test_forbidden_columns_never_appear():
    extractor = TemporalBaselineFeatureExtractor()
    frame = extractor.fit_transform(_sequence(5, fraud_every=2))
    for column in frame.columns:
        for token in _FORBIDDEN_TOKENS:
            assert token not in column


def test_output_is_identical_regardless_of_label_or_metadata():
    """Changing only ground truth / provenance must not change any feature value."""
    plain = _sequence(6, fraud_every=None)
    tagged = [
        t.model_copy(
            update={
                "label": FraudLabel.FRAUD,
                "attack_family": AttackFamily.MULE_NETWORK_STRUCTURING,
                "is_synthetic": True,
                "blueprint_id": "bp-x",
                "scenario_id": "scn-x",
                "metadata": {"isFlaggedFraud": 1, "row_number": 999},
            }
        )
        for t in plain
    ]

    extractor = TemporalBaselineFeatureExtractor()
    frame_plain = extractor.fit_transform(plain)
    frame_tagged = TemporalBaselineFeatureExtractor().fit_transform(tagged)
    pd_testing_equal = frame_plain.equals(frame_tagged)
    assert pd_testing_equal


def test_post_transaction_balance_fields_never_affect_features():
    """Changing only post-transaction balances must not change any feature value.

    `source_balance_after` / `destination_balance_after` are outcomes of
    executing the transaction - not available to a real-time authorization
    decision - so no emitted feature may depend on them.
    """
    plain = _sequence(6, fraud_every=None)
    mutated = [
        t.model_copy(
            update={
                "source_balance_after": 9_999_999.0,
                "destination_balance_after": -9_999_999.0,
            }
        )
        for t in plain
    ]

    frame_plain = TemporalBaselineFeatureExtractor().fit_transform(plain)
    frame_mutated = TemporalBaselineFeatureExtractor().fit_transform(mutated)
    assert frame_plain.equals(frame_mutated)


def test_post_transaction_balance_deltas_are_not_emitted():
    """Regression guard: the removed post-transaction delta features must stay removed."""
    extractor = TemporalBaselineFeatureExtractor().fit(_sequence(1))
    assert "temporal.source_balance_delta" not in extractor.feature_names
    assert "temporal.destination_balance_delta" not in extractor.feature_names
    # Pre-transaction balances are current-request-known and may remain.
    assert "temporal.source_balance_before" in extractor.feature_names
    assert "temporal.destination_balance_before" in extractor.feature_names


def test_features_use_only_strictly_earlier_events():
    """A late-arriving huge transaction must not affect an earlier row's history features."""
    txns = _sequence(4)
    baseline = TemporalBaselineFeatureExtractor().fit_transform(txns)

    mutated = list(txns)
    mutated[-1] = mutated[-1].model_copy(update={"amount": 999_999.0})
    mutated_frame = TemporalBaselineFeatureExtractor().fit_transform(mutated)

    # Every row except the mutated last one must be unaffected by its huge amount.
    import pandas as pd

    for col in baseline.columns:
        if col == "temporal.amount":
            continue
        pd.testing.assert_series_equal(
            baseline[col].iloc[:-1], mutated_frame[col].iloc[:-1], check_names=False
        )


# --- determinism -----------------------------------------------------------
def test_transform_is_deterministic():
    txns = _sequence(15, fraud_every=4)
    extractor = TemporalBaselineFeatureExtractor().fit(txns)
    first = extractor.transform(txns)
    second = extractor.transform(txns)
    assert first.equals(second)


# --- feature semantics -----------------------------------------------------
def test_first_transaction_for_an_account_has_no_history():
    txns = [_txn(transaction_id="only-one", source_account_id="fresh-account")]
    frame = TemporalBaselineFeatureExtractor().fit_transform(txns)
    row = frame.iloc[0]
    assert row["temporal.source_txn_count_before"] == 0.0
    assert row["temporal.amount_deviation_from_source_history"] == 0.0
    import math

    assert math.isnan(row["temporal.seconds_since_source_previous_txn"])


def test_repeat_account_accumulates_history():
    txns = [
        _txn(transaction_id="a", source_account_id="acct-x", timestamp=T0, amount=100.0),
        _txn(
            transaction_id="b",
            source_account_id="acct-x",
            timestamp=T0 + timedelta(minutes=30),
            amount=300.0,
        ),
    ]
    frame = TemporalBaselineFeatureExtractor().fit_transform(txns)
    assert frame.iloc[1]["temporal.source_txn_count_before"] == 1.0
    assert frame.iloc[1]["temporal.source_avg_amount_before"] == 100.0
    assert frame.iloc[1]["temporal.seconds_since_source_previous_txn"] == 1800.0


def test_velocity_window_expires_after_one_hour():
    txns = [
        _txn(transaction_id="a", source_account_id="acct-y", timestamp=T0),
        _txn(
            transaction_id="b",
            source_account_id="acct-y",
            timestamp=T0 + timedelta(hours=2),
        ),
    ]
    frame = TemporalBaselineFeatureExtractor().fit_transform(txns)
    assert frame.iloc[1]["temporal.source_velocity_1h"] == 0.0


def test_no_destination_zeroes_destination_features():
    txns = [_txn(transaction_id="cashout", destination_account_id=None)]
    frame = TemporalBaselineFeatureExtractor().fit_transform(txns)
    row = frame.iloc[0]
    assert row["temporal.has_destination"] == 0.0
    assert row["temporal.destination_txn_count_before"] == 0.0
    assert row["temporal.destination_velocity_1h"] == 0.0


def test_transaction_type_one_hot_is_exclusive():
    txns = [_txn(transaction_type=TransactionType.CASH_OUT)]
    frame = TemporalBaselineFeatureExtractor().fit_transform(txns)
    type_columns = [c for c in frame.columns if c.startswith("temporal.type_")]
    row = frame.iloc[0]
    assert row["temporal.type_cash_out"] == 1.0
    assert sum(row[c] for c in type_columns) == 1.0
