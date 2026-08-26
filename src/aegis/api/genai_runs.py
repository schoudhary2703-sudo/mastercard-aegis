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
ATTACK_ANALYST_STAGE = "attack_analyst"
BLIND_SPOT_ANALYST_STAGE = "blind_spot_analyst"


def _run_summary(stage: str, payload: dict[str, Any], source: str) -> dict[str, Any] | None:
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return None
    response = payload.get("response")
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
        "response": response if isinstance(response, dict) else None,
        "source_artifact": source,
    }


def build_genai_runs(root: Path) -> list[dict[str, Any]]:
    """Every persisted GenAI run under `root`, newest first per stage.

    Malformed files are skipped rather than failing the endpoint -- the same
    best-effort posture the rest of the artifact layer uses.
    """
    out: list[dict[str, Any]] = []
    for stage_dir in safe_child_dirs(root, GENAI_DIR):
        stage = stage_dir.name
        for path in sorted(stage_dir.glob("*.json")):
            payload = read_json(resolve_within(root, GENAI_DIR, stage, path.name))
            if not isinstance(payload, dict):
                continue
            summary = _run_summary(stage, payload, f"{GENAI_DIR}/{stage}/{path.name}")
            if summary:
                out.append(summary)
    out.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return out


def latest_by_stage(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    """The most recent *successful* run per analyst stage, if any."""
    result: dict[str, dict[str, Any] | None] = {
        ATTACK_ANALYST_STAGE: None,
        BLIND_SPOT_ANALYST_STAGE: None,
    }
    for run in runs:
        stage = run.get("stage")
        if stage in result and result[stage] is None and run.get("schema_valid"):
            result[stage] = run
    return result


__all__ = [
    "ATTACK_ANALYST_STAGE",
    "BLIND_SPOT_ANALYST_STAGE",
    "GENAI_DIR",
    "build_genai_runs",
    "latest_by_stage",
]
