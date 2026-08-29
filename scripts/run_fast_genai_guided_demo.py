"""Run the live-artifact -> bounded mutation -> scenario -> Defender v3 demo fast.

No provider call is made. The command reuses a persisted artifact whose
``live`` provenance remains intact, a hash-bound train-only reference snapshot,
and the frozen Defender v3 model. It never fits or retrains anything.
"""

from __future__ import annotations

import argparse
import importlib
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter

from aegis.generate import GenerationReferenceSnapshot

_guided = importlib.import_module(
    "scripts.run_genai_guided_generation" if __package__ else "run_genai_guided_generation"
)
DEFAULT_MODEL_DIR = _guided.DEFAULT_MODEL_DIR
GUIDED_ARTIFACT_DIR = _guided.GUIDED_ARTIFACT_DIR
GUIDED_EVIDENCE_DIR = _guided.GUIDED_EVIDENCE_DIR
GenAIGuidedConfig = _guided.GenAIGuidedConfig
GenAIGuidedGenerationError = _guided.GenAIGuidedGenerationError
run_genai_guided_generation = _guided.run_genai_guided_generation


DEFAULT_LIVE_ARTIFACT = Path(
    "data/genai/blind_spot_analyst/blind_spot_analyst-4a31d071288af1f5.json"
)
DEFAULT_CONFRONTATION = Path(
    "submission/artifacts/data/synthetic/confrontations/confrontation-416e606888de1ffa"
)
DEFAULT_SNAPSHOT = Path(
    "submission/artifacts/data/reports/generation_reference_snapshot.json"
)
DEFAULT_SEED = 20261011


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--genai-artifact", type=Path, default=DEFAULT_LIVE_ARTIFACT)
    parser.add_argument("--confrontation-dir", type=Path, default=DEFAULT_CONFRONTATION)
    parser.add_argument("--reference-snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--artifact-dir", type=Path, default=GUIDED_ARTIFACT_DIR)
    parser.add_argument("--evidence-dir", type=Path, default=GUIDED_EVIDENCE_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = GenerationReferenceSnapshot.model_validate_json(
        args.reference_snapshot.read_text(encoding="utf-8")
    )
    started = perf_counter()
    try:
        result = run_genai_guided_generation(
            GenAIGuidedConfig(
                genai_artifact=args.genai_artifact,
                confrontation_dir=args.confrontation_dir,
                processed_dir=Path(snapshot.dataset_id),
                model_dir=args.model_dir,
                artifact_dir=args.artifact_dir,
                evidence_dir=args.evidence_dir,
                seed=args.seed,
                reference_snapshot=args.reference_snapshot,
                reuse_identical=True,
                require_live=True,
            )
        )
    except (GenAIGuidedGenerationError, FileExistsError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    elapsed = perf_counter() - started
    record = result.record
    print(f"runtime_seconds  {elapsed:.3f}")
    print(
        f"live_artifact    {record.provenance.genai_run_id} "
        f"({record.provenance.provider}/{record.provenance.model}, "
        f"live={record.provenance.live})"
    )
    print(f"bounded_mutation {len(record.applied_mutations)} accepted, "
          f"{len(record.rejected_mutations)} rejected")
    print(f"scenario         {record.scenario_id} seed={record.provenance.seed}")
    print(f"defender         {record.provenance.detector_model_version}")
    print(f"fraud/caught     {record.fraud_count}/{record.caught_count}")
    print(f"fidelity         {record.fidelity_score}")
    print(f"artifact         {result.artifact_path}")
    print(f"evidence         {result.evidence_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
