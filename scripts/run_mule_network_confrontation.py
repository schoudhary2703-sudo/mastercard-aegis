"""Generate and score one fresh mule-network scenario against a frozen detector."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from aegis.defend import XGBoostDetector
from aegis.evaluate import (
    MuleNetworkConfrontationReport,
    build_mule_network_confrontation_report,
    scan_training_overlap,
)
from aegis.features import TemporalBaselineFeatureExtractor
from aegis.generate import (
    GenerationConfig,
    MuleNetworkReferenceProfile,
    MuleNetworkStructuringGenerator,
)
from aegis.identify import build_mule_network_blueprint
from aegis.shared.base import AegisModel
from aegis.shared.contracts import AttackBlueprint, DetectorOutput, TransactionBatch
from aegis.shared.enums import DataSplit


@dataclass(frozen=True)
class MuleConfrontationConfig:
    """Inputs for one no-training, reproducible static confrontation."""

    processed_dir: Path
    model_dir: Path
    output_dir: Path = Path("data/synthetic/mule_confrontations")
    seed: int = 20260835


@dataclass(frozen=True)
class MuleConfrontationResult:
    """In-memory result plus canonical artifact locations."""

    report: MuleNetworkConfrontationReport
    batch: TransactionBatch
    outputs: list[DetectorOutput]
    output_dir: Path
    artifacts: dict[str, Path]


def run_mule_network_confrontation(
    config: MuleConfrontationConfig,
) -> MuleConfrontationResult:
    """Use TRAIN only for reference/freshness and never call detector fitting."""
    processed_dir = Path(config.processed_dir)
    train_path = processed_dir / "train.jsonl"
    if not train_path.is_file():
        raise ValueError(f"prepared PaySim TRAIN artifact not found: {train_path}")
    model_dir = Path(config.model_dir)
    model_path = model_dir / "model.json"
    metadata_path = model_dir / "metadata.json"
    if not model_path.is_file() or not metadata_path.is_file():
        raise ValueError(f"frozen XGBoost detector artifact not found: {model_dir}")
    model_hash_before = _sha256(model_path)
    metadata_hash_before = _sha256(metadata_path)

    profile = MuleNetworkReferenceProfile.from_processed_paysim(processed_dir)
    if profile.latest_timestamp is None:
        raise ValueError("PaySim TRAIN reference has no timestamp")
    blueprint = build_mule_network_blueprint(
        transfer_amount_mean=profile.transfer_amount_mean,
        transfer_amount_stddev=max(profile.transfer_amount_stddev, 5.0),
        context_amount_mean=profile.amount_mean,
        context_amount_stddev=max(profile.amount_stddev, 1.0),
        currency=profile.currency,
        reference_basis=profile.basis,
    )
    generation_config = GenerationConfig(
        seed=config.seed,
        n_scenarios=1,
        start_time=profile.latest_timestamp + timedelta(days=1),
        time_horizon=timedelta(days=60),
        split=DataSplit.TEST,
        generation=0,
        deterministic=True,
    )
    generator = MuleNetworkStructuringGenerator(profile)
    batch = generator.generate(blueprint, generation_config)
    detector = XGBoostDetector.load(str(model_dir))
    extractor = TemporalBaselineFeatureExtractor().fit([])
    outputs = detector.predict(
        extractor.transform(batch.transactions),
        [transaction.transaction_id for transaction in batch.transactions],
        explain=False,
    )
    training_scan = scan_training_overlap(train_path, batch.transactions)
    report = build_mule_network_confrontation_report(
        batch=batch,
        outputs=outputs,
        training_overlap_scan=training_scan,
        training_dataset_id=processed_dir.name,
        data_basis="processed_paysim_train",
        integration_only=False,
    )
    model_hash_after = _sha256(model_path)
    metadata_hash_after = _sha256(metadata_path)
    if model_hash_before != model_hash_after or metadata_hash_before != metadata_hash_after:
        raise RuntimeError("frozen detector artifact changed during mule confrontation")
    report = report.model_copy(
        update={
            "metadata": {
                **report.metadata,
                "model_sha256_before": model_hash_before,
                "model_sha256_after": model_hash_after,
                "metadata_sha256_before": metadata_hash_before,
                "metadata_sha256_after": metadata_hash_after,
                "detector_fit_called": False,
                "reference_splits_read": ["train"],
            }
        }
    )
    destination = Path(config.output_dir) / report.report_id
    artifacts = write_mule_confrontation_artifacts(
        destination, report, batch, outputs, blueprint
    )
    return MuleConfrontationResult(
        report=report,
        batch=batch,
        outputs=list(outputs),
        output_dir=destination,
        artifacts=artifacts,
    )


def write_mule_confrontation_artifacts(
    output_dir: Path,
    report: MuleNetworkConfrontationReport,
    batch: TransactionBatch,
    outputs: Sequence[DetectorOutput],
    blueprint: AttackBlueprint,
) -> dict[str, Path]:
    """Write all evidence once and refuse replacement of an existing run."""
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite mule confrontation: {destination}")
    destination.mkdir(parents=True)
    artifacts = {
        "blueprint": destination / "blueprint.json",
        "transactions": destination / "transactions.jsonl",
        "detector_outputs": destination / "detector_outputs.jsonl",
        "report": destination / "confrontation.json",
        "evasions": destination / "evasions.jsonl",
        "hardest_evasions": destination / "hardest_evasions.json",
    }
    _write_model(artifacts["blueprint"], blueprint)
    _write_jsonl(artifacts["transactions"], batch.transactions)
    _write_jsonl(artifacts["detector_outputs"], outputs)
    _write_model(artifacts["report"], report)
    _write_jsonl(artifacts["evasions"], report.successful_evasions)
    artifacts["hardest_evasions"].write_text(
        json.dumps(
            [record.model_dump(mode="json") for record in report.hardest_evasions],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifacts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_model(path: Path, model: AegisModel) -> None:
    path.write_text(model.to_json(indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[AegisModel]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(record.to_json())
            handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate one fresh synthetic mule-network scenario and score it against an "
            "existing frozen detector. This command has no training path."
        )
    )
    parser.add_argument("processed_dir", type=Path)
    parser.add_argument(
        "model_dir",
        type=Path,
        nargs="?",
        default=Path("models/xgboost-hardened-r1-20260201"),
    )
    parser.add_argument("--seed", type=int, default=20260835)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/synthetic/mule_confrontations"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_mule_network_confrontation(
        MuleConfrontationConfig(
            processed_dir=args.processed_dir,
            model_dir=args.model_dir,
            output_dir=args.output_dir,
            seed=args.seed,
        )
    )
    scenario = result.report.scenario_reports[0]
    print(f"Mule confrontation: {result.report.report_id}")
    print(f"  scenario={scenario.scenario_id} seed={scenario.seed}")
    print(f"  model={scenario.model_version}")
    print(
        f"  total={scenario.total_transactions} "
        f"context={scenario.legitimate_context_transaction_count} "
        f"fraud={scenario.fraudulent_structuring_count}"
    )
    print(
        f"  caught={scenario.caught_fraud_count} evaded={scenario.evaded_fraud_count} "
        f"recall={scenario.fraud_recall:.4f}"
    )
    print(
        "  fidelity="
        f"{scenario.fidelity_summary.get('overall_fidelity_score', 0.0):.4f}"
    )
    print(f"  report: {result.artifacts['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
