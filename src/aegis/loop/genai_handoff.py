"""Adapter: validated GenAI blind-spot reasoning -> deterministic mutation.

This is the only place the two halves meet, and it is deliberately a thin
translation layer:

    validated BlindSpotAnalystResponse   (aegis.genai.contracts)
      -> bounds check against the parent blueprint
      -> aegis.loop.adaptive.move_parameter / build_mutated_blueprint
      -> next-generation AttackBlueprint

It lives in `loop/` because `loop/` is the only package permitted to span
boundaries (AGENTS.md SS3), and it imports **data models only** from
`aegis.genai` -- no provider, no client, no API key, no network. Swapping the
model provider cannot change anything in this file.

Two rules govern every decision here:

* **Reject, never clamp.** A proposal outside the bounds is refused and
  recorded. Silently shrinking an over-large magnitude would let the model
  widen the search space while appearing compliant on disk.
* **GenAI never supplies values, only directions.** The adapter takes the
  *direction* and *magnitude* and recomputes the new value with the same
  deterministic arithmetic the built-in optimizer uses. A structured
  `proposed_value` (a list/dict -- i.e. an attempt to hand over rows) is
  refused outright.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aegis.genai.contracts import (
    MAX_MUTATION_MAGNITUDE,
    MAX_MUTATION_PROPOSALS,
    AttackAnalystResponse,
    BlindSpotAnalystResponse,
    BoundedMutationProposal,
    SimulatorParameterProposal,
)
from aegis.genai.handoff_contracts import (
    AppliedMutation,
    AttackRecommendationPreview,
    GenAIHandoffProvenance,
    RecommendedParameter,
    RejectedMutation,
)
from aegis.loop.adaptive import AdaptiveEvolutionError, build_mutated_blueprint, move_parameter
from aegis.shared.contracts import AttackBlueprint, ParameterSpec
from aegis.shared.enums import MutationDirection, ParameterType

# The deterministic step function moves a value along a bounded numeric span.
# SET / JITTER / RESAMPLE have no such definition here, so they are refused
# rather than approximated into something the optimizer never does.
SUPPORTED_DIRECTIONS = frozenset({MutationDirection.INCREASE, MutationDirection.DECREASE})

_NUMERIC_TYPES = frozenset({ParameterType.INT, ParameterType.FLOAT, ParameterType.DURATION_SECONDS})


class GenAIHandoffError(ValueError):
    """The handoff cannot proceed at all (e.g. too many proposals)."""


@dataclass(frozen=True)
class HandoffResult:
    """Outcome of one adapter run.

    `blueprint` is populated for both real and dry runs -- a preview that did
    not compute the child blueprint would not actually preview anything. What
    `dry_run` changes is that the caller must not persist or generate from it.
    """

    blueprint: AttackBlueprint | None
    applied: list[AppliedMutation]
    rejected: list[RejectedMutation]
    provenance: GenAIHandoffProvenance
    dry_run: bool

    @property
    def accepted_any(self) -> bool:
        return bool(self.applied)

    @property
    def is_genai_guided(self) -> bool:
        """Label gate: complete provenance *and* a surviving mutation."""
        return self.provenance.is_complete and self.accepted_any


def _reject(proposal: BoundedMutationProposal, reason: str) -> RejectedMutation:
    return RejectedMutation(
        parameter=proposal.parameter,
        direction=str(proposal.direction),
        magnitude=proposal.magnitude,
        reason=reason,
    )


def _validate(
    proposal: BoundedMutationProposal, blueprint: AttackBlueprint
) -> tuple[ParameterSpec, float] | RejectedMutation:
    """Bounds-check one proposal against the parent blueprint.

    Returns the spec and magnitude to use, or the rejection that stops it.
    """
    # A structured value is an attempt to hand over data rather than a
    # direction -- the one shape that could smuggle transaction rows through.
    if isinstance(proposal.proposed_value, (list, dict)):
        return _reject(
            proposal,
            "proposed_value carries a structured payload; GenAI proposes parameter "
            "directions, the deterministic simulator produces transactions",
        )

    if proposal.direction not in SUPPORTED_DIRECTIONS:
        return _reject(
            proposal,
            f"direction {proposal.direction} is not supported by the deterministic "
            f"step function (expected one of {sorted(d.value for d in SUPPORTED_DIRECTIONS)})",
        )

    spec = blueprint.parameters.get(proposal.parameter)
    if spec is None:
        return _reject(
            proposal, f"parameter {proposal.parameter!r} is not declared on the blueprint"
        )
    if not spec.mutable:
        return _reject(proposal, f"parameter {proposal.parameter!r} is structural (mutable=False)")
    if spec.param_type not in _NUMERIC_TYPES:
        return _reject(
            proposal, f"parameter {proposal.parameter!r} is {spec.param_type}, not numeric"
        )
    if spec.minimum is None or spec.maximum is None:
        return _reject(proposal, f"parameter {proposal.parameter!r} has no declared bounds")

    magnitude = proposal.magnitude
    if magnitude is None:
        return _reject(proposal, "magnitude is required for an INCREASE/DECREASE mutation")
    # Re-checked here even though BoundedMutationProposal constrains it: a
    # caller could hand-build the object, and this is the enforcement point.
    if not 0.0 < magnitude <= MAX_MUTATION_MAGNITUDE:
        return _reject(
            proposal,
            f"magnitude {magnitude} outside (0.0, {MAX_MUTATION_MAGNITUDE}]",
        )
    return spec, magnitude


def apply_blind_spot_proposals(
    response: BlindSpotAnalystResponse,
    parent: AttackBlueprint,
    *,
    seed: int,
    provenance: GenAIHandoffProvenance,
    dry_run: bool = False,
    max_proposals: int = MAX_MUTATION_PROPOSALS,
) -> HandoffResult:
    """Turn validated blind-spot reasoning into a next-generation blueprint.

    `seed` is required and explicit: the child's identity is a hash of
    (parent, seed, changes), so the same seed and the same accepted mutations
    always reproduce the identical blueprint.

    Raises `GenAIHandoffError` only when the whole handoff is inadmissible
    (too many proposals). Individual bad proposals are rejected and reported,
    not fatal -- one unusable suggestion should not discard the rest.
    """
    if len(response.mutation_proposals) > max_proposals:
        msg = (
            f"{len(response.mutation_proposals)} mutation proposals exceeds the "
            f"maximum of {max_proposals}"
        )
        raise GenAIHandoffError(msg)

    stamped = provenance.model_copy(update={"seed": seed})

    applied: list[AppliedMutation] = []
    rejected: list[RejectedMutation] = []
    changes: dict[str, dict[str, Any]] = {}

    for proposal in response.mutation_proposals:
        outcome = _validate(proposal, parent)
        if isinstance(outcome, RejectedMutation):
            rejected.append(outcome)
            continue
        spec, magnitude = outcome
        current = spec.default
        try:
            new_value = move_parameter(spec, current, proposal.direction, magnitude)
        except AdaptiveEvolutionError as exc:
            rejected.append(_reject(proposal, str(exc)))
            continue
        if new_value == current:
            rejected.append(_reject(proposal, "mutation would not change the parameter"))
            continue

        changes[proposal.parameter] = {"from": current, "to": new_value}
        applied.append(
            AppliedMutation(
                parameter=proposal.parameter,
                direction=proposal.direction,
                magnitude=magnitude,
                from_value=float(current),
                to_value=float(new_value),
                rationale=proposal.rationale,
                confidence=proposal.confidence,
            )
        )

    blueprint: AttackBlueprint | None = None
    if changes:
        try:
            blueprint = build_mutated_blueprint(parent, changes, seed=seed)
        except AdaptiveEvolutionError as exc:
            # The deterministic path refused the combined result (e.g. an
            # exact parent clone). Nothing is applied in that case.
            rejected.append(RejectedMutation(reason=f"blueprint construction failed: {exc}"))
            return HandoffResult(
                blueprint=None,
                applied=[],
                rejected=rejected,
                provenance=stamped,
                dry_run=dry_run,
            )
        blueprint = blueprint.model_copy(
            update={
                "metadata": {
                    **blueprint.metadata,
                    "genai_guided": stamped.is_complete,
                    "genai_run_id": stamped.genai_run_id,
                    "genai_provider": stamped.provider,
                    "genai_model": stamped.model,
                    "genai_prompt_version": stamped.prompt_version,
                    "genai_live": stamped.live,
                    "source_confrontation_id": stamped.source_confrontation_id,
                    "detector_model_version": stamped.detector_model_version,
                }
            }
        )

    return HandoffResult(
        blueprint=blueprint,
        applied=applied,
        rejected=rejected,
        provenance=stamped,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Attack Analyst recommendations -- preview only
# ---------------------------------------------------------------------------
#
# The Attack Analyst recommends *parameter values* for a blueprint, which is a
# different (and looser) thing than the Blind-Spot Analyst's bounded
# directional mutations. Applying a value directly would let the model author a
# blueprint, so this function stops one step short: it reports which
# recommendations a blueprint's declared `ParameterSpec`s would accept and why
# the others would not. Nothing here generates, mutates, or persists anything.


def _check_recommendation(
    proposal: SimulatorParameterProposal, blueprint: AttackBlueprint
) -> RecommendedParameter:
    """Check one recommendation against the blueprint's declared spec."""
    spec = blueprint.parameters.get(proposal.name)
    common: dict[str, Any] = {
        "name": proposal.name,
        "recommended_value": proposal.value,
        "unit": proposal.unit,
        "rationale": proposal.rationale,
    }
    if spec is None:
        return RecommendedParameter(
            **common,
            actionable=False,
            reason=f"{proposal.name!r} is not a declared parameter on this blueprint",
        )
    declared: dict[str, Any] = {
        "current_value": spec.default,
        "minimum": spec.minimum,
        "maximum": spec.maximum,
        "param_type": str(spec.param_type),
    }
    if not spec.mutable:
        return RecommendedParameter(
            **common, **declared, actionable=False, reason="parameter is structural (mutable=False)"
        )
    value = proposal.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if spec.param_type in _NUMERIC_TYPES:
            return RecommendedParameter(
                **common,
                **declared,
                actionable=False,
                reason=f"recommended value is not numeric but the spec is {spec.param_type}",
            )
        return RecommendedParameter(**common, **declared, actionable=True)
    if spec.minimum is not None and value < spec.minimum:
        return RecommendedParameter(
            **common,
            **declared,
            actionable=False,
            reason=f"{value} is below the declared minimum {spec.minimum}",
        )
    if spec.maximum is not None and value > spec.maximum:
        return RecommendedParameter(
            **common,
            **declared,
            actionable=False,
            reason=f"{value} exceeds the declared maximum {spec.maximum}",
        )
    return RecommendedParameter(**common, **declared, actionable=True)


def preview_attack_recommendations(
    response: AttackAnalystResponse,
    blueprint: AttackBlueprint,
    *,
    genai_run_id: str = "",
) -> AttackRecommendationPreview:
    """Report which Attack Analyst recommendations a blueprint would accept.

    Preview only -- `applied` is always False. An out-of-range recommendation is
    reported with the bound it broke rather than clamped into range, which is
    the same reject-never-clamp rule the mutation path uses.
    """
    parameters = [
        _check_recommendation(proposal, blueprint)
        for proposal in response.recommended_simulator_parameters
    ]
    return AttackRecommendationPreview(
        blueprint_id=blueprint.attack_id,
        genai_run_id=genai_run_id,
        recommended_count=len(parameters),
        actionable_count=sum(1 for p in parameters if p.actionable),
        parameters=parameters,
        applied=False,
    )


__all__ = [
    "SUPPORTED_DIRECTIONS",
    "GenAIHandoffError",
    "HandoffResult",
    "apply_blind_spot_proposals",
    "preview_attack_recommendations",
]
