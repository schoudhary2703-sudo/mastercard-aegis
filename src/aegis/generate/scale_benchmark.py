"""Generation-only scale and fidelity benchmark utilities.

No detector is imported or invoked here.  The benchmark measures the existing
deterministic simulators, keeps fidelity descriptive, and reports constraint
validity separately instead of treating a valid row as distributional realism.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol, cast

from pydantic import Field

from aegis.generate.base import BaseGenerator
from aegis.generate.config import GenerationConfig
from aegis.shared.base import AegisModel
from aegis.shared.contracts import AttackBlueprint, Transaction, TransactionBatch
from aegis.shared.enums import AttackFamily


class FidelityComponentGroups(AegisModel):
    amount_distribution: dict[str, float]
    temporal_behavior: dict[str, float]
    transaction_type_behavior: dict[str, float]
    structural_topology: dict[str, float]


class DeterminismEvidence(AegisModel):
    verified: bool
    first_fingerprint_sha256: str = Field(..., min_length=64, max_length=64)
    repeat_fingerprint_sha256: str = Field(..., min_length=64, max_length=64)
    repeat_generation_seconds: float = Field(..., ge=0.0)


class FamilyGenerationBenchmark(AegisModel):
    attack_family: AttackFamily
    blueprint_id: str
    generator_name: str
    generator_version: str
    seed: int
    scenarios_generated: int = Field(..., ge=1)
    transactions_generated: int = Field(..., ge=1)
    fraud_transactions_generated: int = Field(..., ge=1)
    generation_seconds: float = Field(..., ge=0.0)
    throughput_transactions_per_second: float = Field(..., ge=0.0)
    reference_basis: str
    reference_sample_count: int = Field(..., ge=0)
    distributional_fidelity_score: float = Field(..., ge=0.0, le=1.0)
    fidelity_excluding_constraints: float = Field(..., ge=0.0, le=1.0)
    generator_reported_overall_fidelity_score: float = Field(..., ge=0.0, le=1.0)
    family_specific_fidelity_components: FidelityComponentGroups
    constraint_violation_rate: float = Field(..., ge=0.0, le=1.0)
    constraint_valid_percentage: float = Field(..., ge=0.0, le=100.0)
    violations_detected: bool
    deterministic_reproducibility: DeterminismEvidence
    historical_scenario_id_overlap_count: int = Field(..., ge=0)
    historical_scenario_id_overlaps: list[str]
    limitations: list[str]


class GenerationScaleSummary(AegisModel):
    family_count: int = Field(..., ge=1)
    total_scenarios: int = Field(..., ge=1)
    total_transactions: int = Field(..., ge=1)
    total_fraud_transactions: int = Field(..., ge=1)
    total_generation_seconds: float = Field(..., ge=0.0)
    aggregate_throughput_transactions_per_second: float = Field(..., ge=0.0)
    all_constraints_valid: bool
    all_deterministic: bool
    historical_scenario_id_overlap_count: int = Field(..., ge=0)
    deeply_simulated_families: int = Field(..., ge=0)


class GenerationScaleBenchmark(AegisModel):
    benchmark_version: str = "generation-scale-v1"
    benchmark_scope: str = (
        "Generation only: no detector scoring, PaySim pipeline run, fitting, or retraining."
    )
    environment: dict[str, str]
    families: list[FamilyGenerationBenchmark]
    summary: GenerationScaleSummary


@dataclass(frozen=True)
class GenerationBenchmarkCase:
    family: AttackFamily
    generator: BaseGenerator
    blueprint: AttackBlueprint
    config: GenerationConfig


class _FidelitySummary(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


class _FidelityAssessor(Protocol):
    def assess_fidelity(
        self, transactions: Sequence[Transaction], blueprint: AttackBlueprint
    ) -> _FidelitySummary: ...


_COMPONENT_KEYS: dict[AttackFamily, dict[str, tuple[str, ...]]] = {
    AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT: {
        "amount_distribution": ("warmup_amount_similarity",),
        "temporal_behavior": ("temporal_spacing_reasonableness",),
        "transaction_type_behavior": ("transaction_type_similarity",),
        "structural_topology": ("transition_multiplier_similarity",),
    },
    AttackFamily.MULE_NETWORK_STRUCTURING: {
        "amount_distribution": ("amount_distribution_realism",),
        "temporal_behavior": ("temporal_spacing_reasonableness",),
        "transaction_type_behavior": ("transfer_type_realism",),
        "structural_topology": (
            "fan_out_reasonableness",
            "fan_in_reasonableness",
            "mule_account_reuse_score",
            "destination_diversity_score",
            "structuring_consistency",
        ),
    },
    AttackFamily.ADAPTIVE_DETECTOR_EVASION: {
        "amount_distribution": ("context_amount_similarity", "fraud_amount_similarity"),
        "temporal_behavior": ("temporal_pacing_reasonableness",),
        "transaction_type_behavior": ("transaction_type_similarity",),
        "structural_topology": (
            "history_blend_consistency",
            "destination_diversity_score",
            "perturbation_budget_score",
        ),
    },
}


def batch_fingerprint(batch: TransactionBatch) -> str:
    """Hash every deterministic batch field and transaction without a giant JSON copy."""
    digest = hashlib.sha256()
    header = batch.model_dump(mode="json", exclude={"transactions"})
    digest.update(json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    for transaction in batch.transactions:
        digest.update(b"\n")
        digest.update(transaction.to_json().encode("utf-8"))
    return digest.hexdigest()


def _component_groups(
    family: AttackFamily, fidelity: dict[str, object]
) -> FidelityComponentGroups:
    groups: dict[str, dict[str, float]] = {}
    for group, keys in _COMPONENT_KEYS[family].items():
        values: dict[str, float] = {}
        for key in keys:
            value = fidelity.get(key)
            if not isinstance(value, (int, float)):
                raise ValueError(f"{family.value} fidelity is missing numeric component {key}")
            score = float(value)
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"{family.value} fidelity component {key} is outside [0, 1]")
            values[key] = score
        groups[group] = values
    return FidelityComponentGroups(**groups)


def _average(values: list[float]) -> float:
    if not values:
        raise ValueError("at least one fidelity component is required")
    return sum(values) / len(values)


def _average_groups(groups: list[FidelityComponentGroups]) -> FidelityComponentGroups:
    if not groups:
        raise ValueError("at least one per-scenario fidelity breakdown is required")
    averaged: dict[str, dict[str, float]] = {}
    for group_name in FidelityComponentGroups.model_fields:
        first = getattr(groups[0], group_name)
        averaged[group_name] = {
            key: _average([getattr(group, group_name)[key] for group in groups])
            for key in first
        }
    return FidelityComponentGroups(**averaged)


def _per_scenario_fidelity(
    case: GenerationBenchmarkCase, batch: TransactionBatch
) -> tuple[FidelityComponentGroups, float, float, str, int]:
    """Aggregate scenario diagnostics so scale itself does not distort topology/pacing.

    Each generator's fidelity routine is scenario-shaped. Running it once over
    interleaved rows from thousands of scenarios would compare a 3-node fan-out
    target with 3,000 nodes and treat cross-scenario timestamps as event gaps.
    Assessing each scenario independently preserves the existing semantics.
    """
    by_scenario: dict[str, list[Transaction]] = defaultdict(list)
    for transaction in batch.transactions:
        if transaction.scenario_id is None:
            raise ValueError("benchmark transaction is missing scenario_id")
        by_scenario[transaction.scenario_id].append(transaction)
    assessor = cast(_FidelityAssessor, case.generator)
    payloads = [
        assessor.assess_fidelity(transactions, case.blueprint).to_dict()
        for transactions in by_scenario.values()
    ]
    groups = [_component_groups(case.family, payload) for payload in payloads]
    violation_rate = _average([float(payload["constraint_violation_rate"]) for payload in payloads])
    overall = _average([float(payload["overall_fidelity_score"]) for payload in payloads])
    basis = {str(payload.get("reference_basis", "unknown")) for payload in payloads}
    reference_counts = {payload.get("reference_sample_count", 0) for payload in payloads}
    if len(basis) != 1 or len(reference_counts) != 1:
        raise ValueError("per-scenario fidelity reference provenance differs within one batch")
    reference_count = reference_counts.pop()
    if not isinstance(reference_count, int):
        raise ValueError("reference_sample_count must be an int")
    return _average_groups(groups), violation_rate, overall, basis.pop(), reference_count


def run_generation_scale_benchmark(
    cases: list[GenerationBenchmarkCase],
    *,
    historical_scenario_ids: set[str] | None = None,
) -> GenerationScaleBenchmark:
    if not cases:
        raise ValueError("at least one generation benchmark case is required")
    known = historical_scenario_ids or set()
    results: list[FamilyGenerationBenchmark] = []
    for case in cases:
        if not case.config.deterministic:
            raise ValueError(f"{case.family.value} benchmark config must be deterministic")
        started = perf_counter()
        batch = case.generator.generate(case.blueprint, case.config)
        generation_seconds = perf_counter() - started
        first_fingerprint = batch_fingerprint(batch)

        repeat_started = perf_counter()
        repeat = case.generator.generate(case.blueprint, case.config)
        repeat_seconds = perf_counter() - repeat_started
        repeat_fingerprint = batch_fingerprint(repeat)
        deterministic = first_fingerprint == repeat_fingerprint
        if not deterministic:
            raise ValueError(f"{case.family.value} failed deterministic reproducibility")

        overlaps = sorted(set(batch.scenario_ids) & known)
        if overlaps:
            raise ValueError(
                f"{case.family.value} generated historical scenario id(s): {overlaps[:5]}"
            )
        groups, violation_rate, overall, reference_basis, reference_count = (
            _per_scenario_fidelity(case, batch)
        )
        distributional_values = [
            *groups.amount_distribution.values(),
            *groups.transaction_type_behavior.values(),
        ]
        all_fidelity_values = [
            *distributional_values,
            *groups.temporal_behavior.values(),
            *groups.structural_topology.values(),
        ]
        transaction_count = len(batch.transactions)
        results.append(
            FamilyGenerationBenchmark(
                attack_family=case.family,
                blueprint_id=case.blueprint.attack_id,
                generator_name=batch.generator_name,
                generator_version=batch.generator_version,
                seed=case.config.seed,
                scenarios_generated=len(batch.scenario_ids),
                transactions_generated=transaction_count,
                fraud_transactions_generated=batch.fraud_count,
                generation_seconds=generation_seconds,
                throughput_transactions_per_second=(
                    transaction_count / generation_seconds if generation_seconds else 0.0
                ),
                reference_basis=reference_basis,
                reference_sample_count=reference_count,
                distributional_fidelity_score=_average(distributional_values),
                fidelity_excluding_constraints=_average(all_fidelity_values),
                generator_reported_overall_fidelity_score=overall,
                family_specific_fidelity_components=groups,
                constraint_violation_rate=violation_rate,
                constraint_valid_percentage=(1.0 - violation_rate) * 100.0,
                violations_detected=violation_rate > 0.0,
                deterministic_reproducibility=DeterminismEvidence(
                    verified=True,
                    first_fingerprint_sha256=first_fingerprint,
                    repeat_fingerprint_sha256=repeat_fingerprint,
                    repeat_generation_seconds=repeat_seconds,
                ),
                historical_scenario_id_overlap_count=0,
                historical_scenario_id_overlaps=overlaps,
                limitations=[
                    "Fidelity is descriptive similarity to the declared train-only reference, "
                    "not certification of real fraud realism.",
                    "Constraint validity reports simulator invariants and is not distributional "
                    "fidelity.",
                    "Throughput is a single-process development-machine observation, not an SLA.",
                ],
            )
        )

    total_transactions = sum(item.transactions_generated for item in results)
    total_seconds = sum(item.generation_seconds for item in results)
    return GenerationScaleBenchmark(
        environment={
            "python": platform.python_version(),
            "platform": platform.platform(),
            "implementation": sys.implementation.name,
        },
        families=results,
        summary=GenerationScaleSummary(
            family_count=len(results),
            total_scenarios=sum(item.scenarios_generated for item in results),
            total_transactions=total_transactions,
            total_fraud_transactions=sum(item.fraud_transactions_generated for item in results),
            total_generation_seconds=total_seconds,
            aggregate_throughput_transactions_per_second=(
                total_transactions / total_seconds if total_seconds else 0.0
            ),
            all_constraints_valid=all(not item.violations_detected for item in results),
            all_deterministic=all(
                item.deterministic_reproducibility.verified for item in results
            ),
            historical_scenario_id_overlap_count=sum(
                item.historical_scenario_id_overlap_count for item in results
            ),
            deeply_simulated_families=len(results),
        ),
    )


__all__ = [
    "FamilyGenerationBenchmark",
    "GenerationBenchmarkCase",
    "GenerationScaleBenchmark",
    "run_generation_scale_benchmark",
]
