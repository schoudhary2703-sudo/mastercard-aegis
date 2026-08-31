"""Acceptance gate for a retrained detector.

`scripts/harden_defender.py` already computed a full baseline-vs-hardened
regression report and wrote it to disk - but nothing ever *read* it. Every
retrained model shipped regardless of what the comparison said, which is how
`submission/artifacts/data/reports/final_benchmark_summary.json` ended up
recording two hardening rounds that both left the detector below the
untouched baseline on F1, recall and PR-AUC:

    baseline_v1  f1 0.8568  recall 0.7948  pr_auc 0.9089
    defender_v2  f1 0.8433  recall 0.7708  pr_auc 0.9008
    defender_v3  f1 0.8512  recall 0.7791  pr_auc 0.9036

A closed loop that cannot decline its own output is not a closed loop. This
module supplies the missing decision: given the frozen incumbent's evaluation
and the candidate's, on the same untouched test split, it returns an explicit
accept/reject with per-check evidence.

What is gated, and why those metrics
------------------------------------
* **PR-AUC** and **ROC-AUC** are threshold-free. They measure whether the
  model's *ranking* got better or worse, independently of where the operating
  point happens to sit - so a candidate cannot pass by re-tuning its
  threshold into a flattering position.
* **Recall at the operating FPR budget** is the business outcome: fraud
  caught at a review load the issuer can actually staff.

Deliberately *not* gated: raw precision, F1, and the confusion counts. All
three move with the threshold, and the threshold legitimately differs between
a candidate and an incumbent trained under a different operating-point rule
(see `scripts/train_baseline_detector.py`). Gating on them would reward
threshold choice rather than model quality.

Tolerance, not equality: retraining on a different training set moves metrics
by small amounts that are noise, not regression. `DEFAULT_TOLERANCE` allows a
candidate to give up a little ranking quality; it does not allow it to give
up recall at the budget the system is operated at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from aegis.shared.contracts import EvaluationResult

DEFAULT_TOLERANCE = 0.002
"""Allowed regression per gated metric, in absolute terms.

0.002 of PR-AUC is about the run-to-run movement retraining on a marginally
different training set produces; a real regression from a bad hardening round
is an order of magnitude larger (defender_v2 gave up 0.008 of PR-AUC and
0.024 of recall against baseline_v1)."""

DEFAULT_OPERATING_FPR_BUDGET = 0.005
"""Budget whose recall is gated. Matches the pipeline's default operating
point (`scripts/train_baseline_detector.py`)."""


@dataclass(frozen=True)
class AcceptanceCriteria:
    """What a candidate must satisfy to replace the incumbent."""

    tolerance: float = DEFAULT_TOLERANCE
    operating_fpr_budget: float = DEFAULT_OPERATING_FPR_BUDGET
    require_pr_auc: bool = True
    require_roc_auc: bool = True
    require_recall_at_budget: bool = True


@dataclass(frozen=True)
class AcceptanceCheck:
    """One gated metric's incumbent value, candidate value, and verdict."""

    metric: str
    incumbent: float | None
    candidate: float | None
    delta: float | None
    tolerance: float
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "incumbent": self.incumbent,
            "candidate": self.candidate,
            "delta": self.delta,
            "tolerance": self.tolerance,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AcceptanceDecision:
    """Whether the candidate is promoted, and the evidence for that call."""

    accepted: bool
    checks: list[AcceptanceCheck] = field(default_factory=list)
    incumbent_model_version: str = ""
    candidate_model_version: str = ""

    @property
    def failures(self) -> list[AcceptanceCheck]:
        """Checks that blocked promotion, in evaluation order."""
        return [check for check in self.checks if not check.passed]

    @property
    def summary(self) -> str:
        """One-line verdict suitable for a console line or a report field."""
        if self.accepted:
            return (
                f"ACCEPTED: {self.candidate_model_version} does not regress "
                f"{self.incumbent_model_version} on any gated metric"
            )
        reasons = "; ".join(check.detail for check in self.failures)
        return f"REJECTED: {self.candidate_model_version} regresses {reasons}"

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "summary": self.summary,
            "incumbent_model_version": self.incumbent_model_version,
            "candidate_model_version": self.candidate_model_version,
            "checks": [check.to_dict() for check in self.checks],
            "failed_metrics": [check.metric for check in self.failures],
        }


