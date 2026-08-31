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
    threshold_at_fpr_budget,
    tune_threshold_for_f1,
)
from aegis.shared.enums import AttackFamily, DataSplit, EvaluationProtocol
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


# --- brute-force equivalence: the O(n^2) implementation this replaced -------
def _brute_force_tune_threshold_for_f1(y_true: np.ndarray, scores: np.ndarray) -> float:
    """The original O(n * unique_scores) implementation, kept only as a test
    oracle. This is deliberately NOT imported from production code - it is
    what stalled the first real PaySim run for ~90 minutes on a 943k-row
    validation split with no completed artifact to show for it, and it must
    never run again outside a small fixture.
    """
    if len(scores) == 0:
        return 0.5
    candidates = np.unique(scores)
    best_threshold = float(candidates[-1])
    best_f1 = -1.0
    for threshold in candidates:
        predicted = (scores >= threshold).astype(int)
        tp = int(((predicted == 1) & (y_true == 1)).sum())
        fp = int(((predicted == 1) & (y_true == 0)).sum())
        fn = int(((predicted == 0) & (y_true == 1)).sum())
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        if f1 >= best_f1:
            best_f1 = f1
            best_threshold = float(threshold)
    return best_threshold


def _f1_at_threshold(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> float:
    predicted = (scores >= threshold).astype(int)
    tp = int(((predicted == 1) & (y_true == 1)).sum())
    fp = int(((predicted == 1) & (y_true == 0)).sum())
    fn = int(((predicted == 0) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0


@pytest.mark.parametrize(
    ("y_true", "scores"),
    [
        (np.array([1, 0, 1, 0, 0]), np.array([0.9, 0.8, 0.7, 0.6, 0.1])),
        (np.array([1, 1, 0, 0]), np.array([0.9, 0.4, 0.3, 0.1])),
        (np.array([0, 1, 0, 1, 1, 0, 0, 1]), np.array([0.2, 0.9, 0.1, 0.9, 0.5, 0.5, 0.5, 0.3])),
        (np.array([1, 0, 1, 0]), np.array([0.5, 0.5, 0.5, 0.5])),  # all-tied scores
        (np.array([1, 1, 1, 1]), np.array([0.9, 0.1, 0.5, 0.3])),  # all-positive
        (np.array([0, 0, 0, 0]), np.array([0.9, 0.1, 0.5, 0.3])),  # all-negative
        (np.array([1]), np.array([0.7])),  # single row
        (np.random.default_rng(7).integers(0, 2, size=200), np.random.default_rng(7).random(200)),
    ],
)
def test_optimized_threshold_matches_brute_force_exactly(y_true, scores):
    optimized = tune_threshold_for_f1(y_true, scores)
    brute_force = _brute_force_tune_threshold_for_f1(y_true, scores)
    assert optimized == pytest.approx(brute_force)
    # Same threshold implies same F1 by construction, but assert the F1
    # values directly too - a matching threshold with a different F1 would
    # mean the two implementations disagree about what "boundary" means.
    assert _f1_at_threshold(y_true, scores, optimized) == pytest.approx(
        _f1_at_threshold(y_true, scores, brute_force)
    )


def test_optimized_threshold_duplicate_scores_are_grouped_as_one_boundary():
    # Three rows share score 0.5; the threshold must never land strictly
    # between them (that boundary does not exist as a real decision point).
    y = np.array([1, 0, 1, 0, 1])
    scores = np.array([0.9, 0.5, 0.5, 0.5, 0.1])
    optimized = tune_threshold_for_f1(y, scores)
    assert optimized in set(np.unique(scores).tolist())


def test_optimized_threshold_all_positive_picks_lowest_score_for_full_recall():
    y = np.array([1, 1, 1])
    scores = np.array([0.8, 0.5, 0.2])
    # With no negatives, precision is always 1.0, so F1 is maximized at
    # whichever threshold captures every positive - the minimum score.
    assert tune_threshold_for_f1(y, scores) == pytest.approx(0.2)


def test_optimized_threshold_all_negative_ties_favor_highest_score():
    y = np.array([0, 0, 0])
    scores = np.array([0.8, 0.5, 0.2])
    # No positives exist, so F1 is 0 at every threshold - the tie-break rule
    # (favor the higher threshold) determines the result, matching the
    # brute-force oracle exactly.
    assert tune_threshold_for_f1(y, scores) == pytest.approx(0.8)
    assert tune_threshold_for_f1(y, scores) == pytest.approx(
        _brute_force_tune_threshold_for_f1(y, scores)
    )


def test_optimized_threshold_single_row_each_class():
    assert tune_threshold_for_f1(np.array([1]), np.array([0.6])) == pytest.approx(0.6)
    assert tune_threshold_for_f1(np.array([0]), np.array([0.6])) == pytest.approx(0.6)


def test_optimized_threshold_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        tune_threshold_for_f1(np.array([1, 0, 1]), np.array([0.5, 0.5]))


def test_optimized_threshold_is_subquadratic_on_a_large_near_continuous_split():
    """Regression guard for the actual production incident: this must finish
    in well under a second, not the ~90 minutes the O(n^2) version needed at
    real validation-split scale."""
    import time

    rng = np.random.default_rng(20260101)
    n = 50_000
    y_true = (rng.random(n) < 0.01).astype(int)
    scores = rng.random(n).astype(np.float32)  # near-continuous, ~all unique

    start = time.perf_counter()
    threshold = tune_threshold_for_f1(y_true, scores)
    elapsed = time.perf_counter() - start

    assert 0.0 <= threshold <= 1.0
    assert elapsed < 2.0


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


def test_build_evaluation_result_accepts_leave_one_attack_family_out():
    result = build_evaluation_result(
        evaluation_id="loafo-eval-1",
        y_true=Y,
        scores=SCORES,
        threshold=0.5,
        model_version="test-model-v0",
        dataset_id="fixture-dataset",
        split=DataSplit.TEST,
        protocol=EvaluationProtocol.LEAVE_ONE_ATTACK_FAMILY_OUT,
        held_out_family=AttackFamily.MULE_NETWORK_STRUCTURING,
    )
    assert result.protocol is EvaluationProtocol.LEAVE_ONE_ATTACK_FAMILY_OUT
    assert result.held_out_family is AttackFamily.MULE_NETWORK_STRUCTURING


def test_build_evaluation_result_leave_one_attack_family_out_requires_held_out_family():
    with pytest.raises(ValueError, match="held_out_family"):
        build_evaluation_result(
            evaluation_id="loafo-eval-missing",
            y_true=Y,
            scores=SCORES,
            threshold=0.5,
            model_version="test-model-v0",
            dataset_id="fixture-dataset",
            split=DataSplit.TEST,
            protocol=EvaluationProtocol.LEAVE_ONE_ATTACK_FAMILY_OUT,
        )


def test_build_evaluation_result_default_static_holdout_still_omits_held_out_family():
    """Regression guard: the new optional param must not change any existing caller's output."""
    result = build_evaluation_result(
        evaluation_id="eval-plain",
        y_true=Y,
        scores=SCORES,
        threshold=0.5,
        model_version="test-model-v0",
        dataset_id="fixture-dataset",
        split=DataSplit.TEST,
    )
    assert result.protocol is EvaluationProtocol.STATIC_HOLDOUT
    assert result.held_out_family is None
    assert result.round_index is None


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


# --- threshold_at_fpr_budget -------------------------------------------


def _brute_force_threshold_at_fpr_budget(
    y_true: np.ndarray, scores: np.ndarray, budget: float
) -> float:
    """Sweep every observed score, keep the affordable one with the best recall.

    Independent O(n^2) restatement of the rule, used to prove the vectorized
    implementation rather than asserting its output by inspection - the same
    technique `_brute_force_tune_threshold_for_f1` uses above.
    """
    best_threshold = float(np.nextafter(float(np.max(scores)), np.inf))
    best_recall = -1.0
    for candidate in sorted({float(s) for s in scores}, reverse=True):
        predicted = (scores >= candidate).astype(int)
        fp = int(((predicted == 1) & (y_true == 0)).sum())
        tn = int(((predicted == 0) & (y_true == 0)).sum())
        tp = int(((predicted == 1) & (y_true == 1)).sum())
        fn = int(((predicted == 0) & (y_true == 1)).sum())
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        if fpr > budget:
            continue
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        # Strict `>` keeps the first (highest) threshold on ties, matching the
        # documented tie-break.
        if recall > best_recall:
            best_recall = recall
            best_threshold = candidate
    return best_threshold


@pytest.mark.parametrize(
    ("y_true", "scores", "budget"),
    [
        (np.array([1, 0, 1, 0, 0]), np.array([0.9, 0.8, 0.7, 0.6, 0.1]), 0.0),
        (np.array([1, 0, 1, 0, 0]), np.array([0.9, 0.8, 0.7, 0.6, 0.1]), 0.34),
        (np.array([1, 0, 1, 0, 0]), np.array([0.9, 0.8, 0.7, 0.6, 0.1]), 1.0),
        (np.array([1, 1, 0, 0]), np.array([0.9, 0.4, 0.3, 0.1]), 0.5),
        (np.array([1, 0, 1, 0]), np.array([0.5, 0.5, 0.5, 0.5]), 0.5),  # all-tied
        (np.array([1, 1, 1, 1]), np.array([0.9, 0.1, 0.5, 0.3]), 0.0),  # no negatives
        (np.array([0, 0, 0, 0]), np.array([0.9, 0.1, 0.5, 0.3]), 0.25),  # no positives
        (
            np.random.default_rng(11).integers(0, 2, size=200),
            np.random.default_rng(11).random(200),
            0.05,
        ),
    ],
)
def test_threshold_at_fpr_budget_matches_brute_force_exactly(y_true, scores, budget):
    assert threshold_at_fpr_budget(y_true, scores, budget) == pytest.approx(
        _brute_force_threshold_at_fpr_budget(y_true, scores, budget)
    )


@pytest.mark.parametrize("budget", [0.0, 0.001, 0.01, 0.05, 0.2])
def test_threshold_at_fpr_budget_never_breaches_the_budget(budget):
    rng = np.random.default_rng(23)
    y_true = (rng.random(2_000) < 0.02).astype(int)
    scores = np.clip(rng.random(2_000) + y_true * 0.4, 0.0, 1.0)

    threshold = threshold_at_fpr_budget(y_true, scores, budget)
    predicted = (scores >= threshold).astype(int)
    fp = int(((predicted == 1) & (y_true == 0)).sum())
    tn = int(((predicted == 0) & (y_true == 0)).sum())
    achieved_fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    assert achieved_fpr <= budget + 1e-12


def test_threshold_at_fpr_budget_recovers_the_documented_recall_at_that_budget():
    """The chosen threshold's recall must equal `recall_at_fpr` for the same budget.

    This is the property the whole change rests on: the reported
    `recall_at_fixed_fpr` figure is only honest if the model is actually
    *operated* at a threshold that achieves it.
    """
    rng = np.random.default_rng(29)
    y_true = (rng.random(5_000) < 0.03).astype(int)
    scores = np.clip(rng.random(5_000) + y_true * 0.5, 0.0, 1.0)

    for budget in (0.001, 0.005, 0.01, 0.05):
        threshold = threshold_at_fpr_budget(y_true, scores, budget)
        predicted = (scores >= threshold).astype(int)
        tp = int(((predicted == 1) & (y_true == 1)).sum())
        fn = int(((predicted == 0) & (y_true == 1)).sum())
        achieved_recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        assert achieved_recall == pytest.approx(recall_at_fpr(y_true, scores, budget))


def test_threshold_at_fpr_budget_beats_f1_tuning_on_recall_at_a_real_budget():
    """The motivating result, as an executable assertion.

    On an imbalanced split resembling PaySim's test set, the F1-optimal
    threshold sacrifices substantial recall relative to operating at an
    explicit 0.5% false-positive budget.
    """
    rng = np.random.default_rng(31)
    y_true = (rng.random(20_000) < 0.004).astype(int)
    scores = np.clip(rng.normal(0.3, 0.15, 20_000) + y_true * 0.45, 0.0, 1.0)

    f1_threshold = tune_threshold_for_f1(y_true, scores)
    budget_threshold = threshold_at_fpr_budget(y_true, scores, 0.005)

    def recall_of(threshold: float) -> float:
        predicted = (scores >= threshold).astype(int)
        tp = int(((predicted == 1) & (y_true == 1)).sum())
        fn = int(((predicted == 0) & (y_true == 1)).sum())
        return tp / (tp + fn) if (tp + fn) > 0 else 0.0

    assert budget_threshold < f1_threshold
    assert recall_of(budget_threshold) > recall_of(f1_threshold)


def test_threshold_at_fpr_budget_empty_scores_returns_default():
    assert threshold_at_fpr_budget(np.array([]), np.array([]), 0.01) == 0.5


def test_threshold_at_fpr_budget_flags_nothing_when_budget_is_unaffordable():
    """Top-scoring row is a false positive and the budget cannot absorb it."""
    y_true = np.array([0, 1, 1])
    scores = np.array([0.9, 0.8, 0.7])
    threshold = threshold_at_fpr_budget(y_true, scores, 0.0)
    assert threshold > 0.9
    assert not (scores >= threshold).any()


def test_threshold_at_fpr_budget_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        threshold_at_fpr_budget(np.array([1, 0]), np.array([0.5]), 0.01)


@pytest.mark.parametrize("budget", [-0.1, 1.5])
def test_threshold_at_fpr_budget_rejects_out_of_range_budget(budget):
    with pytest.raises(ValueError, match="false-positive rate"):
        threshold_at_fpr_budget(np.array([1, 0]), np.array([0.9, 0.1]), budget)
