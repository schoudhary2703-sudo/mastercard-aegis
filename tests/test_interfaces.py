"""The abstract interfaces are subclassable and enforce their own contracts.

The subclasses under test live in `conftest.py` and are deliberately trivial -
a constant score and a fixed sequence. Nothing here is a stand-in for a real
detector or generator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aegis.defend import ActionPolicy, BaseDetector, NotFittedError
from aegis.defend.policy import DEFAULT_ACTION_POLICY
from aegis.evaluate import BaseEvaluator
from aegis.features import BaseFeatureExtractor
from aegis.generate import BaseGenerator, BlueprintNotSupportedError, GenerationConfig
from aegis.identify import BaseAttackIdentifier, IdentificationContext
from aegis.shared.enums import DataSplit, FraudLabel, RecommendedAction
from tests.conftest import ConstantDetector, FixedSequenceGenerator, PassthroughExtractor


# --- abstractness ----------------------------------------------------------
@pytest.mark.parametrize(
    "interface",
    [BaseDetector, BaseGenerator, BaseFeatureExtractor, BaseAttackIdentifier, BaseEvaluator],
)
def test_interfaces_cannot_be_instantiated(interface):
    with pytest.raises(TypeError):
        interface()


# --- detector --------------------------------------------------------------
def test_detector_subclass_fits_and_scores():
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    y = np.array([0, 1, 0])
    det = ConstantDetector(0.42).fit(X, y)
    assert det.is_fitted is True
    assert det.feature_names == ["a"]
    assert det.score(X).tolist() == [0.42, 0.42, 0.42]


def test_detector_predict_builds_contract_objects():
    X = pd.DataFrame({"a": [1.0, 2.0]})
    det = ConstantDetector(0.97).fit(X, np.array([0, 1]))
    outputs = det.predict(X, ["t1", "t2"])
    assert [o.transaction_id for o in outputs] == ["t1", "t2"]
    assert outputs[0].recommended_action is RecommendedAction.DECLINE
    assert outputs[0].predicted_label is FraudLabel.FRAUD
    assert outputs[0].model_version == "constant-v0"
    assert outputs[0].policy_version == DEFAULT_ACTION_POLICY.policy_version


def test_detector_predict_before_fit_raises():
    with pytest.raises(NotFittedError):
        ConstantDetector().predict(pd.DataFrame({"a": [1.0]}), ["t1"])


def test_detector_predict_rejects_misaligned_ids():
    X = pd.DataFrame({"a": [1.0, 2.0]})
    det = ConstantDetector().fit(X, np.array([0, 1]))
    with pytest.raises(ValueError, match="does not match"):
        det.predict(X, ["only-one"])


# --- action policy ---------------------------------------------------------
@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.00, RecommendedAction.APPROVE),
        (0.49, RecommendedAction.APPROVE),
        (0.50, RecommendedAction.STEP_UP),
        (0.79, RecommendedAction.STEP_UP),
        (0.80, RecommendedAction.REVIEW),
        (0.94, RecommendedAction.REVIEW),
        (0.95, RecommendedAction.DECLINE),
        (1.00, RecommendedAction.DECLINE),
    ],
)
def test_action_policy_bands(score, expected):
    assert DEFAULT_ACTION_POLICY.action_for(score) is expected


def test_action_policy_rejects_non_monotonic_thresholds():
    with pytest.raises(ValueError, match="step_up_at <= review_at"):
        ActionPolicy(step_up_at=0.9, review_at=0.5, decline_at=0.95)


def test_action_policy_rejects_out_of_range_score():
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        DEFAULT_ACTION_POLICY.action_for(1.5)


# --- generator -------------------------------------------------------------
def test_generator_subclass_produces_provenanced_batch(blueprint):
    config = GenerationConfig(seed=7, n_scenarios=3, split=DataSplit.TRAIN)
    batch = FixedSequenceGenerator().generate(blueprint, config)

    assert len(batch) == 6  # 3 scenarios x 2 steps
    assert batch.seed == 7
    assert batch.blueprint_id == blueprint.attack_id
    assert batch.attack_family is blueprint.attack_family
    assert batch.generator_name == "fixed-sequence"
    assert len(batch.scenario_ids) == 3
    assert all(t.is_synthetic for t in batch.transactions)
    assert all(t.split is DataSplit.TRAIN for t in batch.transactions)
    assert all(t.blueprint_id == blueprint.attack_id for t in batch.transactions)


def test_generator_respects_max_transactions(blueprint):
    batch = FixedSequenceGenerator().generate(
        blueprint, GenerationConfig(n_scenarios=5, max_transactions=3)
    )
    assert len(batch) == 3


def test_generator_stream_yields_transactions(blueprint):
    stream = FixedSequenceGenerator().stream(blueprint, GenerationConfig(n_scenarios=1))
    assert len(list(stream)) == 2


def test_generator_is_deterministic_for_a_seed(blueprint):
    config = GenerationConfig(seed=99, n_scenarios=2)
    first = FixedSequenceGenerator().generate(blueprint, config).to_records()
    second = FixedSequenceGenerator().generate(blueprint, config).to_records()
    assert first == second


def test_generator_rejects_unsupported_family(blueprint):
    class NarrowGenerator(FixedSequenceGenerator):
        supported_families = ("synthetic_identity_bustout",)

    with pytest.raises(BlueprintNotSupportedError):
        NarrowGenerator().generate(blueprint, GenerationConfig())


# --- feature extractor -----------------------------------------------------
def test_feature_extractor_subclass_round_trips(blueprint):
    batch = FixedSequenceGenerator().generate(blueprint, GenerationConfig(n_scenarios=2))
    extractor = PassthroughExtractor()
    frame = extractor.fit_transform(batch.transactions)
    assert list(frame.columns) == extractor.feature_names
    assert len(frame) == len(batch)


def test_extracted_matrix_feeds_the_detector(blueprint):
    batch = FixedSequenceGenerator().generate(blueprint, GenerationConfig(n_scenarios=2))
    X = PassthroughExtractor().fit_transform(batch.transactions)
    y = np.array([int(t.is_fraud) for t in batch.transactions])
    outputs = (
        ConstantDetector().fit(X, y).predict(X, [t.transaction_id for t in batch.transactions])
    )
    assert len(outputs) == len(batch)


# --- identifier ------------------------------------------------------------
def test_identifier_subclass_returns_blueprints(blueprint):
    class EchoIdentifier(BaseAttackIdentifier):
        name = "echo"

        def propose(self, context):
            return [blueprint][: context.max_blueprints]

    proposals = EchoIdentifier().propose(IdentificationContext(max_blueprints=1))
    assert len(proposals) == 1
    assert proposals[0].attack_id == blueprint.attack_id
