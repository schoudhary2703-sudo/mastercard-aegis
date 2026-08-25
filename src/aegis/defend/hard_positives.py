"""Promote prior Red-Team false negatives into the next training set.

Implements `docs/EVALUATION_RULES.md` SS2 ("Previous-round false negatives may
become hard positives") for the synthetic-identity bust-out family: an
already-frozen confrontation or adaptive-round artifact recorded ground-truth
`Transaction` rows that a frozen detector missed. This module re-stamps those
rows `split=train`, preserves their full provenance, and validates the two
things SS2/SS3 require before they can safely enter a retrain:

* they must not collide, by `transaction_id`, with any row already in
  validation or test (SS2: "Promoted records must be removed from every
  evaluation set they previously belonged to" - here it never overlaps
  because the source artifacts are separate Red-generated scenario files, not
  the PaySim validation/test split itself, but the check is what makes that
  a verified fact rather than an assumption);
* ground truth is copied unchanged - promotion never relabels a row based on
  what the detector predicted (`docs/EVALUATION_RULES.md` SS2/SS3).

Deliberately reads only `Transaction` records (the frozen shared contract),
never an `AttackBlueprint` or detector internals - promotion is a Blue-only
concern that happens to consume Red-Team output, not a Red/Blue integration
point requiring `loop/`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aegis.features.io import load_transactions_jsonl
from aegis.shared.contracts import Transaction
from aegis.shared.enums import DataSplit, FraudLabel

HARD_POSITIVES_FILENAME = "hard_positives.jsonl"
PROVENANCE_FILENAME = "provenance.json"

_TRANSACTION_ID_PATTERN = re.compile(r'"transaction_id":"([^"]+)"')
"""Minimal per-line extraction, mirroring `scripts/run_bustout_confrontation.py`'s
`_TRANSACTION_ID_PATTERN` - avoids building a full `Transaction` (and its
`features`/`metadata` dicts) per row just to read one string field, which
matters when the file being scanned for overlap is a multi-million-row real
PaySim split."""


class HardPositiveValidationError(ValueError):
    """Raised when a promotion input or overlap check fails."""


@dataclass(frozen=True)
class HardPositiveSource:
    """One prior confrontation or adaptive-round artifact to promote from."""

    artifact_dir: Path
    source_round: str
    """Free-form provenance label, e.g. `"round-0"`, `"adaptive-round-1"` -
    not a contract field, stored under `Transaction.metadata`."""
    transactions_filename: str = "transactions.jsonl"

    @property
    def transactions_path(self) -> Path:
        return self.artifact_dir / self.transactions_filename


@dataclass(frozen=True)
class ScenarioProvenance:
    """Per-scenario summary of what was promoted from one source."""

    source_round: str
    artifact_dir: str
    scenario_id: str
    attack_family: str
    blueprint_id: str
    generation: int
    warmup_transaction_count: int
    fraud_transaction_count: int
    fraud_transaction_ids: list[str]


@dataclass(frozen=True)
class HardPositivePromotion:
    """Result of promoting one or more sources: ready-to-train rows plus provenance."""

    transactions: list[Transaction]
    provenance: list[ScenarioProvenance]

    @property
    def fraud_count(self) -> int:
        return sum(1 for txn in self.transactions if txn.is_fraud)

    @property
    def transaction_ids(self) -> list[str]:
        return [txn.transaction_id for txn in self.transactions]

    @property
    def fraud_transaction_ids(self) -> list[str]:
        return [txn.transaction_id for txn in self.transactions if txn.is_fraud]


@dataclass(frozen=True)
class HardPositiveArtifact:
    """Paths and counts for one materialized, on-disk promotion."""

    directory: Path
    jsonl_path: Path
    provenance_path: Path
    row_count: int
    fraud_count: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def promote_hard_positives(
    sources: Sequence[HardPositiveSource], *, promoted_at: datetime | None = None
) -> HardPositivePromotion:
    """Load, validate, and re-stamp every scenario transaction from `sources`.

    Every row of each source scenario is promoted - both the fraudulent
    bust-out events (ground truth `FRAUD`, unchanged) and their legitimate
    warm-up rows. The warm-up rows are not "new positives"; they stay
    `LEGITIMATE`. They are promoted anyway because
    `aegis.features.temporal._CausalHistoryState` computes every fraud row's
    velocity/history features from exactly the rows that precede it in the
    same materialized stream - promoting the fraud rows alone would train on
    a cold-start account with no history, which is a *different*, easier
    pattern than the one that actually evaded the frozen detector.
    """
    if not sources:
        raise HardPositiveValidationError("at least one hard-positive source is required")

    stamp = promoted_at or _utcnow()
    all_transactions: list[Transaction] = []
    provenance: list[ScenarioProvenance] = []
    seen_ids: set[str] = set()

    for source in sources:
        raw = load_transactions_jsonl(source.transactions_path)
        if not raw:
            raise HardPositiveValidationError(f"{source.transactions_path} has no transactions")

        by_scenario: dict[str, list[Transaction]] = {}
        for txn in raw:
            if txn.label is FraudLabel.UNKNOWN:
                raise HardPositiveValidationError(
                    f"{source.transactions_path}: {txn.transaction_id!r} is unlabelled; "
                    "hard positives require ground truth"
                )
            if txn.scenario_id is None:
                raise HardPositiveValidationError(
                    f"{source.transactions_path}: {txn.transaction_id!r} has no scenario_id"
                )
            by_scenario.setdefault(txn.scenario_id, []).append(txn)

        for scenario_id in sorted(by_scenario):
            scenario_rows = sorted(
                by_scenario[scenario_id],
                key=lambda t: (t.timestamp, t.sequence_index or 0),
            )
            fraud_rows = [t for t in scenario_rows if t.label is FraudLabel.FRAUD]
            warmup_rows = [t for t in scenario_rows if t.label is FraudLabel.LEGITIMATE]
            if not fraud_rows:
                raise HardPositiveValidationError(
                    f"{source.transactions_path}: scenario {scenario_id!r} has no fraud rows "
                    "to promote as hard positives"
                )
            for txn in fraud_rows:
                if txn.attack_family is None or txn.blueprint_id is None or txn.generation is None:
                    raise HardPositiveValidationError(
                        f"{source.transactions_path}: fraud row {txn.transaction_id!r} lacks "
                        "attack_family/blueprint_id/generation provenance"
                    )

            promoted_rows = [
                _promote_one(txn, source=source, promoted_at=stamp) for txn in scenario_rows
            ]
            for txn in promoted_rows:
                if txn.transaction_id in seen_ids:
                    raise HardPositiveValidationError(
                        f"duplicate transaction_id across hard-positive sources: "
                        f"{txn.transaction_id!r}"
                    )
                seen_ids.add(txn.transaction_id)
            all_transactions.extend(promoted_rows)

            first_fraud = fraud_rows[0]
            provenance.append(
                ScenarioProvenance(
                    source_round=source.source_round,
                    artifact_dir=str(source.artifact_dir),
                    scenario_id=scenario_id,
                    attack_family=str(first_fraud.attack_family),
                    blueprint_id=first_fraud.blueprint_id or "",
                    generation=first_fraud.generation or 0,
                    warmup_transaction_count=len(warmup_rows),
                    fraud_transaction_count=len(fraud_rows),
                    fraud_transaction_ids=[t.transaction_id for t in fraud_rows],
                )
            )

    all_transactions.sort(key=lambda t: (t.timestamp, t.sequence_index or 0))
    return HardPositivePromotion(transactions=all_transactions, provenance=provenance)


def _promote_one(
    txn: Transaction, *, source: HardPositiveSource, promoted_at: datetime
) -> Transaction:
    """Re-stamp one transaction for training, preserving ground truth and provenance.

    Only `split` and `metadata["hardening"]` change. `label`, `attack_family`,
    `blueprint_id`, `scenario_id`, `generation`, and every payment field are
    copied through unmodified - ground truth stays whatever it already was,
    "regardless of Blue prediction".
    """
    merged_metadata = dict(txn.metadata)
    merged_metadata["hardening"] = {
        "source_round": source.source_round,
        "source_artifact_dir": str(source.artifact_dir),
        "promoted_at": promoted_at.isoformat(),
    }
    return txn.model_copy(update={"split": DataSplit.TRAIN, "metadata": merged_metadata})


def assert_no_duplicate_transaction_ids(transactions: Iterable[Transaction]) -> None:
    """Raise if any two promoted rows share a `transaction_id`."""
    seen: set[str] = set()
    for txn in transactions:
        if txn.transaction_id in seen:
            raise HardPositiveValidationError(
                f"duplicate transaction_id in promoted set: {txn.transaction_id!r}"
            )
        seen.add(txn.transaction_id)


def assert_no_id_overlap_with_jsonl(
    candidate_ids: set[str], jsonl_path: Path | str, *, label: str
) -> None:
    """Raise if any `candidate_ids` entry appears as a `transaction_id` in `jsonl_path`.

    Streams the file line-by-line with a cheap regex extraction (no
    `Transaction` construction, no full-file `set` of the other side's IDs)
    so this is safe to run against a multi-million-row real PaySim split -
    see the module docstring.
    """
    if not candidate_ids:
        return
    path = Path(jsonl_path)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            match = _TRANSACTION_ID_PATTERN.search(stripped)
            if match is None:
                msg = f"{path}: could not find transaction_id in line: {stripped[:120]!r}"
                raise HardPositiveValidationError(msg)
            found = match.group(1)
            if found in candidate_ids:
                raise HardPositiveValidationError(
                    f"hard-positive transaction_id {found!r} already present in {label} "
                    f"({path}) - promotion must not overlap an evaluation split"
                )


def write_hard_positive_artifact(
    promotion: HardPositivePromotion, output_dir: Path | str
) -> HardPositiveArtifact:
    """Write the promoted rows and their provenance manifest, refusing to overwrite."""
    destination = Path(output_dir)
    if destination.exists():
        msg = f"refusing to overwrite existing hard-positive artifact: {destination}"
        raise FileExistsError(msg)
    destination.mkdir(parents=True)

    jsonl_path = destination / HARD_POSITIVES_FILENAME
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for txn in promotion.transactions:
            handle.write(txn.to_json())
            handle.write("\n")

    provenance_path = destination / PROVENANCE_FILENAME
    manifest = {
        "row_count": len(promotion.transactions),
        "fraud_count": promotion.fraud_count,
        "fraud_transaction_ids": promotion.fraud_transaction_ids,
        "scenarios": [
            {
                "source_round": p.source_round,
                "artifact_dir": p.artifact_dir,
                "scenario_id": p.scenario_id,
                "attack_family": p.attack_family,
                "blueprint_id": p.blueprint_id,
                "generation": p.generation,
                "warmup_transaction_count": p.warmup_transaction_count,
                "fraud_transaction_count": p.fraud_transaction_count,
                "fraud_transaction_ids": p.fraud_transaction_ids,
            }
            for p in promotion.provenance
        ],
    }
    provenance_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return HardPositiveArtifact(
        directory=destination,
        jsonl_path=jsonl_path,
        provenance_path=provenance_path,
        row_count=len(promotion.transactions),
        fraud_count=promotion.fraud_count,
    )


__all__ = [
    "HARD_POSITIVES_FILENAME",
    "PROVENANCE_FILENAME",
    "HardPositiveArtifact",
    "HardPositivePromotion",
    "HardPositiveSource",
    "HardPositiveValidationError",
    "ScenarioProvenance",
    "assert_no_duplicate_transaction_ids",
    "assert_no_id_overlap_with_jsonl",
    "promote_hard_positives",
    "write_hard_positive_artifact",
]
