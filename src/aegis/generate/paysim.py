"""Prepare PaySim as the canonical, leakage-conscious AEGIS payment world.

The preparation pass is intentionally separate from attack generation. It maps
real source rows into the frozen :class:`Transaction` contract and establishes
evaluation partitions without inventing fraud behaviour.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import sqlite3
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from aegis.shared.contracts import Transaction
from aegis.shared.enums import Channel, DataSplit, FraudLabel, TransactionType

PAYSIM_REQUIRED_COLUMNS: tuple[str, ...] = (
    "step",
    "type",
    "amount",
    "nameOrig",
    "oldbalanceOrg",
    "newbalanceOrig",
    "nameDest",
    "oldbalanceDest",
    "newbalanceDest",
    "isFraud",
    "isFlaggedFraud",
)

DEFAULT_PAYSIM_EPOCH = datetime(2017, 1, 1, tzinfo=timezone.utc)
DEFAULT_PAYSIM_CURRENCY = "XXX"
PREPARATION_VERSION = "1.1.0"
_SQLITE_PARAMETER_BATCH = 800
PaySimSplitMode = Literal["temporal", "entity_isolated"]

_TYPE_MAP: dict[str, TransactionType] = {
    "PAYMENT": TransactionType.PAYMENT,
    "TRANSFER": TransactionType.TRANSFER,
    "CASH_IN": TransactionType.CASH_IN,
    "CASH_OUT": TransactionType.CASH_OUT,
    "DEBIT": TransactionType.DEBIT,
}


class PaySimPreparationError(ValueError):
    """Base error for invalid PaySim input or preparation configuration."""


class PaySimSchemaError(PaySimPreparationError):
    """Raised when the CSV header does not contain the PaySim source schema."""


class PaySimRowError(PaySimPreparationError):
    """Raised when a source row cannot be represented by the frozen contract."""


@dataclass(frozen=True)
class PaySimPreparationConfig:
    """Configuration recorded in every deterministic preparation manifest."""

    data_root: Path = Path("data")
    seed: int = 20260101
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    split_mode: PaySimSplitMode = "temporal"
    currency: str | None = None
    epoch: datetime = DEFAULT_PAYSIM_EPOCH

    def __post_init__(self) -> None:
        ratios = (self.train_ratio, self.validation_ratio, self.test_ratio)
        if any(ratio <= 0.0 for ratio in ratios) or not math.isclose(sum(ratios), 1.0):
            msg = "train, validation, and test ratios must be positive and sum to 1"
            raise PaySimPreparationError(msg)
        if self.split_mode not in ("temporal", "entity_isolated"):
            msg = f"unsupported PaySim split mode: {self.split_mode!r}"
            raise PaySimPreparationError(msg)
        currency = self.currency.upper() if self.currency is not None else None
        if currency is not None and (len(currency) != 3 or not currency.isalpha()):
            msg = f"currency must be an ISO-4217 alpha-3 code, got {self.currency!r}"
            raise PaySimPreparationError(msg)
        if self.epoch.tzinfo is None:
            msg = "PaySim epoch must be timezone-aware"
            raise PaySimPreparationError(msg)


@dataclass(frozen=True)
class PaySimPreparationResult:
    """Paths and summary returned after an atomic preparation run."""

    output_dir: Path
    artifacts: dict[str, Path]
    summary: dict[str, Any]


@dataclass(frozen=True)
class _SourceRow:
    step: int
    transaction_type: TransactionType
    source_type: str
    amount: float
    source_account_id: str
    source_balance_before: float
    source_balance_after: float
    destination_account_id: str
    destination_balance_before: float
    destination_balance_after: float
    is_fraud: int
    is_flagged_fraud: int


@dataclass
class _ScanStats:
    total: int
    fraud: int
    legitimate: int
    step_counts: Counter[int]
    type_counts: Counter[str]


def validate_paysim_schema(csv_path: str | Path) -> tuple[str, ...]:
    """Validate and return the source header without reading data rows."""
    source_path = Path(csv_path)
    if not source_path.is_file():
        msg = f"PaySim CSV does not exist or is not a file: {source_path}"
        raise PaySimSchemaError(msg)
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = tuple(next(reader))
        except StopIteration as exc:
            raise PaySimSchemaError("PaySim CSV is empty") from exc
    missing = sorted(set(PAYSIM_REQUIRED_COLUMNS).difference(header))
    if missing:
        msg = f"PaySim CSV is missing required columns: {', '.join(missing)}"
        raise PaySimSchemaError(msg)
    if len(header) != len(set(header)):
        raise PaySimSchemaError("PaySim CSV contains duplicate column names")
    return header


def map_paysim_row(
    row: Mapping[str, str],
    *,
    source_row_number: int,
    split: DataSplit = DataSplit.UNASSIGNED,
    epoch: datetime = DEFAULT_PAYSIM_EPOCH,
    currency: str = DEFAULT_PAYSIM_CURRENCY,
) -> Transaction:
    """Map one standard PaySim source row into the frozen Transaction contract."""
    missing = sorted(set(PAYSIM_REQUIRED_COLUMNS).difference(row))
    if missing:
        msg = f"PaySim row is missing required fields: {', '.join(missing)}"
        raise PaySimRowError(msg)
    parsed = _parse_row(row, source_row_number)
    return _to_transaction(
        parsed,
        source_row_number=source_row_number,
        split=split,
        epoch=epoch,
        currency=currency,
    )


def prepare_paysim(
    csv_path: str | Path,
    config: PaySimPreparationConfig | None = None,
) -> PaySimPreparationResult:
    """Prepare a local PaySim CSV into canonical split and quarantine artifacts."""
    source_path = Path(csv_path).expanduser().resolve()
    active_config = config or PaySimPreparationConfig()
    validate_paysim_schema(source_path)

    data_root = active_config.data_root.expanduser().resolve()
    interim_parent = data_root / "interim" / "paysim"
    processed_parent = data_root / "processed" / "paysim"
    interim_parent.mkdir(parents=True, exist_ok=True)
    processed_parent.mkdir(parents=True, exist_ok=True)

    source_checksum = _sha256_file(source_path)
    run_id = _run_id(source_checksum, active_config)
    final_dir = processed_parent / run_id
    if final_dir.exists():
        msg = f"prepared output already exists; refusing to overwrite: {final_dir}"
        raise FileExistsError(msg)

    work_dir = _make_work_directory(interim_parent, run_id)
    try:
        database_path = work_dir / "entity_profiles.sqlite3"
        with closing(sqlite3.connect(database_path)) as connection:
            _initialise_database(connection)
            scan_stats = _scan_source(source_path, connection)
            train_end, validation_end = _choose_boundaries(
                scan_stats.step_counts,
                train_ratio=active_config.train_ratio,
                validation_ratio=active_config.validation_ratio,
                seed=active_config.seed,
            )
            source_entity_counts = _source_entity_counts(connection)

            temporary_output = _make_work_directory(processed_parent, run_id)
            try:
                prepared_stats = _write_artifacts(
                    source_path,
                    temporary_output,
                    connection,
                    active_config,
                    train_end,
                    validation_end,
                )
                summary = _build_summary(
                    source_path=source_path,
                    source_checksum=source_checksum,
                    run_id=run_id,
                    config=active_config,
                    scan_stats=scan_stats,
                    source_entity_counts=source_entity_counts,
                    train_end=train_end,
                    validation_end=validation_end,
                    prepared_stats=prepared_stats,
                    output_dir=temporary_output,
                )
                _write_json(temporary_output / "summary.json", summary)
                os.replace(temporary_output, final_dir)
            except Exception:
                shutil.rmtree(temporary_output, ignore_errors=True)
                raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    artifact_names = ("train", "validation", "test", "quarantine", "summary")
    artifacts = {name: final_dir / f"{name}.jsonl" for name in artifact_names[:-1]}
    artifacts["summary"] = final_dir / "summary.json"
    return PaySimPreparationResult(output_dir=final_dir, artifacts=artifacts, summary=summary)


def _parse_row(row: Mapping[str, str], source_row_number: int) -> _SourceRow:
    try:
        step = int(row["step"])
        source_type = row["type"].strip().upper()
        transaction_type = _TYPE_MAP[source_type]
        amount = float(row["amount"])
        source_balance_before = float(row["oldbalanceOrg"])
        source_balance_after = float(row["newbalanceOrig"])
        destination_balance_before = float(row["oldbalanceDest"])
        destination_balance_after = float(row["newbalanceDest"])
        is_fraud = int(row["isFraud"])
        is_flagged_fraud = int(row["isFlaggedFraud"])
    except (KeyError, TypeError, ValueError) as exc:
        msg = f"invalid PaySim value at CSV row {source_row_number}: {exc}"
        raise PaySimRowError(msg) from exc

    source_account_id = row["nameOrig"].strip()
    destination_account_id = row["nameDest"].strip()
    numeric_values = (
        amount,
        source_balance_before,
        source_balance_after,
        destination_balance_before,
        destination_balance_after,
    )
    if step < 1:
        raise PaySimRowError(f"step must be at least 1 at CSV row {source_row_number}")
    if not source_account_id or not destination_account_id:
        msg = f"account identifiers must be non-empty at CSV row {source_row_number}"
        raise PaySimRowError(msg)
    if not all(math.isfinite(value) for value in numeric_values):
        raise PaySimRowError(f"numeric values must be finite at CSV row {source_row_number}")
    if amount < 0.0:
        raise PaySimRowError(f"amount must be non-negative at CSV row {source_row_number}")
    if is_fraud not in (0, 1) or is_flagged_fraud not in (0, 1):
        raise PaySimRowError(f"fraud flags must be 0 or 1 at CSV row {source_row_number}")

    return _SourceRow(
        step=step,
        transaction_type=transaction_type,
        source_type=source_type,
        amount=amount,
        source_account_id=source_account_id,
        source_balance_before=source_balance_before,
        source_balance_after=source_balance_after,
        destination_account_id=destination_account_id,
        destination_balance_before=destination_balance_before,
        destination_balance_after=destination_balance_after,
        is_fraud=is_fraud,
        is_flagged_fraud=is_flagged_fraud,
    )


def _to_transaction(
    row: _SourceRow,
    *,
    source_row_number: int,
    split: DataSplit,
    epoch: datetime,
    currency: str,
) -> Transaction:
    identity = "|".join(
        (
            str(source_row_number),
            str(row.step),
            row.source_type,
            repr(row.amount),
            row.source_account_id,
            row.destination_account_id,
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    merchant_id = row.destination_account_id if row.destination_account_id.startswith("M") else None
    return Transaction(
        transaction_id=f"paysim-{source_row_number:010d}-{digest}",
        timestamp=epoch.astimezone(timezone.utc) + timedelta(hours=row.step - 1),
        source_account_id=row.source_account_id,
        destination_account_id=row.destination_account_id,
        amount=row.amount,
        currency=currency.upper(),
        transaction_type=row.transaction_type,
        channel=Channel.UNKNOWN,
        merchant_id=merchant_id,
        source_balance_before=row.source_balance_before,
        source_balance_after=row.source_balance_after,
        destination_balance_before=row.destination_balance_before,
        destination_balance_after=row.destination_balance_after,
        label=FraudLabel(row.is_fraud),
        attack_family=None,
        is_synthetic=False,
        split=split,
        metadata={
            "paysim.step": row.step,
            "paysim.type": row.source_type,
            "paysim.is_flagged_fraud": row.is_flagged_fraud,
            "paysim.source_row_number": source_row_number,
            "paysim.source_entity_kind": _entity_kind(row.source_account_id),
            "paysim.destination_entity_kind": _entity_kind(row.destination_account_id),
        },
    )


def _entity_kind(entity_id: str) -> str:
    if entity_id.startswith("M"):
        return "merchant"
    if entity_id.startswith("C"):
        return "customer"
    return "unknown"


def _initialise_database(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE entities (
            entity_id TEXT PRIMARY KEY,
            first_step INTEGER NOT NULL,
            last_step INTEGER NOT NULL,
            roles INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE split_entities (
            entity_id TEXT NOT NULL,
            split TEXT NOT NULL,
            roles INTEGER NOT NULL,
            PRIMARY KEY (entity_id, split)
        )
        """
    )
    connection.commit()


