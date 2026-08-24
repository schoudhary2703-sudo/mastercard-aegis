"""Contracts round-trip through JSON without losing or changing anything.

This is what makes the two workstreams independent: a Red Team agent can write
a blueprint to disk and a Blue Team agent can read it back without sharing a
single line of implementation code.
"""

from __future__ import annotations

import json

import pytest

from aegis.shared.contracts import (
    AttackBlueprint,
    ClassificationMetrics,
    DetectorOutput,
    EvaluationResult,
    EvasionFeedback,
    ParameterMutation,
    SignalContribution,
    Transaction,
    TransactionBatch,
)
from aegis.shared.enums import (
    AttackFamily,
    EvaluationProtocol,
    FraudLabel,
    MutationDirection,
    RecommendedAction,
)

pytestmark = pytest.mark.contract


def test_blueprint_round_trip(blueprint):
    restored = AttackBlueprint.from_json(blueprint.to_json())
    assert restored == blueprint


def test_transaction_round_trip(transaction):
    enriched = transaction.with_features("graph", {"fan_out": 5, "is_hub": True})
    restored = Transaction.from_json(enriched.to_json())
    assert restored == enriched
    assert restored.features["graph.is_hub"] is True


def test_batch_round_trip(transaction):
    batch = TransactionBatch(batch_id="b1", transactions=[transaction], seed=42)
    restored = TransactionBatch.from_json(batch.to_json())
    assert restored == batch
    assert restored.seed == 42


def test_detector_output_round_trip():
    out = DetectorOutput(
        transaction_id="t1",
        risk_score=0.42,
        predicted_label=FraudLabel.LEGITIMATE,
        recommended_action=RecommendedAction.APPROVE,
        model_version="m-v1",
        important_signals=[SignalContribution(name="a", contribution=0.1, rank=0)],
    )
    assert DetectorOutput.from_json(out.to_json()) == out


def test_evaluation_result_round_trip():
    result = EvaluationResult(
        evaluation_id="ev-1",
        protocol=EvaluationProtocol.CLOSED_LOOP_ROUND,
        round_index=3,
        model_version="m-v1",
        overall=ClassificationMetrics(precision=0.8, recall=0.6, f1=0.69, false_positive_rate=0.01),
        per_attack_family={
            AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT: ClassificationMetrics(
                precision=0.7, recall=0.5, f1=0.58, false_positive_rate=0.02
            )
        },
    )
    restored = EvaluationResult.from_json(result.to_json())
    assert restored == result
    assert AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT in restored.per_attack_family


def test_evasion_feedback_round_trip():
    feedback = EvasionFeedback(
        feedback_id="fb-1",
        attack_family=AttackFamily.ADAPTIVE_DETECTOR_EVASION,
        detector_score=0.2,
        detector_model_version="m-v1",
        evaded=True,
        realism_score=0.9,
        suggested_mutations=[
            ParameterMutation(parameter="x", direction=MutationDirection.SET, proposed_value=0.5)
        ],
    )
    assert EvasionFeedback.from_json(feedback.to_json()) == feedback


def test_enums_serialize_as_stable_strings(transaction):
    payload = json.loads(transaction.to_json())
    assert payload["attack_family"] == "mule_network_structuring"
    assert payload["transaction_type"] == "transfer"
    assert payload["label"] == 1


def test_json_schema_is_generatable():
    """The API layer and any cross-language consumer depend on this."""
    for model in (AttackBlueprint, Transaction, DetectorOutput, EvaluationResult):
        schema = model.model_json_schema()
        assert schema["title"] == model.__name__
        assert "properties" in schema
