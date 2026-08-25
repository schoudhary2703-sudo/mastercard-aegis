"""Write the canonical final benchmark summary artifact.

Thin wrapper around `aegis.api.benchmark.build_final_benchmark_summary` -
all aggregation logic lives there (and is shared with `GET /api/benchmark`,
so the persisted file and the live API can never drift from each other).
This script only resolves paths, calls it once, and writes the result.

    python scripts/build_final_benchmark_summary.py

Writes `data/reports/final_benchmark_summary.json` (override with
`--output-path`). Read-only over every source artifact; never trains,
retrains, or modifies a model.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from aegis.api.benchmark import build_final_benchmark_summary

DEFAULT_OUTPUT_PATH = Path("data/reports/final_benchmark_summary.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate baseline v1, Defender v2, Defender v3, and the LOAFO benchmark's "
            "persisted artifacts into one canonical data/reports/final_benchmark_summary.json."
        )
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("."),
        help="repository root to read models/ and data/ under (default: current directory)",
    )
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_final_benchmark_summary(args.artifacts_root)

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {output_path}")
    print(f"  model_comparison: {'present' if summary['model_comparison'] else 'MISSING'}")
    print(f"  fresh_family_performance: {len(summary['fresh_family_performance'])} families")
    print(f"  loafo: {'present' if summary['loafo'] else 'MISSING'}")
    print(f"  hardest_surviving_attacks: {len(summary['hardest_surviving_attacks'])}")
    if summary["loafo"]:
        print(f"  loafo.overall_verdict: {summary['loafo']['overall_verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
