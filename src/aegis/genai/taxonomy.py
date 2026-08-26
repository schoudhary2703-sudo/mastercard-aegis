"""Researched fraud-taxonomy entries, as inputs to the attack analyst.

These are the *research* half of the pipeline: publicly-documented fraud
typologies written up as prose, with no numbers attached. They are the input
to GenAI reasoning, not its output -- the analyst's job is to turn one of
these descriptions into structured, executable simulator parameters.

Nothing here is a metric or a claim about this system's performance. The
simulator parameter lists mirror what the corresponding generator in
`aegis.generate` actually exposes, so the analyst is constrained to knobs
that really exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aegis.shared.enums import AttackFamily

PAYMENT_CONTEXT = (
    "A PaySim-derived mobile-money world: accounts send PAYMENT, TRANSFER, "
    "CASH_IN, CASH_OUT and DEBIT operations. A detector sees only "
    "decision-time-safe features derived from the current transaction and "
    "strictly earlier events for the accounts involved: amount, hour of day, "
    "balances before, per-account transaction counts and velocities over 1h "
    "and 24h windows, deviation from that account's own historical amounts, "
    "and distinct-counterparty counts. It never sees attack labels, "
    "blueprint parameters, or which scenario a transaction belongs to."
)

SHARED_SAFETY_CONSTRAINTS = (
    "Synthetic data only -- never reference real institutions, real account "
    "identifiers, or real customers.",
    "Propose simulator parameters, never concrete transaction rows.",
    "Stay inside the three in-scope attack families; do not invent a fourth.",
    "An evasion that requires implausible traffic is a bug, not a finding.",
)


@dataclass(frozen=True)
class TaxonomyEntry:
    """One researched typology the attack analyst can be pointed at."""

    key: str
    scenario_name: str
    expected_family: AttackFamily
    research_summary: str
    simulator_parameters: tuple[str, ...]
    known_constraints: tuple[str, ...] = field(default=SHARED_SAFETY_CONSTRAINTS)


_BUSTOUT = TaxonomyEntry(
    key="synthetic-identity-bustout",
    scenario_name="Synthetic identity bust-out",
    expected_family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
    research_summary=(
        "A fabricated or blended identity -- assembled from a mix of real and "
        "invented attributes -- is used to open an account that behaves "
        "unremarkably for weeks or months. The account makes small, regular, "
        "plausible payments, builds a transaction history, and earns whatever "
        "implicit trust the institution's models assign to established "
        "accounts. Once that history exists, the attacker converts it: a short "
        "burst of high-value transfers drains the available balance and credit "
        "before any manual review cycle completes. The defining property is "
        "that the fraudulent phase is preceded by a genuinely benign phase, so "
        "any detector relying on account tenure or historical good behavior is "
        "being fed exactly the signal the attacker cultivated."
    ),
    simulator_parameters=(
        "warmup_transaction_count",
        "warmup_amount_mean",
        "warmup_amount_stddev",
        "warmup_duration_days",
        "account_age_days",
        "bustout_amount_multiplier",
        "bustout_transaction_count",
        "bustout_window_hours",
        "destination_diversity",
        "transition_delay_hours",
        "warmup_transfer_probability",
    ),
)

_MULE = TaxonomyEntry(
    key="mule-network-structuring",
    scenario_name="Mule network structuring",
    expected_family=AttackFamily.MULE_NETWORK_STRUCTURING,
    research_summary=(
        "A coordinator account distributes illicit funds across a set of mule "
        "accounts, which then layer the money through intermediate transfers "
        "before consolidating it toward a cash-out point. Individual amounts "
        "are deliberately kept unremarkable -- often below reporting or review "
        "thresholds -- so that no single transaction looks anomalous in "
        "isolation. The signal lives in the topology rather than the "
        "magnitudes: an account paying six distinct counterparties once each "
        "is structurally different from one paying the same counterparty six "
        "times, even though per-transaction volume features cannot tell them "
        "apart. Mule accounts are frequently recruited rather than fabricated, "
        "so they may carry real, legitimate history."
    ),
    simulator_parameters=(
        "mule_account_count",
        "fan_out_transaction_count",
        "layering_depth",
        "layering_transaction_count",
        "structuring_threshold",
        "amount_jitter_ratio",
        "inter_transfer_delay_hours",
        "cash_out_count",
    ),
)

_ADAPTIVE = TaxonomyEntry(
    key="adaptive-detector-evasion",
    scenario_name="Adaptive detector evasion",
    expected_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
    research_summary=(
        "An attacker with query access to a scoring system probes it, observes "
        "which attempts are approved versus declined or stepped up, and infers "
        "roughly which behavioral dimensions move the score. Subsequent "
        "attempts are adjusted along those dimensions -- smaller amounts, "
        "longer gaps, more counterparties, different hours -- until they land "
        "below the decision threshold while still achieving the attacker's "
        "objective. The distinguishing feature is that the attack is a "
        "feedback-driven search rather than a fixed pattern, so a detector "
        "hardened against yesterday's parameter values is not necessarily "
        "hardened against the search process that produced them. Generative "
        "tooling makes the search cheaper: variants can be drafted and "
        "prioritized far faster than a human could enumerate them."
    ),
    simulator_parameters=(
        "probe_transaction_count",
        "amount_scale",
        "amount_jitter_ratio",
        "inter_transaction_delay_hours",
        "counterparty_count",
        "active_hour_start",
        "active_hour_end",
        "escalation_ratio",
    ),
)

TAXONOMY: dict[str, TaxonomyEntry] = {
    entry.key: entry for entry in (_BUSTOUT, _MULE, _ADAPTIVE)
}


def taxonomy_keys() -> list[str]:
    return sorted(TAXONOMY)


def get_taxonomy_entry(key: str) -> TaxonomyEntry:
    try:
        return TAXONOMY[key]
    except KeyError as exc:
        msg = f"unknown taxonomy entry {key!r}; expected one of {taxonomy_keys()}"
        raise KeyError(msg) from exc


__all__ = [
    "PAYMENT_CONTEXT",
    "SHARED_SAFETY_CONSTRAINTS",
    "TAXONOMY",
    "TaxonomyEntry",
    "get_taxonomy_entry",
    "taxonomy_keys",
]
