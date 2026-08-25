"""`XGBoostDetector`: interface compliance, training, persistence, reproducibility."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from aegis.defend import ActionPolicy, BaseDetector, NotFittedError
from aegis.defend.xgboost_detector import XGBoostDetector
from aegis.features import TemporalBaselineFeatureExtractor
from aegis.shared.contracts import Transaction
from aegis.shared.enums import FraudLabel, RecommendedAction, TransactionType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def tmp_model_dir() -> Iterator[Path]:
    path = Path("data/interim") / f"xgb-test-{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _fixture_frame(n: int = 80, seed: int = 0):
    rng = np.random.default_rng(seed)
    txns = []
    for i in range(n):
        is_fraud = i % 6 == 0
        amount = 5000.0 + rng.normal(0, 200) if is_fraud else 80.0 + rng.normal(0, 20)
        txns.append(
            Transaction(
                transaction_id=f"t{i}",
                timestamp=T0 + timedelta(minutes=i * 5),
                source_account_id=f"src{i % 10}",
                destination_account_id=f"dst{i % 7}",
                amount=max(1.0, amount),
                transaction_type=TransactionType.TRANSFER,
                source_balance_before=2000.0,
                source_balance_after=2000.0 - amount,
                destination_balance_before=100.0,
                destination_balance_after=100.0 + amount,
                label=FraudLabel.FRAUD if is_fraud else FraudLabel.LEGITIMATE,
            )
        )
    X = TemporalBaselineFeatureExtractor().fit_transform(txns)
    y = np.array([int(t.is_fraud) for t in txns])
    return X, y, txns


# --- interface compliance ----------------------------------------------
def test_is_a_base_detector_subclass():
    assert issubclass(XGBoostDetector, BaseDetector)


def test_score_before_fit_raises():
    X, _, _ = _fixture_frame(5)
    with pytest.raises(NotFittedError):
        XGBoostDetector().score(X)


def test_explain_before_fit_raises():
    X, _, _ = _fixture_frame(5)
    with pytest.raises(NotFittedError):
        XGBoostDetector().explain(X)


def test_predict_before_fit_raises():
    X, _, txns = _fixture_frame(5)
    with pytest.raises(NotFittedError):
        XGBoostDetector().predict(X, [t.transaction_id for t in txns])


# --- training and scoring ---------------------------------------------
def test_fit_sets_feature_names_and_fitted_flag():
    X, y, _ = _fixture_frame()
    detector = XGBoostDetector(seed=1, num_boost_round=20).fit(X, y)
    assert detector.is_fitted is True
    assert detector.feature_names == list(X.columns)


def test_scores_are_in_unit_interval():
    X, y, _ = _fixture_frame()
    detector = XGBoostDetector(seed=1, num_boost_round=20).fit(X, y)
    scores = detector.score(X)
    assert scores.shape == (len(X),)
    assert bool(np.all(scores >= 0.0))
    assert bool(np.all(scores <= 1.0))


def test_score_does_not_mutate_input():
    X, y, _ = _fixture_frame()
    detector = XGBoostDetector(seed=1, num_boost_round=20).fit(X, y)
    before = X.copy(deep=True)
    detector.score(X)
    assert X.equals(before)


def test_scale_pos_weight_is_auto_computed_from_imbalance():
    X, y, _ = _fixture_frame(n=90)  # 1-in-6 fraud
    detector = XGBoostDetector(seed=1, num_boost_round=10).fit(X, y)
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    assert detector.scale_pos_weight == pytest.approx(n_neg / n_pos)


def test_explain_returns_ranked_signal_contributions():
    X, y, _ = _fixture_frame()
    detector = XGBoostDetector(seed=1, num_boost_round=20).fit(X, y)
    signals = detector.explain(X.iloc[:3])
    assert len(signals) == 3
    for row_signals in signals:
        assert len(row_signals) == len(X.columns)
        ranks = [s.rank for s in row_signals if s.rank is not None]
        assert len(ranks) == len(row_signals)
        assert ranks == sorted(ranks)
        assert all(s.name in set(X.columns) for s in row_signals)


# --- threshold / action behavior ----------------------------------------
def test_predict_respects_custom_action_policy():
    X, y, txns = _fixture_frame()
    strict_policy = ActionPolicy(
        step_up_at=0.05, review_at=0.10, decline_at=0.15, label_threshold=0.05
    )
    detector = XGBoostDetector(action_policy=strict_policy, seed=1, num_boost_round=20).fit(X, y)
    outputs = detector.predict(X, [t.transaction_id for t in txns])
    # A very permissive threshold should flag essentially everyone past approve.
    flagged_actions = (
        RecommendedAction.STEP_UP,
        RecommendedAction.REVIEW,
        RecommendedAction.DECLINE,
    )
    assert all(o.recommended_action is not None for o in outputs)
    assert any(o.recommended_action in flagged_actions for o in outputs)
    assert all(o.threshold == pytest.approx(0.05) for o in outputs)
    assert all(o.model_version == detector.model_version for o in outputs)


def test_predict_output_length_matches_input():
    X, y, txns = _fixture_frame()
    detector = XGBoostDetector(seed=1, num_boost_round=20).fit(X, y)
    ids = [t.transaction_id for t in txns]
    outputs = detector.predict(X, ids)
    assert len(outputs) == len(txns)
    assert [o.transaction_id for o in outputs] == ids


# --- save / load ---------------------------------------------------------
def test_save_before_fit_raises(tmp_model_dir):
    with pytest.raises(NotFittedError):
        XGBoostDetector().save(str(tmp_model_dir / "model"))


def test_save_load_round_trip_preserves_scores(tmp_model_dir):
    X, y, _ = _fixture_frame()
    detector = XGBoostDetector(seed=7, num_boost_round=25).fit(X, y)
    original_scores = detector.score(X)

    artifact_path = tmp_model_dir / "model"
    detector.save(str(artifact_path))
    loaded = XGBoostDetector.load(str(artifact_path))

    assert loaded.is_fitted is True
    assert loaded.feature_names == detector.feature_names
    assert loaded.model_version == detector.model_version
    np.testing.assert_allclose(loaded.score(X), original_scores)


def test_save_load_preserves_action_policy(tmp_model_dir):
    X, y, _ = _fixture_frame()
    policy = ActionPolicy(step_up_at=0.3, review_at=0.6, decline_at=0.9, label_threshold=0.3)
    detector = XGBoostDetector(action_policy=policy, seed=3, num_boost_round=15).fit(X, y)
    artifact_path = tmp_model_dir / "model"
    detector.save(str(artifact_path))
    loaded = XGBoostDetector.load(str(artifact_path))
    assert loaded.action_policy.step_up_at == pytest.approx(0.3)
    assert loaded.action_policy.decline_at == pytest.approx(0.9)


# --- reproducibility -----------------------------------------------------
def test_same_seed_and_data_produce_identical_scores():
    X, y, _ = _fixture_frame()
    first = XGBoostDetector(seed=42, num_boost_round=20).fit(X, y).score(X)
    second = XGBoostDetector(seed=42, num_boost_round=20).fit(X, y).score(X)
    np.testing.assert_array_equal(first, second)


def test_model_version_is_stable_and_specific():
    detector = XGBoostDetector(seed=20260101)
    assert "20260101" in detector.model_version


# --- memory-safe QuantileDMatrix equivalence -----------------------------
def test_quantile_dmatrix_matches_plain_dmatrix_for_hist():
    """`fit()` uses QuantileDMatrix for tree_method=hist (see xgboost_detector.py).

    This proves that choice is a pure execution-level optimization: training
    the identical data/params/seed through a plain `xgb.DMatrix` and through
    `xgb.QuantileDMatrix` must produce the same predictions.
    """
    import xgboost as xgb

    X, y, _ = _fixture_frame(n=120, seed=3)
    feature_names = list(X.columns)
    params = {
        "max_depth": 4,
        "eta": 0.1,
        "objective": "binary:logistic",
        "tree_method": "hist",
        "seed": 5,
        "scale_pos_weight": 1.0,
    }

    dtrain_plain = xgb.DMatrix(X, label=y, feature_names=feature_names)
    booster_plain = xgb.train(params, dtrain_plain, num_boost_round=15)

    dtrain_quantile = xgb.QuantileDMatrix(X, label=y, feature_names=feature_names)
    booster_quantile = xgb.train(params, dtrain_quantile, num_boost_round=15)

    dtest = xgb.DMatrix(X, feature_names=feature_names)
    np.testing.assert_allclose(
        booster_plain.predict(dtest), booster_quantile.predict(dtest), rtol=1e-5, atol=1e-6
    )


def test_fit_actually_uses_quantile_dmatrix_for_hist_tree_method(monkeypatch):
    """Regression guard: `fit()` must route through QuantileDMatrix, not silently
    fall back to plain DMatrix, for the approved default `tree_method=hist`."""
    import xgboost as xgb

    X, y, _ = _fixture_frame(n=40)
    calls = {"quantile": 0, "plain": 0}
    real_quantile_dmatrix = xgb.QuantileDMatrix
    real_dmatrix = xgb.DMatrix

    def spy_quantile(*args, **kwargs):
        calls["quantile"] += 1
        return real_quantile_dmatrix(*args, **kwargs)

    def spy_plain(*args, **kwargs):
        calls["plain"] += 1
        return real_dmatrix(*args, **kwargs)

    monkeypatch.setattr(xgb, "QuantileDMatrix", spy_quantile)
    monkeypatch.setattr(xgb, "DMatrix", spy_plain)

    XGBoostDetector(seed=1, num_boost_round=10).fit(X, y)
    assert calls["quantile"] == 1
    assert calls["plain"] == 0
