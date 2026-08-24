"""`EvasionFeedback` - the return path from Blue Team to Red Team.

This is the closed loop's only channel. `defend/` and `evaluate/` produce it;
`loop/` turns it into blueprint mutations; `generate/` consumes the mutated
blueprint. Neither team imports the other's code to make this work.

Leakage boundary: `important_signals` carries detector-visible *feature* names
and attributions. It must never carry model internals, blueprint parameters the
detector could not have observed, or ground-truth labels of unscored data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, model_validator

from aegis.shared.base import AegisModel
from aegis.shared.contracts.detector import SignalContribution
from aegis.shared.enums import AttackFamily, MutationDirection
from aegis.shared.version import CONTRACT_VERSION


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParameterMutation(AegisModel):
    """A proposed change to one blueprint parameter.

    A proposal is advisory. `loop/` decides whether to apply it, and
    `AttackBlueprint.mutable_parameters()` decides whether it is even legal.
    """

    parameter: str = Field(..., min_length=1, description="Must name a declared ParameterSpec.")
    direction: MutationDirection = Field(...)
    current_value: Any = Field(default=None)
    proposed_value: Any = Field(
        default=None, description="Required when direction is SET; advisory otherwise."
    )
    magnitude: float | None = Field(
        default=None, description="Relative step size for INCREASE / DECREASE / JITTER."
    )
    rationale: str = Field(default="", description="Which signal motivated this change.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    priority: int = Field(default=0, ge=0, description="0 = apply first.")

    @model_validator(mode="after")
    def _check_set_has_value(self) -> ParameterMutation:
        if self.direction is MutationDirection.SET and self.proposed_value is None:
            msg = "proposed_value is required when direction is SET"
            raise ValueError(msg)
        return self


class EvasionFeedback(AegisModel):
    """Outcome of one attack attempt against one detector version."""

    contract_version: str = Field(default=CONTRACT_VERSION)

    feedback_id: str = Field(..., min_length=1)
    attack_family: AttackFamily = Field(...)
    attack_id: str | None = Field(default=None)
    blueprint_id: str | None = Field(default=None)
    scenario_id: str | None = Field(default=None)

    original_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Parameter values the attempt actually used."
    )

    detector_score: float = Field(
        ..., ge=0.0, le=1.0, description="Risk score assigned to the attempt."
    )
    detector_model_version: str = Field(..., min_length=1)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    evaded: bool = Field(..., description="True when the attack was not caught.")

    realism_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fidelity of the attempt; low realism invalidates an evasion.",
    )
    important_signals: list[SignalContribution] = Field(
        default_factory=list, description="Detector-visible signals that drove the score."
    )
    suggested_mutations: list[ParameterMutation] = Field(default_factory=list)

    round_index: int = Field(default=0, ge=0, description="Closed-loop round.")
    generation: int = Field(default=0, ge=0, description="Blueprint generation of the attempt.")
    transaction_ids: list[str] = Field(
        default_factory=list, description="Transactions this feedback summarizes."
    )
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_mutation_priorities(self) -> EvasionFeedback:
        names = [m.parameter for m in self.suggested_mutations]
        if len(names) != len(set(names)):
            msg = "duplicate parameter names in suggested_mutations"
            raise ValueError(msg)
        return self

    @property
    def is_credible_evasion(self) -> bool:
        """True when the attack evaded *and* realism was measured and acceptable.

        An evasion with an unmeasured or poor realism score is not counted; see
        docs/EVALUATION_RULES.md.
        """
        return self.evaded and self.realism_score is not None and self.realism_score >= 0.5

    def ordered_mutations(self) -> list[ParameterMutation]:
        """Return proposed mutations by priority, then descending confidence."""
        return sorted(self.suggested_mutations, key=lambda m: (m.priority, -m.confidence))


__all__ = [
    "EvasionFeedback",
    "ParameterMutation",
]
