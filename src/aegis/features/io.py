"""Loading canonical `Transaction` records from processed JSONL artifacts.

Reads the output of `scripts/prepare_paysim.py` (or any producer of the same
shape): one JSON-serialized `Transaction` per line. Validation happens through
the frozen contract itself, so a schema drift between the preparation
pipeline and this loader is a loud `ValidationError`, not a silent mismatch.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from aegis.shared.contracts import Transaction
from aegis.shared.enums import FraudLabel


def load_transactions_jsonl(path: Path | str) -> list[Transaction]:
    """Read one `Transaction` per non-blank line of a JSONL file.

    Holds the entire file in memory as `Transaction` objects - fine for small
    fixtures and tests, but the wrong tool for a multi-million-row split. Use
    `iter_transactions_jsonl_chunks` for that; see
    `aegis.features.streaming`.
    """
    resolved = Path(path)
    transactions: list[Transaction] = []
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            transactions.append(Transaction.model_validate_json(stripped))
    return transactions


def count_labelled_jsonl_lines(path: Path | str) -> int:
    """Count non-blank lines whose `label` is not `UNKNOWN`, without building any `Transaction`.

    Minimal JSON parsing only (no pydantic validation) - lets a streaming
    writer pre-allocate an exactly-sized array before its one real pass over
    the file, with no reallocation or truncate-after-the-fact step needed.
    """
    resolved = Path(path)
    count = 0
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload_label = json.loads(stripped).get("label", FraudLabel.UNKNOWN.value)
            if payload_label != FraudLabel.UNKNOWN.value:
                count += 1
    return count


def iter_transactions_jsonl_chunks(
    path: Path | str, chunk_size: int
) -> Iterator[list[Transaction]]:
    """Yield up to `chunk_size` `Transaction` objects at a time, in file order.

    Never holds more than one chunk in memory. The file is not re-ordered or
    buffered beyond the current chunk, so callers that need a causal,
    chronologically-ordered pass must supply a file that is already sorted by
    timestamp (as every artifact from `scripts/prepare_paysim.py` is).
    """
    if chunk_size <= 0:
        msg = f"chunk_size must be positive, got {chunk_size}"
        raise ValueError(msg)

    resolved = Path(path)
    chunk: list[Transaction] = []
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            chunk.append(Transaction.model_validate_json(stripped))
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
    if chunk:
        yield chunk


__all__ = [
    "count_labelled_jsonl_lines",
    "iter_transactions_jsonl_chunks",
    "load_transactions_jsonl",
]
