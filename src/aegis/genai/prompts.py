"""Versioned prompt templates for the two GenAI reasoning stages.

`PROMPT_VERSION` is persisted on every run artifact. Bump it whenever a
template below changes in a way that could change model output, so two
artifacts produced under different wording are never silently compared as if
they came from the same instrument.

Both system prompts state the architectural rule explicitly, because it is
the rule most likely to be violated by a helpful model: *propose parameters,
never emit transactions.* The deterministic simulators own row generation, and
a run that came back with rows would be unreproducible from a seed.
"""

from __future__ import annotations

import json
from typing import Final

from aegis.genai.contracts import (
    MAX_MUTATION_MAGNITUDE,
    MAX_MUTATION_PROPOSALS,
    AttackAnalystRequest,
    BlindSpotAnalystRequest,
)

PROMPT_VERSION: Final[str] = "genai-prompts-v1"

_SHARED_RULES = """\
You are part of AEGIS, a defensive payment-fraud research system that runs a \
red-team / blue-team loop over SYNTHETIC data only (PaySim, a public synthetic \
mobile-money simulator). No real customer, account, or card data exists \
anywhere in this system, and nothing you propose is executed against a real \
payment network.

Hard architectural rule you must respect:
- You reason and propose STRUCTURED PARAMETERS. You never write transaction \
rows, amounts-per-row, account identifiers, or any concrete payment record.
- A separate deterministic, seeded simulator turns your parameters into \
reproducible synthetic transactions. If you emitted rows directly, the corpus \
would stop being reproducible from its seed.

Answer with a single JSON object matching the requested schema. No prose \
outside the JSON, no markdown fences."""

_ATTACK_ANALYST_SYSTEM = f"""\
{_SHARED_RULES}

Your role: ATTACK ANALYST. You turn researched fraud-taxonomy material into an \
executable, structured attack hypothesis that a deterministic simulator can \
run. Choose exactly one attack family from the fixed in-scope list you are \
given -- the scope is deliberately closed and you must not invent a fourth.

Recommend only parameters that appear in the simulator's exposed parameter \
list. Be explicit about what would make the generated traffic implausible, \
because an evasion achieved by unrealistic traffic is discarded as a bug, not \
counted as a finding."""

_BLIND_SPOT_ANALYST_SYSTEM = f"""\
{_SHARED_RULES}

Your role: BLIND-SPOT ANALYST. You are shown a real detector's real failures \
on already-generated synthetic attacks: which transactions it missed, the risk \
scores it assigned, and the detector-visible signals that drove those scores. \
Infer the most likely blind spot and propose bounded next-generation mutations.

Bounds you must respect:
- Propose changes ONLY to parameters listed as mutable. Any other parameter is \
structural and off-limits.
- At most {MAX_MUTATION_PROPOSALS} proposals.
- `magnitude` is a relative step and must be between 0.0 and \
{MAX_MUTATION_MAGNITUDE} inclusive.
- Every proposal must state its expected trade-off; a mutation that evades by \
destroying realism is not a win."""


def attack_analyst_system_prompt() -> str:
    return _ATTACK_ANALYST_SYSTEM


def blind_spot_analyst_system_prompt() -> str:
    return _BLIND_SPOT_ANALYST_SYSTEM


def attack_analyst_user_prompt(request: AttackAnalystRequest) -> str:
    """Render the attack-analyst input as an explicit, labeled block.

    The request is embedded as JSON rather than prose so the same template
    produces byte-identical text for identical inputs -- a prerequisite for
    comparing two runs at the same `PROMPT_VERSION`.
    """
    payload = request.model_dump(mode="json")
    return (
        "Analyze this fraud-taxonomy scenario and produce a structured attack "
        "hypothesis.\n\n"
        f"SCENARIO INPUT:\n{json.dumps(payload, indent=2, sort_keys=True)}\n\n"
        "Return one JSON object with exactly these keys: attack_family, "
        "attack_hypothesis, genai_enablement, payment_system_assumptions, "
        "observable_signals, recommended_simulator_parameters, realism_risks, "
        "safety_constraints, confidence.\n"
        "`recommended_simulator_parameters` is a list of objects with keys: "
        "name, value, rationale, unit (unit may be null).\n"
        "`confidence` is a number from 0.0 to 1.0."
    )


def blind_spot_analyst_user_prompt(request: BlindSpotAnalystRequest) -> str:
    """Render the blind-spot input, restating the bounds next to the data."""
    payload = request.model_dump(mode="json")
    return (
        "A detector failed on the attack described below. Diagnose the blind "
        "spot and propose bounded mutations.\n\n"
        f"OBSERVED FAILURE:\n{json.dumps(payload, indent=2, sort_keys=True)}\n\n"
        "Return one JSON object with exactly these keys: "
        "blind_spot_hypothesis, evidence, mutation_proposals, "
        "expected_trade_offs, safety_constraints, confidence.\n"
        "`mutation_proposals` is a list of objects with keys: parameter, "
        "direction, proposed_value, magnitude, rationale, confidence.\n"
        "`direction` is one of: increase, decrease, set, jitter, resample. "
        "`proposed_value` is required only when direction is 'set', otherwise "
        "null.\n"
        f"`magnitude` must be between 0.0 and {MAX_MUTATION_MAGNITUDE}, and "
        f"`parameter` must be one of: {request.mutable_parameters}."
    )


__all__ = [
    "PROMPT_VERSION",
    "attack_analyst_system_prompt",
    "attack_analyst_user_prompt",
    "blind_spot_analyst_system_prompt",
    "blind_spot_analyst_user_prompt",
]
