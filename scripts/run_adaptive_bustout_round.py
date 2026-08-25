"""Evolve Round 0 bust-out evasions against one frozen Blue model."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from aegis.defend import XGBoostDetector
from aegis.evaluate import BustOutConfrontationReport
from aegis.features import TemporalBaselineFeatureExtractor, load_transactions_jsonl
from aegis.generate import PaySimReferenceProfile, SyntheticIdentityBustOutGenerator
from aegis.loop import AdaptiveRoundExecution, evolve_bustout_round
from aegis.shared.base import AegisModel
from aegis.shared.contracts import AttackBlueprint, DetectorOutput
from aegis.shared.enums import FraudLabel


@dataclass(frozen=True)
class AdaptiveBustOutConfig:
    """Inputs for one reproducible attacker-only evolution round."""

    processed_dir: Path
    confrontation_dir: Path
    model_dir: Path
    output_dir: Path = Path("data/synthetic/adaptive_rounds")
    seed: int = 20260102
    candidate_count: int = 4
    reference_max_rows: int | None = None


@dataclass(frozen=True)
class AdaptiveBustOutResult:
    """Round report and its written artifact locations."""

    execution: AdaptiveRoundExecution
    output_dir: Path
    artifacts: dict[str, Path]


def run_adaptive_bustout_round(config: AdaptiveBustOutConfig) -> AdaptiveBustOutResult:
    """Load Round 0 evidence, evolve attacks, and score without fitting Blue."""
    processed_dir = Path(config.processed_dir)
    confrontation_dir = Path(config.confrontation_dir)
    train = [
        txn
        for txn in load_transactions_jsonl(processed_dir / "train.jsonl")
        if txn.label is not FraudLabel.UNKNOWN
    ]
    if not train:
        raise ValueError("prepared PaySim train artifact has no labelled transactions")

    parent_report = BustOutConfrontationReport.model_validate_json(
        (confrontation_dir / "confrontation.json").read_text(encoding="utf-8")
    )
    parent_blueprint = AttackBlueprint.model_validate_json(
        (confrontation_dir / "blueprint.json").read_text(encoding="utf-8")
    )
    round0_transactions = load_transactions_jsonl(confrontation_dir / "transactions.jsonl")
    round0_outputs = _load_detector_outputs(confrontation_dir / "detector_outputs.jsonl")

    detector = XGBoostDetector.load(str(config.model_dir))
    if detector.model_version != parent_report.model_version:
        raise ValueError("model artifact does not match the Round 0 confrontation")
    extractor = TemporalBaselineFeatureExtractor().fit(train)
    explained_round0 = detector.predict(
        extractor.transform(round0_transactions),
        [txn.transaction_id for txn in round0_transactions],
        explain=True,
    )
    _validate_rescore(round0_outputs, explained_round0)

    reference = PaySimReferenceProfile.from_processed_paysim(
        processed_dir, max_rows=config.reference_max_rows
    )
    generator = SyntheticIdentityBustOutGenerator(reference)
    execution = evolve_bustout_round(
        parent_confrontation=parent_report,
        parent_blueprint=parent_blueprint,
        round0_outputs=explained_round0,
        generator=generator,
        extractor=extractor,
        detector=detector,
        training_transactions=train,
        seed=config.seed,
        start_time=max(txn.timestamp for txn in round0_transactions) + timedelta(days=1),
        candidate_count=config.candidate_count,
    )
    output_dir = Path(config.output_dir) / execution.report.report_id
    artifacts = write_adaptive_round_artifacts(output_dir, execution)
    return AdaptiveBustOutResult(
        execution=execution,
        output_dir=output_dir,
        artifacts=artifacts,
    )


def write_adaptive_round_artifacts(
    output_dir: Path, execution: AdaptiveRoundExecution
) -> dict[str, Path]:
    """Write Round 1 evidence and every candidate without overwriting a prior run."""
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite adaptive round: {destination}")
    destination.mkdir(parents=True)
    artifacts = {
        "report": destination / "adaptive_round.json",
        "blind_spot_analysis": destination / "blind_spot_analysis.json",
        "comparison": destination / "round_comparison.json",
        "parent_blueprint": destination / "parent_blueprint.json",
        "selected_blueprint": destination / "selected_blueprint.json",
        "hardest_evasions": destination / "hardest_surviving_evasions.json",
    }
    report = execution.report
    _write_model(artifacts["report"], report)
    _write_model(artifacts["blind_spot_analysis"], report.blind_spot_analysis)
    _write_model(artifacts["comparison"], report.comparison)
    _write_model(artifacts["parent_blueprint"], report.parent_blueprint)
    _write_model(artifacts["selected_blueprint"], report.selected_blueprint)
    artifacts["hardest_evasions"].write_text(
        json.dumps(
            [record.model_dump(mode="json") for record in report.hardest_surviving_evasions],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    candidates_dir = destination / "candidates"
    for result in report.candidate_results:
        candidate_id = result.candidate.candidate_id
        candidate_dir = candidates_dir / candidate_id
        candidate_dir.mkdir(parents=True)
        _write_model(candidate_dir / "blueprint.json", result.candidate.blueprint)
        _write_model(candidate_dir / "confrontation.json", result.confrontation)
        _write_jsonl(
            candidate_dir / "transactions.jsonl",
            execution.batches[candidate_id].transactions,
        )
        _write_jsonl(
            candidate_dir / "detector_outputs.jsonl",
            execution.outputs[candidate_id],
        )
    return artifacts


def _load_detector_outputs(path: Path) -> list[DetectorOutput]:
    outputs: list[DetectorOutput] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                outputs.append(DetectorOutput.model_validate_json(line))
    return outputs


def _validate_rescore(
    original: Sequence[DetectorOutput], explained: Sequence[DetectorOutput]
) -> None:
    original_by_id = {output.transaction_id: output for output in original}
    explained_by_id = {output.transaction_id: output for output in explained}
    if original_by_id.keys() != explained_by_id.keys():
        raise ValueError("Round 0 rescore transaction IDs differ from the confrontation")
    for transaction_id, prior in original_by_id.items():
        enriched = explained_by_id[transaction_id]
        if abs(prior.risk_score - enriched.risk_score) > 1e-12:
            raise ValueError("frozen model did not reproduce the Round 0 risk score")
        if prior.predicted_label is not enriched.predicted_label:
            raise ValueError("frozen model changed a Round 0 predicted label")
        if prior.recommended_action is not enriched.recommended_action:
            raise ValueError("frozen policy changed a Round 0 action")
        if prior.threshold != enriched.threshold:
            raise ValueError("frozen policy changed the Round 0 threshold")


def _write_model(path: Path, model: AegisModel) -> None:
    path.write_text(model.to_json(indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: Sequence[AegisModel]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.to_json())
            handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Use Round 0 bust-out evasions to generate and score bounded Round 1 variants "
            "against the same frozen detector. No defender retraining occurs."
        )
    )
    parser.add_argument("processed_dir", type=Path)
    parser.add_argument("confrontation_dir", type=Path)
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("--seed", type=int, default=20260102)
    parser.add_argument("--candidate-count", type=int, default=4)
    parser.add_argument("--reference-max-rows", type=int)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/synthetic/adaptive_rounds"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_adaptive_bustout_round(
        AdaptiveBustOutConfig(
            processed_dir=args.processed_dir,
            confrontation_dir=args.confrontation_dir,
            model_dir=args.model_dir,
            output_dir=args.output_dir,
            seed=args.seed,
            candidate_count=args.candidate_count,
            reference_max_rows=args.reference_max_rows,
        )
    )
    report = result.execution.report
    comparison = report.comparison
    print(f"Adaptive round: {report.report_id}")
    print(f"  frozen model: {report.model_version}")
    print(f"  candidates: {len(report.candidate_results)}")
    print(f"  selected: {report.selected_candidate_id}")
    print(
        f"  recall round0={comparison.round0.fraud_recall:.4f} "
        f"round1={comparison.round1.fraud_recall:.4f}"
    )
    print(
        f"  risk round0={comparison.round0.average_fraud_risk_score:.4f} "
        f"round1={comparison.round1.average_fraud_risk_score:.4f}"
    )
    print(f"  report: {result.artifacts['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
