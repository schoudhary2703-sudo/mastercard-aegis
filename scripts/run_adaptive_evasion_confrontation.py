"""Run one bounded feedback step and one fresh STATIC_HOLDOUT confrontation."""

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
    AdaptiveEvasionConfrontationReport,
    build_adaptive_evasion_confrontation_report,
    scan_training_overlap,
)
from aegis.features import TemporalBaselineFeatureExtractor
from aegis.generate import (
    AdaptiveDetectorEvasionGenerator,
    AdaptiveEvasionReferenceProfile,
    GenerationConfig,
)
from aegis.identify import build_adaptive_evasion_blueprint
from aegis.loop import (
    GuidedAdaptation,
    adapt_blueprint_from_evasions,
    build_adaptive_evasion_feedback,
)
from aegis.shared.base import AegisModel
from aegis.shared.contracts import (
    AttackBlueprint,
    DetectorOutput,
    EvasionFeedback,
    TransactionBatch,
)
from aegis.shared.enums import DataSplit


@dataclass(frozen=True)
class AdaptiveEvasionConfrontationConfig:
    """Inputs for a fixed one-probe, one-child benchmark run."""

    processed_dir: Path
    model_dir: Path
    output_dir: Path = Path("data/synthetic/adaptive_evasion_confrontations")
    seed: int = 20260836


@dataclass(frozen=True)
class AdaptiveEvasionConfrontationResult:
    """Final evaluation plus probe/adaptation evidence."""

    report: AdaptiveEvasionConfrontationReport
    probe_batch: TransactionBatch
    final_batch: TransactionBatch
    feedback: list[EvasionFeedback]
    adaptation: GuidedAdaptation
    output_dir: Path
    artifacts: dict[str, Path]


def run_adaptive_evasion_confrontation(
    config: AdaptiveEvasionConfrontationConfig,
) -> AdaptiveEvasionConfrontationResult:
    """Adapt once from a probe evasion and report only a fresh child sample."""
    processed_dir = Path(config.processed_dir)
    train_path = processed_dir / "train.jsonl"
    if not train_path.is_file():
        raise ValueError(f"prepared PaySim TRAIN artifact not found: {train_path}")
    model_dir = Path(config.model_dir)
    model_path = model_dir / "model.json"
    metadata_path = model_dir / "metadata.json"
    if not model_path.is_file() or not metadata_path.is_file():
        raise ValueError(f"frozen detector artifact not found: {model_dir}")
    model_hash_before = _sha256(model_path)
    metadata_hash_before = _sha256(metadata_path)

    profile = AdaptiveEvasionReferenceProfile.from_processed_paysim(processed_dir)
    if profile.latest_timestamp is None:
        raise ValueError("PaySim TRAIN reference has no timestamp")
    parent = build_adaptive_evasion_blueprint(
        context_amount_mean=profile.amount_mean,
        context_amount_stddev=max(profile.amount_stddev, 1.0),
        fraud_amount_mean=profile.transfer_amount_mean,
        fraud_amount_stddev=max(profile.transfer_amount_stddev, 20.0),
        currency=profile.currency,
        reference_basis=profile.basis,
    )
    generator = AdaptiveDetectorEvasionGenerator(profile)
    detector = XGBoostDetector.load(str(model_dir))
    extractor = TemporalBaselineFeatureExtractor().fit([])

    probe_config = GenerationConfig(
        seed=config.seed,
        n_scenarios=1,
        start_time=profile.latest_timestamp + timedelta(days=1),
        time_horizon=timedelta(days=90),
        split=DataSplit.TEST,
        generation=parent.generation,
        deterministic=True,
    )
    probe_batch = generator.generate(parent, probe_config)
    probe_outputs = detector.predict(
        extractor.transform(probe_batch.transactions),
        [transaction.transaction_id for transaction in probe_batch.transactions],
        explain=True,
    )
    feedback = build_adaptive_evasion_feedback(
        batch=probe_batch,
        blueprint=parent,
        outputs=probe_outputs,
    )
    adaptation = adapt_blueprint_from_evasions(
        parent,
        feedback,
        seed=config.seed + 1,
    )
    child = adaptation.child_blueprint
    final_config = GenerationConfig(
        seed=config.seed + 2,
        n_scenarios=1,
        start_time=max(transaction.timestamp for transaction in probe_batch.transactions)
        + timedelta(days=1),
        time_horizon=timedelta(days=90),
        split=DataSplit.TEST,
        generation=child.generation,
        deterministic=True,
    )
    final_batch = generator.generate(child, final_config)
    final_outputs = detector.predict(
        extractor.transform(final_batch.transactions),
        [transaction.transaction_id for transaction in final_batch.transactions],
        explain=True,
    )
    combined_scan = scan_training_overlap(
        train_path, [*probe_batch.transactions, *final_batch.transactions]
    )
    if not combined_scan.is_fresh:
        raise ValueError("probe or final adaptive scenario overlaps detector TRAIN")
    final_scan = combined_scan.model_copy(
        update={"generated_transaction_count": len(final_batch.transactions)}
    )
    report = build_adaptive_evasion_confrontation_report(
        batch=final_batch,
        blueprint_parent_id=child.parent_blueprint_id,
        outputs=final_outputs,
        training_overlap_scan=final_scan,
        training_dataset_id=processed_dir.name,
        data_basis="processed_paysim_train",
        integration_only=False,
    )
    model_hash_after = _sha256(model_path)
    metadata_hash_after = _sha256(metadata_path)
    if model_hash_before != model_hash_after or metadata_hash_before != metadata_hash_after:
        raise RuntimeError("frozen detector changed during adaptive-evasion confrontation")
    report = report.model_copy(
        update={
            "metadata": {
                **report.metadata,
                "probe_batch_id": probe_batch.batch_id,
                "probe_seed": probe_batch.seed,
                "adaptation_id": adaptation.adaptation_id,
                "adaptation_seed": adaptation.seed,
                "final_seed": final_batch.seed,
                "feedback_count": len(feedback),
                "credible_feedback_count": sum(
                    item.is_credible_evasion for item in feedback
                ),
                "model_sha256_before": model_hash_before,
                "model_sha256_after": model_hash_after,
                "metadata_sha256_before": metadata_hash_before,
                "metadata_sha256_after": metadata_hash_after,
                "detector_fit_called": False,
                "reference_splits_read": ["train"],
                "bounded_candidate_count": 1,
            }
        }
    )
    destination = Path(config.output_dir) / report.report_id
    artifacts = write_adaptive_evasion_artifacts(
        destination=destination,
        report=report,
        parent=parent,
        adaptation=adaptation,
        feedback=feedback,
        probe_batch=probe_batch,
        probe_outputs=probe_outputs,
        final_batch=final_batch,
        final_outputs=final_outputs,
        combined_scan=combined_scan,
    )
    return AdaptiveEvasionConfrontationResult(
        report=report,
        probe_batch=probe_batch,
        final_batch=final_batch,
        feedback=feedback,
        adaptation=adaptation,
        output_dir=destination,
        artifacts=artifacts,
    )


