"""`TemporalBaselineFeatureExtractor` - point-in-time-safe baseline features.

Every feature is computed from a transaction's own fields, or from a running
per-account aggregate built by a single **causal** pass over exactly the rows
passed to `transform`, ordered by `timestamp`. A row's aggregates reflect only
strictly earlier rows in that same call; state updates happen *after* a row's
features are recorded, never before.

Deliberate simplification: running per-account state does **not** carry over
between separate `transform` calls (e.g. from a `train` call into a later
`validation` call). This keeps the extractor a pure function of its input -
simple to test and unambiguously leakage-safe - at the cost of a "cold start"
at the beginning of each split for accounts that also appear earlier in time
in a different split. See `docs/BASELINE_DETECTOR.md` for the trade-off.

Never read: `label`, `attack_family`, `blueprint_id`, `scenario_id`,
`is_synthetic`, `generation`, or `metadata` (where PaySim's `isFlaggedFraud`
lives as provenance). Reading any of these would be target leakage.

Decision-time feature policy: every emitted feature must be computable from
(a) the current transaction's request-time fields, or (b) history strictly
earlier than it. `source_balance_after` / `destination_balance_after` are
*post*-transaction outcomes - the balance the ledger settles into once the
transfer executes - and are therefore never read here, even though the
canonical `Transaction` contract carries them (they exist for provenance and
downstream analysis, not for a real-time authorization decision). See
"Decision-time feature policy" in `docs/BASELINE_DETECTOR.md` for the full
per-feature audit.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

import pandas as pd

from aegis.features.base import BaseFeatureExtractor
from aegis.shared.contracts import Transaction
from aegis.shared.enums import TransactionType

_VELOCITY_WINDOW = timedelta(hours=1)
_KNOWN_TYPES: list[str] = [member.value for member in TransactionType]
"""Fixed, schema-known vocabulary - not learned from data, so one-hot column
order is stable no matter which types appear in a given split."""


class TemporalBaselineFeatureExtractor(BaseFeatureExtractor):
    """Baseline per-transaction and per-account-history features."""

    namespace = "temporal"
    version = "0.1.0"

    def fit(
        self, transactions: Sequence[Transaction], meta: dict[str, Any] | None = None
    ) -> TemporalBaselineFeatureExtractor:
        self._feature_names = self._column_order()
        self._is_fitted = True
        return self

    def transform(self, transactions: Sequence[Transaction]) -> pd.DataFrame:
        if not self._is_fitted:
            msg = f"{type(self).__name__}.transform called before fit"
            raise RuntimeError(msg)

        rows = self._compute_rows(transactions)
        ordered = [rows[i] for i in range(len(transactions))]
        return pd.DataFrame(ordered, columns=self._feature_names)

    def _column_order(self) -> list[str]:
        ns = self.namespace
        base = [
            f"{ns}.amount",
            f"{ns}.hour_of_day",
            f"{ns}.source_balance_before",
            f"{ns}.destination_balance_before",
            f"{ns}.has_destination",
            f"{ns}.source_txn_count_before",
            f"{ns}.destination_txn_count_before",
            f"{ns}.source_velocity_1h",
            f"{ns}.destination_velocity_1h",
            f"{ns}.source_avg_amount_before",
            f"{ns}.amount_deviation_from_source_history",
            f"{ns}.seconds_since_source_previous_txn",
            f"{ns}.seconds_since_destination_previous_txn",
        ]
        base += [f"{ns}.type_{value}" for value in _KNOWN_TYPES]
        return base

    def _compute_rows(self, transactions: Sequence[Transaction]) -> dict[int, dict[str, float]]:
        ns = self.namespace
        # Stable causal order: timestamp, then original position as a
        # deterministic tie-break for same-instant rows (PaySim's hourly
        # `step` resolution means many rows legitimately share one timestamp).
        order = sorted(range(len(transactions)), key=lambda i: (transactions[i].timestamp, i))

        src_count: dict[str, int] = defaultdict(int)
        src_sum: dict[str, float] = defaultdict(float)
        src_sumsq: dict[str, float] = defaultdict(float)
        src_last_ts: dict[str, Any] = {}
        src_recent: dict[str, deque[Any]] = defaultdict(deque)
        dst_count: dict[str, int] = defaultdict(int)
        dst_last_ts: dict[str, Any] = {}
        dst_recent: dict[str, deque[Any]] = defaultdict(deque)

        rows: dict[int, dict[str, float]] = {}

        for i in order:
            txn = transactions[i]
            src = txn.source_account_id
            dst = txn.destination_account_id

            row: dict[str, float] = {
                f"{ns}.amount": float(txn.amount),
                f"{ns}.hour_of_day": float(txn.timestamp.hour),
                # Pre-transaction balances only. `*_balance_after` is a
                # post-transaction outcome and must never appear here - see
                # the decision-time feature policy in the module docstring.
                f"{ns}.source_balance_before": _optional(txn.source_balance_before),
                f"{ns}.destination_balance_before": _optional(txn.destination_balance_before),
                f"{ns}.has_destination": 1.0 if dst else 0.0,
                f"{ns}.source_txn_count_before": float(src_count[src]),
                f"{ns}.destination_txn_count_before": float(dst_count[dst]) if dst else 0.0,
            }

            src_window = src_recent[src]
            while src_window and (txn.timestamp - src_window[0]) > _VELOCITY_WINDOW:
                src_window.popleft()
            row[f"{ns}.source_velocity_1h"] = float(len(src_window))

            if dst:
                dst_window = dst_recent[dst]
                while dst_window and (txn.timestamp - dst_window[0]) > _VELOCITY_WINDOW:
                    dst_window.popleft()
                row[f"{ns}.destination_velocity_1h"] = float(len(dst_window))
            else:
                row[f"{ns}.destination_velocity_1h"] = 0.0

            n = src_count[src]
            if n > 0:
                mean = src_sum[src] / n
                variance = max(src_sumsq[src] / n - mean**2, 0.0)
                std = variance**0.5
                row[f"{ns}.source_avg_amount_before"] = mean
                row[f"{ns}.amount_deviation_from_source_history"] = (
                    (txn.amount - mean) / std if std > 1e-9 else 0.0
                )
            else:
                row[f"{ns}.source_avg_amount_before"] = float("nan")
                row[f"{ns}.amount_deviation_from_source_history"] = 0.0

            row[f"{ns}.seconds_since_source_previous_txn"] = (
                (txn.timestamp - src_last_ts[src]).total_seconds()
                if src in src_last_ts
                else float("nan")
            )
            row[f"{ns}.seconds_since_destination_previous_txn"] = (
                (txn.timestamp - dst_last_ts[dst]).total_seconds()
                if dst and dst in dst_last_ts
                else float("nan")
            )

            for value in _KNOWN_TYPES:
                row[f"{ns}.type_{value}"] = 1.0 if txn.transaction_type.value == value else 0.0

            rows[i] = row

            src_count[src] += 1
            src_sum[src] += txn.amount
            src_sumsq[src] += txn.amount**2
            src_last_ts[src] = txn.timestamp
            src_recent[src].append(txn.timestamp)
            if dst:
                dst_count[dst] += 1
                dst_last_ts[dst] = txn.timestamp
                dst_recent[dst].append(txn.timestamp)

        return rows


def _optional(value: float | None) -> float:
    return float(value) if value is not None else float("nan")


__all__ = ["TemporalBaselineFeatureExtractor"]
