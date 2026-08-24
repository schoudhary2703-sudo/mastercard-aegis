"""`AttackBlueprint` - the Red Team's declarative description of an attack.

A blueprint is *data*, not code. It says what an attack looks like and which
knobs may be turned; it says nothing about how transactions are produced. That
separation is what lets the closed loop mutate an attack (see
`EvasionFeedback`) without touching generator internals.

Ownership: `identify/` authors blueprints, `generate/` consumes them, `loop/`
mutates them. `defend/` must never read a blueprint - doing so is target
leakage (see docs/EVALUATION_RULES.md).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator, model_validator

from aegis.shared.base import AegisModel
from aegis.shared.enums import AttackFamily, Channel, ParameterType
from aegis.shared.version import CONTRACT_VERSION


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParameterSpec(AegisModel):
    """Declaration of one tunable knob on a blueprint.

    The spec constrains what `loop/` is allowed to propose and what
    `generate/` is allowed to accept. A parameter with `mutable=False` is
    structural and must not be changed by the optimizer.
    """

    name: str = Field(..., min_length=1, description="Parameter key.")
    param_type: ParameterType = Field(..., description="Declared value type.")
    default: Any = Field(default=None, description="Value used when unspecified.")
    description: str = Field(default="", description="What the knob controls.")
    minimum: float | None = Field(default=None, description="Inclusive lower bound.")
    maximum: float | None = Field(default=None, description="Inclusive upper bound.")
    choices: list[Any] | None = Field(
        default=None, description="Allowed values for categorical parameters."
    )
    mutable: bool = Field(
        default=True, description="Whether the closed loop may mutate this parameter."
    )
    unit: str | None = Field(default=None, description="Unit hint, e.g. 'seconds', 'USD'.")

    @model_validator(mode="after")
    def _check_bounds(self) -> ParameterSpec:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            msg = f"parameter {self.name!r}: minimum {self.minimum} exceeds maximum {self.maximum}"
            raise ValueError(msg)
        return self


class BehavioralStep(AegisModel):
    """One step in the attack's behavioural / temporal sequence.

    Steps are ordered by `order` and positioned in time by
    `offset_seconds` relative to the start of the scenario, not by absolute
    timestamps - a blueprint must stay reusable across time windows.
    """

    step_id: str = Field(..., min_length=1, description="Unique within the blueprint.")
    order: int = Field(..., ge=0, description="Execution order within the sequence.")
    action: str = Field(
        ..., min_length=1, description="What happens, e.g. 'open_account', 'micro_deposit'."
    )
    description: str = Field(default="", description="Human-readable intent of the step.")
    channel: Channel | None = Field(default=None, description="Channel this step uses.")
    offset_seconds: float = Field(
        default=0.0, ge=0.0, description="Delay from scenario start, in seconds."
    )
    repeat: int = Field(default=1, ge=1, description="How many times the step repeats.")
    amount_policy: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form amount rule, e.g. {'distribution': 'lognormal', 'mu': 3.1}.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Step-local parameter overrides."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class RealismConstraints(AegisModel):
    """Bounds that generated traffic must respect to stay plausible.

    Violations are measured by fidelity metrics in `EvaluationResult`. An attack
    that evades detection by breaking realism is not a finding, it is a bug.
    """

    min_amount: float | None = Field(default=None, ge=0.0)
    max_amount: float | None = Field(default=None, ge=0.0)
    allowed_currencies: list[str] = Field(
        default_factory=list, description="ISO-4217 codes; empty means unrestricted."
    )
    allowed_channels: list[Channel] = Field(
        default_factory=list, description="Empty means unrestricted."
    )
    max_transactions_per_account_per_day: int | None = Field(default=None, ge=1)
    max_accounts_involved: int | None = Field(default=None, ge=1)
    min_sequence_length: int | None = Field(default=None, ge=1)
    max_sequence_length: int | None = Field(default=None, ge=1)
    active_hours_utc: list[int] = Field(
        default_factory=list, description="Permitted hours 0-23; empty means unrestricted."
    )
    custom: dict[str, Any] = Field(
        default_factory=dict, description="Additional domain constraints."
    )

    @field_validator("active_hours_utc")
    @classmethod
    def _check_hours(cls, value: list[int]) -> list[int]:
        for hour in value:
            if not 0 <= hour <= 23:
                msg = f"active_hours_utc entries must be in 0..23, got {hour}"
                raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _check_ranges(self) -> RealismConstraints:
        if (
            self.min_amount is not None
            and self.max_amount is not None
            and self.min_amount > self.max_amount
        ):
            msg = "min_amount exceeds max_amount"
            raise ValueError(msg)
        if (
            self.min_sequence_length is not None
            and self.max_sequence_length is not None
            and self.min_sequence_length > self.max_sequence_length
        ):
            msg = "min_sequence_length exceeds max_sequence_length"
            raise ValueError(msg)
        return self


class AttackBlueprint(AegisModel):
    """Declarative, versioned description of one attack.

    A blueprint plus a `GenerationConfig` is the complete input to any
    generator. `parent_blueprint_id` and `generation` make lineage explicit so
    that a mutated attack can always be traced back to its ancestor.
    """

    contract_version: str = Field(default=CONTRACT_VERSION)

    attack_id: str = Field(..., min_length=1, description="Stable identifier.")
    attack_family: AttackFamily = Field(..., description="One of the three in-scope families.")
    name: str = Field(default="", description="Short human label.")
    description: str = Field(..., min_length=1, description="What the attack does.")
    objective: str = Field(..., min_length=1, description="What the attacker is trying to achieve.")

    target_features: list[str] = Field(
        default_factory=list,
        description="Detector-visible features the attack intends to influence.",
    )
    sequence: list[BehavioralStep] = Field(
        default_factory=list, description="Ordered behavioural pattern."
    )
    parameters: dict[str, ParameterSpec] = Field(
        default_factory=dict, description="Tunable knobs, keyed by parameter name."
    )
    realism_constraints: RealismConstraints = Field(default_factory=RealismConstraints)

    parent_blueprint_id: str | None = Field(
        default=None, description="Blueprint this one was mutated from, if any."
    )
    generation: int = Field(default=0, ge=0, description="Closed-loop generation index.")
    source: str = Field(
        default="manual",
        description="Provenance, e.g. 'manual', 'threat_intel', 'llm_proposed', 'mutation'.",
    )
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_sequence(self) -> AttackBlueprint:
        step_ids = [step.step_id for step in self.sequence]
        if len(step_ids) != len(set(step_ids)):
            msg = "duplicate step_id values in sequence"
            raise ValueError(msg)
        for key, spec in self.parameters.items():
            if key != spec.name:
                msg = f"parameters key {key!r} does not match ParameterSpec.name {spec.name!r}"
                raise ValueError(msg)
        return self

    def ordered_sequence(self) -> list[BehavioralStep]:
        """Return the behavioural steps sorted by `order` then `offset_seconds`."""
        return sorted(self.sequence, key=lambda step: (step.order, step.offset_seconds))

    def mutable_parameters(self) -> dict[str, ParameterSpec]:
        """Return only the parameters the closed loop is permitted to mutate."""
        return {name: spec for name, spec in self.parameters.items() if spec.mutable}

    def default_parameters(self) -> dict[str, Any]:
        """Return the default value of every declared parameter."""
        return {name: spec.default for name, spec in self.parameters.items()}


__all__ = [
    "AttackBlueprint",
    "BehavioralStep",
    "ParameterSpec",
    "RealismConstraints",
]
