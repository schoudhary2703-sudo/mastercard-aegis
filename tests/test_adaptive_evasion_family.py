"""Focused tests for bounded adaptive AI-guided detector evasion."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aegis.evaluate import (
    TrainingOverlapScan,
    build_adaptive_evasion_confrontation_report,
)
from aegis.features import TemporalBaselineFeatureExtractor
from aegis.generate import (
    AdaptiveDetectorEvasionGenerator,
    AdaptiveEvasionConfigurationError,
    AdaptiveEvasionReferenceProfile,
    GenerationConfig,
)
from aegis.identify import (
    ADAPTIVE_EVASION_BLUEPRINT_PROMPT,
    AdaptiveEvasionBlueprintIdentifier,
    IdentificationContext,
    build_adaptive_evasion_blueprint,
)
from aegis.loop import (
    adapt_blueprint_from_evasions,
    build_adaptive_evasion_feedback,
)
from aegis.shared.contracts import DetectorOutput, SignalContribution, Transaction
from aegis.shared.enums import (
    AttackFamily,
    DataSplit,
    EvaluationProtocol,
    FraudLabel,
    RecommendedAction,
    SignalDirection,
    TransactionType,
)

T0 = datetime(2026, 3, 1, tzinfo=timezone.utc)


@pytest.fixture
def adaptive_tmp_path() -> Iterator[Path]:
    path = (Path("data/interim") / f"adaptive-evasion-test-{uuid.uuid4().hex}").resolve()
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def adaptive_blueprint():
    return build_adaptive_evasion_blueprint()


@pytest.fixture
def adaptive_config():
    return GenerationConfig(
        seed=303,
        n_scenarios=1,
        start_time=T0,
        time_horizon=timedelta(days=90),
        split=DataSplit.TEST,
        generation=0,
        deterministic=True,
    )


def _reference_transaction(
    index: int,
    *,
    split: DataSplit = DataSplit.TRAIN,
    label: FraudLabel = FraudLabel.LEGITIMATE,
    transaction_type: TransactionType = TransactionType.TRANSFER,
) -> Transaction:
    return Transaction(
        transaction_id=f"adaptive-reference-{index}",
        timestamp=T0 + timedelta(minutes=index),
        source_account_id=f"source-{index % 3}",
        destination_account_id=f"destination-{index % 4}",
        amount=100.0 + index * 20.0,
        currency="XXX",
        transaction_type=transaction_type,
        label=label,
        split=split,
    )


def _write_jsonl(path: Path, transactions: list[Transaction]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for transaction in transactions:
            handle.write(transaction.to_json())
            handle.write("\n")


def _outputs(transactions: list[Transaction], *, all_evade: bool = False) -> list[DetectorOutput]:
    outputs: list[DetectorOutput] = []
    fraud_index = 0
    for transaction in transactions:
        if transaction.is_fraud:
            caught = False if all_evade else fraud_index % 2 == 1
            risk = 0.22 if not caught else 0.82
            fraud_index += 1
            signals = [
                SignalContribution(
                    name="temporal.amount",
                    contribution=0.50,
                    value=transaction.amount,
                    direction=SignalDirection.INCREASES_RISK,
                    rank=0,
                ),
                SignalContribution(
                    name="temporal.amount_deviation_from_source_history",
                    contribution=0.30,
                    value=2.0,
                    direction=SignalDirection.INCREASES_RISK,
                    rank=1,
                ),
            ]
        else:
            caught = False
            risk = 0.02
            signals = []
        outputs.append(
            DetectorOutput(
                transaction_id=transaction.transaction_id,
                risk_score=risk,
                predicted_label=FraudLabel.FRAUD if caught else FraudLabel.LEGITIMATE,
                recommended_action=(
                    RecommendedAction.DECLINE if caught else RecommendedAction.APPROVE
                ),
                important_signals=signals,
                model_version="fixture-frozen-v2",
                threshold=0.5,
                policy_version="fixture-policy-v1",
            )
        )
    return outputs


def test_blueprint_is_distinct_bounded_and_safe(adaptive_blueprint):
    assert adaptive_blueprint.attack_family is AttackFamily.ADAPTIVE_DETECTOR_EVASION
    assert [step.step_id for step in adaptive_blueprint.ordered_sequence()] == [
        "behavioral-context",
        "adaptive-pacing",
        "adversarial-transfers",
    ]
    assert "bustout" not in adaptive_blueprint.attack_id
    assert "mule" not in adaptive_blueprint.attack_id
    for name, spec in adaptive_blueprint.parameters.items():
        assert spec.minimum is not None and spec.maximum is not None
        assert spec.minimum <= spec.default <= spec.maximum
        assert spec.mutable is (name not in {"max_parameter_changes", "randomness_seed_offset"})
    custom = adaptive_blueprint.realism_constraints.custom
    assert custom["unrestricted_search"] is False
    assert custom["real_system_targeting"] is False
    assert "EvasionFeedback" in ADAPTIVE_EVASION_BLUEPRINT_PROMPT


def test_identifier_routes_only_family_three():
    identifier = AdaptiveEvasionBlueprintIdentifier()
    result = identifier.propose(
        IdentificationContext(
            target_families=[AttackFamily.ADAPTIVE_DETECTOR_EVASION], seed=17
        )
    )
    assert result[0].attack_id == "adaptive-detector-evasion-17"
    assert identifier.propose(
        IdentificationContext(target_families=[AttackFamily.MULE_NETWORK_STRUCTURING])
    ) == []


def test_deterministic_generation_and_seed_variation(adaptive_blueprint, adaptive_config):
    generator = AdaptiveDetectorEvasionGenerator()
    first = generator.generate(adaptive_blueprint, adaptive_config)
    second = generator.generate(adaptive_blueprint, adaptive_config)
    changed = generator.generate(
        adaptive_blueprint, adaptive_config.model_copy(update={"seed": 304})
    )
    assert first.to_json() == second.to_json()
    assert first.batch_id == second.batch_id
    assert first.batch_id != changed.batch_id
    assert set(first.scenario_ids).isdisjoint(changed.scenario_ids)
    assert {transaction.transaction_id for transaction in first.transactions}.isdisjoint(
        transaction.transaction_id for transaction in changed.transactions
    )


def test_labels_lineage_order_and_no_collisions(adaptive_blueprint, adaptive_config):
    batch = AdaptiveDetectorEvasionGenerator().generate(adaptive_blueprint, adaptive_config)
    assert len(batch.transactions) == 14
    assert batch.fraud_count == 4
    assert len({transaction.transaction_id for transaction in batch.transactions}) == 14
    assert [transaction.sequence_index for transaction in batch.transactions] == list(range(14))
    assert [transaction.timestamp for transaction in batch.transactions] == sorted(
        transaction.timestamp for transaction in batch.transactions
    )
    context = batch.transactions[:10]
    fraud = batch.transactions[10:]
    assert all(transaction.label is FraudLabel.LEGITIMATE for transaction in context)
    assert all(transaction.attack_family is None for transaction in context)
    assert all(transaction.label is FraudLabel.FRAUD for transaction in fraud)
    assert all(
        transaction.attack_family is AttackFamily.ADAPTIVE_DETECTOR_EVASION
        for transaction in fraud
    )
    assert all(transaction.blueprint_id == adaptive_blueprint.attack_id for transaction in fraud)


def test_bounds_and_complete_scenario_enforcement(adaptive_blueprint, adaptive_config):
    generator = AdaptiveDetectorEvasionGenerator()
    with pytest.raises(AdaptiveEvasionConfigurationError, match="below minimum"):
        generator.generate(
            adaptive_blueprint,
            adaptive_config.model_copy(
                update={"parameter_overrides": {"history_blend_ratio": 0.1}}
            ),
        )
    with pytest.raises(AdaptiveEvasionConfigurationError, match="cannot exceed"):
        generator.generate(
            adaptive_blueprint,
            adaptive_config.model_copy(
                update={
                    "parameter_overrides": {
                        "fraud_amount_mean": 3_000.0,
                        "per_transaction_cap": 500.0,
                    }
                }
            ),
        )
    with pytest.raises(AdaptiveEvasionConfigurationError, match="truncate"):
        generator.generate(
            adaptive_blueprint,
            adaptive_config.model_copy(update={"max_transactions": 5}),
        )


def test_reference_is_streaming_equivalent_and_train_only(adaptive_tmp_path):
    train = [
        _reference_transaction(0, transaction_type=TransactionType.PAYMENT),
        _reference_transaction(1),
        _reference_transaction(2, transaction_type=TransactionType.CASH_OUT),
        _reference_transaction(3, label=FraudLabel.FRAUD),
    ]
    _write_jsonl(adaptive_tmp_path / "train.jsonl", train)
    (adaptive_tmp_path / "validation.jsonl").write_text("invalid\n", encoding="utf-8")
    (adaptive_tmp_path / "test.jsonl").write_text("invalid\n", encoding="utf-8")
    path_profile = AdaptiveEvasionReferenceProfile.from_processed_paysim(adaptive_tmp_path)
    iterator_profile = AdaptiveEvasionReferenceProfile.from_transactions(
        iter(train), source=str((adaptive_tmp_path / "train.jsonl").resolve())
    )
    assert path_profile == iterator_profile
    assert path_profile.sample_count == 3
    assert path_profile.transfer_sample_count == 1
    assert path_profile.latest_timestamp == train[-1].timestamp
    with pytest.raises(AdaptiveEvasionConfigurationError, match="non-train"):
        AdaptiveEvasionReferenceProfile.from_transactions(
            [_reference_transaction(9, split=DataSplit.VALIDATION)]
        )


def test_fidelity_is_deterministic_and_above_credibility_floor(
    adaptive_blueprint, adaptive_config
):
    generator = AdaptiveDetectorEvasionGenerator()
    first = generator.generate(adaptive_blueprint, adaptive_config).metadata["fidelity"]
    second = generator.generate(adaptive_blueprint, adaptive_config).metadata["fidelity"]
    assert first == second
    assert first["context_count"] == 10
    assert first["fraud_count"] == 4
    assert first["constraint_violation_rate"] == 0.0
    assert first["overall_fidelity_score"] >= 0.5


def test_feedback_contains_only_false_negatives(adaptive_blueprint, adaptive_config):
    batch = AdaptiveDetectorEvasionGenerator().generate(adaptive_blueprint, adaptive_config)
    outputs = _outputs(batch.transactions)
    feedback = build_adaptive_evasion_feedback(
        batch=batch, blueprint=adaptive_blueprint, outputs=outputs
    )
    assert len(feedback) == 2
    assert all(item.evaded and item.is_credible_evasion for item in feedback)
    assert all(item.attack_family is AttackFamily.ADAPTIVE_DETECTOR_EVASION for item in feedback)
    assert all(item.metadata["ground_truth_label"] == "FRAUD" for item in feedback)
    assert all(item.important_signals for item in feedback)


def test_guided_adaptation_is_deterministic_bounded_and_lineaged(
    adaptive_blueprint, adaptive_config
):
    generator = AdaptiveDetectorEvasionGenerator()
    batch = generator.generate(adaptive_blueprint, adaptive_config)
    feedback = build_adaptive_evasion_feedback(
        batch=batch,
        blueprint=adaptive_blueprint,
        outputs=_outputs(batch.transactions, all_evade=True),
    )
    first = adapt_blueprint_from_evasions(adaptive_blueprint, feedback, seed=404)
    second = adapt_blueprint_from_evasions(adaptive_blueprint, feedback, seed=404)
    assert first == second
    child = first.child_blueprint
    assert child.parent_blueprint_id == adaptive_blueprint.attack_id
    assert child.generation == adaptive_blueprint.generation + 1
    assert child.attack_family is AttackFamily.ADAPTIVE_DETECTOR_EVASION
    assert 1 <= len(first.changed_parameters) <= 2
    assert first.candidate_count == 1 and first.bounded_search
    assert first.evidence_basis == "detector_visible_attribution"
    assert child.parameters["randomness_seed_offset"] == adaptive_blueprint.parameters[
        "randomness_seed_offset"
    ]
    assert child.parameters["max_parameter_changes"] == adaptive_blueprint.parameters[
        "max_parameter_changes"
    ]
    for name, change in first.changed_parameters.items():
        spec = child.parameters[name]
        assert spec.minimum <= change["to"] <= spec.maximum


def test_child_seed_is_fresh_and_has_no_parent_id_reuse(adaptive_blueprint, adaptive_config):
    generator = AdaptiveDetectorEvasionGenerator()
    parent_batch = generator.generate(adaptive_blueprint, adaptive_config)
    feedback = build_adaptive_evasion_feedback(
        batch=parent_batch,
        blueprint=adaptive_blueprint,
        outputs=_outputs(parent_batch.transactions, all_evade=True),
    )
    child = adapt_blueprint_from_evasions(
        adaptive_blueprint, feedback, seed=404
    ).child_blueprint
    child_batch = generator.generate(
        child,
        adaptive_config.model_copy(update={"seed": 305, "generation": child.generation}),
    )
    assert set(parent_batch.scenario_ids).isdisjoint(child_batch.scenario_ids)
    assert {transaction.transaction_id for transaction in parent_batch.transactions}.isdisjoint(
        transaction.transaction_id for transaction in child_batch.transactions
    )


def test_detector_feature_and_evaluator_compatibility(adaptive_blueprint, adaptive_config):
    generator = AdaptiveDetectorEvasionGenerator()
    parent_batch = generator.generate(adaptive_blueprint, adaptive_config)
    feedback = build_adaptive_evasion_feedback(
        batch=parent_batch,
        blueprint=adaptive_blueprint,
        outputs=_outputs(parent_batch.transactions, all_evade=True),
    )
    adaptation = adapt_blueprint_from_evasions(adaptive_blueprint, feedback, seed=404)
    child = adaptation.child_blueprint
    child_batch = generator.generate(
        child,
        adaptive_config.model_copy(update={"seed": 305, "generation": child.generation}),
    )
    frame = TemporalBaselineFeatureExtractor().fit([]).transform(child_batch.transactions)
    assert len(frame) == len(child_batch.transactions)
    outputs = _outputs(child_batch.transactions, all_evade=True)
    scan = TrainingOverlapScan(
        source="fixture-train.jsonl",
        training_transaction_count=100,
        generated_transaction_count=len(child_batch.transactions),
        train_only_verified=True,
    )
    report = build_adaptive_evasion_confrontation_report(
        batch=child_batch,
        blueprint_parent_id=child.parent_blueprint_id,
        outputs=list(reversed(outputs)),
        training_overlap_scan=scan,
        training_dataset_id="fixture-paysim",
        data_basis="synthetic_fixture",
        integration_only=True,
    )
    scenario = report.scenario_reports[0]
    assert scenario.evaluation_result.protocol is EvaluationProtocol.STATIC_HOLDOUT
    assert scenario.fraudulent_perturbation_count == 4
    assert scenario.caught_fraud_count == 0
    assert scenario.evaded_fraud_count == 4
    assert scenario.average_fraud_risk_score == pytest.approx(0.22)
    assert scenario.fitness == pytest.approx(
        (1.0 - scenario.average_fraud_risk_score) * scenario.fidelity_score
    )
    assert all(evasion.credible_evasion for evasion in report.successful_evasions)
    assert all(
        evasion.ground_truth_label is FraudLabel.FRAUD
        for evasion in report.successful_evasions
    )
    assert report == type(report).from_json(report.to_json())
