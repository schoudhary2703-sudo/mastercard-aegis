"""Benchmark deterministic generation scale for the three implemented families."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

from aegis.generate import (
    AdaptiveDetectorEvasionGenerator,
    GenerationBenchmarkCase,
    GenerationConfig,
    GenerationReferenceSnapshot,
    MuleNetworkStructuringGenerator,
    SyntheticIdentityBustOutGenerator,
    run_generation_scale_benchmark,
)
from aegis.identify import (
    build_adaptive_evasion_blueprint,
    build_mule_network_blueprint,
    build_synthetic_identity_blueprint,
)
from aegis.shared.enums import AttackFamily, DataSplit

DEFAULT_SNAPSHOT = Path(
    "submission/artifacts/data/reports/generation_reference_snapshot.json"
)
DEFAULT_OUTPUT = Path("submission/artifacts/data/reports/generation_scale_benchmark.json")


def _collect_scenario_ids(value: Any, output: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "scenario_id" and isinstance(child, str):
                output.add(child)
            elif key in {"scenario_ids", "additional_training_scenario_ids"} and isinstance(
                child, list
            ):
                output.update(item for item in child if isinstance(item, str))
            else:
                _collect_scenario_ids(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_scenario_ids(child, output)


def known_scenario_ids(roots: Sequence[Path], *, excluded: set[Path] | None = None) -> set[str]:
    known: set[str] = set()
    ignored = {path.resolve() for path in (excluded or set())}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.json"):
            if path.resolve() in ignored:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            _collect_scenario_ids(payload, known)
    return known


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--scenarios-per-family", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261001)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.scenarios_per_family < 1:
        raise ValueError("--scenarios-per-family must be positive")
    snapshot = GenerationReferenceSnapshot.model_validate_json(
        args.snapshot.read_text(encoding="utf-8")
    )
    start = snapshot.latest_train_timestamp + timedelta(days=1)
    horizon = timedelta(days=120)
    common = {
        "n_scenarios": args.scenarios_per_family,
        "start_time": start,
        "time_horizon": horizon,
        "split": DataSplit.TEST,
        "generation": 0,
        "deterministic": True,
    }
    cases = [
        GenerationBenchmarkCase(
            family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
            generator=SyntheticIdentityBustOutGenerator(snapshot.to_bustout_profile()),
            blueprint=build_synthetic_identity_blueprint(),
            config=GenerationConfig(seed=args.seed, **common),
        ),
        GenerationBenchmarkCase(
            family=AttackFamily.MULE_NETWORK_STRUCTURING,
            generator=MuleNetworkStructuringGenerator(snapshot.to_mule_profile()),
            blueprint=build_mule_network_blueprint(),
            config=GenerationConfig(seed=args.seed + 1, **common),
        ),
        GenerationBenchmarkCase(
            family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
            generator=AdaptiveDetectorEvasionGenerator(snapshot.to_adaptive_profile()),
            blueprint=build_adaptive_evasion_blueprint(),
            config=GenerationConfig(seed=args.seed + 2, **common),
        ),
    ]
    historical = known_scenario_ids(
        [Path("data"), Path("submission/artifacts/data")], excluded={args.output}
    )
    result = run_generation_scale_benchmark(cases, historical_scenario_ids=historical)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.to_json(indent=2) + "\n", encoding="utf-8")
    for family in result.families:
        print(
            f"{family.attack_family.value:31} tx={family.transactions_generated:6d} "
            f"fraud={family.fraud_transactions_generated:5d} "
            f"seconds={family.generation_seconds:.3f} "
            f"throughput={family.throughput_transactions_per_second:.1f}/s "
            f"valid={family.constraint_valid_percentage:.2f}% "
            f"fidelity(no constraints)={family.fidelity_excluding_constraints:.4f}"
        )
    print(f"artifact {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
