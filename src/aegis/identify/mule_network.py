"""Deterministic blueprint for synthetic mule-network structuring scenarios."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aegis.identify.base import BaseAttackIdentifier, IdentificationContext
from aegis.shared.contracts import (
    AttackBlueprint,
    BehavioralStep,
    ParameterSpec,
    RealismConstraints,
)
from aegis.shared.enums import AttackFamily, Channel, ParameterType

MULE_NETWORK_BLUEPRINT_PROMPT = """\
Produce one JSON AttackBlueprint for the mule_network_structuring family.
The blueprint must remain a synthetic benchmark specification: coordinated
context activity, bounded source allocation, mule-to-mule layering, and
bounded fan-in or synthetic cash-out. Declare every tunable value as a
ParameterSpec with safe minimum and maximum bounds. Do not include real bank
accounts, jurisdiction-specific reporting thresholds, operational laundering
instructions, detector internals, or executable code. The output must validate
against the frozen AEGIS AttackBlueprint schema with extra fields forbidden.
"""

_CREATED_AT = datetime(2026, 2, 1, tzinfo=timezone.utc)


def build_mule_network_blueprint(
    *,
    attack_id: str = "mule-network-structuring-v1",
    transfer_amount_mean: float = 500.0,
    transfer_amount_stddev: float = 150.0,
    context_amount_mean: float = 75.0,
    context_amount_stddev: float = 25.0,
    currency: str = "XXX",
    reference_basis: str = "bounded_fallback",
    target_features: list[str] | None = None,
) -> AttackBlueprint:
    """Build a bounded benchmark topology without encoding real-world procedures."""
    transfer_mean = min(max(float(transfer_amount_mean), 100.0), 2_000.0)
    transfer_stddev = min(max(float(transfer_amount_stddev), 5.0), 800.0)
    context_mean = min(max(float(context_amount_mean), 10.0), 500.0)
    context_stddev = min(max(float(context_amount_stddev), 1.0), 200.0)
    currency_code = currency.upper()
    return AttackBlueprint(
        attack_id=attack_id,
        attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
        name="Synthetic mule network with bounded structuring",
        description=(
            "A benchmark-only graph of coordinated accounts moves bounded synthetic funds "
            "through allocation, layering, and consolidation stages."
        ),
        objective=(
            "Stress behavioral and graph-aware fraud detection with lower-value coordinated "
            "movement while preserving explicit fraud ground truth."
        ),
        target_features=target_features
        or [
            "temporal.amount",
            "temporal.source_velocity_1h",
            "temporal.destination_velocity_1h",
            "temporal.source_txn_count_before",
            "graph.fan_out",
            "graph.fan_in",
            "graph.layering_depth",
        ],
        sequence=[
            BehavioralStep(
                step_id="network-context",
                order=0,
                action="emit_legitimate_account_context",
                description="Create bounded legitimate history for synthetic network accounts.",
                channel=Channel.ONLINE_BANKING,
                offset_seconds=0.0,
                amount_policy={"distribution": "bounded_reference_normal"},
            ),
            BehavioralStep(
                step_id="source-allocation",
                order=1,
                action="allocate_synthetic_source_funds",
                description="Fan synthetic funds out to entry mule accounts.",
                channel=Channel.ONLINE_BANKING,
                offset_seconds=timedelta(days=7, hours=1).total_seconds(),
                amount_policy={"distribution": "bounded_structured_normal"},
            ),
            BehavioralStep(
                step_id="layering",
                order=2,
                action="route_across_synthetic_mules",
                description="Move funds across a bounded number of synthetic graph layers.",
                channel=Channel.ONLINE_BANKING,
                offset_seconds=timedelta(days=7, hours=2).total_seconds(),
                amount_policy={"distribution": "bounded_structured_normal"},
            ),
            BehavioralStep(
                step_id="fan-in-cashout",
                order=3,
                action="consolidate_or_cash_out_synthetic_funds",
                description="Consolidate into bounded exit destinations with optional cash-out.",
                channel=Channel.ONLINE_BANKING,
                offset_seconds=timedelta(days=7, hours=8).total_seconds(),
                amount_policy={"distribution": "bounded_structured_normal"},
            ),
        ],
        parameters={
            "mule_account_count": ParameterSpec(
                name="mule_account_count",
                param_type=ParameterType.INT,
                default=6,
                minimum=3,
                maximum=12,
                unit="accounts",
                description="Synthetic intermediary accounts participating in the graph.",
            ),
            "fan_out": ParameterSpec(
                name="fan_out",
                param_type=ParameterType.INT,
                default=3,
                minimum=2,
                maximum=6,
                unit="entry mules",
            ),
            "fan_in": ParameterSpec(
                name="fan_in",
                param_type=ParameterType.INT,
                default=2,
                minimum=1,
                maximum=4,
                unit="exit-stage source mules",
            ),
            "transfer_count": ParameterSpec(
                name="transfer_count",
                param_type=ParameterType.INT,
                default=12,
                minimum=6,
                maximum=32,
                unit="fraud transactions",
            ),
            "transfer_amount_mean": ParameterSpec(
                name="transfer_amount_mean",
                param_type=ParameterType.FLOAT,
                default=transfer_mean,
                minimum=100.0,
                maximum=2_000.0,
                unit=currency_code,
            ),
            "transfer_amount_stddev": ParameterSpec(
                name="transfer_amount_stddev",
                param_type=ParameterType.FLOAT,
                default=transfer_stddev,
                minimum=5.0,
                maximum=800.0,
                unit=currency_code,
            ),
            "per_transfer_cap": ParameterSpec(
                name="per_transfer_cap",
                param_type=ParameterType.FLOAT,
                default=9_500.0,
                minimum=500.0,
                maximum=10_000.0,
                unit=currency_code,
                description="Synthetic benchmark cap; not a real reporting threshold.",
            ),
            "inter_transfer_delay_minutes": ParameterSpec(
                name="inter_transfer_delay_minutes",
                param_type=ParameterType.FLOAT,
                default=45.0,
                minimum=5.0,
                maximum=360.0,
                unit="minutes",
            ),
            "layering_depth": ParameterSpec(
                name="layering_depth",
                param_type=ParameterType.INT,
                default=2,
                minimum=1,
                maximum=4,
                unit="layers",
            ),
            "destination_diversity": ParameterSpec(
                name="destination_diversity",
                param_type=ParameterType.INT,
                default=4,
                minimum=2,
                maximum=10,
                unit="exit destinations",
            ),
            "temporal_spread_hours": ParameterSpec(
                name="temporal_spread_hours",
                param_type=ParameterType.FLOAT,
                default=24.0,
                minimum=2.0,
                maximum=168.0,
                unit="hours",
            ),
            "source_allocation_concentration": ParameterSpec(
                name="source_allocation_concentration",
                param_type=ParameterType.FLOAT,
                default=0.45,
                minimum=0.20,
                maximum=0.70,
                unit="share",
            ),
            "cash_out_probability": ParameterSpec(
                name="cash_out_probability",
                param_type=ParameterType.FLOAT,
                default=0.25,
                minimum=0.0,
                maximum=0.75,
                unit="probability",
            ),
            "context_transaction_count_per_account": ParameterSpec(
                name="context_transaction_count_per_account",
                param_type=ParameterType.INT,
                default=2,
                minimum=1,
                maximum=5,
                unit="transactions",
            ),
            "context_duration_days": ParameterSpec(
                name="context_duration_days",
                param_type=ParameterType.INT,
                default=7,
                minimum=2,
                maximum=30,
                unit="days",
            ),
            "context_amount_mean": ParameterSpec(
                name="context_amount_mean",
                param_type=ParameterType.FLOAT,
                default=context_mean,
                minimum=10.0,
                maximum=500.0,
                unit=currency_code,
            ),
            "context_amount_stddev": ParameterSpec(
                name="context_amount_stddev",
                param_type=ParameterType.FLOAT,
                default=context_stddev,
                minimum=1.0,
                maximum=200.0,
                unit=currency_code,
            ),
            "randomness_seed_offset": ParameterSpec(
                name="randomness_seed_offset",
                param_type=ParameterType.INT,
                default=0,
                minimum=0,
                maximum=1_000_000,
                unit="seed offset",
                mutable=False,
            ),
        },
        realism_constraints=RealismConstraints(
            min_amount=1.0,
            max_amount=10_000.0,
            allowed_currencies=[currency_code],
            allowed_channels=[Channel.ONLINE_BANKING],
            max_transactions_per_account_per_day=24,
            max_accounts_involved=40,
            min_sequence_length=10,
            max_sequence_length=100,
            custom={
                "benchmark_only": True,
                "no_real_accounts": True,
                "no_jurisdiction_threshold_semantics": True,
            },
        ),
        source="deterministic_template",
        created_at=_CREATED_AT,
        metadata={
            "reference_basis": reference_basis,
            "llm_prompt_template_available": True,
            "simulator_version": "1.0.0",
            "safety_scope": "synthetic_benchmark_only",
        },
    )


class MuleNetworkBlueprintIdentifier(BaseAttackIdentifier):
    """Propose the canonical mule-network template through the Red interface."""

    name = "mule-network-template"
    version = "1.0.0"

    def propose(self, context: IdentificationContext) -> list[AttackBlueprint]:
        family = AttackFamily.MULE_NETWORK_STRUCTURING
        if context.target_families and family not in context.target_families:
            return []
        blueprint = build_mule_network_blueprint(
            attack_id=f"mule-network-structuring-{context.seed}",
            target_features=context.observed_feature_names or None,
        )
        return [blueprint][: context.max_blueprints]


__all__ = [
    "MULE_NETWORK_BLUEPRINT_PROMPT",
    "MuleNetworkBlueprintIdentifier",
    "build_mule_network_blueprint",
]
