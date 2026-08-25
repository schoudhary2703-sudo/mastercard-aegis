"""Discovers and indexes existing AEGIS experiment artifacts.

This is the only module that knows the on-disk layout of `models/` and
`data/synthetic/**` / `data/hardening/**`. Everything above it (`service.py`)
works against the `ArtifactIndex` objects built here, never against raw
paths. Discovery is best-effort per artifact directory: a malformed or
partial directory is skipped, not fatal to the rest of the index.

Artifacts are read-only. Nothing in this module ever writes to `root`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from aegis.api.paths import resolve_within, safe_child_dirs
from aegis.api.reader import count_jsonl_rows, read_json

MODELS_DIR = "models"
CONFRONTATIONS_DIR = "data/synthetic/confrontations"
ADAPTIVE_ROUNDS_DIR = "data/synthetic/adaptive_rounds"
HARDENING_DIR = "data/hardening"

ModelRole = Literal["baseline_v1", "defender_v2", "defender_v3"]

# LOAFO fold models (`models/loafo-*/`) are evaluation/generalization
# artifacts -- each is a detector trained with one attack family withheld, to
# measure whether hardening transfers to an unseen family. They are not part
# of the core baseline-v1 -> Defender-v2 -> Defender-v3 lineage, so they are
# excluded from `ArtifactIndex.models` entirely; `aegis.api.benchmark`
# discovers them separately (by the same prefix) for the LOAFO section of
# the final benchmark.
LOAFO_FOLD_PREFIX = "loafo-"


@dataclass(frozen=True)
class ModelArtifact:
    model_version: str
    dir_path: Path
    metadata: dict[str, Any] | None
    evaluation_test: dict[str, Any] | None
    evaluation_validation: dict[str, Any] | None
    regression_vs_baseline: dict[str, Any] | None
    generation2_handoff: dict[str, Any] | None

    @property
    def source_artifact(self) -> str:
        return self.dir_path.name

    @property
    def is_hardened(self) -> bool:
        return self.generation2_handoff is not None

    @property
    def role(self) -> ModelRole:
        """`baseline_v1` / `defender_v2` / `defender_v3`, classified the same
        way `aegis.api.benchmark` classifies them: by which regression report
        the model directory carries, not by directory name -- so a reseeded
        rerun under a different `model_version` is still classified
        correctly. `defender_v3` (cross-family hardening) is checked first
        because it also satisfies the `defender_v2` condition were the
        pipeline ever rerun with both reports present."""
        if (self.dir_path / "regression_vs_v1_v2.json").is_file():
            return "defender_v3"
        if (self.dir_path / "regression_vs_baseline.json").is_file():
            return "defender_v2"
        return "baseline_v1"


@dataclass(frozen=True)
class ConfrontationArtifact:
    report_id: str
    dir_path: Path
    report: dict[str, Any]
    blueprint: dict[str, Any] | None
    hardest_evasions: list[dict[str, Any]]
    transaction_count: int
    evasion_count: int
    detector_output_count: int

    @property
    def model_version(self) -> str:
        return str(self.report.get("model_version", ""))

    @property
    def is_adaptive(self) -> bool:
        return bool(self.report.get("metadata", {}).get("adaptive", False))

    @property
    def source_artifact(self) -> str:
        return self.dir_path.name


@dataclass(frozen=True)
class AdaptiveRoundCandidate:
    candidate_id: str
    dir_path: Path
    blueprint: dict[str, Any] | None
    confrontation: dict[str, Any] | None

    @property
    def source_artifact(self) -> str:
        return self.dir_path.name


@dataclass(frozen=True)
class AdaptiveRoundArtifact:
    report_id: str
    dir_path: Path
    report: dict[str, Any]
    candidates: list[AdaptiveRoundCandidate] = field(default_factory=list)

    @property
    def round_index(self) -> int:
        return int(self.report.get("round_index", 0))

    @property
    def model_version(self) -> str:
        return str(self.report.get("model_version", ""))

    @property
    def parent_confrontation_id(self) -> str | None:
        value = self.report.get("parent_confrontation_id")
        return str(value) if value else None

    @property
    def selected_candidate_id(self) -> str | None:
        value = self.report.get("selected_candidate_id")
        return str(value) if value else None

    @property
    def source_artifact(self) -> str:
        return self.dir_path.name


@dataclass(frozen=True)
class HardeningArtifact:
    run_id: str
    dir_path: Path
    provenance: dict[str, Any] | None
    hard_positive_count: int

    @property
    def source_artifact(self) -> str:
        return self.dir_path.name


class ArtifactIndex:
    """A snapshot of every real artifact discovered under `root`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.models: list[ModelArtifact] = _discover_models(root)
        self.confrontations: list[ConfrontationArtifact] = _discover_confrontations(root)
        self.adaptive_rounds: list[AdaptiveRoundArtifact] = _discover_adaptive_rounds(root)
        self.hardening_runs: list[HardeningArtifact] = _discover_hardening(root)

    # -- lineage -----------------------------------------------------------

    def baseline_model(self) -> ModelArtifact | None:
        candidates = [m for m in self.models if not m.is_hardened]
        if not candidates:
            return None
        return min(candidates, key=lambda m: _saved_at(m))

    def hardened_model(self) -> ModelArtifact | None:
        candidates = [m for m in self.models if m.is_hardened]
        if not candidates:
            return None
        return min(candidates, key=lambda m: _saved_at(m))

    def current_defender_model(self) -> ModelArtifact | None:
        """The most-evolved core defender available: Defender v3 if it has
        been trained, else Defender v2, else baseline v1."""
        by_role = {m.role: m for m in self.models}
        return by_role.get("defender_v3") or by_role.get("defender_v2") or by_role.get(
            "baseline_v1"
        )

    def model_by_version(self, model_version: str) -> ModelArtifact | None:
        for m in self.models:
            if m.model_version == model_version:
                return m
        return None

    def earliest_confrontation_for_model(
        self, model_version: str, *, adaptive: bool = False
    ) -> ConfrontationArtifact | None:
        candidates = [
            c
            for c in self.confrontations
            if c.model_version == model_version and c.is_adaptive == adaptive
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda c: c.report_id)

    def adaptive_round_by_parent(
        self, confrontation_report_id: str
    ) -> AdaptiveRoundArtifact | None:
        candidates = [
            a for a in self.adaptive_rounds if a.parent_confrontation_id == confrontation_report_id
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda a: a.report_id)

    def confrontation_by_id(self, report_id: str) -> ConfrontationArtifact | None:
        for c in self.confrontations:
            if c.report_id == report_id:
                return c
        return None

    def adaptive_round_by_id(self, report_id: str) -> AdaptiveRoundArtifact | None:
        for a in self.adaptive_rounds:
            if a.report_id == report_id:
                return a
        return None


