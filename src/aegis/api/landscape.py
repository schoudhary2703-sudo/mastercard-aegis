"""Read-only projections of the breadth taxonomy and the generation-scale run.

Two persisted artifacts, served for the judge-facing screens:

* `data/reports/attack_taxonomy.json` -- 14 evidence-backed scenarios, of
  which exactly the three implemented `AttackFamily` values are
  `DEEP_SIMULATED`. The rest are `IDENTIFIED_ONLY` and must never be rendered
  as if AEGIS simulates them.
* `data/reports/generation_scale_benchmark.json` -- one generation-only
  throughput/fidelity observation per family, plus its aggregate.

Like the rest of `aegis.api`, this is deliberately dumb: every number is
copied out of a file. Nothing is computed, defaulted to a plausible value, or
derived from a second artifact -- a count the artifact does not carry comes
back as `None` and the UI shows a dash. Missing artifacts return `None`, which
the UI renders as "not produced yet".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aegis.api.paths import resolve_within
from aegis.api.reader import read_json

REPORTS_DIR = "data/reports"
TAXONOMY_FILE = "attack_taxonomy.json"
SCALE_BENCHMARK_FILE = "generation_scale_benchmark.json"

DEEP_SIMULATED = "DEEP_SIMULATED"
IDENTIFIED_ONLY = "IDENTIFIED_ONLY"

# Deep-simulated taxonomy ids map onto the three implemented attack families,
# which is what lets a judge jump from a landscape card into the real
# experiment. An id with no entry here is breadth-only and gets no link.
_ATTACK_FAMILY_BY_TAXONOMY_ID = {
    "synthetic-identity-bustout": "synthetic_identity_bustout",
    "mule-network-structuring": "mule_network_structuring",
    "adaptive-detector-evasion": "adaptive_detector_evasion",
}

FIDELITY_CAVEAT = (
    "Descriptive similarity to PaySim/reference behavior — not proof of production realism."
)


def _str_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _sources(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            out.append({"title": str(item.get("title", "")), "url": item["url"]})
    return out


def _scenario(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("implementation_status", ""))
    taxonomy_id = str(payload.get("id", ""))
    return {
        "id": taxonomy_id,
        "name": str(payload.get("name", "")),
        "category": str(payload.get("category", "")),
        "channels": _str_list(payload.get("channels")),
        "rails": _str_list(payload.get("rails")),
        "genai_abuse_mechanism": str(payload.get("genai_abuse_mechanism", "")),
        "observable_signals": _str_list(payload.get("observable_signals")),
        "plausibility_evidence_note": str(payload.get("plausibility_evidence_note", "")),
        "evidence_sources": _sources(payload.get("evidence_sources")),
        "simulation_readiness": str(payload.get("simulation_readiness", "")),
        "implementation_status": status,
        "deeply_simulated": status == DEEP_SIMULATED,
        # Only a deep-simulated entry can point at a real experiment.
        "attack_family": (
            _ATTACK_FAMILY_BY_TAXONOMY_ID.get(taxonomy_id) if status == DEEP_SIMULATED else None
        ),
    }


def build_taxonomy(root: Path) -> dict[str, Any] | None:
    """The breadth catalog, or `None` when the artifact has not been exported."""
    payload = read_json(resolve_within(root, REPORTS_DIR, TAXONOMY_FILE))
    if not isinstance(payload, dict):
        return None
    raw_scenarios = payload.get("scenarios")
    scenarios = [_scenario(s) for s in raw_scenarios if isinstance(s, dict)] if (
        isinstance(raw_scenarios, list)
    ) else []
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    categories = _str_list(summary.get("categories_represented"))
    channels = _str_list(summary.get("channels_represented"))
    rails = _str_list(summary.get("rails_represented"))
    return {
        "taxonomy_version": str(payload.get("taxonomy_version", "")),
        "scope_note": str(payload.get("scope_note", "")),
        "total_attacks_identified": _int(summary.get("total_attacks_identified")),
        "deeply_simulated": _int(summary.get("deeply_simulated")),
        "category_count": len(categories),
        "channel_count": len(channels),
        "rail_count": len(rails),
        "categories": categories,
        "channels": channels,
        "rails": rails,
        "scenarios": scenarios,
        "source_artifact": f"{REPORTS_DIR}/{TAXONOMY_FILE}",
    }


def _fidelity_components(payload: Any) -> list[dict[str, Any]]:
    """Flatten `{group: {metric: score}}` into ordered, renderable rows.

    Group names differ per family (each generator declares its own invariants),
    so the shape is kept generic rather than forced into a fixed schema the
    artifact does not have.
    """
    if not isinstance(payload, dict):
        return []
    out: list[dict[str, Any]] = []
    for group, metrics in payload.items():
        if not isinstance(metrics, dict):
            continue
        scores = [
            {"name": str(name), "score": _number(score)}
            for name, score in metrics.items()
            if _number(score) is not None
        ]
        if scores:
            out.append({"group": str(group), "metrics": scores})
    return out


def _family(payload: dict[str, Any]) -> dict[str, Any]:
    reproducibility = payload.get("deterministic_reproducibility")
    reproducibility = reproducibility if isinstance(reproducibility, dict) else {}
    return {
        "attack_family": str(payload.get("attack_family", "")),
        "blueprint_id": str(payload.get("blueprint_id", "")),
        "generator_name": str(payload.get("generator_name", "")),
        "seed": _int(payload.get("seed")),
        "scenarios_generated": _int(payload.get("scenarios_generated")),
        "transactions_generated": _int(payload.get("transactions_generated")),
        "fraud_transactions_generated": _int(payload.get("fraud_transactions_generated")),
        "generation_seconds": _number(payload.get("generation_seconds")),
        "throughput_transactions_per_second": _number(
            payload.get("throughput_transactions_per_second")
        ),
        # Fidelity excluding constraint validity is the honest headline: mixing
        # invariant checks into a similarity score would inflate it.
        "fidelity_excluding_constraints": _number(payload.get("fidelity_excluding_constraints")),
        "distributional_fidelity_score": _number(payload.get("distributional_fidelity_score")),
        "generator_reported_overall_fidelity_score": _number(
            payload.get("generator_reported_overall_fidelity_score")
        ),
        "constraint_valid_percentage": _number(payload.get("constraint_valid_percentage")),
        "constraint_violation_rate": _number(payload.get("constraint_violation_rate")),
        "deterministic_verified": bool(reproducibility.get("verified", False)),
        "historical_scenario_id_overlap_count": _int(
            payload.get("historical_scenario_id_overlap_count")
        ),
        "fidelity_components": _fidelity_components(
            payload.get("family_specific_fidelity_components")
        ),
        "limitations": _str_list(payload.get("limitations")),
    }


def build_generation_scale(root: Path) -> dict[str, Any] | None:
    """The generation-scale benchmark, or `None` when it has not been run."""
    payload = read_json(resolve_within(root, REPORTS_DIR, SCALE_BENCHMARK_FILE))
    if not isinstance(payload, dict):
        return None
    raw_families = payload.get("families")
    families = [_family(f) for f in raw_families if isinstance(f, dict)] if (
        isinstance(raw_families, list)
    ) else []
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    environment = payload.get("environment")
    environment = environment if isinstance(environment, dict) else {}
    return {
        "benchmark_version": str(payload.get("benchmark_version", "")),
        "benchmark_scope": str(payload.get("benchmark_scope", "")),
        "platform": str(environment.get("platform", "")),
        "family_count": _int(summary.get("family_count")),
        "total_scenarios": _int(summary.get("total_scenarios")),
        "total_transactions": _int(summary.get("total_transactions")),
        "total_fraud_transactions": _int(summary.get("total_fraud_transactions")),
        "total_generation_seconds": _number(summary.get("total_generation_seconds")),
        "aggregate_throughput_transactions_per_second": _number(
            summary.get("aggregate_throughput_transactions_per_second")
        ),
        "all_constraints_valid": bool(summary.get("all_constraints_valid", False)),
        "all_deterministic": bool(summary.get("all_deterministic", False)),
        "historical_scenario_id_overlap_count": _int(
            summary.get("historical_scenario_id_overlap_count")
        ),
        "families": families,
        "fidelity_caveat": FIDELITY_CAVEAT,
        "source_artifact": f"{REPORTS_DIR}/{SCALE_BENCHMARK_FILE}",
    }


__all__ = [
    "DEEP_SIMULATED",
    "FIDELITY_CAVEAT",
    "IDENTIFIED_ONLY",
    "REPORTS_DIR",
    "SCALE_BENCHMARK_FILE",
    "TAXONOMY_FILE",
    "build_generation_scale",
    "build_taxonomy",
]
