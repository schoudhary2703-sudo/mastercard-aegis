"""Build the frozen train-only reference snapshot used by fast demo/benchmarks."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from aegis.generate import build_reference_snapshot

DEFAULT_OUTPUT = Path("submission/artifacts/data/reports/generation_reference_snapshot.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--feature-dir",
        type=Path,
        default=Path("models/xgboost-baseline-20260101/features/train"),
    )
    parser.add_argument(
        "--processed-summary",
        type=Path,
        default=Path(
            "data/processed/paysim/paysim-16910f90577b-086de09508a4/summary.json"
        ),
    )
    parser.add_argument(
        "--hardening-dir",
        type=Path,
        default=Path("data/hardening/hard-positives-crossfamily-20260301"),
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("models/xgboost-hardened-crossfamily-20260301"),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = build_reference_snapshot(
        feature_dir=args.feature_dir,
        processed_summary_path=args.processed_summary,
        hardening_dir=args.hardening_dir,
        defender_model_dir=args.model_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(snapshot.to_json(indent=2) + "\n", encoding="utf-8")
    print(f"dataset          {snapshot.dataset_id}")
    print(f"reference rows   {snapshot.legitimate_reference_count}")
    print(f"training rows    {snapshot.total_training_transaction_count}")
    print(f"model            {snapshot.defender_model_version}")
    print(f"artifact         {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
