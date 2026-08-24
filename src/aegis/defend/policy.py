"""Score-to-action policy.

Turning a calibrated risk score into `approve / step_up / review / decline` is a
*business* decision, not a model decision. Keeping it out of the detector means
the policy can be re-tuned, versioned and evaluated without retraining, and two
detectors can be compared under an identical policy.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from aegis.shared.base import AegisModel
from aegis.shared.enums import RecommendedAction


class ActionPolicy(AegisModel):
    """Monotonic banding of risk score into a recommended action.

    Bands are half-open and ascending::

        [0, step_up)   -> approve
        [step_up, review)   -> step_up
        [review, decline)   -> review
        [decline, 1]        -> decline

    The default thresholds are placeholders. Tuning them is Blue Team work and
    must be justified against a fixed false-positive budget.
    """

    policy_version: str = Field(default="policy-v0")
    step_up_at: float = Field(default=0.50, ge=0.0, le=1.0)
    review_at: float = Field(default=0.80, ge=0.0, le=1.0)
    decline_at: float = Field(default=0.95, ge=0.0, le=1.0)
    label_threshold: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Score at or above which `predicted_label` becomes FRAUD.",
    )

    @model_validator(mode="after")
    def _check_monotonic(self) -> ActionPolicy:
        if not self.step_up_at <= self.review_at <= self.decline_at:
            msg = "thresholds must satisfy step_up_at <= review_at <= decline_at"
            raise ValueError(msg)
        return self

    def action_for(self, risk_score: float) -> RecommendedAction:
        """Map a risk score in [0, 1] to a recommended action."""
        if not 0.0 <= risk_score <= 1.0:
            msg = f"risk_score must be in [0, 1], got {risk_score}"
            raise ValueError(msg)
        if risk_score >= self.decline_at:
            return RecommendedAction.DECLINE
        if risk_score >= self.review_at:
            return RecommendedAction.REVIEW
        if risk_score >= self.step_up_at:
            return RecommendedAction.STEP_UP
        return RecommendedAction.APPROVE


DEFAULT_ACTION_POLICY = ActionPolicy()
"""Shared default so every detector starts from the same operating point."""

__all__ = ["DEFAULT_ACTION_POLICY", "ActionPolicy"]
