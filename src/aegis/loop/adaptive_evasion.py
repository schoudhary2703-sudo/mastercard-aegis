"""One-step bounded adaptation for the synthetic adaptive-evasion family."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from pydantic import Field

from aegis.shared.base import AegisModel
from aegis.shared.contracts import (
    AttackBlueprint,
    DetectorOutput,
    EvasionFeedback,
    ParameterMutation,
    SignalContribution,
    TransactionBatch,
)
from aegis.shared.enums import (
    AttackFamily,
    FraudLabel,
    MutationDirection,
    ParameterType,
)

_PARAMETER_RELATION: dict[str, tuple[str, int]] = {
    "temporal.amount": ("fraud_amount_mean", 1),
    "temporal.amount_deviation_from_source_history": ("history_blend_ratio", -1),
    "temporal.source_txn_count_before": ("context_transaction_count", 1),
    "temporal.source_velocity_1h": ("inter_event_delay_hours", -1),
    "temporal.destination_velocity_1h": ("destination_diversity", -1),
    "temporal.seconds_since_source_previous_txn": ("inter_event_delay_hours", 1),
    "temporal.source_avg_amount_before": ("context_amount_mean", 1),
}
_FALLBACK_PARAMETERS = (
    "history_blend_ratio",
    "inter_event_delay_hours",
    "destination_diversity",
)
_STEP_FRACTION = 0.12


class AdaptiveEvasionLoopError(ValueError):
    """Raised when feedback cannot support a safe one-step mutation."""


class GuidedAdaptation(AegisModel):
    """Traceable parent-to-child mutation produced only from EvasionFeedback."""

    adaptation_id: str = Field(..., min_length=1)
    seed: int
    parent_blueprint_id: str = Field(..., min_length=1)
    child_blueprint: AttackBlueprint
    feedback_ids: list[str] = Field(..., min_length=1)
    mutations: list[ParameterMutation] = Field(..., min_length=1)
    changed_parameters: dict[str, dict[str, Any]]
    evidence_basis: str = Field(..., min_length=1)
    bounded_search: bool = True
    candidate_count: int = Field(default=1, ge=1, le=1)


def build_adaptive_evasion_feedback(
    *,
    batch: TransactionBatch,
    blueprint: AttackBlueprint,
    outputs: Sequence[DetectorOutput],
) -> list[EvasionFeedback]:
    """Translate credible false negatives into the frozen feedback contract."""
    if batch.attack_family is not AttackFamily.ADAPTIVE_DETECTOR_EVASION:
        raise AdaptiveEvasionLoopError("feedback batch has the wrong attack family")
    if batch.blueprint_id != blueprint.attack_id or batch.generation is None:
        raise AdaptiveEvasionLoopError("feedback batch does not match blueprint lineage")
    by_id = {output.transaction_id: output for output in outputs}
    if len(by_id) != len(outputs) or set(by_id) != {
        transaction.transaction_id for transaction in batch.transactions
    }:
        raise AdaptiveEvasionLoopError("detector outputs do not align with feedback batch")
    models = {output.model_version for output in outputs}
    thresholds = {output.threshold for output in outputs}
    if len(models) != 1 or len(thresholds) != 1:
        raise AdaptiveEvasionLoopError("feedback requires one frozen model and threshold")
    fidelity_payload = batch.metadata.get("fidelity")
    if not isinstance(fidelity_payload, dict):
        raise AdaptiveEvasionLoopError("feedback batch has no fidelity summary")
    fidelity_value = fidelity_payload.get("overall_fidelity_score")
    if isinstance(fidelity_value, bool) or not isinstance(fidelity_value, (int, float)):
        raise AdaptiveEvasionLoopError("feedback batch has no numeric fidelity score")
    fidelity = float(fidelity_value)
    feedback: list[EvasionFeedback] = []
    for transaction in batch.transactions:
        output = by_id[transaction.transaction_id]
        if not transaction.is_fraud or output.predicted_label is FraudLabel.FRAUD:
            continue
        if transaction.scenario_id is None:
            raise AdaptiveEvasionLoopError("fraud feedback transaction has no scenario")
        identity = json.dumps(
            {
                "batch": batch.batch_id,
                "transaction": transaction.transaction_id,
                "model": output.model_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        feedback.append(
            EvasionFeedback(
                feedback_id=f"adaptive-feedback-{digest}",
                attack_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
                attack_id=blueprint.attack_id,
                blueprint_id=blueprint.attack_id,
                scenario_id=transaction.scenario_id,
                original_parameters=blueprint.default_parameters(),
                detector_score=output.risk_score,
                detector_model_version=output.model_version,
                threshold=output.threshold,
                evaded=True,
                realism_score=fidelity,
                important_signals=_serializable_signals(output.important_signals),
                round_index=batch.generation,
                generation=batch.generation,
                transaction_ids=[transaction.transaction_id],
                created_at=transaction.timestamp,
                metadata={
                    "source_batch_id": batch.batch_id,
                    "ground_truth_label": FraudLabel.FRAUD.name,
                    "feedback_channel": "EvasionFeedback",
                },
            )
        )
    return feedback


def adapt_blueprint_from_evasions(
    parent: AttackBlueprint,
    feedback: Sequence[EvasionFeedback],
    *,
    seed: int,
) -> GuidedAdaptation:
    """Apply at most one deterministic, fixed-budget child mutation."""
    if parent.attack_family is not AttackFamily.ADAPTIVE_DETECTOR_EVASION:
        raise AdaptiveEvasionLoopError("parent is not an adaptive detector-evasion blueprint")
    credible = [item for item in feedback if item.is_credible_evasion]
    if not credible:
        raise AdaptiveEvasionLoopError("at least one credible evasion is required")
    if any(item.attack_family is not parent.attack_family for item in credible):
        raise AdaptiveEvasionLoopError("feedback mixes attack families")
    mutable = parent.mutable_parameters()
    votes: dict[str, float] = defaultdict(float)
    signals_by_parameter: dict[str, set[str]] = defaultdict(set)
    for item in credible:
        realism = 0.0 if item.realism_score is None else item.realism_score
        weight = (1.0 - item.detector_score) * realism
        for signal in item.important_signals:
            relation = _PARAMETER_RELATION.get(signal.name)
            if relation is None or signal.contribution == 0.0:
                continue
            parameter, feature_relation = relation
            if parameter not in mutable:
                continue
            votes[parameter] += -signal.contribution * feature_relation * weight
            signals_by_parameter[parameter].add(signal.name)
    ranked = sorted(votes, key=lambda name: (-abs(votes[name]), name))
    evidence_basis = "detector_visible_attribution"
    if not ranked:
        rng = random.Random(seed)
        ranked = [name for name in _FALLBACK_PARAMETERS if name in mutable]
        rng.shuffle(ranked)
        evidence_basis = "seeded_bounded_fallback"
    budget_spec = parent.parameters.get("max_parameter_changes")
    if budget_spec is None or type(budget_spec.default) is not int:
        raise AdaptiveEvasionLoopError("parent lacks immutable max_parameter_changes")
    budget = int(budget_spec.default)
    changes: dict[str, dict[str, Any]] = {}
    mutations: list[ParameterMutation] = []
    for parameter in ranked:
        if len(changes) >= budget:
            break
        spec = mutable[parameter]
        if spec.param_type not in {ParameterType.INT, ParameterType.FLOAT}:
            continue
        if spec.minimum is None or spec.maximum is None:
            continue
        vote = votes.get(parameter, 1.0)
        direction = (
            MutationDirection.INCREASE if vote > 0.0 else MutationDirection.DECREASE
        )
        proposed = _bounded_move(
            spec.default, spec.minimum, spec.maximum, spec.param_type, direction
        )
        if proposed == spec.default:
            continue
        changes[parameter] = {"from": spec.default, "to": proposed}
        signal_names = sorted(signals_by_parameter.get(parameter, set()))
        rationale = (
            "Bounded move derived from detector-visible signals: " + ", ".join(signal_names)
            if signal_names
            else "No mapped attribution survived; apply one seeded bounded fallback move."
        )
        mutations.append(
            ParameterMutation(
                parameter=parameter,
                direction=direction,
                current_value=spec.default,
                proposed_value=proposed,
                magnitude=_STEP_FRACTION,
                rationale=rationale,
                confidence=(min(0.95, 0.55 + abs(vote)) if signal_names else 0.30),
                priority=len(mutations),
            )
        )
    if not changes:
        raise AdaptiveEvasionLoopError("bounded adaptation produced no legal change")
    parameters = dict(parent.parameters)
    for name, change in changes.items():
        parameters[name] = parameters[name].model_copy(update={"default": change["to"]})
    identity = json.dumps(
        {
            "parent": parent.attack_id,
            "seed": seed,
            "feedback": sorted(item.feedback_id for item in credible),
            "changes": changes,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    payload = parent.model_dump()
    payload.update(
        {
            "attack_id": f"{parent.attack_id}-g{parent.generation + 1}-{digest}",
            "parameters": parameters,
            "parent_blueprint_id": parent.attack_id,
            "generation": parent.generation + 1,
            "source": "evasion_feedback_mutation",
            "created_at": parent.created_at,
            "metadata": {
                **parent.metadata,
                "mutation_seed": seed,
                "changed_parameters": changes,
                "feedback_ids": sorted(item.feedback_id for item in credible),
                "bounded_candidate_count": 1,
            },
        }
    )
    child = AttackBlueprint.model_validate(payload)
    adaptation_digest = hashlib.sha256(
        f"{identity}:{child.attack_id}".encode()
    ).hexdigest()[:16]
    return GuidedAdaptation(
        adaptation_id=f"guided-adaptation-{adaptation_digest}",
        seed=seed,
        parent_blueprint_id=parent.attack_id,
        child_blueprint=child,
        feedback_ids=sorted(item.feedback_id for item in credible),
        mutations=mutations,
        changed_parameters=changes,
        evidence_basis=evidence_basis,
    )


def _bounded_move(
    current: Any,
    minimum: float,
    maximum: float,
    parameter_type: ParameterType,
    direction: MutationDirection,
) -> int | float:
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise AdaptiveEvasionLoopError("adaptive mutation requires a numeric default")
    signed = _STEP_FRACTION if direction is MutationDirection.INCREASE else -_STEP_FRACTION
    moved = min(max(float(current) + (maximum - minimum) * signed, minimum), maximum)
    if parameter_type is ParameterType.INT:
        if direction is MutationDirection.INCREASE:
            return min(int(maximum), max(int(current) + 1, round(moved)))
        return max(int(minimum), min(int(current) - 1, round(moved)))
    return round(moved, 8)


def _serializable_signals(
    signals: Sequence[SignalContribution],
) -> list[SignalContribution]:
    normalized: list[SignalContribution] = []
    for signal in signals:
        value = signal.value
        if isinstance(value, float) and not math.isfinite(value):
            value = None
        normalized.append(signal.model_copy(update={"value": value}))
    return normalized


__all__ = [
    "AdaptiveEvasionLoopError",
    "GuidedAdaptation",
    "adapt_blueprint_from_evasions",
    "build_adaptive_evasion_feedback",
]
