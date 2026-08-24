"""Contracts can be instantiated and enforce the invariants we rely on."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aegis.shared.contracts import (
    AttackBlueprint,
    ClassificationMetrics,
    ConfusionCounts,
    DetectorOutput,
    EvaluationResult,
    EvasionFeedback,
    FidelityMetrics,
    LatencyMetrics,
    ParameterMutation,
    SignalContribution,
    Transaction,
    TransactionBatch,
)
from aegis.shared.enums import (
    AttackFamily,
    DataSplit,
    EvaluationProtocol,
    FraudLabel,
    MutationDirection,
    RecommendedAction,
    SignalDirection,
)

pytestmark = pytest.mark.contract

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


# --- AttackBlueprint -------------------------------------------------------
def test_blueprint_instantiates(blueprint):
    assert blueprint.attack_family is AttackFamily.MULE_NETWORK_STRUCTURING
    assert blueprint.generation == 0
    assert blueprint.contract_version


def test_blueprint_orders_sequence(blueprint):
    assert [s.step_id for s in blueprint.ordered_sequence()] == ["fan-out", "cash-out"]


def test_blueprint_separates_mutable_parameters(blueprint):
    assert set(blueprint.mutable_parameters()) == {"split_count", "threshold_margin"}
    assert blueprint.default_parameters()["split_count"] == 4


def test_blueprint_rejects_duplicate_step_ids(blueprint):
    payload = blueprint.model_dump()
    payload["sequence"][1]["step_id"] = payload["sequence"][0]["step_id"]
    with pytest.raises(ValidationError, match="duplicate step_id"):
        AttackBlueprint.model_validate(payload)


def test_blueprint_rejects_parameter_key_mismatch(blueprint):
    payload = blueprint.model_dump()
    payload["parameters"]["renamed"] = payload["parameters"].pop("split_count")
    with pytest.raises(ValidationError, match="does not match"):
        AttackBlueprint.model_validate(payload)


def test_blueprint_rejects_unknown_field(blueprint):
    payload = blueprint.model_dump()
    payload["totally_new_field"] = 1
    with pytest.raises(ValidationError):
        AttackBlueprint.model_validate(payload)


# --- Transaction -----------------------------------------------------------
def test_transaction_instantiates(transaction):
    assert transaction.is_fraud is True
    assert transaction.currency == "USD"  # normalised
    assert transaction.split is DataSplit.UNASSIGNED


def test_transaction_naive_timestamp_becomes_utc():
    txn = Transaction(
        transaction_id="t1",
        timestamp=datetime(2026, 1, 1),  # deliberately naive
        source_account_id="a",
        amount=1.0,
    )
    assert txn.timestamp.tzinfo is not None


def test_transaction_rejects_bad_currency():
    with pytest.raises(ValidationError, match="ISO-4217"):
        Transaction(
            transaction_id="t1",
            timestamp=T0,
            source_account_id="a",
            amount=1.0,
            currency="dollars",
        )


def test_transaction_rejects_negative_amount():
    with pytest.raises(ValidationError):
        Transaction(transaction_id="t1", timestamp=T0, source_account_id="a", amount=-1.0)


def test_transaction_rejects_legit_label_with_attack_family():
    with pytest.raises(ValidationError, match="attack_family"):
        Transaction(
            transaction_id="t1",
            timestamp=T0,
            source_account_id="a",
            amount=1.0,
            label=FraudLabel.LEGITIMATE,
            attack_family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
        )


def test_unknown_label_is_not_fraud():
    txn = Transaction(transaction_id="t1", timestamp=T0, source_account_id="a", amount=1.0)
    assert txn.label is FraudLabel.UNKNOWN
    assert txn.is_fraud is False


def test_features_are_namespaced_and_do_not_mutate_source(transaction):
    enriched = transaction.with_features("temporal", {"velocity_1h": 3})
    assert enriched.features == {"temporal.velocity_1h": 3}
    assert transaction.features == {}


def test_features_from_two_producers_coexist(transaction):
    enriched = transaction.with_features("temporal", {"v": 1}).with_features("graph", {"v": 2})
    assert enriched.features == {"temporal.v": 1, "graph.v": 2}


def test_flat_record_lifts_features(transaction):
    record = transaction.with_features("graph", {"fan_out": 5}).to_flat_record()
    assert record["graph.fan_out"] == 5
    assert record["transaction_id"] == "txn-0001"
    assert "features" not in record


def test_transaction_batch_counts(transaction):
    batch = TransactionBatch(batch_id="b1", transactions=[transaction], seed=7)
    assert len(batch) == 1
    assert batch.fraud_count == 1
    assert batch.to_records()[0]["amount"] == 2500.0


# --- DetectorOutput --------------------------------------------------------
def test_detector_output_instantiates():
    out = DetectorOutput(
        transaction_id="t1",
        risk_score=0.87,
        predicted_label=FraudLabel.FRAUD,
        recommended_action=RecommendedAction.REVIEW,
        model_version="m-v1",
        important_signals=[
            SignalContribution(
                name="temporal.velocity_1h",
                contribution=0.4,
                direction=SignalDirection.INCREASES_RISK,
                rank=0,
            ),
            SignalContribution(name="graph.fan_out", contribution=-0.1, rank=1),
        ],
    )
    assert out.top_signals(1)[0].name == "temporal.velocity_1h"


def test_detector_output_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        DetectorOutput(
            transaction_id="t1",
            risk_score=1.4,
            predicted_label=FraudLabel.FRAUD,
            recommended_action=RecommendedAction.DECLINE,
            model_version="m-v1",
        )


def test_detector_output_rejects_duplicate_signal_ranks():
    with pytest.raises(ValidationError, match="duplicate rank"):
        DetectorOutput(
            transaction_id="t1",
            risk_score=0.2,
            predicted_label=FraudLabel.LEGITIMATE,
            recommended_action=RecommendedAction.APPROVE,
            model_version="m-v1",
            important_signals=[
                SignalContribution(name="a", contribution=0.1, rank=0),
                SignalContribution(name="b", contribution=0.1, rank=0),
            ],
        )


def test_all_four_actions_exist():
    assert {a.value for a in RecommendedAction} == {
        "approve",
        "step_up",
        "review",
        "decline",
    }


# --- EvaluationResult ------------------------------------------------------
def _metrics() -> ClassificationMetrics:
    return ClassificationMetrics(
        precision=0.8,
        recall=0.6,
        f1=0.686,
        pr_auc=0.72,
        roc_auc=0.94,
        false_positive_rate=0.004,
        recall_at_fixed_fpr={"0.001": 0.41, "0.01": 0.73},
        counts=ConfusionCounts(
            true_positives=60, false_positives=15, true_negatives=3985, false_negatives=40
        ),
        support=4100,
        positive_support=100,
    )


def test_evaluation_result_instantiates():
    result = EvaluationResult(
        evaluation_id="ev-1",
        protocol=EvaluationProtocol.STATIC_HOLDOUT,
        model_version="m-v1",
        overall=_metrics(),
        per_attack_family={AttackFamily.MULE_NETWORK_STRUCTURING: _metrics()},
        latency=LatencyMetrics(mean_ms=4.2, p95_ms=9.1, samples=4100),
        fidelity=FidelityMetrics(discriminator_auc=0.55, overall_fidelity_score=0.82),
    )
    assert result.overall.recall_at_fixed_fpr["0.001"] == 0.41
    assert result.overall.counts.support == 4100
    assert result.overall.counts.positives == 100


def test_loafo_requires_held_out_family():
    with pytest.raises(ValidationError, match="held_out_family"):
        EvaluationResult(
            evaluation_id="ev-2",
            protocol=EvaluationProtocol.LEAVE_ONE_ATTACK_FAMILY_OUT,
            model_version="m-v1",
            overall=_metrics(),
        )


def test_closed_loop_requires_round_index():
    with pytest.raises(ValidationError, match="round_index"):
        EvaluationResult(
            evaluation_id="ev-3",
            protocol=EvaluationProtocol.CLOSED_LOOP_ROUND,
            model_version="m-v1",
            overall=_metrics(),
        )


# --- EvasionFeedback -------------------------------------------------------
def test_evasion_feedback_instantiates():
    feedback = EvasionFeedback(
        feedback_id="fb-1",
        attack_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
        blueprint_id="bp-1",
        original_parameters={"split_count": 4},
        detector_score=0.31,
        detector_model_version="m-v1",
        threshold=0.5,
        evaded=True,
        realism_score=0.78,
        important_signals=[SignalContribution(name="temporal.velocity_1h", contribution=0.2)],
        suggested_mutations=[
            ParameterMutation(
                parameter="split_count",
                direction=MutationDirection.INCREASE,
                current_value=4,
                magnitude=0.25,
                priority=1,
                confidence=0.6,
            ),
            ParameterMutation(
                parameter="threshold_margin",
                direction=MutationDirection.SET,
                proposed_value=0.92,
                priority=0,
                confidence=0.9,
            ),
        ],
    )
    assert feedback.is_credible_evasion is True
    assert [m.parameter for m in feedback.ordered_mutations()] == [
        "threshold_margin",
        "split_count",
    ]


def test_evasion_without_realism_is_not_credible():
    feedback = EvasionFeedback(
        feedback_id="fb-2",
        attack_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
        detector_score=0.1,
        detector_model_version="m-v1",
        evaded=True,
    )
    assert feedback.is_credible_evasion is False


def test_set_mutation_requires_value():
    with pytest.raises(ValidationError, match="proposed_value"):
        ParameterMutation(parameter="x", direction=MutationDirection.SET)


def test_feedback_rejects_duplicate_mutation_targets():
    with pytest.raises(ValidationError, match="duplicate parameter"):
        EvasionFeedback(
            feedback_id="fb-3",
            attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
            detector_score=0.4,
            detector_model_version="m-v1",
            evaded=False,
            suggested_mutations=[
                ParameterMutation(parameter="x", direction=MutationDirection.INCREASE),
                ParameterMutation(parameter="x", direction=MutationDirection.DECREASE),
            ],
        )
