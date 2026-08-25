"""`TemporalBaselineFeatureExtractor` - point-in-time-safe baseline features.

Every feature is computed from a transaction's own fields, or from a running
per-account aggregate built by a single **causal** pass over exactly the rows
passed to `transform`, ordered by `timestamp`. A row's aggregates reflect only
strictly earlier rows in that same call; state updates happen *after* a row's
features are recorded, never before.

The causal state machine lives in `_CausalHistoryState` below and is shared,
unmodified, with `aegis.features.streaming` - the disk-materializing path used
for large datasets that do not fit comfortably in memory. Both paths call the
exact same `compute()` / `observe()` methods in the exact same order, so the
two are structurally guaranteed to agree, not just tested to agree. See
`tests/test_features_streaming.py` for the equivalence proof and
`docs/BASELINE_DETECTOR.md` "Memory-safe materialization" for the full design.

Deliberate simplification: running per-account state does **not** carry over
between separate `transform` calls (e.g. from a `train` call into a later
`validation` call) in the in-memory path, nor across split boundaries in the
streaming path. This keeps a single call a pure function of its input - simple
to test and unambiguously leakage-safe - at the cost of a "cold start" at the
beginning of each split for accounts that also appear earlier in time in a
different split. See `docs/BASELINE_DETECTOR.md` for the trade-off.

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

Cross-family feature addition (Defender v3): `source_distinct_destinations_before`
and `destination_distinct_sources_before` count *distinct* prior counterparties
per account - not prior transaction volume, which `source_txn_count_before` /
`destination_txn_count_before` already cover. They exist because a real
mule-network-structuring confrontation (`data/synthetic/mule_confrontations/`)
showed a coordinator account paying several distinct mule accounts, and mule
accounts layering funds on to further distinct accounts before a fan-in
cash-out - a graph shape the other 19 columns cannot represent, since they
track *how many* payments an account made, never *how many different
counterparties*. Both new columns follow the exact same rules as every other
feature here: strictly-prior-only (folded into `_CausalHistoryState` via the
same `compute()`-then-`observe()` contract), no future edges, no labels, no
post-transaction fields, deterministic given a fixed input order, and bounded
in memory by distinct-account count (a `set` of counterparty ids per account,
same order of memory as the existing `src_recent`/`dst_recent` deques - not a
full transaction graph). They are cumulative counts (matching
`source_txn_count_before`'s convention), not windowed.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from aegis.features.base import BaseFeatureExtractor
from aegis.shared.contracts import Transaction
from aegis.shared.enums import TransactionType

_VELOCITY_WINDOW = timedelta(hours=1)
_KNOWN_TYPES: list[str] = [member.value for member in TransactionType]
"""Fixed, schema-known vocabulary - not learned from data, so one-hot column
order is stable no matter which types appear in a given split."""

FEATURE_SUFFIXES: list[str] = [
    "amount",
    "hour_of_day",
    "source_balance_before",
    "destination_balance_before",
    "has_destination",
    "source_txn_count_before",
    "destination_txn_count_before",
    "source_distinct_destinations_before",
    "destination_distinct_sources_before",
    "source_velocity_1h",
    "destination_velocity_1h",
    "source_avg_amount_before",
    "amount_deviation_from_source_history",
    "seconds_since_source_previous_txn",
    "seconds_since_destination_previous_txn",
    *[f"type_{value}" for value in _KNOWN_TYPES],
]
"""Un-namespaced feature names, in emission order. 21 columns: 15 scalar/
history features plus one-hot over the 6 known transaction types.

`source_distinct_destinations_before` / `destination_distinct_sources_before`
are the Defender-v3 cross-family addition (see `docs/BASELINE_DETECTOR.md`
"Cross-family hardening (Defender v3)"): a minimal, decision-time-safe
counterparty-fan-out signal added because the other 19 columns count total
prior transaction *volume* per account but never distinct *counterparties*,
so a source paying one destination six times and a source paying six
distinct destinations once each were indistinguishable - exactly the
difference between ordinary repeat payments and mule-network structuring's
fan-out/layering pattern. See the module-level "Cross-family feature
addition" note below for the full reasoning and the leakage argument."""


def feature_columns(namespace: str) -> list[str]:
    """Namespaced column names in emission order, e.g. `temporal.amount`."""
    return [f"{namespace}.{suffix}" for suffix in FEATURE_SUFFIXES]


