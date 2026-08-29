"""Typed records for the GenAI -> deterministic-simulator handoff.

These describe what the adapter (`aegis.loop.genai_handoff`) decided and why,
and they are the schema of the persisted "GenAI-guided generation" artifact.
They live in `aegis.genai` because they are GenAI-layer vocabulary, but they
import `aegis.shared` only -- no provider, no network, no loop internals --
so the adapter can consume them without dragging provider code into `loop/`.

The provenance model is the load-bearing piece: a downstream reader may only
label a scenario "GenAI-guided" when `GenAIHandoffProvenance.is_complete` is
true, and may only call it *live* GenAI when `live` is additionally true. A
recorded replay therefore cannot be presented as a live model call at any
point downstream.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from aegis.shared.base import AegisModel
from aegis.shared.enums import AttackFamily, MutationDirection


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppliedMutation(AegisModel):
    """One mutation the adapter actually applied to the parent blueprint."""

    parameter: str = Field(..., min_length=1)
    direction: MutationDirection = Field(...)
    magnitude: float = Field(..., ge=0.0)
    from_value: float = Field(..., description="Parent blueprint's value.")
    to_value: float = Field(..., description="Child blueprint's value.")
    rationale: str = Field(default="", description="The analyst's stated reason.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RejectedMutation(AegisModel):
    """One proposal the adapter refused, and the rule that refused it.

    Rejections are recorded rather than dropped so an artifact shows what the
    model asked for *and* what the bounds allowed -- the difference is the
    evidence that the bounds are real.
    """

    parameter: str = Field(default="")
    direction: str = Field(default="")
    magnitude: float | None = Field(default=None)
    reason: str = Field(..., min_length=1)


class GenAIHandoffProvenance(AegisModel):
    """Where a GenAI-guided mutation came from, end to end."""

    genai_run_id: str = Field(default="", description="The Blind-Spot run artifact id.")
    provider: str = Field(default="")
    model: str = Field(default="")
    prompt_version: str = Field(default="")
    live: bool = Field(
        default=False, description="False for recorded/replayed reasoning. Never inferred."
    )
    genai_artifact: str = Field(default="", description="Path of the persisted GenAI run.")
    source_confrontation_id: str = Field(default="")
    source_artifact: str = Field(default="")
    detector_model_version: str = Field(
        default="", description="Detector whose failures motivated the mutation."
    )
    seed: int | None = Field(default=None, description="Deterministic mutation seed.")

    @property
    def is_complete(self) -> bool:
        """True only when every field needed to attribute the reasoning exists.

        Gate for the "GenAI-guided" label: without a run id, provider, model
        and prompt version there is nothing to audit, so the scenario is just
        a mutation, not a GenAI-guided one.
        """
        return bool(self.genai_run_id and self.provider and self.model and self.prompt_version)

    @property
    def is_live_genai(self) -> bool:
        """Complete provenance *and* a live model call."""
        return self.is_complete and self.live


class GenAIGuidedGeneration(AegisModel):
    """The persisted artifact for one GenAI-guided next generation.

    Written by the (later) generation step; read by the API. Scenario-outcome
    fields stay optional so the record can be persisted from a dry run or a
    preview before any scenario has been generated or scored.
    """

    generation_id: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=_utcnow)
    attack_family: AttackFamily | None = Field(default=None)

    provenance: GenAIHandoffProvenance = Field(...)
    blind_spot_hypothesis: str = Field(default="")
    proposed_mutation_count: int = Field(default=0, ge=0)
    applied_mutations: list[AppliedMutation] = Field(default_factory=list)
    rejected_mutations: list[RejectedMutation] = Field(default_factory=list)

    parent_blueprint_id: str = Field(default="")
    resulting_blueprint_id: str = Field(default="")
    resulting_blueprint: dict[str, Any] | None = Field(default=None)

    scenario_id: str | None = Field(default=None)
    fraud_count: int | None = Field(default=None)
    caught_count: int | None = Field(default=None)
    escaped_count: int | None = Field(default=None)
    recall: float | None = Field(default=None)
    fidelity_score: float | None = Field(default=None)
    hardest_survivor: dict[str, Any] | None = Field(default=None)

    dry_run: bool = Field(
        default=True, description="True when no scenario was generated or scored."
    )
    notes: str = Field(default="")

    @property
    def is_genai_guided(self) -> bool:
        """Only labelable as GenAI-guided with complete provenance and at
        least one mutation that actually survived the bounds check."""
        return self.provenance.is_complete and bool(self.applied_mutations)


__all__ = [
    "AppliedMutation",
    "GenAIGuidedGeneration",
    "GenAIHandoffProvenance",
    "RejectedMutation",
]
