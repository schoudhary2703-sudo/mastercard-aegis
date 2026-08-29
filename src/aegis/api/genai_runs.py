"""Read-only discovery of persisted GenAI run artifacts.

Serves what `aegis.genai` wrote to `data/genai/<stage>/<run_id>.json` so the
UI can show the reasoning layer's actual output alongside its provenance.

Two properties matter more than completeness here:

* If no run artifact exists, this returns an empty list. The UI then says so.
  There is no placeholder reasoning anywhere in this path.
* `live` is carried through untouched from the artifact. A recorded/offline
  replay stays visibly a replay all the way to the screen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aegis.api.paths import resolve_within, safe_child_dirs
from aegis.api.reader import read_json

GENAI_DIR = "data/genai"
GUIDED_DIR = "data/genai/guided_generations"
ATTACK_ANALYST_STAGE = "attack_analyst"
BLIND_SPOT_ANALYST_STAGE = "blind_spot_analyst"

# `guided_generations/` sits under data/genai/ but holds handoff artifacts,
# not analyst runs -- excluded from run discovery so it is never mistaken for
# a reasoning stage.
_NON_STAGE_DIRS = frozenset({"guided_generations"})


def _str_list(value: Any) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _proposed_mutations(response: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Flatten the analyst's proposals for display.

    Read straight off the persisted response -- these are what the model
    *asked for*, which is not the same as what the bounds adapter accepted.
    The applied set lives on the guided-generation artifact instead.
    """
    if not isinstance(response, dict):
        return []
    raw = response.get("mutation_proposals")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "parameter": str(item.get("parameter", "")),
                "direction": str(item.get("direction", "")),
                "magnitude": item.get("magnitude"),
                "rationale": str(item.get("rationale", "")),
                "confidence": item.get("confidence"),
            }
        )
    return out


def _run_summary(stage: str, payload: dict[str, Any], source: str) -> dict[str, Any] | None:
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return None
    response = payload.get("response")
    response = response if isinstance(response, dict) else None
    return {
        "run_id": str(payload.get("run_id", "")),
        "stage": stage,
        "created_at": payload.get("created_at"),
        "provider": str(provenance.get("provider", "")),
        "model": str(provenance.get("model", "")),
        "prompt_version": str(provenance.get("prompt_version", "")),
        "live": bool(provenance.get("live", False)),
        "schema_valid": bool(payload.get("schema_valid", False)),
        "failure": payload.get("failure"),
        "response": response,
        "source_artifact": source,
        # Convenience projections so the UI renders one-line cards without
        # re-parsing the raw response shape. Empty when absent -- never a
        # placeholder sentence.
        "attack_hypothesis": str((response or {}).get("attack_hypothesis", "")),
        "genai_enablement": str((response or {}).get("genai_enablement", "")),
        "blind_spot_hypothesis": str((response or {}).get("blind_spot_hypothesis", "")),
        "evidence": _str_list((response or {}).get("evidence")),
        "observable_signals": _str_list((response or {}).get("observable_signals")),
        "confidence": (response or {}).get("confidence"),
        "proposed_mutations": _proposed_mutations(response),
    }


def build_genai_runs(root: Path) -> list[dict[str, Any]]:
    """Every persisted GenAI run under `root`, newest first per stage.

    Malformed files are skipped rather than failing the endpoint -- the same
    best-effort posture the rest of the artifact layer uses.
    """
    out: list[dict[str, Any]] = []
    for stage_dir in safe_child_dirs(root, GENAI_DIR):
        stage = stage_dir.name
        if stage in _NON_STAGE_DIRS:
            continue
        for path in sorted(stage_dir.glob("*.json")):
            payload = read_json(resolve_within(root, GENAI_DIR, stage, path.name))
            if not isinstance(payload, dict):
                continue
            summary = _run_summary(stage, payload, f"{GENAI_DIR}/{stage}/{path.name}")
            if summary:
                out.append(summary)
    out.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return out


def latest_by_stage(
    runs: list[dict[str, Any]], *, live_only: bool = False
) -> dict[str, dict[str, Any] | None]:
    """The most recent *successful* run per analyst stage, if any.

    `live_only` restricts to genuinely live model calls, which is how the UI
    asks "is there a live artifact?" without ever treating a recorded replay
    as one.
    """
    result: dict[str, dict[str, Any] | None] = {
        ATTACK_ANALYST_STAGE: None,
        BLIND_SPOT_ANALYST_STAGE: None,
    }
    for run in runs:
        stage = run.get("stage")
        if stage not in result or result[stage] is not None:
            continue
        if not run.get("schema_valid"):
            continue
        if live_only and not run.get("live"):
            continue
        result[stage] = run
    return result


def build_guided_generations(root: Path) -> list[dict[str, Any]]:
    """Persisted GenAI-guided next-generation artifacts, newest first.

    Empty until the generation step has actually run. `genai_guided` is
    computed the same way `GenAIGuidedGeneration.is_genai_guided` does --
    complete provenance *and* at least one surviving mutation -- so an
    artifact missing provenance is served, but never labeled GenAI-guided.
    """
    out: list[dict[str, Any]] = []
    for path in sorted((resolve_within(root, GUIDED_DIR)).glob("*.json")):
        payload = read_json(resolve_within(root, GUIDED_DIR, path.name))
        if not isinstance(payload, dict):
            continue
        prov = payload.get("provenance")
        prov = prov if isinstance(prov, dict) else {}
        applied = payload.get("applied_mutations")
        applied = applied if isinstance(applied, list) else []
        complete = bool(
            prov.get("genai_run_id")
            and prov.get("provider")
            and prov.get("model")
            and prov.get("prompt_version")
        )
        out.append(
            {
                "generation_id": str(payload.get("generation_id", "")),
                "created_at": payload.get("created_at"),
                "attack_family": payload.get("attack_family"),
                "genai_run_id": str(prov.get("genai_run_id", "")),
                "provider": str(prov.get("provider", "")),
                "model": str(prov.get("model", "")),
                "prompt_version": str(prov.get("prompt_version", "")),
                "live": bool(prov.get("live", False)),
                "seed": prov.get("seed"),
                "source_confrontation_id": str(prov.get("source_confrontation_id", "")),
                "detector_model_version": str(prov.get("detector_model_version", "")),
                "blind_spot_hypothesis": str(payload.get("blind_spot_hypothesis", "")),
                "applied_mutations": applied,
                "rejected_mutations": payload.get("rejected_mutations") or [],
                "parent_blueprint_id": str(payload.get("parent_blueprint_id", "")),
                "resulting_blueprint_id": str(payload.get("resulting_blueprint_id", "")),
                "scenario_id": payload.get("scenario_id"),
                "fraud_count": payload.get("fraud_count"),
                "caught_count": payload.get("caught_count"),
                "escaped_count": payload.get("escaped_count"),
                "recall": payload.get("recall"),
                "fidelity_score": payload.get("fidelity_score"),
                "hardest_survivor": payload.get("hardest_survivor"),
                "dry_run": bool(payload.get("dry_run", True)),
                "genai_guided": complete and bool(applied),
                "source_artifact": f"{GUIDED_DIR}/{path.name}",
            }
        )
    out.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return out


__all__ = [
    "ATTACK_ANALYST_STAGE",
    "BLIND_SPOT_ANALYST_STAGE",
    "GENAI_DIR",
    "GUIDED_DIR",
    "build_genai_runs",
    "build_guided_generations",
    "latest_by_stage",
]
