"""Export the evidence-backed broad fraud taxonomy as deterministic JSON."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from aegis.identify import build_fraud_taxonomy

DEFAULT_OUTPUT = Path("submission/artifacts/data/reports/attack_taxonomy.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    taxonomy = build_fraud_taxonomy()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(taxonomy.to_json(indent=2) + "\n", encoding="utf-8")
    summary = taxonomy.summary
    print(f"identified       {summary.total_attacks_identified}")
    print(f"deeply simulated {summary.deeply_simulated}")
    print(f"categories       {', '.join(summary.categories_represented)}")
    print(f"channels         {', '.join(summary.channels_represented)}")
    print(f"artifact         {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
