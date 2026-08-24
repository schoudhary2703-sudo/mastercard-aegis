"""Run the first non-adaptive Red-versus-Blue bust-out confrontation."""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from aegis.defend import XGBoostDetector
from aegis.evaluate import BustOutConfrontationReport, build_bustout_confrontation_report
from aegis.features import TemporalBaselineFeatureExtractor, load_transactions_jsonl
from aegis.generate import (
    GenerationConfig,
    PaySimReferenceProfile,
    SyntheticIdentityBustOutGenerator,
)
from aegis.identify import build_synthetic_identity_blueprint
from aegis.shared.contracts import AttackBlueprint, DetectorOutput, Transaction, TransactionBatch
from aegis.shared.enums import DataSplit, FraudLabel

# Direct ``python scripts/run_bustout_confrontation.py`` execution places
# scripts/, not the repository root, on sys.path. Importing by the appropriate
# runtime name keeps both that command and normal module imports working.
_training_module = importlib.import_module(
    "scripts.train_baseline_detector" if __package__ else "train_baseline_detector"
)
BaselinePipelineConfig = _training_module.BaselinePipelineConfig
run_baseline_pipeline = _training_module.run_baseline_pipeline


@dataclass(frozen=True)
class ConfrontationPipelineConfig:
    """Inputs needed to reproduce training and one fresh confrontation."""

    processed_dir: Path
    output_dir: Path = Path("data/synthetic/confrontations")
    model_output_dir: Path = Path("models/confrontations")
    seed: int = 20260101
    num_boost_round: int = 300
    latency_sample_size: int = 50
    reference_max_rows: int | None = None
    integration_only: bool = False
    data_basis: str = "processed_paysim"


@dataclass(frozen=True)
class ConfrontationPipelineResult:
    """In-memory result and paths written by one confrontation run."""

    report: BustOutConfrontationReport
    batch: TransactionBatch
    outputs: list[DetectorOutput]
    output_dir: Path
    model_dir: Path
    artifacts: dict[str, Path]


def run_bustout_confrontation(
    config: ConfrontationPipelineConfig,
) -> ConfrontationPipelineResult:
    """Train/tune the approved baseline, then score one unseen bust-out batch."""
    processed_dir = Path(config.processed_dir)
    train = _labelled_only(load_transactions_jsonl(processed_dir / "train.jsonl"))
    validation = _labelled_only(load_transactions_jsonl(processed_dir / "validation.jsonl"))
    test = _labelled_only(load_transactions_jsonl(processed_dir / "test.jsonl"))
    if not train or not validation or not test:
        raise ValueError("prepared train, validation, and test artifacts must all be non-empty")

    baseline = run_baseline_pipeline(
        BaselinePipelineConfig(
            processed_dir=processed_dir,
            output_dir=Path(config.model_output_dir),
            seed=config.seed,
            num_boost_round=config.num_boost_round,
            latency_sample_size=config.latency_sample_size,
        )
    )
    detector = XGBoostDetector.load(str(baseline.artifact_dir))

    # The extractor is fitted on train only. Its current vocabulary is fixed,
    # but following the interface keeps this safe if a later approved version
    # learns train-only encodings.
    extractor = TemporalBaselineFeatureExtractor().fit(train)
    reference = PaySimReferenceProfile.from_processed_paysim(
        processed_dir, max_rows=config.reference_max_rows
    )
    blueprint = build_synthetic_identity_blueprint(
        warmup_amount_mean=reference.amount_mean,
        warmup_amount_stddev=max(reference.amount_stddev, 1.0),
        currency=reference.currency,
        reference_basis=reference.basis,
    )
    start_time = max(txn.timestamp for txn in [*train, *validation, *test]) + timedelta(days=1)
    generation_config = GenerationConfig(
        seed=config.seed,
        n_scenarios=1,
        start_time=start_time,
        time_horizon=timedelta(days=120),
        split=DataSplit.TEST,
        generation=0,
        deterministic=True,
    )
    batch = SyntheticIdentityBustOutGenerator(reference).generate(blueprint, generation_config)
    X_synthetic = extractor.transform(batch.transactions)
    outputs = detector.predict(
        X_synthetic,
        [txn.transaction_id for txn in batch.transactions],
        explain=False,
    )
    report = build_bustout_confrontation_report(
        batch=batch,
        outputs=outputs,
        training_transactions=train,
        training_dataset_id=processed_dir.name,
        data_basis=config.data_basis,
        integration_only=config.integration_only,
    )
    output_dir = Path(config.output_dir) / report.report_id
    artifacts = write_confrontation_artifacts(output_dir, report, batch, outputs, blueprint)
    return ConfrontationPipelineResult(
        report=report,
        batch=batch,
        outputs=outputs,
        output_dir=output_dir,
        model_dir=baseline.artifact_dir,
        artifacts=artifacts,
    )