class _CausalHistoryState:
    """Running per-account state for one causal, chronologically-ordered pass.

    `compute(txn)` reads only state built by *earlier* `observe()` calls;
    `observe(txn)` folds `txn` into that state afterwards. Callers must call
    them in that order, once per transaction, in non-decreasing timestamp
    order - the same contract whether the caller holds the whole split in
    memory (`TemporalBaselineFeatureExtractor`) or streams it in chunks
    (`aegis.features.streaming`).
    """

    __slots__ = (
        "dst_count",
        "dst_last_ts",
        "dst_recent",
        "dst_src_seen",
        "src_count",
        "src_dst_seen",
        "src_last_ts",
        "src_recent",
        "src_sum",
        "src_sumsq",
    )

    def __init__(self) -> None:
        self.src_count: dict[str, int] = defaultdict(int)
        self.src_sum: dict[str, float] = defaultdict(float)
        self.src_sumsq: dict[str, float] = defaultdict(float)
        self.src_last_ts: dict[str, datetime] = {}
        self.src_recent: dict[str, deque[datetime]] = defaultdict(deque)
        self.dst_count: dict[str, int] = defaultdict(int)
        self.dst_last_ts: dict[str, datetime] = {}
        self.dst_recent: dict[str, deque[datetime]] = defaultdict(deque)
        # Distinct-counterparty sets, bounded by distinct-account count - see
        # "Cross-family feature addition" in the module docstring.
        self.src_dst_seen: dict[str, set[str]] = defaultdict(set)
        self.dst_src_seen: dict[str, set[str]] = defaultdict(set)

    def compute(self, txn: Transaction) -> list[float]:
        """Feature values for `txn`, in `FEATURE_SUFFIXES` order."""
        src = txn.source_account_id
        dst = txn.destination_account_id

        src_window = self.src_recent[src]
        while src_window and (txn.timestamp - src_window[0]) > _VELOCITY_WINDOW:
            src_window.popleft()
        source_velocity_1h = float(len(src_window))

        if dst:
            dst_window = self.dst_recent[dst]
            while dst_window and (txn.timestamp - dst_window[0]) > _VELOCITY_WINDOW:
                dst_window.popleft()
            destination_velocity_1h = float(len(dst_window))
        else:
            destination_velocity_1h = 0.0

        n = self.src_count[src]
        if n > 0:
            mean = self.src_sum[src] / n
            variance = max(self.src_sumsq[src] / n - mean**2, 0.0)
            std = variance**0.5
            source_avg_amount_before = mean
            amount_deviation = (txn.amount - mean) / std if std > 1e-9 else 0.0
        else:
            source_avg_amount_before = float("nan")
            amount_deviation = 0.0

        seconds_since_source = (
            (txn.timestamp - self.src_last_ts[src]).total_seconds()
            if src in self.src_last_ts
            else float("nan")
        )
        seconds_since_destination = (
            (txn.timestamp - self.dst_last_ts[dst]).total_seconds()
            if dst and dst in self.dst_last_ts
            else float("nan")
        )

        row = [
            float(txn.amount),
            float(txn.timestamp.hour),
            # Pre-transaction balances only. `*_balance_after` is a
            # post-transaction outcome and must never appear here - see the
            # decision-time feature policy in the module docstring.
            _optional(txn.source_balance_before),
            _optional(txn.destination_balance_before),
            1.0 if dst else 0.0,
            float(self.src_count[src]),
            float(self.dst_count[dst]) if dst else 0.0,
            float(len(self.src_dst_seen[src])),
            float(len(self.dst_src_seen[dst])) if dst else 0.0,
            source_velocity_1h,
            destination_velocity_1h,
            source_avg_amount_before,
            amount_deviation,
            seconds_since_source,
            seconds_since_destination,
        ]
        row.extend(1.0 if txn.transaction_type.value == value else 0.0 for value in _KNOWN_TYPES)
        return row

    def observe(self, txn: Transaction) -> None:
        """Fold `txn` into the running state, after its features were computed."""
        src = txn.source_account_id
        dst = txn.destination_account_id
        self.src_count[src] += 1
        self.src_sum[src] += txn.amount
        self.src_sumsq[src] += txn.amount**2
        self.src_last_ts[src] = txn.timestamp
        self.src_recent[src].append(txn.timestamp)
        if dst:
            self.dst_count[dst] += 1
            self.dst_last_ts[dst] = txn.timestamp
            self.dst_recent[dst].append(txn.timestamp)
            self.src_dst_seen[src].add(dst)
            self.dst_src_seen[dst].add(src)


class TemporalBaselineFeatureExtractor(BaseFeatureExtractor):
    """Baseline per-transaction and per-account-history features."""

    namespace = "temporal"
    version = "0.2.0"
    """Bumped from 0.1.0: adds the two distinct-counterparty columns for
    Defender v3 cross-family hardening. See the module docstring's
    "Cross-family feature addition" note."""

    def fit(
        self, transactions: Sequence[Transaction], meta: dict[str, Any] | None = None
    ) -> TemporalBaselineFeatureExtractor:
        self._feature_names = feature_columns(self.namespace)
        self._is_fitted = True
        return self

    def transform(self, transactions: Sequence[Transaction]) -> pd.DataFrame:
        if not self._is_fitted:
            msg = f"{type(self).__name__}.transform called before fit"
            raise RuntimeError(msg)

        rows = self._compute_rows(transactions)
        ordered = [rows[i] for i in range(len(transactions))]
        return pd.DataFrame(ordered, columns=self._feature_names)

    def _compute_rows(self, transactions: Sequence[Transaction]) -> dict[int, list[float]]:
        # Stable causal order: timestamp, then original position as a
        # deterministic tie-break for same-instant rows (PaySim's hourly
        # `step` resolution means many rows legitimately share one timestamp).
        order = sorted(range(len(transactions)), key=lambda i: (transactions[i].timestamp, i))

        state = _CausalHistoryState()
        rows: dict[int, list[float]] = {}
        for i in order:
            txn = transactions[i]
            rows[i] = state.compute(txn)
            state.observe(txn)
        return rows


def _optional(value: float | None) -> float:
    return float(value) if value is not None else float("nan")


__all__ = [
    "FEATURE_SUFFIXES",
    "TemporalBaselineFeatureExtractor",
    "feature_columns",
]