def _saved_at(model: ModelArtifact) -> str:
    if model.metadata:
        return str(model.metadata.get("saved_at", model.model_version))
    return model.model_version


def _discover_models(root: Path) -> list[ModelArtifact]:
    out: list[ModelArtifact] = []
    for dir_path in safe_child_dirs(root, MODELS_DIR):
        if dir_path.name.startswith(LOAFO_FOLD_PREFIX):
            # Evaluation/generalization fold model, not core defender lineage.
            continue
        try:
            metadata = read_json(resolve_within(root, MODELS_DIR, dir_path.name, "metadata.json"))
            if not isinstance(metadata, dict):
                # A model directory without a valid metadata.json object is not usable.
                continue
            model_version = str(metadata.get("model_version", dir_path.name))
            out.append(
                ModelArtifact(
                    model_version=model_version,
                    dir_path=dir_path,
                    metadata=metadata,
                    evaluation_test=_read_optional(
                        root, MODELS_DIR, dir_path.name, "evaluation_test.json"
                    ),
                    evaluation_validation=_read_optional(
                        root, MODELS_DIR, dir_path.name, "evaluation_validation.json"
                    ),
                    regression_vs_baseline=_read_optional(
                        root, MODELS_DIR, dir_path.name, "regression_vs_baseline.json"
                    ),
                    generation2_handoff=_read_optional(
                        root, MODELS_DIR, dir_path.name, "generation2_handoff.json"
                    ),
                )
            )
        except Exception:
            continue
    return out


