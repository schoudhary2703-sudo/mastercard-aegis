"""Generate one deterministic synthetic-identity bust-out scenario."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aegis.generate import (
    GenerationConfig,
    PaySimReferenceProfile,
    SyntheticIdentityBustOutGenerator,
    write_synthetic_identity_artifacts,
)
from aegis.identify import build_synthetic_identity_blueprint
from aegis.shared.contracts import AttackBlueprint
from aegis.shared.enums import ParameterType


def _parse_start_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("start time must include a timezone")
    return parsed.astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate one canonical synthetic-identity warm-up and bust-out scenario. "
            "No detector, adaptive loop, or live LLM is used."
        )
    )
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--round-index", type=int, default=0)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--reference-dir",
        type=Path,
        help="optional prepared PaySim run directory; only train.jsonl is read",
    )
    parser.add_argument(
        "--reference-max-rows",
        type=int,
        help="optional cap on legitimate train rows used to derive reference moments",
    )
    parser.add_argument(
        "--currency",
        help="explicit three-letter currency override; otherwise use reference/neutral XXX",
    )
    parser.add_argument(
        "--start-time",
        type=_parse_start_time,
        default=_parse_start_time("2026-01-01T00:00:00+00:00"),
    )
    parser.add_argument(
        "--time-horizon-days",
        type=float,
        default=120.0,
        help="available simulation clock horizon (default: 120 days)",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="override a declared blueprint parameter; may be repeated",
    )
    return parser


def _parse_overrides(entries: Sequence[str], blueprint: AttackBlueprint) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"parameter override must be NAME=VALUE, got {entry!r}")
        name, raw_value = entry.split("=", 1)
        spec = blueprint.parameters.get(name)
        if spec is None:
            raise ValueError(f"unknown blueprint parameter: {name}")
        if spec.param_type is ParameterType.INT:
            value: Any = int(raw_value)
        elif spec.param_type is ParameterType.FLOAT:
            value = float(raw_value)
        else:
            value = raw_value
        overrides[name] = value
    return overrides


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.round_index < 0:
        raise ValueError("round-index must be non-negative")
    if args.time_horizon_days <= 0:
        raise ValueError("time-horizon-days must be positive")
    profile = (
        PaySimReferenceProfile.from_processed_paysim(
            args.reference_dir, max_rows=args.reference_max_rows
        )
        if args.reference_dir is not None
        else PaySimReferenceProfile.bounded_fallback()
    )
    currency = args.currency.upper() if args.currency else profile.currency
    blueprint = build_synthetic_identity_blueprint(
        warmup_amount_mean=profile.amount_mean,
        warmup_amount_stddev=max(profile.amount_stddev, 1.0),
        currency=currency,
        reference_basis=profile.basis,
    )
    overrides = _parse_overrides(args.set, blueprint)
    config = GenerationConfig(
        seed=args.seed,
        n_scenarios=1,
        start_time=args.start_time,
        time_horizon=timedelta(days=args.time_horizon_days),
        parameter_overrides=overrides,
        generation=args.round_index,
    )
    batch = SyntheticIdentityBustOutGenerator(profile).generate(blueprint, config)
    output_dir = (
        args.data_root
        / "synthetic"
        / f"round_{args.round_index}"
        / f"synthetic-identity-bustout-seed-{args.seed}-{batch.batch_id.removeprefix('bustout-')}"
    )
    artifacts = write_synthetic_identity_artifacts(output_dir, batch, blueprint)
    print(f"Generated scenario: {batch.scenario_ids[0]}")
    print(f"Transactions: {artifacts['transactions']}")
    print(f"Scenario report: {artifacts['scenario']}")
    print(json.dumps(batch.metadata["fidelity"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
