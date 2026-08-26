"""Typed request/response models for the two GenAI reasoning stages.

These are `aegis.genai`-local models, not `aegis.shared.contracts` additions:
GenAI reasoning is an input *to* the Red Team's blueprint authoring, not a new
cross-team channel, so nothing here changes `CONTRACT_VERSION`. Where a field
maps onto an existing contract concept it reuses that contract's enum
(`AttackFamily`, `MutationDirection`) so a proposal can be handed to
`identify/` or `loop/` without a translation layer.

The critical design rule this file enforces: **a response never contains
transaction rows.** The attack analyst returns simulator *parameters* and the
blind-spot analyst returns bounded parameter *mutations*. Producing the actual
numeric transactions remains the deterministic simulators' job
(`aegis.generate`), which is what keeps every generated corpus reproducible
from a seed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator, model_validator

from aegis.shared.base import AegisModel
from aegis.shared.enums import AttackFamily, MutationDirection

MAX_MUTATION_MAGNITUDE: float = 0.25
"""Ceiling on any single proposed relative parameter step.

Matches the top of `aegis.loop.adaptive._MAGNITUDE_SCHEDULE` (0.24), so a
GenAI proposal can never ask for a larger jump than the deterministic
optimizer would take on its own.
"""

MAX_MUTATION_PROPOSALS: int = 6
"""Upper bound on proposals per blind-spot run, so one call cannot enumerate
an unbounded search space."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# stage 1 -- attack analyst
# ---------------------------------------------------------------------------


class SimulatorParameterProposal(AegisModel):
    """One recommended knob setting for a deterministic simulator.

    A *value*, never a transaction. `aegis.generate` decides whether the value
    is admissible and what traffic it produces.
    """

    name: str = Field(..., min_length=1, description="Simulator parameter name.")
    value: float | int | bool | str = Field(..., description="Recommended value.")
    rationale: str = Field(..., min_length=1, description="Why this value, in one sentence.")
    unit: str | None = Field(default=None, description="Unit hint, e.g. 'hours', 'USD'.")


class AttackAnalystRequest(AegisModel):
    """Everything the attack analyst is allowed to see.

    Deliberately narrow: researched taxonomy text, the payment context, and
    the constraints it must respect. No detector internals, no labels, no
    PaySim rows.
    """

    scenario_name: str = Field(..., min_length=1, description="Taxonomy entry being analyzed.")
    research_summary: str = Field(
        ..., min_length=1, description="Researched fraud/taxonomy description."
    )
    payment_context: str = Field(
        ..., min_length=1, description="The payment world the attack operates in."
    )
    known_constraints: list[str] = Field(
        default_factory=list, description="Hard limits the analyst must respect."
    )
    candidate_families: list[AttackFamily] = Field(
        default_factory=lambda: list(AttackFamily),
        description="Families the analyst may choose from; the scope is fixed at three.",
    )
    available_simulator_parameters: list[str] = Field(
        default_factory=list,
        description="Parameter names the deterministic simulator actually exposes.",
    )


class AttackAnalystResponse(AegisModel):
    """Structured output of the attack-ideation stage."""

    attack_family: AttackFamily = Field(..., description="One of the three in-scope families.")
    attack_hypothesis: str = Field(
        ..., min_length=1, description="The concrete attack being proposed."
    )
    genai_enablement: str = Field(
        ...,
        min_length=1,
        description="How generative AI enables or amplifies this fraud in the real world.",
    )
    payment_system_assumptions: list[str] = Field(
        default_factory=list, description="What must be true of the payment system."
    )
    observable_signals: list[str] = Field(
        default_factory=list, description="Detector-visible signals this attack would move."
    )
    recommended_simulator_parameters: list[SimulatorParameterProposal] = Field(
        default_factory=list, description="Parameter settings for the deterministic simulator."
    )
    realism_risks: list[str] = Field(
        default_factory=list, description="Ways this could produce implausible traffic."
    )
    safety_constraints: list[str] = Field(
        default_factory=list, description="Limits that keep this a defensive simulation."
    )
    confidence: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_no_transactions(self) -> AttackAnalystResponse:
        """Structural guard for the "GenAI never emits transaction rows" rule.

        A model that tries to hand back concrete rows instead of parameters
        would have to smuggle them through a declared field; `extra="forbid"`
        blocks an undeclared one, and this blocks the obvious in-band attempt.
        """
        names = {p.name.lower() for p in self.recommended_simulator_parameters}
        forbidden = {"transactions", "rows", "transaction_rows", "records"}
        overlap = names & forbidden
        if overlap:
            msg = (
                f"simulator parameter names {sorted(overlap)} look like transaction payloads; "
                "GenAI proposes parameters, the deterministic simulator produces rows"
            )
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# stage 2 -- blind-spot analyst
# ---------------------------------------------------------------------------


