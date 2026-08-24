"""Dependency-free metric math, checked against hand-computed examples.

`y_true = [1, 0, 1, 0, 0]`, `scores = [0.9, 0.8, 0.7, 0.6, 0.1]` is worked by
hand in the module docstring's neighbouring comments so the expected values
here are independently verifiable, not just "whatever the code produces".
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from aegis.defend.metrics import (
    average_precision,
    build_evaluation_result,
    compute_classification_metrics,
    measure_scoring_latency,
    recall_at_fpr,
    roc_auc,
    tune_threshold_for_f1,
)
from aegis.shared.enums import DataSplit, EvaluationProtocol
from tests.conftest import ConstantDetector

Y = np.array([1, 0, 1, 0, 0])
SCORES = np.array([0.9, 0.8, 0.7, 0.6, 0.1])


# --- roc_auc -----------------------------------------------------------
def test_roc_auc_matches_hand_computation():
    # positives=[0.9,0.7] negatives=[0.8,0.6,0.1]; rank-sum of positives=3+5=8
    # auc = (8 - 2*3/2) / (2*3) = 5/6
    assert roc_auc(Y, SCORES) == pytest.approx(5 / 6)


def test_roc_auc_none_when_one_class_absent():
    assert roc_auc(np.array([0, 0, 0]), np.array([0.1, 0.2, 0.3])) is None
    assert roc_auc(np.array([1, 1, 1]), np.array([0.1, 0.2, 0.3])) is None


def test_roc_auc_handles_tied_scores():
    y = np.array([1, 0, 1, 0])
    scores = np.array([0.5, 0.5, 0.5, 0.5])
    assert roc_auc(y, scores) == pytest.approx(0.5)


# --- average_precision --------------------------------------------------
def test_average_precision_matches_hand_computation():
    # AP = (0.5-0)*1.0 + (0.5-0.5)*0.5 + (1.0-0.5)*(2/3) + 0 + 0 = 0.5 + 1/3
    assert average_precision(Y, SCORES) == pytest.approx(0.5 + 1 / 3, abs=1e-6)


def test_average_precision_none_with_no_positives():
    assert average_precision(np.array([0, 0]), np.array([0.1, 0.9])) is None


def test_average_precision_perfect_ranking_is_one():
    y = np.array([1, 1, 0, 0])
    scores = np.array([0.9, 0.8, 0.2, 0.1])
    assert average_precision(y, scores) == pytest.approx(1.0)


# --- recall_at_fpr -------------------------------------------------------
def test_recall_at_fpr_zero_budget():
    assert recall_at_fpr(Y, SCORES, 0.0) == pytest.approx(0.5)


def test_recall_at_fpr_wider_budget():
    assert recall_at_fpr(Y, SCORES, 0.34) == pytest.approx(1.0)


def test_recall_at_fpr_zero_when_no_positives():
    assert recall_at_fpr(np.array([0, 0]), np.array([0.1, 0.9]), 0.01) == 0.0


# --- threshold tuning ------------------------------------------------------
def test_tune_threshold_for_f1_picks_perfect_separator():
    y = np.array([1, 1, 0, 0])
    scores = np.array([0.9, 0.4, 0.3, 0.1])
    assert tune_threshold_for_f1(y, scores) == pytest.approx(0.4)


def test_tune_threshold_for_f1_empty_scores_returns_default():
    assert tune_threshold_for_f1(np.array([]), np.array([])) == 0.5


# --- compute_classification_metrics ----------------------------------------
def test_compute_classification_metrics_confusion_counts():
    metrics = compute_classification_metrics(Y, SCORES, threshold=0.65)
    # threshold 0.65 -> predicted [1,1,1,0,0] vs true [1,0,1,0,0]
    assert metrics.counts.true_positives == 2
    assert metrics.counts.false_positives == 1
    assert metrics.counts.true_negatives == 2
    assert metrics.counts.false_negatives == 0
    assert metrics.precision == pytest.approx(2 / 3)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.support == 5
    assert metrics.positive_support == 2
    assert set(metrics.recall_at_fixed_fpr) == {"0.001", "0.005", "0.01"}


def test_compute_classification_metrics_all_negative_predictions_has_zero_precision():
    metrics = compute_classification_metrics(Y, SCORES, threshold=1.0)
    assert metrics.counts.true_positives == 0
    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.f1 == 0.0


# --- build_evaluation_result -------------------------------------------
def test_build_evaluation_result_round_trips_protocol_and_split():
    result = build_evaluation_result(
        evaluation_id="eval-1",
        y_true=Y,
        scores=SCORES,
        threshold=0.5,
        model_version="test-model-v0",
        dataset_id="fixture-dataset",
        split=DataSplit.TEST,
        protocol=EvaluationProtocol.STATIC_HOLDOUT,
        seed=42,
    )
    assert result.protocol is EvaluationProtocol.STATIC_HOLDOUT
    assert result.split is DataSplit.TEST
    assert result.model_version == "test-model-v0"
    assert result.seed == 42
    # Round-trips through the frozen contract's own JSON serialization.
    reloaded = type(result).from_json(result.to_json())
    assert reloaded.evaluation_id == "eval-1"


# --- latency -----------------------------------------------------------
def test_measure_scoring_latency_reports_positive_stats():
    X = pd.DataFrame({"a": np.arange(50, dtype=float)})
    detector = ConstantDetector(0.5).fit(X, np.zeros(50))
    latency = measure_scoring_latency(detector, X, sample_size=10, seed=1)
    assert latency.samples == 10
    assert latency.mean_ms >= 0.0
    assert latency.max_ms is not None
    assert latency.max_ms >= latency.mean_ms


def test_measure_scoring_latency_empty_input():
    X = pd.DataFrame({"a": []})
    detector = ConstantDetector(0.5).fit(X, np.array([]))
    latency = measure_scoring_latency(detector, X)
    assert latency.samples == 0
    assert not math.isnan(latency.mean_ms)