def _scan_source(source_path: Path, connection: sqlite3.Connection) -> _ScanStats:
    total = 0
    fraud = 0
    step_counts: Counter[int] = Counter()
    type_counts: Counter[str] = Counter()
    entity_updates: list[tuple[str, int, int, int]] = []

    for source_row_number, row in _iter_rows(source_path):
        parsed = _parse_row(row, source_row_number)
        total += 1
        fraud += parsed.is_fraud
        step_counts[parsed.step] += 1
        type_counts[parsed.transaction_type.value] += 1
        entity_updates.extend(
            (
                (parsed.source_account_id, parsed.step, parsed.step, 1),
                (parsed.destination_account_id, parsed.step, parsed.step, 2),
            )
        )
        if len(entity_updates) >= 10_000:
            _upsert_entities(connection, entity_updates)
            entity_updates.clear()
    if entity_updates:
        _upsert_entities(connection, entity_updates)
    connection.commit()
    if total == 0:
        raise PaySimRowError("PaySim CSV contains a header but no data rows")
    return _ScanStats(
        total=total,
        fraud=fraud,
        legitimate=total - fraud,
        step_counts=step_counts,
        type_counts=type_counts,
    )


def _upsert_entities(
    connection: sqlite3.Connection, updates: Sequence[tuple[str, int, int, int]]
) -> None:
    connection.executemany(
        """
        INSERT INTO entities(entity_id, first_step, last_step, roles)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(entity_id) DO UPDATE SET
            first_step = MIN(first_step, excluded.first_step),
            last_step = MAX(last_step, excluded.last_step),
            roles = roles | excluded.roles
        """,
        updates,
    )


