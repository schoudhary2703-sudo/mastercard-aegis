"""Deterministic attacker-only evolution for synthetic-identity bust-outs.

The loop package is the sole architectural boundary allowed to import both
teams. This module mutates attack data, generates fresh scenarios, and scores
them with an already-fitted detector; it never fits or reconfigures a model.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import Field

from aegis.defend import BaseDetector
from aegis.evaluate import (
    BustOutConfrontationReport,
    EvasionRecord,
    build_bustout_confrontation_report,
    rank_hardest_evasions,
)
from aegis.features import BaseFeatureExtractor
from aegis.generate import BaseGenerator, GenerationConfig
from aegis.shared.base import AegisModel
from aegis.shared.contracts import (
    AttackBlueprint,
    DetectorOutput,
    EvaluationResult,
    EvasionFeedback,
    ParameterMutation,
    ParameterSpec,
    SignalContribution,
    Transaction,
    TransactionBatch,
)
from aegis.shared.enums import (
    DataSplit,
    FraudLabel,
    MutationDirection,
    ParameterType,
)

_NUMERIC_PARAMETER_TYPES = {ParameterType.INT, ParameterType.FLOAT}
_MAGNITUDE_SCHEDULE = (0.08, 0.12, 0.16, 0.20, 0.24)

# These are simulator relationships, not claims about model behavior. A
# direction is proposed only when an observed positive signal contribution
# supports reducing the corresponding detector-visible feature.
_SIGNAL_PARAMETER_RELATION: dict[str, tuple[str, int]] = {
    "temporal.amount": ("bustout_amount_multiplier", 1),
    "temporal.amount_deviation_from_source_history": ("bustout_amount_multiplier", 1),
    "temporal.source_avg_amount_before": ("warmup_amount_mean", 1),
    "temporal.source_txn_count_before": ("warmup_transaction_count", 1),
    "temporal.source_velocity_1h": ("bustout_window_hours", -1),
    "temporal.destination_velocity_1h": ("destination_diversity", -1),
    "temporal.seconds_since_source_previous_txn": ("bustout_window_hours", 1),
}


class AdaptiveEvolutionError(ValueError):
    """Raised when an adaptive round would be unsupported or invalid."""


class ParameterRegionEvidence(AegisModel):
    """Observed signal attribution mapped to one mutable generator control."""

    parameter: str = Field(..., min_length=1)
    signals: list[str]
    observations: int = Field(..., ge=1)
    mean_signed_contribution: float
    risk_increasing_contribution: float = Field(..., ge=0.0)
    direction_vote: float
    suggested_direction: MutationDirection | None = None
    evidence_type: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)


class BlindSpotAnalysis(AegisModel):
    """Reproducible summary of what Round 0 actually supports."""

    analysis_id: str = Field(..., min_length=1)
    parent_blueprint_id: str = Field(..., min_length=1)
    detector_model_version: str = Field(..., min_length=1)
    round_index: int = Field(default=0, ge=0)
    original_parameters: dict[str, Any]
    evasion_count: int = Field(..., ge=1)
    credible_evasion_count: int = Field(..., ge=1)
    average_evasion_risk_score: float = Field(..., ge=0.0, le=1.0)
    lowest_evasion_risk_score: float = Field(..., ge=0.0, le=1.0)
    average_fidelity_score: float = Field(..., ge=0.0, le=1.0)
    hardest_evasion_ids: list[str]
    feedback: list[EvasionFeedback]
    parameter_evidence: list[ParameterRegionEvidence]
    directional_evidence_available: bool
    notes: list[str]


class MutationCandidate(AegisModel):
    """One bounded child blueprint and the evidence behind its changes."""

    candidate_id: str = Field(..., min_length=1)
    seed: int
    blueprint: AttackBlueprint
    mutations: list[ParameterMutation] = Field(..., min_length=1)
    changed_parameters: dict[str, dict[str, Any]]
    evidence_basis: str = Field(..., min_length=1)


class RoundAttackMetrics(AegisModel):
    """Comparable attack outcome backed by a scenario EvaluationResult."""

    generated_scenario_count: int = Field(..., ge=1)
    transaction_count: int = Field(..., ge=1)
    fraud_count: int = Field(..., ge=1)
    caught_count: int = Field(..., ge=0)
    evaded_count: int = Field(..., ge=0)
    fraud_recall: float = Field(..., ge=0.0, le=1.0)
    average_fraud_risk_score: float = Field(..., ge=0.0, le=1.0)
    fidelity_score: float = Field(..., ge=0.0, le=1.0)
    fitness: float = Field(..., ge=0.0, le=1.0)
    evaluation_result: EvaluationResult


class AdaptiveCandidateResult(AegisModel):
    """Scored Round 1 result for one mutation candidate."""

    fitness_rank: int | None = Field(default=None, ge=1)
    candidate: MutationCandidate
    batch_id: str = Field(..., min_length=1)
    generation_seed: int
    model_version: str = Field(..., min_length=1)
    metrics: RoundAttackMetrics
    confrontation: BustOutConfrontationReport


class RoundComparison(AegisModel):
    """Selected Round 1 candidate compared with its Round 0 parent."""

    round0: RoundAttackMetrics
    round1: RoundAttackMetrics
    fraud_recall_delta: float
    average_fraud_risk_delta: float
    fidelity_delta: float
    fitness_delta: float
    caught_count_delta: int
    evaded_count_delta: int


class AdaptiveRoundReport(AegisModel):
    """Complete attacker-evolution artifact; no defender retraining state."""

    report_id: str = Field(..., min_length=1)
    round_index: int = Field(default=1, ge=1)
    seed: int
    model_version: str = Field(..., min_length=1)
    detector_retrained: bool = False
    threshold_changed: bool = False
    integration_only: bool
    data_basis: str = Field(..., min_length=1)
    parent_confrontation_id: str = Field(..., min_length=1)
    parent_blueprint: AttackBlueprint
    blind_spot_analysis: BlindSpotAnalysis
    candidate_results: list[AdaptiveCandidateResult] = Field(..., min_length=1)
    selected_candidate_id: str = Field(..., min_length=1)
    selected_blueprint: AttackBlueprint
    hardest_surviving_evasions: list[EvasionRecord]
    comparison: RoundComparison
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class AdaptiveRoundExecution:
    """Report plus generated records needed by artifact writers."""

    report: AdaptiveRoundReport
    batches: dict[str, TransactionBatch]
    outputs: dict[str, list[DetectorOutput]]


def build_evasion_feedback(
    confrontation: BustOutConfrontationReport,
    blueprint: AttackBlueprint,
    outputs: Sequence[DetectorOutput],
) -> list[EvasionFeedback]:
    """Translate structured false negatives into the frozen feedback channel."""
    if {output.model_version for output in outputs} != {confrontation.model_version}:
        raise AdaptiveEvolutionError("detector outputs do not match confrontation model version")
    output_by_id = {output.transaction_id: output for output in outputs}
    if len(output_by_id) != len(outputs):
        raise AdaptiveEvolutionError("duplicate detector output transaction IDs")

    hardest_rank = {
        record.transaction_id: record.rank for record in confrontation.hardest_evasions
    }
    feedback: list[EvasionFeedback] = []
    for evasion in confrontation.successful_evasions:
        output = output_by_id.get(evasion.transaction_id)
        if output is None:
            raise AdaptiveEvolutionError(
                f"missing detector output for evasion {evasion.transaction_id!r}"
            )
        identity = json.dumps(
            {
                "report": confrontation.report_id,
                "transaction": evasion.transaction_id,
                "model": output.model_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        feedback.append(
            EvasionFeedback(
                feedback_id=f"feedback-{digest}",
                attack_family=evasion.attack_family,
                attack_id=blueprint.attack_id,
                blueprint_id=evasion.blueprint_id,
                scenario_id=evasion.scenario_id,
                original_parameters=blueprint.default_parameters(),
                detector_score=output.risk_score,
                detector_model_version=output.model_version,
                threshold=output.threshold,
                evaded=True,
                realism_score=evasion.fidelity_score,
                important_signals=_serializable_signals(output.important_signals),
                round_index=0,
                generation=evasion.generation,
                transaction_ids=[evasion.transaction_id],
                metadata={
                    "source_confrontation_id": confrontation.report_id,
                    "ground_truth_label": evasion.ground_truth_label.name,
                    "hardest_evasion_rank": hardest_rank.get(evasion.transaction_id),
                },
            )
        )
    if not feedback:
        raise AdaptiveEvolutionError("confrontation contains no successful evasions")
    return feedback


def analyze_blind_spots(
    confrontation: BustOutConfrontationReport,
    blueprint: AttackBlueprint,
    outputs: Sequence[DetectorOutput],
) -> BlindSpotAnalysis:
    """Aggregate credible evasion evidence without claiming unsupported causality."""
    feedback = build_evasion_feedback(confrontation, blueprint, outputs)
    credible = [item for item in feedback if item.is_credible_evasion]
    if not credible:
        raise AdaptiveEvolutionError("no credible evasions passed the realism gate")

    contributions: dict[str, list[tuple[str, float, int, float]]] = defaultdict(list)
    for item in credible:
        assert item.realism_score is not None
        evidence_weight = (1.0 - item.detector_score) * item.realism_score
        for signal in item.important_signals:
            relation = _SIGNAL_PARAMETER_RELATION.get(signal.name)
            if relation is None:
                continue
            parameter, feature_relation = relation
            spec = blueprint.mutable_parameters().get(parameter)
            if spec is None:
                continue
            contributions[parameter].append(
                (signal.name, signal.contribution, feature_relation, evidence_weight)
            )

    evidence: list[ParameterRegionEvidence] = []
    for parameter in sorted(contributions):
        observations = contributions[parameter]
        positive = [entry for entry in observations if entry[1] > 0.0]
        total_weight = sum(entry[3] for entry in observations)
        risk_contribution = (
            sum(entry[1] * entry[3] for entry in positive) / total_weight
            if total_weight > 0.0
            else 0.0
        )
        direction_vote = sum(-entry[2] * entry[1] * entry[3] for entry in positive)
        if direction_vote > 1e-12:
            direction: MutationDirection | None = MutationDirection.INCREASE
        elif direction_vote < -1e-12:
            direction = MutationDirection.DECREASE
        else:
            direction = None
        signal_names = sorted({entry[0] for entry in observations})
        evidence.append(
            ParameterRegionEvidence(
                parameter=parameter,
                signals=signal_names,
                observations=len(observations),
                mean_signed_contribution=(
                    sum(entry[1] * entry[3] for entry in observations) / total_weight
                    if total_weight > 0.0
                    else 0.0
                ),
                risk_increasing_contribution=risk_contribution,
                direction_vote=direction_vote,
                suggested_direction=direction,
                evidence_type="observed_signal_attribution",
                rationale=(
                    f"Credible Round 0 evasions showed positive risk contribution from "
                    f"{', '.join(signal_names)}; test a bounded {direction.value} move. "
                    "Attribution supports exploration, not a causal efficacy claim."
                    if direction is not None
                    else (
                        f"Mapped signals {', '.join(signal_names)} did not provide a consistent "
                        "risk-increasing direction; no directional conclusion is asserted."
                    )
                ),
            )
        )

    risks = [item.detector_score for item in credible]
    fidelities = [item.realism_score for item in credible if item.realism_score is not None]
    directional = any(item.suggested_direction is not None for item in evidence)
    notes = [
        "Round 0 contains one parent parameter region; signal attribution is associative, "
        "not a cross-region parameter correlation."
    ]
    if not directional:
        notes.append(
            "No mapped directional signal evidence was available; candidate creation will use "
            "seeded symmetric local exploration and will not claim a blind-spot direction."
        )
    identity = json.dumps(
        {
            "report": confrontation.report_id,
            "blueprint": blueprint.attack_id,
            "feedback": [item.feedback_id for item in credible],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return BlindSpotAnalysis(
        analysis_id=f"blind-spot-{digest}",
        parent_blueprint_id=blueprint.attack_id,
        detector_model_version=confrontation.model_version,
        original_parameters=blueprint.default_parameters(),
        evasion_count=len(feedback),
        credible_evasion_count=len(credible),
        average_evasion_risk_score=sum(risks) / len(risks),
        lowest_evasion_risk_score=min(risks),
        average_fidelity_score=sum(fidelities) / len(fidelities),
        hardest_evasion_ids=[item.transaction_id for item in confrontation.hardest_evasions],
        feedback=feedback,
        parameter_evidence=evidence,
        directional_evidence_available=directional,
        notes=notes,
    )


def generate_mutation_candidates(
    blueprint: AttackBlueprint,
    analysis: BlindSpotAnalysis,
    *,
    seed: int,
    candidate_count: int = 4,
) -> list[MutationCandidate]:
    """Create distinct bounded children using evidence or honest local exploration."""
    if candidate_count < 2:
        raise AdaptiveEvolutionError("candidate_count must be at least 2")
    mutable = {
        name: spec
        for name, spec in blueprint.mutable_parameters().items()
        if spec.param_type in _NUMERIC_PARAMETER_TYPES
        and spec.minimum is not None
        and spec.maximum is not None
        and spec.maximum > spec.minimum
    }
    if not mutable:
        raise AdaptiveEvolutionError("blueprint has no bounded mutable numeric parameters")

    supported = [
        item
        for item in analysis.parameter_evidence
        if item.suggested_direction is not None and item.parameter in mutable
    ]
    supported.sort(
        key=lambda item: (-item.risk_increasing_contribution, item.parameter)
    )
    exploratory_names = sorted(mutable)
    rng = random.Random(seed)
    rng.shuffle(exploratory_names)

    candidates: list[MutationCandidate] = []
    seen_changes: set[str] = set()
    attempt = 0
    while len(candidates) < candidate_count and attempt < candidate_count * 20:
        magnitude = _MAGNITUDE_SCHEDULE[attempt % len(_MAGNITUDE_SCHEDULE)]
        evidence_item = supported[attempt % len(supported)] if supported else None
        if evidence_item is not None:
            parameter = evidence_item.parameter
            direction = evidence_item.suggested_direction
            assert direction is not None
            rationale = evidence_item.rationale
            evidence_basis = "observed_signal_attribution"
        else:
            parameter = exploratory_names[attempt % len(exploratory_names)]
            direction = (
                MutationDirection.INCREASE
                if (attempt // len(exploratory_names)) % 2 == 0
                else MutationDirection.DECREASE
            )
            rationale = (
                "Round 0 established a credible local evasion but no supported parameter "
                f"direction for {parameter}; test one bounded side of a seeded symmetric search."
            )
            evidence_basis = "symmetric_local_exploration"

        spec = mutable[parameter]
        current = spec.default
        proposed = _move_parameter(spec, current, direction, magnitude)
        attempt += 1
        if proposed == current:
            continue
        changes = {parameter: {"from": current, "to": proposed}}
        change_key = json.dumps(changes, sort_keys=True, separators=(",", ":"))
        if change_key in seen_changes:
            continue
        seen_changes.add(change_key)
        child = _mutated_blueprint(blueprint, changes, seed=seed, index=len(candidates))
        mutation = ParameterMutation(
            parameter=parameter,
            direction=direction,
            current_value=current,
            proposed_value=proposed,
            magnitude=magnitude,
            rationale=rationale,
            confidence=(
                min(0.95, 0.55 + evidence_item.risk_increasing_contribution)
                if evidence_item is not None
                else 0.35
            ),
            priority=0,
        )
        candidates.append(
            MutationCandidate(
                candidate_id=child.attack_id,
                seed=seed,
                blueprint=child,
                mutations=[mutation],
                changed_parameters=changes,
                evidence_basis=evidence_basis,
            )
        )
    if len(candidates) != candidate_count:
        raise AdaptiveEvolutionError(
            f"could create only {len(candidates)} distinct mutations; requested {candidate_count}"
        )
    return candidates


def calculate_attack_fitness(average_fraud_risk: float, fidelity_score: float) -> float:
    """Balance evasion quality and realism instead of optimizing either alone."""
    if not 0.0 <= average_fraud_risk <= 1.0:
        raise ValueError("average_fraud_risk must be in [0, 1]")
    if not 0.0 <= fidelity_score <= 1.0:
        raise ValueError("fidelity_score must be in [0, 1]")
    return (1.0 - average_fraud_risk) * fidelity_score


def evolve_bustout_round(
    *,
    parent_confrontation: BustOutConfrontationReport,
    parent_blueprint: AttackBlueprint,
    round0_outputs: Sequence[DetectorOutput],
    generator: BaseGenerator,
    extractor: BaseFeatureExtractor,
    detector: BaseDetector,
    training_transactions: Sequence[Transaction],
    seed: int,
    start_time: datetime,
    candidate_count: int = 4,
) -> AdaptiveRoundExecution:
    """Generate and score Round 1 variants against one unchanged fitted detector."""
    if not detector.is_fitted:
        raise AdaptiveEvolutionError("adaptive scoring requires an already-fitted detector")
    if detector.model_version != parent_confrontation.model_version:
        raise AdaptiveEvolutionError("detector model version differs from Round 0")
    round0_seeds = {scenario.seed for scenario in parent_confrontation.scenario_reports}
    candidate_seeds = [seed + index for index in range(candidate_count)]
    if round0_seeds.intersection(candidate_seeds):
        raise AdaptiveEvolutionError("Round 1 generation seeds must be fresh")
    round0_thresholds = {output.threshold for output in round0_outputs}
    if len(round0_thresholds) != 1:
        raise AdaptiveEvolutionError("Round 0 outputs do not share one threshold")
    frozen_threshold = next(iter(round0_thresholds))
    if detector.action_policy.label_threshold != frozen_threshold:
        raise AdaptiveEvolutionError("detector threshold differs from Round 0")

    analysis = analyze_blind_spots(parent_confrontation, parent_blueprint, round0_outputs)
    candidates = generate_mutation_candidates(
        parent_blueprint, analysis, seed=seed, candidate_count=candidate_count
    )
    results: list[AdaptiveCandidateResult] = []
    batches: dict[str, TransactionBatch] = {}
    output_sets: dict[str, list[DetectorOutput]] = {}
    for index, candidate in enumerate(candidates):
        generation_seed = candidate_seeds[index]
        batch = generator.generate(
            candidate.blueprint,
            GenerationConfig(
                seed=generation_seed,
                n_scenarios=1,
                start_time=start_time + timedelta(days=index),
                time_horizon=timedelta(days=120),
                split=DataSplit.TEST,
                generation=1,
                deterministic=True,
            ),
        )
        X_candidate = extractor.transform(batch.transactions)
        outputs = detector.predict(
            X_candidate,
            [txn.transaction_id for txn in batch.transactions],
            explain=True,
        )
        if {output.model_version for output in outputs} != {parent_confrontation.model_version}:
            raise AdaptiveEvolutionError("Round 1 used a different detector model version")
        if {output.threshold for output in outputs} != {frozen_threshold}:
            raise AdaptiveEvolutionError("Round 1 changed the detector threshold")
        confrontation = build_bustout_confrontation_report(
            batch=batch,
            outputs=outputs,
            training_transactions=training_transactions,
            training_dataset_id=parent_confrontation.training_dataset_id,
            data_basis=parent_confrontation.data_basis,
            integration_only=parent_confrontation.integration_only,
        )
        metrics = _metrics_from_confrontation(confrontation)
        metrics = _with_adaptive_metadata(metrics, candidate)
        confrontation = _with_evaluation_result(confrontation, metrics.evaluation_result)
        result = AdaptiveCandidateResult(
            candidate=candidate,
            batch_id=batch.batch_id,
            generation_seed=generation_seed,
            model_version=detector.model_version,
            metrics=metrics,
            confrontation=confrontation,
        )
        results.append(result)
        batches[candidate.candidate_id] = batch
        output_sets[candidate.candidate_id] = outputs

    ordered = sorted(
        results,
        key=lambda result: (
            -result.metrics.fitness,
            result.metrics.average_fraud_risk_score,
            -result.metrics.fidelity_score,
            result.candidate.candidate_id,
        ),
    )
    ranked_results = [
        result.model_copy(update={"fitness_rank": rank})
        for rank, result in enumerate(ordered, 1)
    ]
    credible_candidates = [
        result for result in ranked_results if result.metrics.fidelity_score >= 0.5
    ]
    if not credible_candidates:
        raise AdaptiveEvolutionError("no Round 1 candidate passed the realism gate")
    selected = credible_candidates[0]
    round0_metrics = _metrics_from_confrontation(parent_confrontation)
    comparison = compare_rounds(round0_metrics, selected.metrics)
    all_evasions = [
        evasion
        for result in results
        for evasion in result.confrontation.successful_evasions
        if evasion.ground_truth_label is FraudLabel.FRAUD
    ]
    hardest = rank_hardest_evasions(all_evasions)
    identity = json.dumps(
        {
            "parent": parent_confrontation.report_id,
            "model": detector.model_version,
            "seed": seed,
            "candidates": [item.candidate.candidate_id for item in results],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    report = AdaptiveRoundReport(
        report_id=f"adaptive-round-1-{digest}",
        seed=seed,
        model_version=detector.model_version,
        integration_only=parent_confrontation.integration_only,
        data_basis=parent_confrontation.data_basis,
        parent_confrontation_id=parent_confrontation.report_id,
        parent_blueprint=parent_blueprint,
        blind_spot_analysis=analysis,
        candidate_results=ranked_results,
        selected_candidate_id=selected.candidate.candidate_id,
        selected_blueprint=selected.candidate.blueprint,
        hardest_surviving_evasions=hardest,
        comparison=comparison,
        metadata={
            "attacker_evolution_only": True,
            "detector_fit_called": False,
            "selection": "highest (1-average_fraud_risk)*fidelity",
            "evaluation_protocol": "static_holdout; no defender retrain occurred",
        },
    )
    return AdaptiveRoundExecution(report=report, batches=batches, outputs=output_sets)


def compare_rounds(round0: RoundAttackMetrics, round1: RoundAttackMetrics) -> RoundComparison:
    """Compute signed Round 1-minus-Round 0 differences."""
    return RoundComparison(
        round0=round0,
        round1=round1,
        fraud_recall_delta=round1.fraud_recall - round0.fraud_recall,
        average_fraud_risk_delta=(
            round1.average_fraud_risk_score - round0.average_fraud_risk_score
        ),
        fidelity_delta=round1.fidelity_score - round0.fidelity_score,
        fitness_delta=round1.fitness - round0.fitness,
        caught_count_delta=round1.caught_count - round0.caught_count,
        evaded_count_delta=round1.evaded_count - round0.evaded_count,
    )


def _move_parameter(
    spec: ParameterSpec,
    current: Any,
    direction: MutationDirection,
    magnitude: float,
) -> int | float:
    if spec.minimum is None or spec.maximum is None:
        raise AdaptiveEvolutionError(f"parameter {spec.name!r} is not bounded")
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise AdaptiveEvolutionError(f"parameter {spec.name!r} is not numeric")
    span = spec.maximum - spec.minimum
    signed_step = span * magnitude * (1.0 if direction is MutationDirection.INCREASE else -1.0)
    moved = min(max(float(current) + signed_step, spec.minimum), spec.maximum)
    if spec.param_type is ParameterType.INT:
        if direction is MutationDirection.INCREASE:
            return min(int(spec.maximum), max(int(current) + 1, round(moved)))
        return max(int(spec.minimum), min(int(current) - 1, round(moved)))
    return round(moved, 8)


def _mutated_blueprint(
    parent: AttackBlueprint,
    changes: Mapping[str, Mapping[str, Any]],
    *,
    seed: int,
    index: int,
) -> AttackBlueprint:
    parameters = dict(parent.parameters)
    for name, change in changes.items():
        spec = parameters[name]
        if not spec.mutable:
            raise AdaptiveEvolutionError(f"parameter {name!r} is immutable")
        parameters[name] = spec.model_copy(update={"default": change["to"]})
    identity = json.dumps(
        {"parent": parent.attack_id, "seed": seed, "index": index, "changes": changes},
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
            "source": "mutation",
            "created_at": parent.created_at,
            "metadata": {
                **parent.metadata,
                "mutation_seed": seed,
                "changed_parameters": dict(changes),
            },
        }
    )
    child = AttackBlueprint.model_validate(payload)
    if child.default_parameters() == parent.default_parameters():
        raise AdaptiveEvolutionError("mutation produced an exact parent clone")
    return child


def _metrics_from_confrontation(
    confrontation: BustOutConfrontationReport,
) -> RoundAttackMetrics:
    scenarios = confrontation.scenario_reports
    if not scenarios:
        raise AdaptiveEvolutionError("confrontation contains no scenario reports")
    events = [event for scenario in scenarios for event in scenario.fraudulent_events]
    if not events:
        raise AdaptiveEvolutionError("confrontation contains no fraud events")
    fraud_count = sum(scenario.fraudulent_bustout_count for scenario in scenarios)
    caught = sum(scenario.caught_fraud_count for scenario in scenarios)
    evaded = sum(scenario.evaded_fraud_count for scenario in scenarios)
    fidelity_values = [
        _score(scenario.fidelity_summary.get("overall_fidelity_score"))
        for scenario in scenarios
    ]
    average_risk = sum(event.risk_score for event in events) / len(events)
    fidelity = sum(fidelity_values) / len(fidelity_values)
    evaluation = scenarios[0].evaluation_result
    return RoundAttackMetrics(
        generated_scenario_count=len(scenarios),
        transaction_count=sum(scenario.total_transactions for scenario in scenarios),
        fraud_count=fraud_count,
        caught_count=caught,
        evaded_count=evaded,
        fraud_recall=caught / fraud_count,
        average_fraud_risk_score=average_risk,
        fidelity_score=fidelity,
        fitness=calculate_attack_fitness(average_risk, fidelity),
        evaluation_result=evaluation,
    )


def _with_adaptive_metadata(
    metrics: RoundAttackMetrics, candidate: MutationCandidate
) -> RoundAttackMetrics:
    evaluation = metrics.evaluation_result
    metadata = {
        **evaluation.metadata,
        "adaptive_round": 1,
        "candidate_id": candidate.candidate_id,
        "average_fraud_risk_score": metrics.average_fraud_risk_score,
        "fitness": metrics.fitness,
        "changed_parameters": candidate.changed_parameters,
        "detector_retrained": False,
    }
    return metrics.model_copy(
        update={"evaluation_result": evaluation.model_copy(update={"metadata": metadata})}
    )


def _with_evaluation_result(
    confrontation: BustOutConfrontationReport, evaluation: EvaluationResult
) -> BustOutConfrontationReport:
    if len(confrontation.scenario_reports) != 1:
        raise AdaptiveEvolutionError("v1 expects one scenario per mutation candidate")
    scenario = confrontation.scenario_reports[0].model_copy(
        update={"evaluation_result": evaluation}
    )
    return confrontation.model_copy(update={"scenario_reports": [scenario]})


def _score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdaptiveEvolutionError("fidelity score is missing or non-numeric")
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise AdaptiveEvolutionError("fidelity score must be in [0, 1]")
    return score


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
    "AdaptiveCandidateResult",
    "AdaptiveEvolutionError",
    "AdaptiveRoundExecution",
    "AdaptiveRoundReport",
    "BlindSpotAnalysis",
    "MutationCandidate",
    "ParameterRegionEvidence",
    "RoundAttackMetrics",
    "RoundComparison",
    "analyze_blind_spots",
    "build_evasion_feedback",
    "calculate_attack_fitness",
    "compare_rounds",
    "evolve_bustout_round",
    "generate_mutation_candidates",
]
