"""Loading canonical `Transaction` records from processed JSONL artifacts.

Reads the output of `scripts/prepare_paysim.py` (or any producer of the same
shape): one JSON-serialized `Transaction` per line. Validation happens through
the frozen contract itself, so a schema drift between the preparation
pipeline and this loader is a loud `ValidationError`, not a silent mismatch.
"""

from __future__ import annotations

from pathlib import Path

from aegis.shared.contracts import Transaction


def load_transactions_jsonl(path: Path | str) -> list[Transaction]:
    """Read one `Transaction` per non-blank line of a JSONL file."""
    resolved = Path(path)
    transactions: list[Transaction] = []
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            transactions.append(Transaction.model_validate_json(stripped))
    return transactions


__all__ = ["load_transactions_jsonl"]
