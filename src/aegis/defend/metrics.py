"""Metric computation for the Blue Team baseline, dependency-free.

Deliberately implemented with only `numpy`, not `scikit-learn`: the project
adds runtime dependencies sparingly (AGENTS.md SS5), and `xgboost` is already
the one new dependency this phase needs. ROC-AUC uses the Mann-Whitney
rank-sum identity; PR-AUC uses the same step-function definition as
`sklearn.metrics.average_precision_score`. Both are covered by tests against
hand-computed examples in `tests/test_defend_metrics.py`.

This module produces `EvaluationResult` instances but is **not** a
`BaseEvaluator` implementation - `src/aegis/evaluate/` is jointly owned and
out of scope for this task. Every result built here still declares its
`EvaluationProtocol`, per docs/EVALUATION_RULES.md.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from aegis.shared.contracts import (
    ClassificationMetrics,
    ConfusionCounts,
    EvaluationResult,
    LatencyMetrics,
)
from aegis.shared.enums import DataSplit, EvaluationProtocol

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

    from aegis.defend.base import BaseDetector

DEFAULT_FPR_BUDGETS: tuple[float, ...] = (0.001, 0.005, 0.01)
"""Agreed fixed FPR budgets, per docs/EVALUATION_RULES.md SS'Additional standing requirements'."""


def roc_auc(y_true: np.ndarray, scores: np.ndarray) -> float | None:
    """ROC-AUC via the Mann-Whitney U rank-sum identity. `None` if one class is absent."""
    positives = scores[y_true == 1]
    negatives = scores[y_true == 0]
    if len(positives) == 0 or len(negatives) == 0:
        return None

    combined = np.concatenate([positives, negatives])
    order = np.argsort(combined, kind="mergesort")
    ranks = np.empty(len(combined), dtype=float)
    ranks[order] = np.arange(1, len(combined) + 1, dtype=float)

    sorted_values = combined[order]
    sorted_ranks = ranks[order]
    i = 0
    n = len(sorted_values)
    while i < n:
        j = i + 1
        while j < n and sorted_values[j] == sorted_values[i]:
            j += 1
        if j - i > 1:
            sorted_ranks[i:j] = sorted_ranks[i:j].mean()
        i = j
    ranks[order] = sorted_ranks

    n_pos, n_neg = len(positives), len(negatives)
    rank_sum_pos = ranks[:n_pos].sum()
    auc = (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return float(auc)


def _pr_curve_points(
    y_true: np.ndarray, scores: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Precision, recall, FPR at every distinct-score cutoff, threshold descending."""
    order = np.argsort(-scores, kind="mergesort")
    y_sorted = y_true[order]
    scores_sorted = scores[order]

    n = len(scores_sorted)
    distinct = np.where(np.diff(scores_sorted) != 0)[0]
    cutoffs = np.r_[distinct, n - 1] if n > 0 else np.array([], dtype=int)

    cum_pos = np.cumsum(y_sorted)
    tps = cum_pos[cutoffs] if n > 0 else np.array([])
    predicted_positive = cutoffs + 1
    fps = predicted_positive - tps

    n_pos = float(y_sorted.sum())
    n_neg = float(n - n_pos)

    precision = np.divide(
        tps,
        predicted_positive,
        out=np.zeros_like(tps, dtype=float),
        where=predicted_positive > 0,
    )
    recall = tps / n_pos if n_pos > 0 else np.zeros_like(tps, dtype=float)
    fpr = fps / n_neg if n_neg > 0 else np.zeros_like(fps, dtype=float)
    return precision, recall, fpr


def average_precision(y_true: np.ndarray, scores: np.ndarray) -> float | None:
    """PR-AUC, sklearn's step-function definition: sum((R_n - R_{n-1}) * P_n)."""
    if y_true.sum() == 0:
        return None
    precision, recall, _ = _pr_curve_points(y_true, scores)
    recall_prev = np.concatenate(([0.0], recall[:-1]))
    return float(np.sum((recall - recall_prev) * precision))


