"""Persist the canonical 3-family GenAI coverage summary.

Reads only what is already on disk under ``data/genai/`` and writes one
artifact describing, per deeply simulated family, whether a live Attack
Analyst run, a live Blind-Spot run, and a scored guided generation exist --
with the reason for every gap.

Makes no provider call, generates nothing, scores nothing, and never writes a
GenAI run artifact. Re-running it after a live call refreshes the summary.

    python scripts/build_genai_family_summary.py
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from aegis.genai.coverage import build_family_coverage

DEFAULT_OUTPUT = Path("data/reports/genai_family_summary.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("."),
        help="root that contains data/genai (default: current directory)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--mirror",
        type=Path,
        default=None,
        help="optional second path to write the identical artifact to (e.g. a submission bundle)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_family_coverage(args.artifacts_root)

    payload = summary.to_json(indent=2) + "\n"
    for destination in (args.output, args.mirror):
        if destination is None:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")

    for family in summary.families:
        attack = "yes" if family.attack_analyst.available else "no"
        blind = "yes" if family.blind_spot_analyst.available else "no"
        guided = family.guided_generation
        line = (
            f"{family.label:20s} attack_analyst={attack:3s} blind_spot={blind:3s} "
            f"guided={'yes' if guided.available else 'no':3s}"
        )
        if guided.available:
            line += (
                f"  {guided.caught_count}/{guided.fraud_count} caught"
                f"  recall={guided.recall:.3f}"
                f"  fidelity={guided.fidelity_score:.3f}"
                if guided.recall is not None and guided.fidelity_score is not None
                else ""
            )
        else:
            line += f"  ({guided.reason})"
        print(line)

    print(
        f"\nlive families {summary.live_family_count}/3 · "
        f"guided {summary.guided_family_count}/3 · "
        f"fully covered {summary.fully_covered_family_count}/3"
    )
    print(f"artifact      {args.output}")
    if args.mirror is not None:
        print(f"mirror        {args.mirror}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