def _discover_confrontations(root: Path) -> list[ConfrontationArtifact]:
    out: list[ConfrontationArtifact] = []
    for dir_path in safe_child_dirs(root, CONFRONTATIONS_DIR):
        try:
            report = read_json(
                resolve_within(root, CONFRONTATIONS_DIR, dir_path.name, "confrontation.json")
            )
            if not isinstance(report, dict):
                continue
            hardest = _read_optional(
                root, CONFRONTATIONS_DIR, dir_path.name, "hardest_evasions.json"
            )
            out.append(
                ConfrontationArtifact(
                    report_id=str(report.get("report_id", dir_path.name)),
                    dir_path=dir_path,
                    report=report,
                    blueprint=_read_optional(
                        root, CONFRONTATIONS_DIR, dir_path.name, "blueprint.json"
                    ),
                    hardest_evasions=hardest if isinstance(hardest, list) else [],
                    transaction_count=count_jsonl_rows(
                        resolve_within(
                            root, CONFRONTATIONS_DIR, dir_path.name, "transactions.jsonl"
                        )
                    ),
                    evasion_count=count_jsonl_rows(
                        resolve_within(root, CONFRONTATIONS_DIR, dir_path.name, "evasions.jsonl")
                    ),
                    detector_output_count=count_jsonl_rows(
                        resolve_within(
                            root, CONFRONTATIONS_DIR, dir_path.name, "detector_outputs.jsonl"
                        )
                    ),
                )
            )
        except Exception:
            continue
    return out


def _discover_adaptive_round_candidates(
    root: Path, round_dir_name: str
) -> list[AdaptiveRoundCandidate]:
    out: list[AdaptiveRoundCandidate] = []
    candidates_relative = f"{ADAPTIVE_ROUNDS_DIR}/{round_dir_name}/candidates"
    for dir_path in safe_child_dirs(root, candidates_relative):
        try:
            out.append(
                AdaptiveRoundCandidate(
                    candidate_id=dir_path.name,
                    dir_path=dir_path,
                    blueprint=_read_optional(
                        root,
                        ADAPTIVE_ROUNDS_DIR,
                        round_dir_name,
                        "candidates",
                        dir_path.name,
                        "blueprint.json",
                    ),
                    confrontation=_read_optional(
                        root,
                        ADAPTIVE_ROUNDS_DIR,
                        round_dir_name,
                        "candidates",
                        dir_path.name,
                        "confrontation.json",
                    ),
                )
            )
        except Exception:
            continue
    return out


def _discover_adaptive_rounds(root: Path) -> list[AdaptiveRoundArtifact]:
    out: list[AdaptiveRoundArtifact] = []
    for dir_path in safe_child_dirs(root, ADAPTIVE_ROUNDS_DIR):
        try:
            report = read_json(
                resolve_within(root, ADAPTIVE_ROUNDS_DIR, dir_path.name, "adaptive_round.json")
            )
            if not isinstance(report, dict):
                continue
            out.append(
                AdaptiveRoundArtifact(
                    report_id=str(report.get("report_id", dir_path.name)),
                    dir_path=dir_path,
                    report=report,
                    candidates=_discover_adaptive_round_candidates(root, dir_path.name),
                )
            )
        except Exception:
            continue
    return out


def _discover_hardening(root: Path) -> list[HardeningArtifact]:
    out: list[HardeningArtifact] = []
    for dir_path in safe_child_dirs(root, HARDENING_DIR):
        try:
            provenance = _read_optional(root, HARDENING_DIR, dir_path.name, "provenance.json")
            out.append(
                HardeningArtifact(
                    run_id=dir_path.name,
                    dir_path=dir_path,
                    provenance=provenance,
                    hard_positive_count=count_jsonl_rows(
                        resolve_within(root, HARDENING_DIR, dir_path.name, "hard_positives.jsonl")
                    ),
                )
            )
        except Exception:
            continue
    return out


def _read_optional(root: Path, *parts: str) -> Any | None:
    return read_json(resolve_within(root, *parts))
