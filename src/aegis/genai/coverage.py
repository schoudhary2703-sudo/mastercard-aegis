"""Per-family GenAI coverage: what actually exists on disk, per attack family.

One question, answered honestly for each of the three deeply simulated
families: is there a *live* Attack Analyst run, a *live* Blind-Spot run, and a
guided next generation scored against the frozen detector?

The rules this module exists to enforce:

* A stage counts as covered only when a persisted artifact says
  `schema_valid=true` **and** `live=true`. A recorded replay, a failed run, or
  an absent file all read as not covered -- and each unavailable stage carries
  the reason it is unavailable, so a gap is visible rather than blank.
* Nothing is inferred across families. A bust-out run says nothing about mule
  coverage; every cell is read from an artifact whose `attack_family` matches.
* No number is computed here. Counts, recall and fidelity are copied off the
  guided-generation record that the deterministic pipeline wrote.

Used by both `scripts/build_genai_family_summary.py` (which persists the
canonical artifact) and `aegis.api` (which serves the same shape live), so the
screen and the artifact can never disagree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field

from aegis.shared.base import AegisModel
from aegis.shared.enums import AttackFamily

GENAI_DIR = "data/genai"
ATTACK_ANALYST_STAGE = "attack_analyst"
BLIND_SPOT_ANALYST_STAGE = "blind_spot_analyst"
GUIDED_DIR = "data/genai/guided_generations"

FAMILY_LABELS: dict[AttackFamily, str] = {
    AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT: "Synthetic Identity",
    AttackFamily.MULE_NETWORK_STRUCTURING: "Mule Network",
    AttackFamily.ADAPTIVE_DETECTOR_EVASION: "Adaptive Evasion",
}

# Which taxonomy scenario a live Attack Analyst run would have been asked
# about. The analyst answers with an `attack_family`, so this is only the
# fallback for attributing a run whose response failed to validate.
TAXONOMY_KEY_BY_FAMILY: dict[AttackFamily, str] = {
    AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT: "synthetic-identity-bustout",
    AttackFamily.MULE_NETWORK_STRUCTURING: "mule-network-structuring",
    AttackFamily.ADAPTIVE_DETECTOR_EVASION: "adaptive-detector-evasion",
}

_NO_RUN = "no live run artifact on disk for this family"
_NEEDS_BLIND_SPOT = "requires a live Blind-Spot artifact for this family"


class StageCoverage(AegisModel):
    """One analyst stage for one family."""

    available: bool = Field(..., description="A live, schema-valid artifact exists.")
    run_id: str = Field(default="")
    provider: str = Field(default="")
    model: str = Field(default="")
    prompt_version: str = Field(default="")
    live: bool = Field(default=False)
    created_at: str = Field(default="")
    source_artifact: str = Field(default="")
    reason: str = Field(
        default="", description="Why it is unavailable. Empty when available."
    )


class GuidedCoverage(AegisModel):
    """The guided next generation for one family, if one was produced."""

    available: bool = Field(...)
    generation_id: str = Field(default="")
    scenario_id: str = Field(default="")
    applied_mutation_count: int = Field(default=0, ge=0)
    rejected_mutation_count: int = Field(default=0, ge=0)
    seed: int | None = Field(default=None)
    detector_model_version: str = Field(default="")
    fraud_count: int | None = Field(default=None)
    caught_count: int | None = Field(default=None)
    escaped_count: int | None = Field(default=None)
    recall: float | None = Field(default=None)
    fidelity_score: float | None = Field(default=None)
    runtime_seconds: float | None = Field(default=None)
    hardest_survivor_id: str = Field(default="")
    reason: str = Field(default="")


class FamilyCoverage(AegisModel):
    """Everything the GenAI layer has produced for one attack family."""

    attack_family: AttackFamily = Field(...)
    label: str = Field(...)
    attack_analyst: StageCoverage = Field(...)
    blind_spot_analyst: StageCoverage = Field(...)
    guided_generation: GuidedCoverage = Field(...)

    @property
    def has_live_genai(self) -> bool:
        """Either analyst stage, live and schema-valid."""
        return self.attack_analyst.available or self.blind_spot_analyst.available

    @property
    def is_fully_covered(self) -> bool:
        """Both analyst stages live, plus a scored guided generation."""
        return (
            self.attack_analyst.available
            and self.blind_spot_analyst.available
            and self.guided_generation.available
        )


class GenAIFamilySummary(AegisModel):
    """Canonical 3-family GenAI coverage summary.

    Persisted by `scripts/build_genai_family_summary.py` and served by
    `/api/genai`. Both read the same artifacts through this module.
    """

    summary_version: str = Field(default="genai-family-coverage-v1")
    families: list[FamilyCoverage] = Field(default_factory=list)
    live_family_count: int = Field(default=0, ge=0)
    fully_covered_family_count: int = Field(default=0, ge=0)
    guided_family_count: int = Field(default=0, ge=0)
    limitations: list[str] = Field(default_factory=list)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _family_of_run(payload: dict[str, Any]) -> AttackFamily | None:
    """The family a persisted analyst run is about.

    Read off the validated response (the analyst declares it) or the request
    (the Blind-Spot request carries it). A run whose family cannot be read is
    attributed to nothing rather than guessed at.
    """
    for block in (payload.get("response"), payload.get("request")):
        if not isinstance(block, dict):
            continue
        raw = block.get("attack_family")
        if isinstance(raw, str):
            try:
                return AttackFamily(raw)
            except ValueError:
                return None
    return None


def _stage_runs(root: Path, stage: str) -> list[dict[str, Any]]:
    stage_dir = Path(root) / GENAI_DIR / stage
    if not stage_dir.is_dir():
        return []
    runs = [payload for path in sorted(stage_dir.glob("*.json")) if (payload := _read_json(path))]
    runs.sort(key=lambda p: str(p.get("created_at") or ""), reverse=True)
    return runs


def _stage_coverage(runs: list[dict[str, Any]], family: AttackFamily, stage: str) -> StageCoverage:
    """The newest live, schema-valid run for this family -- or why there is none."""
    matching = [run for run in runs if _family_of_run(run) is family]
    for run in matching:
        provenance = run.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        if not run.get("schema_valid") or not provenance.get("live"):
            continue
        return StageCoverage(
            available=True,
            run_id=str(run.get("run_id", "")),
            provider=str(provenance.get("provider", "")),
            model=str(provenance.get("model", "")),
            prompt_version=str(provenance.get("prompt_version", "")),
            live=True,
            created_at=str(run.get("created_at") or ""),
            source_artifact=f"{GENAI_DIR}/{stage}/{run.get('run_id', '')}.json",
        )
    if matching:
        return StageCoverage(
            available=False,
            reason=(
                f"{len(matching)} artifact(s) exist for this family but none is both live "
                "and schema-valid"
            ),
        )
    return StageCoverage(available=False, reason=_NO_RUN)


def _guided_coverage(
    root: Path, family: AttackFamily, *, blind_spot_available: bool
) -> GuidedCoverage:
    guided_dir = Path(root) / GUIDED_DIR
    records = []
    if guided_dir.is_dir():
        records = [
            payload
            for path in sorted(guided_dir.glob("*.json"))
            if (payload := _read_json(path)) and payload.get("attack_family") == family.value
        ]
    records.sort(key=lambda p: str(p.get("created_at") or ""), reverse=True)
    for record in records:
        provenance = record.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        applied = record.get("applied_mutations")
        applied = applied if isinstance(applied, list) else []
        if not applied:
            continue
        survivor = record.get("hardest_survivor")
        survivor = survivor if isinstance(survivor, dict) else {}
        rejected = record.get("rejected_mutations")
        return GuidedCoverage(
            available=True,
            generation_id=str(record.get("generation_id", "")),
            scenario_id=str(record.get("scenario_id") or ""),
            applied_mutation_count=len(applied),
            rejected_mutation_count=len(rejected) if isinstance(rejected, list) else 0,
            seed=provenance.get("seed") if isinstance(provenance.get("seed"), int) else None,
            detector_model_version=str(provenance.get("detector_model_version", "")),
            fraud_count=record.get("fraud_count"),
            caught_count=record.get("caught_count"),
            escaped_count=record.get("escaped_count"),
            recall=record.get("recall"),
            fidelity_score=record.get("fidelity_score"),
            runtime_seconds=record.get("runtime_seconds"),
            hardest_survivor_id=str(survivor.get("transaction_id", "")),
        )
    reason = (
        "a guided generation exists but no mutation survived the bounds check"
        if records
        else (_NEEDS_BLIND_SPOT if not blind_spot_available else "not run yet for this family")
    )
    return GuidedCoverage(available=False, reason=reason)


def build_family_coverage(root: Path) -> GenAIFamilySummary:
    """Read per-family GenAI coverage out of `root`'s persisted artifacts."""
    attack_runs = _stage_runs(root, ATTACK_ANALYST_STAGE)
    blind_runs = _stage_runs(root, BLIND_SPOT_ANALYST_STAGE)

    families: list[FamilyCoverage] = []
    for family, label in FAMILY_LABELS.items():
        blind = _stage_coverage(blind_runs, family, BLIND_SPOT_ANALYST_STAGE)
        families.append(
            FamilyCoverage(
                attack_family=family,
                label=label,
                attack_analyst=_stage_coverage(attack_runs, family, ATTACK_ANALYST_STAGE),
                blind_spot_analyst=blind,
                guided_generation=_guided_coverage(
                    root, family, blind_spot_available=blind.available
                ),
            )
        )

    return GenAIFamilySummary(
        families=families,
        live_family_count=sum(1 for f in families if f.has_live_genai),
        fully_covered_family_count=sum(1 for f in families if f.is_fully_covered),
        guided_family_count=sum(1 for f in families if f.guided_generation.available),
        limitations=[
            "A stage counts as covered only when its artifact is both live and schema-valid; "
            "a recorded replay is never counted.",
            "Guided-generation figures are one fresh scenario per family (3-12 fraud events), "
            "directional rather than statistically powered.",
            "Coverage describes GenAI reasoning artifacts only. It says nothing about detector "
            "quality, which the benchmark reports separately.",
        ],
    )


__all__ = [
    "ATTACK_ANALYST_STAGE",
    "BLIND_SPOT_ANALYST_STAGE",
    "FAMILY_LABELS",
    "GENAI_DIR",
    "GUIDED_DIR",
    "TAXONOMY_KEY_BY_FAMILY",
    "FamilyCoverage",
    "GenAIFamilySummary",
    "GuidedCoverage",
    "StageCoverage",
    "build_family_coverage",
]
