"""Read-only, fault-tolerant parsing of persisted AEGIS artifacts.

Artifacts on disk are produced by scripts the API does not control. This
module never raises on a missing or malformed file -- it treats both as
"not available" and lets the caller decide whether that stage of the
pipeline simply has not run yet. JSONL files are read line-by-line so a
large evasion/transaction log is never pulled fully into memory.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

JsonValue = dict[str, Any] | list[Any]


def read_json(path: Path) -> JsonValue | None:
    """Parse a JSON file, or return `None` if it is missing or malformed."""
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data: JsonValue = json.load(fh)
            return data
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def iter_jsonl(path: Path, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
    """Yield parsed rows from a JSONL file, skipping any malformed line.

    Reads the file lazily. Pass `limit` to stop after N *valid* rows without
    reading the rest of the file.
    """
    if not path.is_file():
        return
    yielded = 0
    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            if limit is not None and yielded >= limit:
                return
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yielded += 1
                yield row


def count_jsonl_rows(path: Path) -> int:
    """Count well-formed, non-empty rows without materializing them."""
    if not path.is_file():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                continue
            count += 1
    return count
