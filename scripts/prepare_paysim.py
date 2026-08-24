"""Prepare a local PaySim CSV as canonical AEGIS transaction artifacts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from aegis.generate import PaySimPreparationConfig, prepare_paysim


def _parse_epoch(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("epoch must include a timezone offset")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and prepare a local PaySim CSV into canonical, leakage-conscious "
            "train/validation/test JSONL artifacts. This command never downloads data."
        )
    )
    parser.add_argument("csv_path", type=Path, help="path to the local PaySim CSV")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        help="data root containing interim/ and processed/ (default: data)",
    )
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument(
        "--split-mode",
        choices=("temporal", "entity_isolated"),
        default="temporal",
        help="split policy (default: temporal)",
    )
    parser.add_argument(
        "--currency",
        default=None,
        help="explicit ISO-4217 currency assumption (default: neutral XXX)",
    )
    parser.add_argument(
        "--epoch",
        type=_parse_epoch,
        default=_parse_epoch("2017-01-01T00:00:00+00:00"),
        help="timestamp represented by PaySim step 1 (ISO-8601, timezone required)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = prepare_paysim(
        args.csv_path,
        PaySimPreparationConfig(
            data_root=args.data_root,
            seed=args.seed,
            train_ratio=args.train_ratio,
            validation_ratio=args.validation_ratio,
            test_ratio=args.test_ratio,
            split_mode=args.split_mode,
            currency=args.currency,
            epoch=args.epoch,
        ),
    )
    print(f"Prepared PaySim artifacts: {result.output_dir}")
    print(json.dumps(result.summary["source_statistics"], indent=2, sort_keys=True))
    print(json.dumps(result.summary["splitting"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