def recall_at_fpr(y_true: np.ndarray, scores: np.ndarray, budget: float) -> float:
    """Highest recall achievable while false-positive rate stays at or below `budget`."""
    if y_true.sum() == 0:
        return 0.0
    _, recall, fpr = _pr_curve_points(y_true, scores)
    mask = fpr <= budget
    if not mask.any():
        return 0.0
    return float(recall[mask].max())


def tune_threshold_for_f1(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Pick the score threshold maximizing F1 on the given (validation-only) data.

    Candidates are the observed score values themselves, so the search is
    exact rather than grid-approximated. Ties on the best F1 favor the
    *higher* threshold (fewer false positives).
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


def compute_classification_metrics(
    y_true: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    fpr_budgets: Sequence[float] = DEFAULT_FPR_BUDGETS,
) -> ClassificationMetrics:
    """Assemble `ClassificationMetrics` at a fixed operating point plus threshold-free areas."""
    predicted = (scores >= threshold).astype(int)
    tp = int(((predicted == 1) & (y_true == 1)).sum())
    fp = int(((predicted == 1) & (y_true == 0)).sum())
    tn = int(((predicted == 0) & (y_true == 0)).sum())
    fn = int(((predicted == 0) & (y_true == 1)).sum())

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr_value = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr_value = fn / (fn + tp) if (fn + tp) > 0 else None
    alert_rate = float(predicted.mean()) if len(predicted) > 0 else None

    return ClassificationMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        pr_auc=average_precision(y_true, scores),
        roc_auc=roc_auc(y_true, scores),
        false_positive_rate=fpr_value,
        false_negative_rate=fnr_value,
        recall_at_fixed_fpr={
            str(budget): recall_at_fpr(y_true, scores, budget) for budget in fpr_budgets
        },
        alert_rate=alert_rate,
        threshold=threshold,
        counts=ConfusionCounts(
            true_positives=tp, false_positives=fp, true_negatives=tn, false_negatives=fn
        ),
        support=len(y_true),
        positive_support=int(y_true.sum()),
    )


def measure_scoring_latency(
    detector: BaseDetector, X: pd.DataFrame, *, sample_size: int = 200, seed: int = 20260101
) -> LatencyMetrics:
    """Single-row scoring latency over a deterministic sample, in milliseconds."""
    n = len(X)
    if n == 0:
        return LatencyMetrics(mean_ms=0.0, samples=0)
    rng = np.random.default_rng(seed)
    idx = rng.choice(n, size=min(sample_size, n), replace=False)

    samples_ms: list[float] = []
    for i in idx:
        row = X.iloc[[i]]
        start = time.perf_counter()
        detector.score(row)
        samples_ms.append((time.perf_counter() - start) * 1000.0)

    arr = np.array(samples_ms)
    return LatencyMetrics(
        mean_ms=float(arr.mean()),
        p50_ms=float(np.percentile(arr, 50)),
        p95_ms=float(np.percentile(arr, 95)),
        p99_ms=float(np.percentile(arr, 99)),
        max_ms=float(arr.max()),
        samples=len(arr),
    )


def build_evaluation_result(
    *,
    evaluation_id: str,
    y_true: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    model_version: str,
    dataset_id: str,
    split: DataSplit,
    protocol: EvaluationProtocol = EvaluationProtocol.STATIC_HOLDOUT,
    latency: LatencyMetrics | None = None,
    fpr_budgets: Sequence[float] = DEFAULT_FPR_BUDGETS,
    seed: int | None = None,
    notes: str = "",
) -> EvaluationResult:
    """Build a complete, protocol-tagged `EvaluationResult` for one split."""
    overall = compute_classification_metrics(y_true, scores, threshold, fpr_budgets)
    return EvaluationResult(
        evaluation_id=evaluation_id,
        protocol=protocol,
        model_version=model_version,
        dataset_id=dataset_id,
        split=split,
        overall=overall,
        latency=latency,
        seed=seed,
        notes=notes,
    )


__all__ = [
    "DEFAULT_FPR_BUDGETS",
    "average_precision",
    "build_evaluation_result",
    "compute_classification_metrics",
    "measure_scoring_latency",
    "recall_at_fpr",
    "roc_auc",
    "tune_threshold_for_f1",
]
