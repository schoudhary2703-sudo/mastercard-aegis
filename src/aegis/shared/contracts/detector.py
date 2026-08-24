"""`DetectorOutput` - the Blue Team's per-transaction verdict.

This is the only thing the rest of the system sees from a detector. No model
object, no feature matrix, no library type. Any detector - tree ensemble,
anomaly model, graph model, rule engine - produces exactly this.

`important_signals` is the bridge to the closed loop: it is what `loop/` reads
to propose parameter mutations, and it must be populated with detector-visible
signal names only (never blueprint parameter names, which would be leakage).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, model_validator

from aegis.shared.base import AegisModel
from aegis.shared.enums import FraudLabel, RecommendedAction, SignalDirection
from aegis.shared.version import CONTRACT_VERSION


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SignalContribution(AegisModel):
    """One feature's contribution to a risk score."""

    name: str = Field(..., min_length=1, description="Detector-visible feature name.")
    contribution: float = Field(
        ..., description="Signed contribution to the score; sign follows `direction`."
    )
    value: float | int | bool | str | None = Field(
        default=None, description="Observed feature value, when available."
    )
    direction: SignalDirection = Field(default=SignalDirection.NEUTRAL)
    rank: int | None = Field(default=None, ge=0, description="0 = most important.")
    description: str = Field(default="")


class DetectorOutput(AegisModel):
    """Scored verdict for a single transaction."""

    contract_version: str = Field(default=CONTRACT_VERSION)

    transaction_id: str = Field(..., min_length=1)
    risk_score: float = Field(
        ..., ge=0.0, le=1.0, description="Calibrated probability of fraud, in [0, 1]."
    )
    predicted_label: FraudLabel = Field(
        ..., description="Thresholded decision. Should not be UNKNOWN."
    )
    recommended_action: RecommendedAction = Field(...)
    important_signals: list[SignalContribution] = Field(default_factory=list)
    model_version: str = Field(..., min_length=1, description="Identifies the scoring model.")

    threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Decision threshold applied."
    )
    policy_version: str | None = Field(
        default=None, description="Version of the score-to-action policy."
    )
    latency_ms: float | None = Field(default=None, ge=0.0, description="Scoring latency.")
    scored_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_signal_ranks(self) -> DetectorOutput:
        ranks = [s.rank for s in self.important_signals if s.rank is not None]
        if len(ranks) != len(set(ranks)):
            msg = "duplicate rank values in important_signals"
            raise ValueError(msg)
        return self

    def top_signals(self, n: int = 5) -> list[SignalContribution]:
        """Return the `n` signals with the largest absolute contribution."""
        return sorted(self.important_signals, key=lambda s: abs(s.contribution), reverse=True)[:n]


class DetectorOutputBatch(AegisModel):
    """Verdicts for a batch, plus the model identity that produced them."""

    contract_version: str = Field(default=CONTRACT_VERSION)

    batch_id: str = Field(..., min_length=1)
    model_version: str = Field(..., min_length=1)
    outputs: list[DetectorOutput] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.outputs)


__all__ = [
    "DetectorOutput",
    "DetectorOutputBatch",
    "SignalContribution",
]