def write_adaptive_evasion_artifacts(
    *,
    destination: Path,
    report: AdaptiveEvasionConfrontationReport,
    parent: AttackBlueprint,
    adaptation: GuidedAdaptation,
    feedback: Sequence[EvasionFeedback],
    probe_batch: TransactionBatch,
    probe_outputs: Sequence[DetectorOutput],
    final_batch: TransactionBatch,
    final_outputs: Sequence[DetectorOutput],
    combined_scan: AegisModel,
) -> dict[str, Path]:
    """Write probe evidence and final evaluation without overwriting another run."""
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite adaptive confrontation: {destination}")
    destination.mkdir(parents=True)
    artifacts = {
        "parent_blueprint": destination / "parent_blueprint.json",
        "adapted_blueprint": destination / "adapted_blueprint.json",
        "adaptation": destination / "guided_adaptation.json",
        "feedback": destination / "evasion_feedback.jsonl",
        "probe_transactions": destination / "probe_transactions.jsonl",
        "probe_outputs": destination / "probe_detector_outputs.jsonl",
        "transactions": destination / "transactions.jsonl",
        "detector_outputs": destination / "detector_outputs.jsonl",
        "report": destination / "confrontation.json",
        "evasions": destination / "evasions.jsonl",
        "hardest_evasions": destination / "hardest_evasions.json",
        "manifest": destination / "adaptation_manifest.json",
    }
    _write_model(artifacts["parent_blueprint"], parent)
    _write_model(artifacts["adapted_blueprint"], adaptation.child_blueprint)
    _write_model(artifacts["adaptation"], adaptation)
    _write_jsonl(artifacts["feedback"], feedback)
    _write_jsonl(artifacts["probe_transactions"], probe_batch.transactions)
    _write_jsonl(artifacts["probe_outputs"], probe_outputs)
    _write_jsonl(artifacts["transactions"], final_batch.transactions)
    _write_jsonl(artifacts["detector_outputs"], final_outputs)
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
    artifacts["manifest"].write_text(
        json.dumps(
            {
                "probe_batch_id": probe_batch.batch_id,
                "probe_seed": probe_batch.seed,
                "adaptation_id": adaptation.adaptation_id,
                "adaptation_seed": adaptation.seed,
                "final_batch_id": final_batch.batch_id,
                "final_seed": final_batch.seed,
                "feedback_ids": [item.feedback_id for item in feedback],
                "combined_training_overlap_scan": combined_scan.model_dump(mode="json"),
                "reported_sample_is_fresh_child": True,
                "detector_retrained": False,
            },
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
            "Score one synthetic probe, apply one bounded EvasionFeedback mutation, and "
            "evaluate one fresh child against the same frozen detector."
        )
    )
    parser.add_argument("processed_dir", type=Path)
    parser.add_argument(
        "model_dir",
        type=Path,
        nargs="?",
        default=Path("models/xgboost-hardened-r1-20260201"),
    )
    parser.add_argument("--seed", type=int, default=20260836)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/synthetic/adaptive_evasion_confrontations"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_adaptive_evasion_confrontation(
        AdaptiveEvasionConfrontationConfig(
            processed_dir=args.processed_dir,
            model_dir=args.model_dir,
            output_dir=args.output_dir,
            seed=args.seed,
        )
    )
    scenario = result.report.scenario_reports[0]
    print(f"Adaptive evasion confrontation: {result.report.report_id}")
    print(
        f"  probe_seed={result.probe_batch.seed} adaptation_seed={result.adaptation.seed} "
        f"final_seed={result.final_batch.seed}"
    )
    print(f"  model={scenario.model_version} scenario={scenario.scenario_id}")
    print(
        f"  fraud={scenario.fraudulent_perturbation_count} "
        f"caught={scenario.caught_fraud_count} evaded={scenario.evaded_fraud_count} "
        f"recall={scenario.fraud_recall:.4f}"
    )
    print(
        f"  risk={scenario.average_fraud_risk_score:.4f} "
        f"fidelity={scenario.fidelity_score:.4f} fitness={scenario.fitness:.4f}"
    )
    print(f"  report: {result.artifacts['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
