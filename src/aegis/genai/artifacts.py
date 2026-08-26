"""Persistence for GenAI run artifacts.

Every run -- successful or failed -- is written to
`<root>/data/genai/<stage>/<run_id>.json`. Failures are persisted too, with
`schema_valid=false` and the raw text that failed to validate, so a stage that
did not work leaves visible evidence on disk instead of an absent file that
could be mistaken for "not run yet".

Run ids are content-derived (a hash of the request plus prompt version and
model), so re-running the same analysis with the same instrument is
idempotent on disk rather than accumulating near-duplicate files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aegis.genai.contracts import GenAIRunArtifact

GENAI_ARTIFACTS_DIR = "data/genai"


def build_run_id(*, stage: str, request: dict[str, Any], prompt_version: str, model: str) -> str:
    """Deterministic id for one (stage, request, instrument) combination."""
    digest_source = json.dumps(
        {
            "stage": stage,
            "request": request,
            "prompt_version": prompt_version,
            "model": model,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
    return f"{stage}-{digest}"


def artifact_path(root: Path, artifact: GenAIRunArtifact) -> Path:
    return Path(root) / GENAI_ARTIFACTS_DIR / artifact.stage / f"{artifact.run_id}.json"


def write_run_artifact(root: Path, artifact: GenAIRunArtifact) -> Path:
    """Persist one run. Returns the path written."""
    path = artifact_path(root, artifact)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = artifact.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_run_artifact(path: Path) -> GenAIRunArtifact:
    """Load a persisted run artifact, validating it against the contract."""
    return GenAIRunArtifact.model_validate_json(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "GENAI_ARTIFACTS_DIR",
    "artifact_path",
    "build_run_id",
    "read_run_artifact",
    "write_run_artifact",
]
