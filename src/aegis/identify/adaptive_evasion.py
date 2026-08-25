"""Blueprint for bounded, feedback-guided synthetic detector-evasion scenarios."""

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

ADAPTIVE_EVASION_BLUEPRINT_PROMPT = """\
Produce one JSON AttackBlueprint for the adaptive_detector_evasion family.
The blueprint describes a synthetic benchmark only: legitimate behavioral
context followed by bounded fraudulent payment perturbations. Every tunable
value must be a bounded ParameterSpec. Adaptation may consume only contract-
backed EvasionFeedback and detector-visible feature attributions. Do not
include model internals, real accounts, real payment-system instructions,
unbounded search, executable code, or another attack family. The output must
validate against the frozen AEGIS AttackBlueprint schema.
"""

_CREATED_AT = datetime(2026, 3, 1, tzinfo=timezone.utc)


def build_adaptive_evasion_blueprint(
    *,
    attack_id: str = "adaptive-detector-evasion-v1",
    context_amount_mean: float = 75.0,
    context_amount_stddev: float = 25.0,
    fraud_amount_mean: float = 1_000.0,
    fraud_amount_stddev: float = 250.0,
    currency: str = "XXX",
    reference_basis: str = "bounded_fallback",
    target_features: list[str] | None = None,
) -> AttackBlueprint:
    """Create the canonical bounded perturbation envelope."""
    context_mean = min(max(float(context_amount_mean), 10.0), 500.0)
    context_stddev = min(max(float(context_amount_stddev), 1.0), 200.0)
    fraud_mean = min(max(float(fraud_amount_mean), 100.0), 3_000.0)
    fraud_stddev = min(max(float(fraud_amount_stddev), 20.0), 1_000.0)
    currency_code = currency.upper()
    return AttackBlueprint(
        attack_id=attack_id,
        attack_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
        name="Bounded feedback-guided payment perturbation",
        description=(
            "A benchmark-only sequence establishes ordinary single-account history, then "
            "emits bounded fraudulent payments whose declared controls can be mutated from "
            "EvasionFeedback."
        ),
        objective=(
            "Measure whether detector-visible attribution can guide small, realistic, bounded "
            "synthetic changes that lower fraud risk without changing ground truth."
        ),
        target_features=target_features
        or [
            "temporal.amount",
            "temporal.amount_deviation_from_source_history",
            "temporal.source_txn_count_before",
            "temporal.source_velocity_1h",
            "temporal.destination_velocity_1h",
            "temporal.seconds_since_source_previous_txn",
        ],
        sequence=[
            BehavioralStep(
                step_id="behavioral-context",
                order=0,
                action="emit_legitimate_single_account_history",
                description="Build strictly earlier legitimate context for one synthetic source.",
                channel=Channel.MOBILE,
                offset_seconds=0.0,
                amount_policy={"distribution": "bounded_reference_normal"},
            ),
            BehavioralStep(
                step_id="adaptive-pacing",
                order=1,
                action="schedule_bounded_perturbation_window",
                description="Apply a declared delay and jitter envelope before fraud events.",
                channel=Channel.MOBILE,
                offset_seconds=timedelta(days=14, hours=2).total_seconds(),
            ),
            BehavioralStep(
                step_id="adversarial-transfers",
                order=2,
                action="emit_bounded_fraud_perturbations",
                description=(
                    "Emit fraud-labelled transfers or cash-outs within the declared amount, "
                    "destination, and timing envelope."
                ),
                channel=Channel.MOBILE,
                offset_seconds=timedelta(days=14, hours=4).total_seconds(),
                amount_policy={"distribution": "history_blended_bounded_normal"},
            ),
        ],
        parameters={
            "context_transaction_count": ParameterSpec(
                name="context_transaction_count",
                param_type=ParameterType.INT,
                default=10,
                minimum=4,
                maximum=30,
                unit="transactions",
            ),
            "context_duration_days": ParameterSpec(
                name="context_duration_days",
                param_type=ParameterType.INT,
                default=14,
                minimum=3,
                maximum=45,
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
            "fraud_transaction_count": ParameterSpec(
                name="fraud_transaction_count",
                param_type=ParameterType.INT,
                default=4,
                minimum=2,
                maximum=8,
                unit="transactions",
            ),
            "fraud_amount_mean": ParameterSpec(
                name="fraud_amount_mean",
                param_type=ParameterType.FLOAT,
                default=fraud_mean,
                minimum=100.0,
                maximum=3_000.0,
                unit=currency_code,
            ),
            "fraud_amount_stddev": ParameterSpec(
                name="fraud_amount_stddev",
                param_type=ParameterType.FLOAT,
                default=fraud_stddev,
                minimum=20.0,
                maximum=1_000.0,
                unit=currency_code,
            ),
            "per_transaction_cap": ParameterSpec(
                name="per_transaction_cap",
                param_type=ParameterType.FLOAT,
                default=5_000.0,
                minimum=500.0,
                maximum=10_000.0,
                unit=currency_code,
            ),
            "history_blend_ratio": ParameterSpec(
                name="history_blend_ratio",
                param_type=ParameterType.FLOAT,
                default=0.60,
                minimum=0.20,
                maximum=0.90,
                unit="ratio",
                description="Blend fraud target toward prior context amounts.",
            ),
            "inter_event_delay_hours": ParameterSpec(
                name="inter_event_delay_hours",
                param_type=ParameterType.FLOAT,
                default=6.0,
                minimum=0.5,
                maximum=48.0,
                unit="hours",
            ),
            "destination_diversity": ParameterSpec(
                name="destination_diversity",
                param_type=ParameterType.INT,
                default=4,
                minimum=1,
                maximum=8,
                unit="destinations",
            ),
            "transfer_probability": ParameterSpec(
                name="transfer_probability",
                param_type=ParameterType.FLOAT,
                default=0.75,
                minimum=0.25,
                maximum=1.0,
                unit="probability",
            ),
            "amount_jitter_ratio": ParameterSpec(
                name="amount_jitter_ratio",
                param_type=ParameterType.FLOAT,
                default=0.08,
                minimum=0.01,
                maximum=0.25,
                unit="ratio",
            ),
            "timestamp_jitter_minutes": ParameterSpec(
                name="timestamp_jitter_minutes",
                param_type=ParameterType.FLOAT,
                default=15.0,
                minimum=0.0,
                maximum=120.0,
                unit="minutes",
            ),
            "max_parameter_changes": ParameterSpec(
                name="max_parameter_changes",
                param_type=ParameterType.INT,
                default=2,
                minimum=1,
                maximum=3,
                unit="parameters",
                mutable=False,
                description="Immutable bound on one feedback-guided adaptation step.",
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
            allowed_channels=[Channel.MOBILE],
            max_transactions_per_account_per_day=12,
            max_accounts_involved=12,
            min_sequence_length=6,
            max_sequence_length=38,
            custom={
                "benchmark_only": True,
                "single_feedback_step": True,
                "unrestricted_search": False,
                "real_system_targeting": False,
            },
        ),
        source="deterministic_template",
        created_at=_CREATED_AT,
        metadata={
            "reference_basis": reference_basis,
            "simulator_version": "1.0.0",
            "adaptation_channel": "EvasionFeedback_only",
            "safety_scope": "synthetic_benchmark_only",
        },
    )


class AdaptiveEvasionBlueprintIdentifier(BaseAttackIdentifier):
    """Propose only the bounded adaptive-evasion benchmark template."""

    name = "adaptive-evasion-template"
    version = "1.0.0"

    def propose(self, context: IdentificationContext) -> list[AttackBlueprint]:
        family = AttackFamily.ADAPTIVE_DETECTOR_EVASION
        if context.target_families and family not in context.target_families:
            return []
        blueprint = build_adaptive_evasion_blueprint(
            attack_id=f"adaptive-detector-evasion-{context.seed}",
            target_features=context.observed_feature_names or None,
        )
        return [blueprint][: context.max_blueprints]


__all__ = [
    "ADAPTIVE_EVASION_BLUEPRINT_PROMPT",
    "AdaptiveEvasionBlueprintIdentifier",
    "build_adaptive_evasion_blueprint",
]