def _iter_rows(source_path: Path) -> Iterable[tuple[int, dict[str, str]]]:
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for source_row_number, source_row in enumerate(reader, start=2):
            if None in source_row:
                raise PaySimRowError(
                    f"too many CSV fields at row {source_row_number}; check delimiters"
                )
            row = {
                str(key): "" if value is None else str(value) for key, value in source_row.items()
            }
            yield source_row_number, row


def _choose_boundaries(
    step_counts: Mapping[int, int],
    *,
    train_ratio: float,
    validation_ratio: float,
    seed: int,
) -> tuple[int, int]:
    steps = sorted(step_counts)
    if len(steps) < 3:
        msg = "at least three distinct PaySim steps are required for chronological splits"
        raise PaySimPreparationError(msg)
    cumulative: list[int] = []
    running = 0
    for step in steps:
        running += step_counts[step]
        cumulative.append(running)

    train_index = _nearest_boundary(
        steps=steps,
        cumulative=cumulative,
        candidates=range(0, len(steps) - 2),
        target=running * train_ratio,
        seed=seed,
        name="train",
    )
    validation_index = _nearest_boundary(
        steps=steps,
        cumulative=cumulative,
        candidates=range(train_index + 1, len(steps) - 1),
        target=running * (train_ratio + validation_ratio),
        seed=seed,
        name="validation",
    )
    return steps[train_index], steps[validation_index]