def write_confrontation_artifacts(
    output_dir: Path,
    report: BustOutConfrontationReport,
    batch: TransactionBatch,
    outputs: Sequence[DetectorOutput],
    blueprint: AttackBlueprint,
) -> dict[str, Path]:
    """Write canonical inputs, verdicts, report, and ranked evasions once."""
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite confrontation run: {destination}")
    destination.mkdir(parents=True)
    artifacts = {
        "transactions": destination / "transactions.jsonl",
        "detector_outputs": destination / "detector_outputs.jsonl",
        "report": destination / "confrontation.json",
        "evasions": destination / "evasions.jsonl",
        "hardest_evasions": destination / "hardest_evasions.json",
        "blueprint": destination / "blueprint.json",
    }
    _write_jsonl(artifacts["transactions"], batch.transactions)
    _write_jsonl(artifacts["detector_outputs"], outputs)
    _write_jsonl(artifacts["evasions"], report.successful_evasions)
    artifacts["report"].write_text(report.to_json(indent=2) + "\n", encoding="utf-8")
    artifacts["hardest_evasions"].write_text(
        json.dumps(
            [record.model_dump(mode="json") for record in report.hardest_evasions],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    artifacts["blueprint"].write_text(blueprint.to_json(indent=2) + "\n", encoding="utf-8")
    return artifacts


def _write_jsonl(path: Path, records: Sequence[object]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            if not hasattr(record, "to_json"):
                raise TypeError(f"record does not support canonical serialization: {type(record)}")
            handle.write(record.to_json())  # type: ignore[attr-defined]
            handle.write("\n")


def _labelled_only(transactions: Sequence[Transaction]) -> list[Transaction]:
    return [txn for txn in transactions if txn.label is not FraudLabel.UNKNOWN]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train/tune the approved PaySim baseline, generate one fresh synthetic-identity "
            "bust-out scenario, score it, and write a non-adaptive confrontation report."
        )
    )
    parser.add_argument(
        "processed_dir",
        type=Path,
        help="prepared PaySim run containing train/validation/test.jsonl",
    )
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--num-boost-round", type=int, default=300)
    parser.add_argument("--latency-sample-size", type=int, default=50)
    parser.add_argument("--reference-max-rows", type=int)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/synthetic/confrontations"),
    )
    parser.add_argument(
        "--model-output-dir",
        type=Path,
        default=Path("models/confrontations"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_bustout_confrontation(
        ConfrontationPipelineConfig(
            processed_dir=args.processed_dir,
            output_dir=args.output_dir,
            model_output_dir=args.model_output_dir,
            seed=args.seed,
            num_boost_round=args.num_boost_round,
            latency_sample_size=args.latency_sample_size,
            reference_max_rows=args.reference_max_rows,
        )
    )
    scenario = result.report.scenario_reports[0]
    print(f"Confrontation: {result.report.report_id}")
    print(f"  model={result.report.model_version} scenario={scenario.scenario_id}")
    print(
        f"  fraud={scenario.fraudulent_bustout_count} caught={scenario.caught_fraud_count} "
        f"evaded={scenario.evaded_fraud_count} recall={scenario.fraud_recall:.4f}"
    )
    print(f"  report: {result.artifacts['report']}")
    print(f"  hardest evasions: {result.artifacts['hardest_evasions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
