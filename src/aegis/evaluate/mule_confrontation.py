"""Leakage-safe static confrontation reporting for synthetic mule networks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import Field

from aegis.evaluate.confrontation import (
    BustOutConfrontationEvaluator,
    ConfrontationValidationError,
    EvasionRecord,
    FraudEventAssessment,
    _align_outputs,
    _bounded_score,
    _mapping,
    _single_split,
    _validate_labels_and_model,
    rank_hardest_evasions,
)
from aegis.shared.base import AegisModel
from aegis.shared.contracts import DetectorOutput, EvaluationResult, Transaction, TransactionBatch
from aegis.shared.enums import AttackFamily, DataSplit, FraudLabel


class TrainingOverlapScan(AegisModel):
    """Bounded-memory evidence that generated IDs are absent from TRAIN."""

    source: str = Field(..., min_length=1)
    training_transaction_count: int = Field(..., ge=0)
    generated_transaction_count: int = Field(..., ge=0)
    transaction_id_overlaps: list[str] = Field(default_factory=list)
    scenario_id_overlaps: list[str] = Field(default_factory=list)
    train_only_verified: bool

    @property
    def is_fresh(self) -> bool:
        return not self.transaction_id_overlaps and not self.scenario_id_overlaps


class MuleScenarioConfrontationReport(AegisModel):
    """Detector outcomes for one indivisible mule-network scenario."""

    scenario_id: str = Field(..., min_length=1)
    split: DataSplit
    total_transactions: int = Field(..., ge=1)
    legitimate_context_transaction_count: int = Field(..., ge=0)
    fraudulent_structuring_count: int = Field(..., ge=0)
    caught_fraud_count: int = Field(..., ge=0)
    evaded_fraud_count: int = Field(..., ge=0)
    fraud_recall: float = Field(..., ge=0.0, le=1.0)
    fraudulent_events: list[FraudEventAssessment]
    model_version: str = Field(..., min_length=1)
    attack_family: AttackFamily
    blueprint_id: str = Field(..., min_length=1)
    generation: int = Field(..., ge=0)
    batch_id: str = Field(..., min_length=1)
    generator_name: str = Field(..., min_length=1)
    generator_version: str = Field(..., min_length=1)
    seed: int
    fidelity_summary: dict[str, Any]
    evaluation_result: EvaluationResult


class MuleNetworkConfrontationReport(AegisModel):
    """Serializable static-holdout evidence for one fresh mule batch."""

    report_id: str = Field(..., min_length=1)
    training_dataset_id: str = Field(..., min_length=1)
    training_transaction_count: int = Field(..., ge=0)
    data_basis: str = Field(..., min_length=1)
    integration_only: bool
    model_version: str = Field(..., min_length=1)
    generated_batch_id: str = Field(..., min_length=1)
    training_overlap_scan: TrainingOverlapScan
    scenario_reports: list[MuleScenarioConfrontationReport]
    successful_evasions: list[EvasionRecord]
    hardest_evasions: list[EvasionRecord]
    metadata: dict[str, Any] = Field(default_factory=dict)


class MuleNetworkConfrontationEvaluator(BustOutConfrontationEvaluator):
    """Reuse the family-generic static metrics while giving this run its own identity."""

    name = "mule-network-confrontation"


def scan_training_overlap(
    train_path: str | Path, generated: Sequence[Transaction]
) -> TrainingOverlapScan:
    """Scan a multi-GB JSONL file without retaining its transaction population."""
    path = Path(train_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"prepared TRAIN artifact not found: {path}")
    generated_ids = {transaction.transaction_id for transaction in generated}
    generated_scenarios = {
        transaction.scenario_id for transaction in generated if transaction.scenario_id is not None
    }
    transaction_overlaps: set[str] = set()
    scenario_overlaps: set[str] = set()
    row_count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ConfrontationValidationError(
                    f"{path}:{line_number} is not valid JSON"
                ) from exc
            if payload.get("split") != DataSplit.TRAIN.value:
                raise ConfrontationValidationError(
                    f"TRAIN overlap scan encountered non-train row at {path}:{line_number}"
                )
            transaction_id = payload.get("transaction_id")
            if not isinstance(transaction_id, str) or not transaction_id:
                raise ConfrontationValidationError(
                    f"TRAIN overlap scan found invalid transaction_id at {path}:{line_number}"
                )
            scenario_id = payload.get("scenario_id")
            row_count += 1
            if transaction_id in generated_ids:
                transaction_overlaps.add(transaction_id)
            if isinstance(scenario_id, str) and scenario_id in generated_scenarios:
                scenario_overlaps.add(scenario_id)
    return TrainingOverlapScan(
        source=str(path),
        training_transaction_count=row_count,
        generated_transaction_count=len(generated),
        transaction_id_overlaps=sorted(transaction_overlaps),
        scenario_id_overlaps=sorted(scenario_overlaps),
        train_only_verified=True,
    )


def build_mule_network_confrontation_report(
    *,
    batch: TransactionBatch,
    outputs: Sequence[DetectorOutput],
    training_overlap_scan: TrainingOverlapScan,
    training_dataset_id: str,
    data_basis: str,
    integration_only: bool,
) -> MuleNetworkConfrontationReport:
    """Validate freshness, labels, alignment, and build contract-backed metrics."""
    if not batch.transactions:
        raise ConfrontationValidationError("generated batch is empty")
    if batch.seed is None or batch.generation is None or batch.blueprint_id is None:
        raise ConfrontationValidationError("generated batch lacks required provenance")
    if batch.attack_family is not AttackFamily.MULE_NETWORK_STRUCTURING:
        raise ConfrontationValidationError("batch is not a mule-network structuring attack")
    if not batch.generator_name or not batch.generator_version:
        raise ConfrontationValidationError("generated batch lacks generator identity")
    if training_overlap_scan.generated_transaction_count != len(batch.transactions):
        raise ConfrontationValidationError(
            "training overlap scan covers a different generated batch"
        )
    if not training_overlap_scan.train_only_verified:
        raise ConfrontationValidationError(
            "training overlap scan did not verify a TRAIN-only source"
        )
    if not training_overlap_scan.is_fresh:
        raise ConfrontationValidationError(
            "generated mule batch overlaps detector training: "
            f"transactions={training_overlap_scan.transaction_id_overlaps}, "
            f"scenarios={training_overlap_scan.scenario_id_overlaps}"
        )
    aligned = _align_outputs(outputs, batch.transactions)
    _validate_labels_and_model(aligned)
    fidelity_summary = _mapping(batch.metadata.get("fidelity"))
    fidelity_score = _bounded_score(
        fidelity_summary.get("overall_fidelity_score"), default=0.0
    )
    evaluator = MuleNetworkConfrontationEvaluator()
    by_scenario: dict[str, list[tuple[Transaction, DetectorOutput]]] = {}
    for transaction, output in aligned:
        if transaction.scenario_id is None:
            raise ConfrontationValidationError(
                f"generated transaction {transaction.transaction_id!r} has no scenario_id"
            )
        by_scenario.setdefault(transaction.scenario_id, []).append((transaction, output))
    if sorted(by_scenario) != sorted(batch.scenario_ids):
        raise ConfrontationValidationError("batch scenario_ids do not match transaction provenance")

    scenario_reports: list[MuleScenarioConfrontationReport] = []
    evasions: list[EvasionRecord] = []
    for scenario_id in sorted(by_scenario):
        pairs = sorted(
            by_scenario[scenario_id],
            key=lambda pair: (pair[0].timestamp, pair[0].sequence_index or 0),
        )
        transactions = [pair[0] for pair in pairs]
        scenario_outputs = [pair[1] for pair in pairs]
        scenario_split = _single_split(transactions)
        context = [transaction for transaction in transactions if not transaction.is_fraud]
        fraud_pairs = [
            (transaction, output)
            for transaction, output in pairs
            if transaction.is_fraud
        ]
        if any(transaction.label is FraudLabel.UNKNOWN for transaction in transactions):
            raise ConfrontationValidationError("generated scenario contains UNKNOWN labels")
        if not context or not fraud_pairs:
            raise ConfrontationValidationError(
                "mule scenario must contain legitimate context and fraudulent structuring"
            )
        assessments: list[FraudEventAssessment] = []
        caught_count = 0
        for transaction, output in fraud_pairs:
            if transaction.attack_family is not AttackFamily.MULE_NETWORK_STRUCTURING:
                raise ConfrontationValidationError(
                    f"fraud transaction {transaction.transaction_id!r} has wrong attack family"
                )
            caught = output.predicted_label is FraudLabel.FRAUD
            caught_count += int(caught)
            assessments.append(
                FraudEventAssessment(
                    transaction_id=transaction.transaction_id,
                    sequence_index=transaction.sequence_index,
                    risk_score=output.risk_score,
                    predicted_label=output.predicted_label,
                    action=output.recommended_action,
                    caught=caught,
                    model_version=output.model_version,
                )
            )
            if not caught:
                if transaction.blueprint_id is None or transaction.generation is None:
                    raise ConfrontationValidationError(
                        f"fraud transaction {transaction.transaction_id!r} lacks lineage"
                    )
                evasions.append(
                    EvasionRecord(
                        scenario_id=scenario_id,
                        transaction_id=transaction.transaction_id,
                        attack_family=transaction.attack_family,
                        blueprint_id=transaction.blueprint_id,
                        generation=transaction.generation,
                        sequence_index=transaction.sequence_index,
                        detector_risk_score=output.risk_score,
                        action=output.recommended_action,
                        detector_model_version=output.model_version,
                        fidelity_score=fidelity_score,
                        credible_evasion=fidelity_score >= 0.5,
                        hardness_score=(1.0 - output.risk_score) * fidelity_score,
                    )
                )
        evaluation = evaluator.evaluate(
            scenario_outputs,
            transactions,
            meta={
                "evaluation_id": f"{batch.batch_id}-{scenario_id}",
                "dataset_id": batch.batch_id,
                "seed": batch.seed,
                "fidelity_summary": fidelity_summary,
                "integration_only": integration_only,
                "notes": (
                    "Integration fixture only; not a real PaySim efficacy result."
                    if integration_only
                    else "Fresh synthetic mule network scored against a frozen detector."
                ),
            },
        )
        scenario_reports.append(
            MuleScenarioConfrontationReport(
                scenario_id=scenario_id,
                split=scenario_split,
                total_transactions=len(transactions),
                legitimate_context_transaction_count=len(context),
                fraudulent_structuring_count=len(fraud_pairs),
                caught_fraud_count=caught_count,
                evaded_fraud_count=len(fraud_pairs) - caught_count,
                fraud_recall=caught_count / len(fraud_pairs),
                fraudulent_events=assessments,
                model_version=scenario_outputs[0].model_version,
                attack_family=batch.attack_family,
                blueprint_id=batch.blueprint_id,
                generation=batch.generation,
                batch_id=batch.batch_id,
                generator_name=batch.generator_name,
                generator_version=batch.generator_version,
                seed=batch.seed,
                fidelity_summary=fidelity_summary,
                evaluation_result=evaluation,
            )
        )
    hardest = rank_hardest_evasions(evasions)
    identity = json.dumps(
        {
            "batch_id": batch.batch_id,
            "model_version": outputs[0].model_version,
            "training_dataset_id": training_dataset_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return MuleNetworkConfrontationReport(
        report_id=f"mule-confrontation-{digest}",
        training_dataset_id=training_dataset_id,
        training_transaction_count=training_overlap_scan.training_transaction_count,
        data_basis=data_basis,
        integration_only=integration_only,
        model_version=outputs[0].model_version,
        generated_batch_id=batch.batch_id,
        training_overlap_scan=training_overlap_scan,
        scenario_reports=scenario_reports,
        successful_evasions=evasions,
        hardest_evasions=hardest,
        metadata={
            "adaptive": False,
            "detector_retrained": False,
            "evaluation_protocol": "static_holdout",
            "fitness_compatible": "(1-average_fraud_risk)*overall_fidelity_score",
            "ranking": "descending (1-risk_score)*fidelity_score with stable tie-breakers",
        },
    )


__all__ = [
    "MuleNetworkConfrontationEvaluator",
    "MuleNetworkConfrontationReport",
    "MuleScenarioConfrontationReport",
    "TrainingOverlapScan",
    "build_mule_network_confrontation_report",
    "scan_training_overlap",
]
