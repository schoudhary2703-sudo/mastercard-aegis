"""FastAPI application exposing read-only AEGIS artifact data.

Run locally with:

    uvicorn aegis.api.app:app --reload --port 8000

Requires the optional `api` extra: `pip install -e ".[api]"`.

Every route builds a fresh `ArtifactIndex` from `AEGIS_ARTIFACTS_ROOT` (or the
repo root by default), so results always reflect what is currently on disk.
Nothing here mutates or retrains anything -- see `docs/ARCHITECTURE.md`:
"`api/` and `web/` are read-only consumers ... They compute nothing" beyond
summarizing what an artifact already contains.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from aegis.api import service
from aegis.api.dto import (
    AttackDetailDTO,
    AttacksResponseDTO,
    EvaluationResponseDTO,
    EvolutionResponseDTO,
    FinalBenchmarkSummaryDTO,
    HardestEvasionsResponseDTO,
    OverviewResponseDTO,
    RecentDetectionsResponseDTO,
)
from aegis.api.paths import ArtifactPathError, validate_slug
from aegis.api.settings import get_settings

app = FastAPI(
    title="AEGIS API",
    description="Read-only API over persisted AEGIS red/blue confrontation artifacts.",
    version="0.1.0",
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/overview", response_model=OverviewResponseDTO)
def get_overview() -> OverviewResponseDTO:
    settings = get_settings()
    index = service.build_index(settings)
    return service.build_overview(index, settings)


@app.get("/api/attacks", response_model=AttacksResponseDTO)
def get_attacks() -> AttacksResponseDTO:
    settings = get_settings()
    index = service.build_index(settings)
    return service.build_attacks(index, settings)


@app.get("/api/attacks/{attack_id}", response_model=AttackDetailDTO)
def get_attack(attack_id: str) -> AttackDetailDTO:
    try:
        validate_slug(attack_id, field="attack_id")
    except ArtifactPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = get_settings()
    index = service.build_index(settings)
    detail = service.build_attack_detail(index, attack_id, settings)
    if detail is None:
        raise HTTPException(
            status_code=404, detail=f"no attack blueprint found for id {attack_id!r}"
        )
    return detail


@app.get("/api/detections/recent", response_model=RecentDetectionsResponseDTO)
def get_recent_detections(
    limit: int = Query(default=50, ge=1, le=500),
) -> RecentDetectionsResponseDTO:
    settings = get_settings()
    index = service.build_index(settings)
    return service.build_recent_detections(index, settings, limit=limit)


@app.get("/api/evolution", response_model=EvolutionResponseDTO)
def get_evolution() -> EvolutionResponseDTO:
    settings = get_settings()
    index = service.build_index(settings)
    return service.build_evolution(index, settings)


@app.get("/api/evaluation", response_model=EvaluationResponseDTO)
def get_evaluation() -> EvaluationResponseDTO:
    settings = get_settings()
    index = service.build_index(settings)
    return service.build_evaluation(index, settings)


@app.get("/api/hardest-evasions", response_model=HardestEvasionsResponseDTO)
def get_hardest_evasions(
    limit: int = Query(default=25, ge=1, le=200),
) -> HardestEvasionsResponseDTO:
    settings = get_settings()
    index = service.build_index(settings)
    return service.build_hardest_evasions(index, settings, limit=limit)


@app.get("/api/benchmark", response_model=FinalBenchmarkSummaryDTO)
def get_benchmark() -> FinalBenchmarkSummaryDTO:
    """The final, judge-facing benchmark: baseline v1 vs Defender v2 vs
    Defender v3, Defender v3's fresh per-family performance, the LOAFO
    generalization results, and the hardest surviving attacks from LOAFO's
    fresh scenarios. Aggregated live from persisted artifacts on every call
    (see `aegis.api.benchmark`) - never reads a stale cache."""
    settings = get_settings()
    return service.build_benchmark(settings)