def _nearest_boundary(
    *,
    steps: Sequence[int],
    cumulative: Sequence[int],
    candidates: Iterable[int],
    target: float,
    seed: int,
    name: str,
) -> int:
    def key(index: int) -> tuple[float, str]:
        tie = hashlib.sha256(f"{seed}:{name}:{steps[index]}".encode()).hexdigest()
        return abs(cumulative[index] - target), tie

    return min(candidates, key=key)


def _source_entity_counts(connection: sqlite3.Connection) -> dict[str, int]:
    source_count = connection.execute(
        "SELECT COUNT(*) FROM entities WHERE (roles & 1) != 0"
    ).fetchone()
    destination_count = connection.execute(
        "SELECT COUNT(*) FROM entities WHERE (roles & 2) != 0"
    ).fetchone()
    all_count = connection.execute("SELECT COUNT(*) FROM entities").fetchone()
    assert source_count is not None and destination_count is not None and all_count is not None
    return {
        "source": int(source_count[0]),
        "destination": int(destination_count[0]),
        "all": int(all_count[0]),
    }


def _write_artifacts(
    source_path: Path,
    output_dir: Path,
    connection: sqlite3.Connection,
    config: PaySimPreparationConfig,
    train_end: int,
    validation_end: int,
) -> dict[str, Any]:
    split_counts: Counter[str] = Counter()
    label_counts: dict[str, Counter[str]] = {
        split.value: Counter() for split in (DataSplit.TRAIN, DataSplit.VALIDATION, DataSplit.TEST)
    }
    type_counts: dict[str, Counter[str]] = {
        split.value: Counter() for split in (DataSplit.TRAIN, DataSplit.VALIDATION, DataSplit.TEST)
    }
    exclusion_counts: Counter[str] = Counter()
    step_ranges: dict[str, list[int | None]] = {
        split.value: [None, None]
        for split in (DataSplit.TRAIN, DataSplit.VALIDATION, DataSplit.TEST)
    }
    paths = {
        DataSplit.TRAIN: output_dir / "train.jsonl",
        DataSplit.VALIDATION: output_dir / "validation.jsonl",
        DataSplit.TEST: output_dir / "test.jsonl",
        DataSplit.UNASSIGNED: output_dir / "quarantine.jsonl",
    }
    handles = {
        split: path.open("w", encoding="utf-8", newline="\n") for split, path in paths.items()
    }
    currency, _ = _currency_details(config)
    try:
        for source_row_number, rows in _chunked_rows(source_path, 5_000):
            parsed_rows = [
                (row_number, _parse_row(row, row_number))
                for row_number, row in zip(source_row_number, rows, strict=True)
            ]
            profiles: dict[str, tuple[int, int]] = {}
            if config.split_mode == "entity_isolated":
                entity_ids = {
                    entity_id
                    for _, row in parsed_rows
                    for entity_id in (row.source_account_id, row.destination_account_id)
                }
                profiles = _lookup_entity_profiles(connection, entity_ids)
            split_entity_updates: list[tuple[str, str, int]] = []
            for row_number, row in parsed_rows:
                temporal_split = _split_for_step(row.step, train_end, validation_end)
                reasons: list[str] = []
                if config.split_mode == "entity_isolated":
                    source_split = _eligible_entity_split(
                        profiles[row.source_account_id], train_end, validation_end
                    )
                    destination_split = _eligible_entity_split(
                        profiles[row.destination_account_id], train_end, validation_end
                    )
                    if source_split is None:
                        reasons.append("source_entity_crosses_temporal_boundary")
                    elif source_split is not temporal_split:
                        reasons.append("source_entity_outside_row_window")
                    if destination_split is None:
                        reasons.append("destination_entity_crosses_temporal_boundary")
                    elif destination_split is not temporal_split:
                        reasons.append("destination_entity_outside_row_window")

                output_split = DataSplit.UNASSIGNED if reasons else temporal_split
                transaction = _to_transaction(
                    row,
                    source_row_number=row_number,
                    split=output_split,
                    epoch=config.epoch,
                    currency=currency,
                )
                if reasons:
                    transaction = transaction.model_copy(
                        update={
                            "metadata": {
                                **transaction.metadata,
                                "preparation.exclusion_reasons": reasons,
                            }
                        }
                    )
                    exclusion_counts.update(reasons)
                    split_counts["quarantine"] += 1
                else:
                    split_name = temporal_split.value
                    split_counts[split_name] += 1
                    label_counts[split_name]["fraud" if row.is_fraud else "legitimate"] += 1
                    type_counts[split_name][row.transaction_type.value] += 1
                    _update_range(step_ranges[split_name], row.step)
                    split_entity_updates.extend(
                        (
                            (row.source_account_id, split_name, 1),
                            (row.destination_account_id, split_name, 2),
                        )
                    )
                handles[output_split].write(transaction.model_dump_json())
                handles[output_split].write("\n")
            _upsert_split_entities(connection, split_entity_updates)
    finally:
        for handle in handles.values():
            handle.close()

    split_statistics = {
        split: {
            "transaction_count": split_counts[split],
            "legitimate_count": label_counts[split]["legitimate"],
            "fraud_count": label_counts[split]["fraud"],
            "fraud_prevalence": (
                label_counts[split]["fraud"] / split_counts[split] if split_counts[split] else 0.0
            ),
            "transaction_type_distribution": dict(sorted(type_counts[split].items())),
            "step_range": {"minimum": step_ranges[split][0], "maximum": step_ranges[split][1]},
            "timestamp_range_utc": _timestamp_range(step_ranges[split], config.epoch),
        }
        for split in ("train", "validation", "test")
    }
    quarantine_count = split_counts["quarantine"]
    total_count = sum(split_counts.values())
    return {
        "split_sizes": {
            "train": split_counts["train"],
            "validation": split_counts["validation"],
            "test": split_counts["test"],
            "quarantine": split_counts["quarantine"],
        },
        "split_label_counts": {
            split: {"legitimate": counts["legitimate"], "fraud": counts["fraud"]}
            for split, counts in label_counts.items()
        },
        "split_step_ranges": {
            split: {"minimum": values[0], "maximum": values[1]}
            for split, values in step_ranges.items()
        },
        "split_statistics": split_statistics,
        "entity_overlap": _entity_overlap_statistics(connection),
        "quarantine": {
            "count": quarantine_count,
            "percentage": 100.0 * quarantine_count / total_count,
        },
        "exclusion_reasons": dict(sorted(exclusion_counts.items())),
    }


