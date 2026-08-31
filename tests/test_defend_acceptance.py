"""The acceptance gate is the loop's only defence against shipping a regression.

`submission/artifacts/` records two hardening rounds that both left the
detector below the untouched baseline, because `harden_defender.py` computed a
regression report and never read it. These tests pin the behaviour that makes
that impossible: a candidate is promoted only when it does not give up ranking
quality or recall at the operating budget, and an *unmeasurable* metric is
treated as a failure rather than waved through.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.defend import AcceptanceCriteria, evaluate_acceptance
from aegis.shared.contracts import ClassificationMetrics, EvaluationResult
from aegis.shared.enums import DataSplit, EvaluationProtocol

BUDGET = 0.005
SUBMITTED_MODELS = Path("submission/artifacts/models")


def _evaluation(
    *,
    model_version: str,
    pr_auc: float | None = 0.90,
    roc_auc: float | None = 0.99,
    recall_at_budget: float | None = 0.93,
    split: DataSplit = DataSplit.TEST,
    budget_key: str | None = None,
) -> EvaluationResult:
    """An evaluation carrying only the fields the gate actually reads.

    `budget_key` overrides how the FPR budget is spelled in the table, so a
    test can reproduce a producer that wrote it with different float
    formatting.
    """
    table: dict[str, float] = {}
    if recall_at_budget is not None:
        table[budget_key or str(BUDGET)] = recall_at_budget
    return EvaluationResult(
        evaluation_id=f"ev-{model_version}",
        protocol=EvaluationProtocol.STATIC_HOLDOUT,
        model_version=model_version,
        split=split,
        overall=ClassificationMetrics(
            precision=0.93,
            recall=0.78,
            f1=0.85,
            false_positive_rate=0.00022,
            pr_auc=pr_auc,
            roc_auc=roc_auc,
            recall_at_fixed_fpr=table,
        ),
    )


def _criteria() -> AcceptanceCriteria:
    return AcceptanceCriteria(operating_fpr_budget=BUDGET)


# -- promotion --------------------------------------------------------------
def test_accepts_a_candidate_that_improves_every_gated_metric():
    decision = evaluate_acceptance(
        incumbent=_evaluation(
            model_version="v1", pr_auc=0.9089, roc_auc=0.9989, recall_at_budget=0.9394
        ),
        candidate=_evaluation(
            model_version="v2", pr_auc=0.9150, roc_auc=0.9991, recall_at_budget=0.9450
        ),
        criteria=_criteria(),
    )
    assert decision.accepted
    assert decision.failures == []
    assert [check.metric for check in decision.checks] == [
        "pr_auc",
        "roc_auc",
        f"recall_at_fpr_{BUDGET}",
    ]
    assert decision.summary.startswith("ACCEPTED")


def test_accepts_a_regression_inside_tolerance():
    """Retraining moves metrics by noise; the gate must not reject on that."""
    criteria = AcceptanceCriteria(operating_fpr_budget=BUDGET, tolerance=0.002)
    decision = evaluate_acceptance(
        incumbent=_evaluation(model_version="v1", pr_auc=0.9089),
        candidate=_evaluation(model_version="v2", pr_auc=0.9080),  # -0.0009
        criteria=criteria,
    )
    assert decision.accepted


# -- rejection --------------------------------------------------------------
def test_rejects_a_pr_auc_drop_past_tolerance():
    """The real v1 -> v2 regression: PR-AUC 0.9089 -> 0.9008, four times tolerance."""
    decision = evaluate_acceptance(
        incumbent=_evaluation(model_version="v1", pr_auc=0.9089),
        candidate=_evaluation(model_version="v2", pr_auc=0.9008),
        criteria=_criteria(),
    )
    assert not decision.accepted
    assert [check.metric for check in decision.failures] == ["pr_auc"]
    assert decision.summary.startswith("REJECTED")
    assert "pr_auc" in decision.summary


def test_rejects_a_recall_drop_at_the_operating_budget():
    decision = evaluate_acceptance(
        incumbent=_evaluation(model_version="v1", recall_at_budget=0.9394),
        candidate=_evaluation(model_version="v2", recall_at_budget=0.9100),
        criteria=_criteria(),
    )
    assert not decision.accepted
    assert [check.metric for check in decision.failures] == [f"recall_at_fpr_{BUDGET}"]


def test_reports_every_failing_metric_not_just_the_first():
    decision = evaluate_acceptance(
        incumbent=_evaluation(
            model_version="v1", pr_auc=0.91, roc_auc=0.999, recall_at_budget=0.94
        ),
        candidate=_evaluation(
            model_version="v2", pr_auc=0.85, roc_auc=0.980, recall_at_budget=0.88
        ),
        criteria=_criteria(),
    )
    assert not decision.accepted
    assert len(decision.failures) == 3


# -- unmeasurable metrics fail closed ---------------------------------------
def test_missing_budget_key_fails_rather_than_passes():
    """A metric that cannot be read is not evidence that nothing regressed.

    Intentional: a candidate whose evaluation lacks the budget must not be
    promoted on the strength of the two metrics that happen to be present.
    """
    decision = evaluate_acceptance(
        incumbent=_evaluation(model_version="v1", recall_at_budget=0.9394),
        candidate=_evaluation(model_version="v2", recall_at_budget=None),
        criteria=_criteria(),
    )
    assert not decision.accepted
    failure = decision.failures[0]
    assert failure.metric == f"recall_at_fpr_{BUDGET}"
    assert failure.candidate is None
    assert failure.delta is None
    assert "not comparable" in failure.detail


def test_missing_pr_auc_fails_rather_than_passes():
    decision = evaluate_acceptance(
        incumbent=_evaluation(model_version="v1", pr_auc=0.9089),
        candidate=_evaluation(model_version="v2", pr_auc=None),
        criteria=_criteria(),
    )
    assert not decision.accepted
    assert decision.failures[0].metric == "pr_auc"


def test_budget_key_is_matched_numerically_not_by_string():
    """Producers have written the key as "0.005" and with other float formatting."""
    decision = evaluate_acceptance(
        incumbent=_evaluation(model_version="v1", recall_at_budget=0.93),
        candidate=_evaluation(model_version="v2", recall_at_budget=0.94, budget_key="0.00500"),
        criteria=_criteria(),
    )
    assert decision.accepted
    recall_check = decision.checks[-1]
    assert recall_check.candidate == 0.94


# -- guards -----------------------------------------------------------------
def test_refuses_to_compare_across_splits():
    """Both sides must be the same untouched test split (EVALUATION_RULES SS3)."""
    with pytest.raises(ValueError, match="one split only"):
        evaluate_acceptance(
            incumbent=_evaluation(model_version="v1", split=DataSplit.VALIDATION),
            candidate=_evaluation(model_version="v2", split=DataSplit.TEST),
            criteria=_criteria(),
        )


def test_disabled_checks_are_not_evaluated():
    criteria = AcceptanceCriteria(
        operating_fpr_budget=BUDGET, require_roc_auc=False, require_recall_at_budget=False
    )
    decision = evaluate_acceptance(
        incumbent=_evaluation(model_version="v1"),
        candidate=_evaluation(model_version="v2", roc_auc=0.10, recall_at_budget=0.10),
        criteria=criteria,
    )
    assert [check.metric for check in decision.checks] == ["pr_auc"]
    assert decision.accepted


def test_decision_serializes_the_full_evidence():
    decision = evaluate_acceptance(
        incumbent=_evaluation(model_version="v1", pr_auc=0.9089),
        candidate=_evaluation(model_version="v2", pr_auc=0.9008),
        criteria=_criteria(),
    )
    payload = decision.to_dict()
    assert payload["accepted"] is False
    assert payload["incumbent_model_version"] == "v1"
    assert payload["candidate_model_version"] == "v2"
    assert payload["failed_metrics"] == ["pr_auc"]
    # every check is recorded, not only the failures -- the artifact should say
    # what was examined, not just what broke
    assert len(payload["checks"]) == 3


# -- the gate against what actually shipped ---------------------------------
def _submitted(name: str) -> EvaluationResult:
    path = SUBMITTED_MODELS / name / "evaluation_test.json"
    if not path.is_file():
        pytest.skip(f"{path} not in this checkout")
    return EvaluationResult.model_validate_json(path.read_text(encoding="utf-8"))


def test_gate_rejects_the_two_regressions_that_actually_shipped():
    """Regression test in the literal sense: v2 and v3 both sit below v1.

    This is the evidence for the claim that the loop now has a gate. If a
    future run makes these pass, the numbers improved and this test should be
    updated deliberately -- not deleted.
    """
    criteria = AcceptanceCriteria(operating_fpr_budget=BUDGET)
    v1 = _submitted("xgboost-baseline-20260101")
    v2 = _submitted("xgboost-hardened-r1-20260201")
    v3 = _submitted("xgboost-hardened-crossfamily-20260301")

    against_v1 = evaluate_acceptance(incumbent=v1, candidate=v2, criteria=criteria)
    assert not against_v1.accepted
    assert {check.metric for check in against_v1.failures} == {
        "pr_auc",
        f"recall_at_fpr_{BUDGET}",
    }

    # v3 improves on the generation it replaces ...
    assert evaluate_acceptance(incumbent=v2, candidate=v3, criteria=criteria).accepted
    # ... but is still below the untouched baseline, which is why the
    # cross-family gate compares against both and not just the predecessor.
    assert not evaluate_acceptance(incumbent=v1, candidate=v3, criteria=criteria).accepted
