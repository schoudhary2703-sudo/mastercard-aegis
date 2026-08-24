"""`Transaction` - the single canonical record exchanged by every module.

Real and synthetic transactions use the same type. The only difference is
`is_synthetic` and the provenance fields (`scenario_id`, `blueprint_id`,
`step_id`), which exist so a synthetic record can always be traced back to the
attack that produced it.

Schema-coupling rule: derived behavioural and network features go into the open
`features` map, never into new top-level fields. That keeps `features/` and
`defend/` free to evolve their feature sets without a contract change and
without the Red Team needing to know they exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator, model_validator

from aegis.shared.base import AegisModel
from aegis.shared.enums import AttackFamily, Channel, DataSplit, FraudLabel, TransactionType
from aegis.shared.types import FeatureValue
from aegis.shared.version import CONTRACT_VERSION

FEATURE_NAMESPACE_SEPARATOR = "."
"""Feature keys are namespaced, e.g. 'temporal.velocity_1h', 'graph.pagerank'."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Transaction(AegisModel):
    """One payment event, real or simulated."""

    contract_version: str = Field(default=CONTRACT_VERSION)

    # --- core payment fields -------------------------------------------------
    transaction_id: str = Field(..., min_length=1)
    timestamp: datetime = Field(..., description="Event time; timezone-aware, UTC preferred.")
    source_account_id: str = Field(..., min_length=1)
    destination_account_id: str | None = Field(
        default=None, description="None for cash-out / merchant-terminal events."
    )
    amount: float = Field(..., ge=0.0, description="Transaction amount in `currency`.")
    currency: str = Field(default="USD", description="ISO-4217 alpha-3 code.")
    transaction_type: TransactionType = Field(default=TransactionType.TRANSFER)
    channel: Channel = Field(default=Channel.UNKNOWN)

    # --- optional payment context -------------------------------------------
    merchant_id: str | None = Field(default=None)
    merchant_category: str | None = Field(default=None, description="MCC or category label.")
    device_id: str | None = Field(default=None)
    country: str | None = Field(default=None, description="ISO-3166 alpha-2 code.")

    # --- balances (PaySim-shaped, optional) ---------------------------------
    source_balance_before: float | None = Field(default=None)
    source_balance_after: float | None = Field(default=None)
    destination_balance_before: float | None = Field(default=None)
    destination_balance_after: float | None = Field(default=None)

    # --- labelling ----------------------------------------------------------
    label: FraudLabel = Field(
        default=FraudLabel.UNKNOWN,
        description="Ground truth. UNKNOWN means unlabelled, not legitimate.",
    )
    attack_family: AttackFamily | None = Field(
        default=None, description="Set only when the record belongs to an attack."
    )

    # --- simulation provenance ----------------------------------------------
    is_synthetic: bool = Field(default=False)
    scenario_id: str | None = Field(
        default=None, description="Groups the transactions of one simulated scenario."
    )
    blueprint_id: str | None = Field(default=None, description="Blueprint that produced this.")
    step_id: str | None = Field(default=None, description="Blueprint step that produced this.")
    sequence_index: int | None = Field(
        default=None, ge=0, description="Position within the scenario sequence."
    )
    generation: int | None = Field(
        default=None, ge=0, description="Closed-loop generation that produced this."
    )

    # --- partitioning -------------------------------------------------------
    split: DataSplit = Field(
        default=DataSplit.UNASSIGNED, description="Assigned by the evaluation harness only."
    )

    # --- open extension points ----------------------------------------------
    features: dict[str, FeatureValue] = Field(
        default_factory=dict,
        description="Derived behavioural / network features, namespaced by producer.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, value: str) -> str:
        code = value.upper()
        if len(code) != 3 or not code.isalpha():
            msg = f"currency must be an ISO-4217 alpha-3 code, got {value!r}"
            raise ValueError(msg)
        return code

    @field_validator("timestamp")
    @classmethod
    def _ensure_tz(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    @model_validator(mode="after")
    def _check_label_consistency(self) -> Transaction:
        if self.attack_family is not None and self.label is FraudLabel.LEGITIMATE:
            msg = "attack_family must be None when label is LEGITIMATE"
            raise ValueError(msg)
        return self

    @property
    def is_fraud(self) -> bool:
        """True only for an explicit FRAUD label. UNKNOWN is not fraud."""
        return self.label is FraudLabel.FRAUD

    def with_features(self, namespace: str, values: dict[str, FeatureValue]) -> Transaction:
        """Return a copy with `values` merged into `features` under `namespace`.

        Feature producers must namespace their keys ('temporal', 'graph',
        'velocity', ...) so two extractors cannot silently overwrite each other.
        """
        merged = dict(self.features)
        for key, value in values.items():
            merged[f"{namespace}{FEATURE_NAMESPACE_SEPARATOR}{key}"] = value
        return self.model_copy(update={"features": merged})

    def to_flat_record(self) -> dict[str, Any]:
        """Flatten to a single dict suitable for a DataFrame row.

        `features` keys are lifted to the top level; every other field keeps its
        name. Enum fields become their primitive values.
        """
        payload = self.model_dump(mode="json", exclude={"features"})
        payload.update(self.features)
        return payload


class TransactionBatch(AegisModel):
    """A generated or loaded set of transactions plus its provenance.

    This is the return type of `BaseGenerator.generate`. `seed` and
    `generator_version` are mandatory-by-convention for reproducibility: a batch
    that cannot be regenerated is not a valid experimental artifact.
    """

    contract_version: str = Field(default=CONTRACT_VERSION)

    batch_id: str = Field(..., min_length=1)
    transactions: list[Transaction] = Field(default_factory=list)
    blueprint_id: str | None = Field(default=None)
    attack_family: AttackFamily | None = Field(default=None)
    scenario_ids: list[str] = Field(default_factory=list)
    generator_name: str = Field(default="", description="Generator implementation name.")
    generator_version: str = Field(default="", description="Generator implementation version.")
    seed: int | None = Field(default=None, description="Seed used; required for reproducibility.")
    generation: int | None = Field(default=None, ge=0)
    split: DataSplit = Field(default=DataSplit.UNASSIGNED)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.transactions)

    @property
    def fraud_count(self) -> int:
        """Number of explicitly fraud-labelled transactions in the batch."""
        return sum(1 for txn in self.transactions if txn.is_fraud)

    def to_records(self) -> list[dict[str, Any]]:
        """Flatten every transaction; feed straight into `pandas.DataFrame`."""
        return [txn.to_flat_record() for txn in self.transactions]


__all__ = [
    "FEATURE_NAMESPACE_SEPARATOR",
    "Transaction",
    "TransactionBatch",
]
