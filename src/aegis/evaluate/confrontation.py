"""Scenario-level reporting for the first Red-versus-Blue confrontation.

This module deliberately depends only on frozen shared contracts. The caller
owns generation, feature extraction, and detector invocation; evaluation joins
their outputs by transaction ID and refuses ambiguous or leaked inputs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import Field, field_validator

from aegis.evaluate.base import BaseEvaluator
from aegis.shared.base import AegisModel
from aegis.shared.contracts import (
    ClassificationMetrics,
    ConfusionCounts,
    DetectorOutput,
    EvaluationResult,
    FidelityMetrics,
    Transaction,
    TransactionBatch,
)
from aegis.shared.enums import (
    AttackFamily,
    DataSplit,
    EvaluationProtocol,
    FraudLabel,
    RecommendedAction,
)


class ConfrontationValidationError(ValueError):
    """Raised when an integration result would violate evaluation rules."""


class FraudEventAssessment(AegisModel):
    """One ground-truth fraud event and the detector decision made for it."""

    transaction_id: str = Field(..., min_length=1)
    sequence_index: int | None = Field(default=None, ge=0)
    risk_score: float = Field(..., ge=0.0, le=1.0)
    predicted_label: FraudLabel
    action: RecommendedAction
    caught: bool
    ground_truth_label: FraudLabel = FraudLabel.FRAUD
    model_version: str = Field(..., min_length=1)

    @field_validator("ground_truth_label")
    @classmethod
    def _ground_truth_stays_fraud(cls, value: FraudLabel) -> FraudLabel:
        if value is not FraudLabel.FRAUD:
            raise ValueError("fraud-event ground truth must remain FRAUD")
        return value


class EvasionRecord(AegisModel):
    """Structured false negative retained for later, explicitly non-adaptive use."""

    rank: int | None = Field(default=None, ge=1)
    scenario_id: str = Field(..., min_length=1)
    transaction_id: str = Field(..., min_length=1)
    attack_family: AttackFamily
    blueprint_id: str = Field(..., min_length=1)
    generation: int = Field(..., ge=0)
    sequence_index: int | None = Field(default=None, ge=0)
    detector_risk_score: float = Field(..., ge=0.0, le=1.0)
    action: RecommendedAction
    detector_model_version: str = Field(..., min_length=1)
    ground_truth_label: FraudLabel = FraudLabel.FRAUD
    fidelity_score: float = Field(..., ge=0.0, le=1.0)
    credible_evasion: bool
    hardness_score: float = Field(..., ge=0.0, le=1.0)

    @field_validator("ground_truth_label")
    @classmethod
    def _evasion_ground_truth_stays_fraud(cls, value: FraudLabel) -> FraudLabel:
        if value is not FraudLabel.FRAUD:
            raise ValueError("evasion ground truth must remain FRAUD")
        return value


class ScenarioConfrontationReport(AegisModel):
    """Detector outcomes and provenance for one indivisible attack scenario."""

    scenario_id: str = Field(..., min_length=1)
    split: DataSplit
    total_transactions: int = Field(..., ge=1)
    legitimate_warmup_transaction_count: int = Field(..., ge=0)
    fraudulent_bustout_count: int = Field(..., ge=0)
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


class BustOutConfrontationReport(AegisModel):
    """Serializable artifact for one fresh batch confronted by one detector."""

    report_id: str = Field(..., min_length=1)
    training_dataset_id: str = Field(..., min_length=1)
    training_transaction_count: int = Field(..., ge=0)
    data_basis: str = Field(..., min_length=1)
    integration_only: bool
    model_version: str = Field(..., min_length=1)
    generated_batch_id: str = Field(..., min_length=1)
    scenario_reports: list[ScenarioConfrontationReport]
    successful_evasions: list[EvasionRecord]
    hardest_evasions: list[EvasionRecord]
    metadata: dict[str, Any] = Field(default_factory=dict)


class BustOutConfrontationEvaluator(BaseEvaluator):
    """Build contract-backed metrics without importing either team's package."""

    name = "bustout-confrontation"
    protocol = EvaluationProtocol.STATIC_HOLDOUT

    def evaluate(
        self,
        outputs: Sequence[DetectorOutput],
        ground_truth: Sequence[Transaction],
        meta: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        context = meta or {}
        aligned = _align_outputs(outputs, ground_truth)
        if not aligned:
            raise ConfrontationValidationError("at least one scored transaction is required")
        _validate_labels_and_model(aligned)

        counts = _confusion_counts(aligned)
        threshold = outputs[0].threshold
        model_version = outputs[0].model_version
        overall = _classification_metrics(counts, threshold)
        fraud_pairs = [(txn, output) for txn, output in aligned if txn.is_fraud]
        per_family: dict[AttackFamily, ClassificationMetrics] = {}
        families = sorted(
            {txn.attack_family for txn, _ in fraud_pairs if txn.attack_family is not None},
            key=lambda family: family.value,
        )
        for family in families:
            family_pairs = [(txn, out) for txn, out in fraud_pairs if txn.attack_family is family]
            per_family[family] = _classification_metrics(
                _confusion_counts(family_pairs), threshold
            )

        fidelity_summary = _mapping(context.get("fidelity_summary"))
        return EvaluationResult(
            evaluation_id=str(context.get("evaluation_id", "bustout-confrontation")),
            protocol=self.protocol,
            model_version=model_version,
            dataset_id=str(context.get("dataset_id", "synthetic-bustout")),
            split=_single_split(ground_truth),
            overall=overall,
            per_attack_family=per_family,
            fidelity=_fidelity_metrics(fidelity_summary),
            seed=_optional_int(context.get("seed")),
            notes=str(
                context.get(
                    "notes",
                    "First-confrontation result; no adaptation, promotion, or retraining.",
                )
            ),
            metadata={
                "scenario_ids": sorted(
                    {txn.scenario_id for txn in ground_truth if txn.scenario_id is not None}
                ),
                "integration_only": bool(context.get("integration_only", False)),
                "caught_definition": "ground-truth fraud predicted as FRAUD",
            },
        )


def build_bustout_confrontation_report(
    *,
    batch: TransactionBatch,
    outputs: Sequence[DetectorOutput],
    training_transactions: Sequence[Transaction],
    training_dataset_id: str,
    data_basis: str,
    integration_only: bool,
) -> BustOutConfrontationReport:
    """Validate a fresh generated batch and build UI-ready confrontation records."""
    if not batch.transactions:
        raise ConfrontationValidationError("generated batch is empty")
    if batch.seed is None or batch.generation is None or batch.blueprint_id is None:
        raise ConfrontationValidationError("generated batch lacks required provenance")
    if batch.attack_family is not AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT:
        raise ConfrontationValidationError("batch is not a synthetic-identity bust-out attack")
    if not batch.generator_name or not batch.generator_version:
        raise ConfrontationValidationError("generated batch lacks generator identity")

    _assert_fresh_batch(batch.transactions, training_transactions)
    aligned = _align_outputs(outputs, batch.transactions)
    _validate_labels_and_model(aligned)
    fidelity_summary = _mapping(batch.metadata.get("fidelity"))
    fidelity_score = _bounded_score(fidelity_summary.get("overall_fidelity_score"), default=0.0)
    evaluator = BustOutConfrontationEvaluator()

    scenario_reports: list[ScenarioConfrontationReport] = []
    evasions: list[EvasionRecord] = []
    by_scenario: dict[str, list[tuple[Transaction, DetectorOutput]]] = {}
    for txn, output in aligned:
        if txn.scenario_id is None:
            raise ConfrontationValidationError(
                f"generated transaction {txn.transaction_id!r} has no scenario_id"
            )
        by_scenario.setdefault(txn.scenario_id, []).append((txn, output))

    if sorted(by_scenario) != sorted(batch.scenario_ids):
        raise ConfrontationValidationError("batch scenario_ids do not match transaction provenance")

    for scenario_id in sorted(by_scenario):
        pairs = sorted(
            by_scenario[scenario_id],
            key=lambda pair: (pair[0].timestamp, pair[0].sequence_index or 0),
        )
        transactions = [pair[0] for pair in pairs]
        scenario_outputs = [pair[1] for pair in pairs]
        scenario_split = _single_split(transactions)
        legitimate = [txn for txn in transactions if txn.label is FraudLabel.LEGITIMATE]
        fraud_pairs = [(txn, out) for txn, out in pairs if txn.label is FraudLabel.FRAUD]
        unknown = [txn for txn in transactions if txn.label is FraudLabel.UNKNOWN]
        if unknown:
            raise ConfrontationValidationError("generated scenario contains UNKNOWN labels")
        if not legitimate or not fraud_pairs:
            raise ConfrontationValidationError(
                "bust-out scenario must contain legitimate warm-up and fraudulent events"
            )

        event_assessments: list[FraudEventAssessment] = []
        caught_count = 0
        for txn, output in fraud_pairs:
            caught = output.predicted_label is FraudLabel.FRAUD
            caught_count += int(caught)
            event_assessments.append(
                FraudEventAssessment(
                    transaction_id=txn.transaction_id,
                    sequence_index=txn.sequence_index,
                    risk_score=output.risk_score,
                    predicted_label=output.predicted_label,
                    action=output.recommended_action,
                    caught=caught,
                    model_version=output.model_version,
                )
            )
            if not caught:
                if txn.attack_family is None or txn.blueprint_id is None or txn.generation is None:
                    raise ConfrontationValidationError(
                        f"fraud transaction {txn.transaction_id!r} lacks attack provenance"
                    )
                hardness = (1.0 - output.risk_score) * fidelity_score
                evasions.append(
                    EvasionRecord(
                        scenario_id=scenario_id,
                        transaction_id=txn.transaction_id,
                        attack_family=txn.attack_family,
                        blueprint_id=txn.blueprint_id,
                        generation=txn.generation,
                        sequence_index=txn.sequence_index,
                        detector_risk_score=output.risk_score,
                        action=output.recommended_action,
                        detector_model_version=output.model_version,
                        fidelity_score=fidelity_score,
                        credible_evasion=fidelity_score >= 0.5,
                        hardness_score=hardness,
                    )
                )

        evaded_count = len(fraud_pairs) - caught_count
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
                    else "Fresh synthetic bust-out scored after validation-only tuning."
                ),
            },
        )
        scenario_reports.append(
            ScenarioConfrontationReport(
                scenario_id=scenario_id,
                split=scenario_split,
                total_transactions=len(transactions),
                legitimate_warmup_transaction_count=len(legitimate),
                fraudulent_bustout_count=len(fraud_pairs),
                caught_fraud_count=caught_count,
                evaded_fraud_count=evaded_count,
                fraud_recall=caught_count / len(fraud_pairs),
                fraudulent_events=event_assessments,
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
    report_identity = json.dumps(
        {
            "batch_id": batch.batch_id,
            "model_version": outputs[0].model_version,
            "training_dataset_id": training_dataset_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(report_identity.encode("utf-8")).hexdigest()[:16]
    return BustOutConfrontationReport(
        report_id=f"confrontation-{digest}",
        training_dataset_id=training_dataset_id,
        training_transaction_count=len(training_transactions),
        data_basis=data_basis,
        integration_only=integration_only,
        model_version=outputs[0].model_version,
        generated_batch_id=batch.batch_id,
        scenario_reports=scenario_reports,
        successful_evasions=evasions,
        hardest_evasions=hardest,
        metadata={
            "adaptive": False,
            "retrained_after_scoring": False,
            "ranking": (
                "successful false negatives by descending "
                "(1-risk_score)*fidelity_score, then stable tie-breakers"
            ),
        },
    )


def rank_hardest_evasions(evasions: Sequence[EvasionRecord]) -> list[EvasionRecord]:
    """Rank successful evasions by risk/fidelity with deterministic tie-breakers."""
    ordered = sorted(
        evasions,
        key=lambda record: (
            -record.hardness_score,
            record.detector_risk_score,
            -record.fidelity_score,
            record.scenario_id,
            record.transaction_id,
        ),
    )
    return [record.model_copy(update={"rank": index}) for index, record in enumerate(ordered, 1)]


def _align_outputs(
    outputs: Sequence[DetectorOutput], transactions: Sequence[Transaction]
) -> list[tuple[Transaction, DetectorOutput]]:
    transaction_ids = [txn.transaction_id for txn in transactions]
    output_ids = [output.transaction_id for output in outputs]
    if len(transaction_ids) != len(set(transaction_ids)):
        raise ConfrontationValidationError("duplicate transaction IDs in ground truth")
    if len(output_ids) != len(set(output_ids)):
        raise ConfrontationValidationError("duplicate transaction IDs in detector outputs")
    if set(transaction_ids) != set(output_ids):
        missing = sorted(set(transaction_ids).difference(output_ids))
        unexpected = sorted(set(output_ids).difference(transaction_ids))
        raise ConfrontationValidationError(
            f"detector/ground-truth ID mismatch; missing={missing}, unexpected={unexpected}"
        )
    by_id = {output.transaction_id: output for output in outputs}
    return [(txn, by_id[txn.transaction_id]) for txn in transactions]


def _validate_labels_and_model(aligned: Sequence[tuple[Transaction, DetectorOutput]]) -> None:
    model_versions = {output.model_version for _, output in aligned}
    if len(model_versions) != 1:
        raise ConfrontationValidationError("one confrontation must use exactly one model version")
    thresholds = {output.threshold for _, output in aligned}
    if len(thresholds) != 1:
        raise ConfrontationValidationError("one confrontation must use exactly one threshold")
    for txn, output in aligned:
        if txn.label is FraudLabel.UNKNOWN:
            raise ConfrontationValidationError(
                f"ground-truth transaction {txn.transaction_id!r} is unlabelled"
            )
        if output.predicted_label is FraudLabel.UNKNOWN:
            raise ConfrontationValidationError(
                f"detector output {txn.transaction_id!r} has UNKNOWN predicted label"
            )


def _assert_fresh_batch(
    generated: Sequence[Transaction], training: Sequence[Transaction]
) -> None:
    generated_ids = {txn.transaction_id for txn in generated}
    training_ids = {txn.transaction_id for txn in training}
    transaction_overlap = sorted(generated_ids.intersection(training_ids))
    if transaction_overlap:
        raise ConfrontationValidationError(
            f"generated transactions overlap detector training: {transaction_overlap}"
        )
    generated_scenarios = {txn.scenario_id for txn in generated if txn.scenario_id is not None}
    training_scenarios = {txn.scenario_id for txn in training if txn.scenario_id is not None}
    scenario_overlap = sorted(generated_scenarios.intersection(training_scenarios))
    if scenario_overlap:
        raise ConfrontationValidationError(
            f"generated scenarios overlap detector training: {scenario_overlap}"
        )


def _single_split(transactions: Sequence[Transaction]) -> DataSplit:
    splits = {txn.split for txn in transactions}
    if len(splits) != 1:
        raise ConfrontationValidationError("a scenario may not span multiple data splits")
    split = next(iter(splits))
    if split in {DataSplit.TRAIN, DataSplit.VALIDATION, DataSplit.UNASSIGNED}:
        raise ConfrontationValidationError(
            f"scored attack scenarios must use test or holdout split, got {split.value}"
        )
    return split


def _confusion_counts(
    aligned: Sequence[tuple[Transaction, DetectorOutput]],
) -> ConfusionCounts:
    tp = fp = tn = fn = 0
    for txn, output in aligned:
        actual = txn.label is FraudLabel.FRAUD
        predicted = output.predicted_label is FraudLabel.FRAUD
        tp += int(actual and predicted)
        fp += int(not actual and predicted)
        tn += int(not actual and not predicted)
        fn += int(actual and not predicted)
    return ConfusionCounts(
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
    )


def _classification_metrics(
    counts: ConfusionCounts, threshold: float | None
) -> ClassificationMetrics:
    predicted_positive = counts.true_positives + counts.false_positives
    actual_positive = counts.true_positives + counts.false_negatives
    actual_negative = counts.true_negatives + counts.false_positives
    precision = counts.true_positives / predicted_positive if predicted_positive else 0.0
    recall = counts.true_positives / actual_positive if actual_positive else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = counts.false_positives / actual_negative if actual_negative else 0.0
    fnr = counts.false_negatives / actual_positive if actual_positive else 0.0
    return ClassificationMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        alert_rate=predicted_positive / counts.support if counts.support else 0.0,
        threshold=threshold,
        counts=counts,
        support=counts.support,
        positive_support=actual_positive,
    )


def _fidelity_metrics(summary: Mapping[str, Any]) -> FidelityMetrics:
    return FidelityMetrics(
        constraint_violation_rate=_optional_bounded_score(
            summary.get("constraint_violation_rate")
        ),
        overall_fidelity_score=_optional_bounded_score(
            summary.get("overall_fidelity_score")
        ),
        metadata=dict(summary),
    )


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _bounded_score(value: object, *, default: float) -> float:
    score = _optional_bounded_score(value)
    return default if score is None else score


def _optional_bounded_score(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    return score if 0.0 <= score <= 1.0 else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


__all__ = [
    "BustOutConfrontationEvaluator",
    "BustOutConfrontationReport",
    "ConfrontationValidationError",
    "EvasionRecord",
    "FraudEventAssessment",
    "ScenarioConfrontationReport",
    "build_bustout_confrontation_report",
    "rank_hardest_evasions",
]