def _compare(
    metric: str,
    incumbent: float | None,
    candidate: float | None,
    tolerance: float,
) -> AcceptanceCheck:
    """One higher-is-better comparison, tolerant of a small regression.

    A missing value on either side fails the check rather than passing it
    silently: an unmeasurable metric is not evidence of no regression.
    """
    if incumbent is None or candidate is None:
        return AcceptanceCheck(
            metric=metric,
            incumbent=incumbent,
            candidate=candidate,
            delta=None,
            tolerance=tolerance,
            passed=False,
            detail=(f"{metric}: not comparable (incumbent={incumbent!r}, candidate={candidate!r})"),
        )
    delta = candidate - incumbent
    passed = delta >= -tolerance
    if passed:
        detail = (
            f"{metric}: {incumbent:.6f} -> {candidate:.6f} (delta {delta:+.6f}), within tolerance"
        )
    else:
        detail = (
            f"{metric}: {incumbent:.6f} -> {candidate:.6f} "
            f"(delta {delta:+.6f}, exceeds tolerance {tolerance})"
        )
    return AcceptanceCheck(
        metric=metric,
        incumbent=incumbent,
        candidate=candidate,
        delta=delta,
        tolerance=tolerance,
        passed=passed,
        detail=detail,
    )


def _recall_at_budget(evaluation: EvaluationResult, budget: float) -> float | None:
    """Read `recall_at_fixed_fpr` for `budget`, tolerating key formatting.

    The contract stores the budget as a string key. Producers have written it
    both as `str(0.005)` -> `"0.005"` and via other float formatting, so match
    numerically rather than by exact string equality.
    """
    table = evaluation.overall.recall_at_fixed_fpr
    for key, value in table.items():
        try:
            if float(key) == budget:
                return value
        except (TypeError, ValueError):  # pragma: no cover - defensive only
            continue
    return None


def evaluate_acceptance(
    *,
    incumbent: EvaluationResult,
    candidate: EvaluationResult,
    criteria: AcceptanceCriteria | None = None,
) -> AcceptanceDecision:
    """Decide whether `candidate` may replace `incumbent`.

    Both arguments must be evaluations of the *same untouched test split* -
    never of the hard positives used to retrain the candidate
    (`docs/EVALUATION_RULES.md` SS3). This function does not verify that;
    the caller assembles both results and is responsible for it.

    Returns a decision even when every check passes, so the report records
    what was checked rather than only what failed.
    """
    resolved = criteria or AcceptanceCriteria()
    if incumbent.split != candidate.split:
        msg = (
            "acceptance compares one split only, got "
            f"incumbent split={incumbent.split} and candidate split={candidate.split}"
        )
        raise ValueError(msg)

    checks: list[AcceptanceCheck] = []
    if resolved.require_pr_auc:
        checks.append(
            _compare(
                "pr_auc", incumbent.overall.pr_auc, candidate.overall.pr_auc, resolved.tolerance
            )
        )
    if resolved.require_roc_auc:
        checks.append(
            _compare(
                "roc_auc", incumbent.overall.roc_auc, candidate.overall.roc_auc, resolved.tolerance
            )
        )
    if resolved.require_recall_at_budget:
        budget = resolved.operating_fpr_budget
        checks.append(
            _compare(
                f"recall_at_fpr_{budget}",
                _recall_at_budget(incumbent, budget),
                _recall_at_budget(candidate, budget),
                resolved.tolerance,
            )
        )

    return AcceptanceDecision(
        accepted=all(check.passed for check in checks),
        checks=checks,
        incumbent_model_version=incumbent.model_version,
        candidate_model_version=candidate.model_version,
    )


__all__ = [
    "DEFAULT_OPERATING_FPR_BUDGET",
    "DEFAULT_TOLERANCE",
    "AcceptanceCheck",
    "AcceptanceCriteria",
    "AcceptanceDecision",
    "evaluate_acceptance",
]
