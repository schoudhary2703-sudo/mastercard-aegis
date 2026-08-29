"""Run one GenAI reasoning stage and persist its artifact.

Two subcommands, matching the two places AEGIS uses a language model:

    # A. researched taxonomy scenario -> structured attack hypothesis
    python scripts/run_genai_analysis.py attack-analyst \
        --scenario synthetic-identity-bustout

    # B. one real persisted evasion -> bounded mutation proposals
    python scripts/run_genai_analysis.py blind-spot \
        --confrontation-dir submission/artifacts/data/synthetic/confrontations/<id>

Neither subcommand trains, retrains, or re-scores anything: A reads a static
taxonomy entry, B reads artifacts a previous pipeline run already wrote. Both
write to `data/genai/<stage>/<run_id>.json`.

Requires `ANTHROPIC_API_KEY` and the optional extra (`pip install -e
".[genai]"`). Without a key the command fails loudly; pass
`--provider recorded --recorded-artifact <path>` to explicitly replay a
previous run instead. There is no mode that invents reasoning.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from aegis.genai import (
    AttackAnalystRequest,
    BlindSpotAnalystRequest,
    GenAIError,
    build_provider,
    run_attack_analyst,
    run_blind_spot_analyst,
)
from aegis.genai.taxonomy import PAYMENT_CONTEXT, get_taxonomy_entry, taxonomy_keys
from aegis.shared.enums import AttackFamily


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one AEGIS GenAI reasoning stage and persist its artifact."
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("."),
        help="root the run artifact is written under (default: current directory)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="'anthropic' (default, live) or 'recorded' (explicit offline replay)",
    )
    parser.add_argument("--model", default=None, help="override the model id")
    parser.add_argument(
        "--recorded-artifact",
        type=Path,
        default=None,
        help="prior run artifact to replay; required when --provider recorded",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    attack = sub.add_parser(
        "attack-analyst", help="taxonomy scenario -> structured attack hypothesis"
    )
    attack.add_argument(
        "--scenario",
        required=True,
        choices=taxonomy_keys(),
        help="which researched taxonomy entry to analyze",
    )

    blind = sub.add_parser(
        "blind-spot", help="persisted confrontation evasions -> bounded mutation proposals"
    )
    blind.add_argument(
        "--confrontation-dir",
        type=Path,
        required=True,
        help="any family confrontation directory containing confrontation/blueprint artifacts",
    )
    blind.add_argument(
        "--request-only",
        action="store_true",
        help=(
            "validate and print the Blind-Spot request without building a provider or using credits"
        ),
    )

    return parser


def _build_attack_request(scenario_key: str) -> AttackAnalystRequest:
    entry = get_taxonomy_entry(scenario_key)
    return AttackAnalystRequest(
        scenario_name=entry.scenario_name,
        research_summary=entry.research_summary,
        payment_context=PAYMENT_CONTEXT,
        known_constraints=list(entry.known_constraints),
        candidate_families=list(AttackFamily),
        available_simulator_parameters=list(entry.simulator_parameters),
    )


def _build_blind_spot_request(
    confrontation_dir: Path,
) -> tuple[BlindSpotAnalystRequest, list[str]]:
    """Assemble the request purely from what a prior run already persisted."""
    report = _read_json(confrontation_dir / "confrontation.json")
    blueprint = _read_json(confrontation_dir / "blueprint.json")

    hardest_path = confrontation_dir / "hardest_evasions.json"
    hardest = _read_json(hardest_path) if hardest_path.is_file() else []
    if not isinstance(hardest, list):
        hardest = []

    scenario_reports = [s for s in (report.get("scenario_reports") or []) if isinstance(s, dict)]
    missed = sum(int(s.get("evaded_fraud_count", 0)) for s in scenario_reports)
    caught = sum(int(s.get("caught_fraud_count", 0)) for s in scenario_reports)

    fidelity: float | None = None
    for row in hardest:
        if isinstance(row, dict) and isinstance(row.get("fidelity_score"), (int, float)):
            fidelity = float(row["fidelity_score"])
            break

    mutable = [
        name
        for name, spec in (blueprint.get("parameters") or {}).items()
        if isinstance(spec, dict) and spec.get("mutable")
    ]

    request = BlindSpotAnalystRequest(
        blueprint_id=str(blueprint.get("attack_id", "")),
        attack_family=AttackFamily(blueprint["attack_family"]),
        detector_model_version=str(report.get("model_version", "")),
        missed_transaction_count=missed,
        caught_transaction_count=caught,
        observed_risk_scores=[
            float(r["detector_risk_score"])
            for r in hardest
            if isinstance(r, dict) and isinstance(r.get("detector_risk_score"), (int, float))
        ],
        important_signals=[str(f) for f in (blueprint.get("target_features") or [])],
        fidelity_score=fidelity,
        mutable_parameters=sorted(mutable),
        detector_context=(
            "XGBoost gradient-boosted detector over decision-time-safe temporal "
            "features, trained on PaySim plus promoted hard positives. It never "
            "observes blueprint parameters or attack labels."
        ),
    )
    sources = [
        str(confrontation_dir / "confrontation.json"),
        str(confrontation_dir / "blueprint.json"),
    ]
    return request, sources


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "blind-spot" and args.request_only:
        blind_request, _ = _build_blind_spot_request(args.confrontation_dir)
        print(blind_request.to_json(indent=2))
        return 0

    try:
        provider = build_provider(
            args.provider, model=args.model, recorded_artifact=args.recorded_artifact
        )
    except GenAIError as exc:
        print(f"ERROR: {exc}")
        return 2

    try:
        if args.command == "attack-analyst":
            request = _build_attack_request(args.scenario)
            outcome = run_attack_analyst(
                request,
                provider,
                root=args.artifacts_root,
                source_artifacts=[f"taxonomy:{args.scenario}"],
            )
        else:
            blind_request, sources = _build_blind_spot_request(args.confrontation_dir)
            outcome = run_blind_spot_analyst(
                blind_request, provider, root=args.artifacts_root, source_artifacts=sources
            )
    except GenAIError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        print("A failure artifact was written if the provider was reached.")
        return 1

    prov = outcome.artifact.provenance
    print(f"Wrote {outcome.artifact_path}")
    print(f"  stage:          {outcome.artifact.stage}")
    print(f"  provider/model: {prov.provider} / {prov.model}")
    print(f"  live GenAI:     {prov.live}")
    print(f"  prompt version: {prov.prompt_version}")
    print(f"  schema valid:   {outcome.artifact.schema_valid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
