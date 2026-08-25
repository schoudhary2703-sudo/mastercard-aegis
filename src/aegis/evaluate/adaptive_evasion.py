"""Static-holdout reporting for bounded adaptive detector-evasion scenarios."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
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
from aegis.evaluate.mule_confrontation import TrainingOverlapScan
from aegis.shared.base import AegisModel
from aegis.shared.contracts import DetectorOutput, EvaluationResult, Transaction, TransactionBatch
from aegis.shared.enums import AttackFamily, DataSplit, FraudLabel


class AdaptiveEvasionScenarioReport(AegisModel):
    """One fresh child scenario scored against one unchanged detector."""

    scenario_id: str = Field(..., min_length=1)
    split: DataSplit
    total_transactions: int = Field(..., ge=1)
    legitimate_context_transaction_count: int = Field(..., ge=0)
    fraudulent_perturbation_count: int = Field(..., ge=0)
    caught_fraud_count: int = Field(..., ge=0)
    evaded_fraud_count: int = Field(..., ge=0)
    fraud_recall: float = Field(..., ge=0.0, le=1.0)
    average_fraud_risk_score: float = Field(..., ge=0.0, le=1.0)
    fidelity_score: float = Field(..., ge=0.0, le=1.0)
    fitness: float = Field(..., ge=0.0, le=1.0)
    fraudulent_events: list[FraudEventAssessment]
    model_version: str = Field(..., min_length=1)
    attack_family: AttackFamily
    blueprint_id: str = Field(..., min_length=1)
    parent_blueprint_id: str | None = None
    generation: int = Field(..., ge=0)
    batch_id: str = Field(..., min_length=1)
    generator_name: str = Field(..., min_length=1)
    generator_version: str = Field(..., min_length=1)
    seed: int
    fidelity_summary: dict[str, Any]
    evaluation_result: EvaluationResult


class AdaptiveEvasionConfrontationReport(AegisModel):
    """Canonical evidence for one post-feedback, fresh-seed static confrontation."""

    report_id: str = Field(..., min_length=1)
    training_dataset_id: str = Field(..., min_length=1)
    training_transaction_count: int = Field(..., ge=0)
    data_basis: str = Field(..., min_length=1)
    integration_only: bool
    model_version: str = Field(..., min_length=1)
    generated_batch_id: str = Field(..., min_length=1)
    training_overlap_scan: TrainingOverlapScan
    scenario_reports: list[AdaptiveEvasionScenarioReport]
    successful_evasions: list[EvasionRecord]
    hardest_evasions: list[EvasionRecord]
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdaptiveEvasionConfrontationEvaluator(BustOutConfrontationEvaluator):
    """Family-specific name over the existing generic static metrics."""

    name = "adaptive-evasion-confrontation"


def build_adaptive_evasion_confrontation_report(
    *,
    batch: TransactionBatch,
    blueprint_parent_id: str | None,
    outputs: Sequence[DetectorOutput],
    training_overlap_scan: TrainingOverlapScan,
    training_dataset_id: str,
    data_basis: str,
    integration_only: bool,
) -> AdaptiveEvasionConfrontationReport:
    """Validate final child freshness and compute the required attack fitness."""
    if not batch.transactions:
        raise ConfrontationValidationError("generated batch is empty")
    if batch.seed is None or batch.generation is None or batch.blueprint_id is None:
        raise ConfrontationValidationError("generated batch lacks required provenance")
    if batch.attack_family is not AttackFamily.ADAPTIVE_DETECTOR_EVASION:
        raise ConfrontationValidationError("batch is not adaptive detector evasion")
    if training_overlap_scan.generated_transaction_count != len(batch.transactions):
        raise ConfrontationValidationError(
            "training overlap scan covers a different generated batch"
        )
    if not training_overlap_scan.train_only_verified or not training_overlap_scan.is_fresh:
        raise ConfrontationValidationError("adaptive batch freshness was not verified")
    aligned = _align_outputs(outputs, batch.transactions)
    _validate_labels_and_model(aligned)
    fidelity_summary = _mapping(batch.metadata.get("fidelity"))
    fidelity_score = _bounded_score(
        fidelity_summary.get("overall_fidelity_score"), default=0.0
    )
    evaluator = AdaptiveEvasionConfrontationEvaluator()
    by_scenario: dict[str, list[tuple[Transaction, DetectorOutput]]] = {}
    for transaction, output in aligned:
        if transaction.scenario_id is None:
            raise ConfrontationValidationError("adaptive transaction lacks scenario_id")
        by_scenario.setdefault(transaction.scenario_id, []).append((transaction, output))
    if sorted(by_scenario) != sorted(batch.scenario_ids):
        raise ConfrontationValidationError("batch scenario_ids do not match provenance")

    scenario_reports: list[AdaptiveEvasionScenarioReport] = []
    evasions: list[EvasionRecord] = []
    for scenario_id in sorted(by_scenario):
        pairs = sorted(
            by_scenario[scenario_id],
            key=lambda pair: (pair[0].timestamp, pair[0].sequence_index or 0),
        )
        transactions = [pair[0] for pair in pairs]
        scenario_outputs = [pair[1] for pair in pairs]
        split = _single_split(transactions)
        context = [transaction for transaction in transactions if not transaction.is_fraud]
        fraud_pairs = [
            (transaction, output)
            for transaction, output in pairs
            if transaction.is_fraud
        ]
        if not context or not fraud_pairs:
            raise ConfrontationValidationError(
                "adaptive scenario requires legitimate context and fraud perturbations"
            )
        assessments: list[FraudEventAssessment] = []
        caught_count = 0
        risks: list[float] = []
        for transaction, output in fraud_pairs:
            if transaction.label is not FraudLabel.FRAUD:
                raise ConfrontationValidationError("adaptive fraud ground truth changed")
            if transaction.attack_family is not AttackFamily.ADAPTIVE_DETECTOR_EVASION:
                raise ConfrontationValidationError("adaptive fraud family provenance changed")
            caught = output.predicted_label is FraudLabel.FRAUD
            caught_count += int(caught)
            risks.append(output.risk_score)
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
                    raise ConfrontationValidationError("adaptive fraud lacks lineage")
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
        average_risk = sum(risks) / len(risks)
        fitness = (1.0 - average_risk) * fidelity_score
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
                    "Integration fixture only; no efficacy claim."
                    if integration_only
                    else "Fresh post-feedback adaptive-evasion child scored without retraining."
                ),
            },
        )
        scenario_reports.append(
            AdaptiveEvasionScenarioReport(
                scenario_id=scenario_id,
                split=split,
                total_transactions=len(transactions),
                legitimate_context_transaction_count=len(context),
                fraudulent_perturbation_count=len(fraud_pairs),
                caught_fraud_count=caught_count,
                evaded_fraud_count=len(fraud_pairs) - caught_count,
                fraud_recall=caught_count / len(fraud_pairs),
                average_fraud_risk_score=average_risk,
                fidelity_score=fidelity_score,
                fitness=fitness,
                fraudulent_events=assessments,
                model_version=scenario_outputs[0].model_version,
                attack_family=batch.attack_family,
                blueprint_id=batch.blueprint_id,
                parent_blueprint_id=blueprint_parent_id,
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
            "batch": batch.batch_id,
            "model": outputs[0].model_version,
            "training": training_dataset_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return AdaptiveEvasionConfrontationReport(
        report_id=f"adaptive-evasion-confrontation-{digest}",
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
            "adaptive": True,
            "detector_retrained": False,
            "evaluation_protocol": "static_holdout",
            "fitness": "(1-average_fraud_risk)*overall_fidelity_score",
            "selection_sample_reused": False,
        },
    )


__all__ = [
    "AdaptiveEvasionConfrontationEvaluator",
    "AdaptiveEvasionConfrontationReport",
    "AdaptiveEvasionScenarioReport",
    "build_adaptive_evasion_confrontation_report",
]
