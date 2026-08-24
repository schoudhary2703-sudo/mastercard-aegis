"""Deterministic synthetic-identity blueprint authoring and future-LLM prompt shape."""

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

SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT = """\
Produce one JSON AttackBlueprint for the synthetic_identity_bustout family.
The blueprint must describe identity onboarding, legitimate warm-up/history,
a delayed trust transition, and a bounded multi-transaction bust-out. Declare
every tunable value as a ParameterSpec with realistic minimum and maximum
bounds. Use relative BehavioralStep offsets only. Do not include executable
code, detector internals, model thresholds, adaptive mutations, or any attack
family other than synthetic_identity_bustout. The output must validate against
the frozen AEGIS AttackBlueprint JSON schema with extra fields forbidden.
"""

_CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def build_synthetic_identity_blueprint(
    *,
    attack_id: str = "synthetic-identity-bustout-v1",
    warmup_amount_mean: float = 75.0,
    warmup_amount_stddev: float = 25.0,
    currency: str = "XXX",
    reference_basis: str = "bounded_fallback",
    target_features: list[str] | None = None,
) -> AttackBlueprint:
    """Build the canonical bounded blueprint without requiring an LLM service."""
    warmup_mean = min(max(float(warmup_amount_mean), 10.0), 500.0)
    warmup_stddev = min(max(float(warmup_amount_stddev), 1.0), 200.0)
    currency_code = currency.upper()
    warmup_days = 21
    transition_hours = 24
    return AttackBlueprint(
        attack_id=attack_id,
        attack_family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
        name="Synthetic identity trust build and bust-out",
        description=(
            "A low-history synthetic persona establishes ordinary payment behaviour before "
            "a sudden, bounded series of high-value transfers and cash-outs."
        ),
        objective=(
            "Build sufficient legitimate-looking history to make the later behavioral "
            "transition a realistic bust-out stress case."
        ),
        target_features=target_features
        or [
            "temporal.account_age_days",
            "temporal.velocity_24h",
            "temporal.amount_ratio_to_history",
            "behavioral.payee_diversity",
        ],
        sequence=[
            BehavioralStep(
                step_id="identity-onboarding",
                order=0,
                action="establish_low_history_persona",
                description="Create a new synthetic persona with a bounded account-age proxy.",
                channel=Channel.MOBILE,
                offset_seconds=0.0,
            ),
            BehavioralStep(
                step_id="warmup-history",
                order=1,
                action="build_legitimate_payment_history",
                description="Emit spaced, moderate, explicitly legitimate warm-up activity.",
                channel=Channel.MOBILE,
                offset_seconds=timedelta(days=1).total_seconds(),
                amount_policy={"distribution": "bounded_normal"},
            ),
            BehavioralStep(
                step_id="trust-transition",
                order=2,
                action="pause_after_warmup",
                description="Leave a configurable delay before the behavioral transition.",
                channel=Channel.MOBILE,
                offset_seconds=timedelta(days=warmup_days).total_seconds(),
            ),
            BehavioralStep(
                step_id="bust-out",
                order=3,
                action="execute_bounded_bustout",
                description="Concentrate elevated transfers and cash-outs into a short window.",
                channel=Channel.MOBILE,
                offset_seconds=(
                    timedelta(days=warmup_days) + timedelta(hours=transition_hours)
                ).total_seconds(),
                amount_policy={"distribution": "warmup_mean_multiplier"},
            ),
        ],
        parameters={
            "warmup_transaction_count": ParameterSpec(
                name="warmup_transaction_count",
                param_type=ParameterType.INT,
                default=12,
                minimum=4,
                maximum=40,
                unit="transactions",
                description="Legitimate transactions used to establish behavioral history.",
            ),
            "warmup_amount_mean": ParameterSpec(
                name="warmup_amount_mean",
                param_type=ParameterType.FLOAT,
                default=warmup_mean,
                minimum=10.0,
                maximum=500.0,
                unit=currency_code,
                description="Target mean for bounded warm-up amounts.",
            ),
            "warmup_amount_stddev": ParameterSpec(
                name="warmup_amount_stddev",
                param_type=ParameterType.FLOAT,
                default=warmup_stddev,
                minimum=1.0,
                maximum=200.0,
                unit=currency_code,
                description="Warm-up amount dispersion before realism clipping.",
            ),
            "warmup_duration_days": ParameterSpec(
                name="warmup_duration_days",
                param_type=ParameterType.INT,
                default=warmup_days,
                minimum=7,
                maximum=90,
                unit="days",
            ),
            "account_age_days": ParameterSpec(
                name="account_age_days",
                param_type=ParameterType.INT,
                default=14,
                minimum=1,
                maximum=60,
                unit="days",
                description="History proxy at the beginning of observable warm-up activity.",
            ),
            "bustout_amount_multiplier": ParameterSpec(
                name="bustout_amount_multiplier",
                param_type=ParameterType.FLOAT,
                default=8.0,
                minimum=3.0,
                maximum=20.0,
                unit="ratio",
            ),
            "bustout_transaction_count": ParameterSpec(
                name="bustout_transaction_count",
                param_type=ParameterType.INT,
                default=3,
                minimum=1,
                maximum=8,
                unit="transactions",
            ),
            "bustout_window_hours": ParameterSpec(
                name="bustout_window_hours",
                param_type=ParameterType.FLOAT,
                default=6.0,
                minimum=1.0,
                maximum=24.0,
                unit="hours",
            ),
            "destination_diversity": ParameterSpec(
                name="destination_diversity",
                param_type=ParameterType.INT,
                default=3,
                minimum=1,
                maximum=8,
                unit="destinations",
            ),
            "transition_delay_hours": ParameterSpec(
                name="transition_delay_hours",
                param_type=ParameterType.FLOAT,
                default=float(transition_hours),
                minimum=1.0,
                maximum=168.0,
                unit="hours",
            ),
            "warmup_transfer_probability": ParameterSpec(
                name="warmup_transfer_probability",
                param_type=ParameterType.FLOAT,
                default=0.25,
                minimum=0.05,
                maximum=0.75,
                unit="probability",
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
            max_accounts_involved=25,
            min_sequence_length=5,
            max_sequence_length=48,
        ),
        source="deterministic_template",
        created_at=_CREATED_AT,
        metadata={
            "reference_basis": reference_basis,
            "llm_prompt_template_available": True,
            "simulator_version": "1.0.0",
        },
    )


class SyntheticIdentityBlueprintIdentifier(BaseAttackIdentifier):
    """Propose the canonical template through the existing identification interface."""

    name = "synthetic-identity-template"
    version = "1.0.0"

    def propose(self, context: IdentificationContext) -> list[AttackBlueprint]:
        family = AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT
        if context.target_families and family not in context.target_families:
            return []
        target_features = context.observed_feature_names or None
        blueprint = build_synthetic_identity_blueprint(
            attack_id=f"synthetic-identity-bustout-{context.seed}",
            target_features=target_features,
        )
        return [blueprint][: context.max_blueprints]


__all__ = [
    "SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT",
    "SyntheticIdentityBlueprintIdentifier",
    "build_synthetic_identity_blueprint",
]