def _upsert_split_entities(
    connection: sqlite3.Connection, updates: Sequence[tuple[str, str, int]]
) -> None:
    connection.executemany(
        """
        INSERT INTO split_entities(entity_id, split, roles)
        VALUES (?, ?, ?)
        ON CONFLICT(entity_id, split) DO UPDATE SET roles = roles | excluded.roles
        """,
        updates,
    )


def _entity_overlap_statistics(connection: sqlite3.Connection) -> dict[str, dict[str, int]]:
    pairs = (
        ("train_vs_validation", "train", "validation"),
        ("train_vs_test", "train", "test"),
        ("validation_vs_test", "validation", "test"),
    )

    def overlaps(role_mask: int) -> dict[str, int]:
        result: dict[str, int] = {}
        for name, left, right in pairs:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM split_entities AS left_split
                JOIN split_entities AS right_split
                  ON left_split.entity_id = right_split.entity_id
                WHERE left_split.split = ? AND right_split.split = ?
                  AND (left_split.roles & ?) != 0
                  AND (right_split.roles & ?) != 0
                """,
                (left, right, role_mask, role_mask),
            ).fetchone()
            assert row is not None
            result[name] = int(row[0])
        return result

    return {
        "source_accounts": overlaps(1),
        "destination_accounts": overlaps(2),
    }


def _timestamp_range(values: Sequence[int | None], epoch: datetime) -> dict[str, str | None]:
    def timestamp(step: int | None) -> str | None:
        if step is None:
            return None
        return (epoch.astimezone(timezone.utc) + timedelta(hours=step - 1)).isoformat()

    return {"minimum": timestamp(values[0]), "maximum": timestamp(values[1])}


def _chunked_rows(
    source_path: Path, chunk_size: int
) -> Iterable[tuple[list[int], list[dict[str, str]]]]:
    row_numbers: list[int] = []
    rows: list[dict[str, str]] = []
    for row_number, row in _iter_rows(source_path):
        row_numbers.append(row_number)
        rows.append(row)
        if len(rows) == chunk_size:
            yield row_numbers, rows
            row_numbers, rows = [], []
    if rows:
        yield row_numbers, rows


def _lookup_entity_profiles(
    connection: sqlite3.Connection, entity_ids: set[str]
) -> dict[str, tuple[int, int]]:
    profiles: dict[str, tuple[int, int]] = {}
    ordered = sorted(entity_ids)
    for start in range(0, len(ordered), _SQLITE_PARAMETER_BATCH):
        batch = ordered[start : start + _SQLITE_PARAMETER_BATCH]
        placeholders = ",".join("?" for _ in batch)
        query = (
            "SELECT entity_id, first_step, last_step "
            f"FROM entities WHERE entity_id IN ({placeholders})"
        )
        for entity_id, first_step, last_step in connection.execute(query, batch):
            profiles[str(entity_id)] = (int(first_step), int(last_step))
    if len(profiles) != len(entity_ids):
        missing = sorted(entity_ids.difference(profiles))
        raise RuntimeError(f"entity profile lookup failed for: {missing[:3]}")
    return profiles


def _split_for_step(step: int, train_end: int, validation_end: int) -> DataSplit:
    if step <= train_end:
        return DataSplit.TRAIN
    if step <= validation_end:
        return DataSplit.VALIDATION
    return DataSplit.TEST


def _eligible_entity_split(
    profile: tuple[int, int], train_end: int, validation_end: int
) -> DataSplit | None:
    first_split = _split_for_step(profile[0], train_end, validation_end)
    last_split = _split_for_step(profile[1], train_end, validation_end)
    return first_split if first_split is last_split else None


def _update_range(values: list[int | None], step: int) -> None:
    if values[0] is None or step < values[0]:
        values[0] = step
    if values[1] is None or step > values[1]:
        values[1] = step


def _build_summary(
    *,
    source_path: Path,
    source_checksum: str,
    run_id: str,
    config: PaySimPreparationConfig,
    scan_stats: _ScanStats,
    source_entity_counts: dict[str, int],
    train_end: int,
    validation_end: int,
    prepared_stats: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    minimum_step = min(scan_stats.step_counts)
    maximum_step = max(scan_stats.step_counts)
    artifact_checksums = {
        name: _sha256_file(output_dir / f"{name}.jsonl")
        for name in ("train", "validation", "test", "quarantine")
    }
    currency, currency_basis = _currency_details(config)
    strategy = (
        "whole_step_temporal_windows"
        if config.split_mode == "temporal"
        else "whole_step_temporal_windows_with_strict_entity_embargo"
    )
    return {
        "dataset_id": "paysim",
        "preparation_version": PREPARATION_VERSION,
        "run_id": run_id,
        "source": {
            "path": str(source_path),
            "sha256": source_checksum,
            "required_columns": list(PAYSIM_REQUIRED_COLUMNS),
        },
        "configuration": {
            "seed": config.seed,
            "ratios": {
                "train": config.train_ratio,
                "validation": config.validation_ratio,
                "test": config.test_ratio,
            },
            "currency": {"value": currency, "basis": currency_basis},
            "step_epoch_utc": config.epoch.astimezone(timezone.utc).isoformat(),
            "step_duration_hours": 1,
        },
        "source_statistics": {
            "total_transactions": scan_stats.total,
            "legitimate_count": scan_stats.legitimate,
            "fraud_count": scan_stats.fraud,
            "fraud_prevalence": scan_stats.fraud / scan_stats.total,
            "transaction_type_distribution": dict(sorted(scan_stats.type_counts.items())),
            "step_range": {"minimum": minimum_step, "maximum": maximum_step},
            "timestamp_range_utc": {
                "minimum": (
                    config.epoch.astimezone(timezone.utc) + timedelta(hours=minimum_step - 1)
                ).isoformat(),
                "maximum": (
                    config.epoch.astimezone(timezone.utc) + timedelta(hours=maximum_step - 1)
                ).isoformat(),
            },
            "entity_counts": source_entity_counts,
        },
        "splitting": {
            "mode": config.split_mode,
            "strategy": strategy,
            "train_end_step": train_end,
            "validation_end_step": validation_end,
            "test_start_step": validation_end + 1,
            **prepared_stats,
        },
        "artifacts": {
            name: {"file": f"{name}.jsonl", "sha256": checksum}
            for name, checksum in artifact_checksums.items()
        },
    }


def _run_id(source_checksum: str, config: PaySimPreparationConfig) -> str:
    currency, currency_basis = _currency_details(config)
    payload = json.dumps(
        {
            "source_sha256": source_checksum,
            "seed": config.seed,
            "ratios": [config.train_ratio, config.validation_ratio, config.test_ratio],
            "split_mode": config.split_mode,
            "currency": currency,
            "currency_basis": currency_basis,
            "epoch": config.epoch.astimezone(timezone.utc).isoformat(),
            "preparation_version": PREPARATION_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"paysim-{source_checksum[:12]}-{digest}"


def _currency_details(config: PaySimPreparationConfig) -> tuple[str, str]:
    if config.currency is None:
        return DEFAULT_PAYSIM_CURRENCY, "neutral_default"
    return config.currency.upper(), "explicit_override"


def _make_work_directory(parent: Path, run_id: str) -> Path:
    path = parent / f".{run_id}-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


__all__ = [
    "DEFAULT_PAYSIM_CURRENCY",
    "DEFAULT_PAYSIM_EPOCH",
    "PAYSIM_REQUIRED_COLUMNS",
    "PREPARATION_VERSION",
    "PaySimPreparationConfig",
    "PaySimPreparationError",
    "PaySimPreparationResult",
    "PaySimRowError",
    "PaySimSchemaError",
    "PaySimSplitMode",
    "map_paysim_row",
    "prepare_paysim",
    "validate_paysim_schema",
]