class BoundedMutationProposal(AegisModel):
    """One proposed, bounded change to a declared mutable blueprint parameter.

    Mirrors `aegis.shared.contracts.feedback.ParameterMutation` field-for-field
    where they overlap, so `loop/` can consume a proposal without a mapping
    step -- but adds a hard magnitude ceiling that the shared contract leaves
    to the caller.
    """

    parameter: str = Field(..., min_length=1, description="Must name a mutable ParameterSpec.")
    direction: MutationDirection = Field(...)
    proposed_value: Any = Field(
        default=None, description="Required when direction is SET; advisory otherwise."
    )
    magnitude: float | None = Field(
        default=None,
        ge=0.0,
        le=MAX_MUTATION_MAGNITUDE,
        description=f"Relative step size, capped at {MAX_MUTATION_MAGNITUDE}.",
    )
    rationale: str = Field(..., min_length=1, description="Which observed failure motivates this.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_set_has_value(self) -> BoundedMutationProposal:
        if self.direction is MutationDirection.SET and self.proposed_value is None:
            msg = "proposed_value is required when direction is SET"
            raise ValueError(msg)
        return self


class BlindSpotAnalystRequest(AegisModel):
    """Real, already-persisted evidence of a detector failure.

    Every field here is copied out of an artifact the pipeline already wrote
    -- this stage never re-scores anything and never sees model internals
    beyond the detector-visible signals the Blue Team already published.
    """

    blueprint_id: str = Field(..., min_length=1)
    attack_family: AttackFamily = Field(...)
    detector_model_version: str = Field(..., min_length=1)
    detector_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    missed_transaction_count: int = Field(..., ge=0)
    caught_transaction_count: int = Field(default=0, ge=0)
    observed_risk_scores: list[float] = Field(
        default_factory=list, description="Risk scores of the evasions, as scored."
    )
    important_signals: list[str] = Field(
        default_factory=list, description="Detector-visible signal names that drove the scores."
    )
    fidelity_score: float | None = Field(default=None, ge=0.0, le=1.0)
    mutable_parameters: list[str] = Field(
        default_factory=list,
        description="Parameters the blueprint declares mutable; proposals are limited to these.",
    )
    detector_context: str = Field(
        default="", description="What the detector is and what it was trained on."
    )


class BlindSpotAnalystResponse(AegisModel):
    """Structured output of the detector-blind-spot stage."""

    blind_spot_hypothesis: str = Field(
        ..., min_length=1, description="The likely gap in the detector."
    )
    evidence: list[str] = Field(
        default_factory=list, description="Which observed facts support the hypothesis."
    )
    mutation_proposals: list[BoundedMutationProposal] = Field(
        default_factory=list, max_length=MAX_MUTATION_PROPOSALS
    )
    expected_trade_offs: list[str] = Field(
        default_factory=list, description="What each proposal likely costs (e.g. realism)."
    )
    safety_constraints: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("mutation_proposals")
    @classmethod
    def _check_unique_parameters(
        cls, value: list[BoundedMutationProposal]
    ) -> list[BoundedMutationProposal]:
        names = [p.parameter for p in value]
        if len(names) != len(set(names)):
            msg = "duplicate parameter names in mutation_proposals"
            raise ValueError(msg)
        return value


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------


class GenAIProvenance(AegisModel):
    """Who produced a GenAI response, with what, and whether it was live.

    `live` is the field that makes the judge-facing claim auditable: a
    recorded/offline run is persisted with `live=False` and can never be
    mistaken for a fresh model call.
    """

    provider: str = Field(..., min_length=1, description="e.g. 'anthropic', 'recorded'.")
    model: str = Field(..., min_length=1)
    prompt_version: str = Field(..., min_length=1)
    live: bool = Field(..., description="False for replayed/recorded responses.")
    request_id: str | None = Field(default=None, description="Provider-side request id.")
    latency_ms: float | None = Field(default=None, ge=0.0)
    attempts: int = Field(default=1, ge=1)
    source_artifacts: list[str] = Field(
        default_factory=list, description="Artifacts this reasoning was derived from."
    )


class GenAIRunArtifact(AegisModel):
    """One persisted GenAI run: inputs, provenance, and outcome.

    Written for successes *and* failures. A failed run keeps `response=None`,
    `schema_valid=False` and a populated `failure` -- so a missing analysis is
    visibly a failure on disk rather than an absent file.
    """

    run_id: str = Field(..., min_length=1)
    stage: str = Field(..., min_length=1, description="'attack_analyst' | 'blind_spot_analyst'.")
    created_at: datetime = Field(default_factory=_utcnow)
    provenance: GenAIProvenance = Field(...)
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] | None = Field(default=None)
    schema_valid: bool = Field(...)
    failure: str | None = Field(default=None)
    raw_response_text: str | None = Field(
        default=None, description="Kept when validation failed, for auditability."
    )


__all__ = [
    "MAX_MUTATION_MAGNITUDE",
    "MAX_MUTATION_PROPOSALS",
    "AttackAnalystRequest",
    "AttackAnalystResponse",
    "BlindSpotAnalystRequest",
    "BlindSpotAnalystResponse",
    "BoundedMutationProposal",
    "GenAIProvenance",
    "GenAIRunArtifact",
    "SimulatorParameterProposal",
]
