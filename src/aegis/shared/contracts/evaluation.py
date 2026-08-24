"""`EvaluationResult` - the only accepted way to report performance.

Every number the project claims must come out of this contract, tagged with the
protocol that produced it (`EvaluationProtocol`). A metric without its protocol
is not interpretable: 0.95 recall on a static holdout and 0.95 recall on
post-retrain closed-loop attacks are very different claims.

Rules that govern how these numbers may be produced live in
docs/EVALUATION_RULES.md and are binding on both workstreams.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, model_validator

from aegis.shared.base import AegisModel
from aegis.shared.enums import AttackFamily, DataSplit, EvaluationProtocol
from aegis.shared.version import CONTRACT_VERSION


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConfusionCounts(AegisModel):
    """Raw counts underlying every rate. Reported so numbers can be re-derived."""

    true_positives: int = Field(default=0, ge=0)
    false_positives: int = Field(default=0, ge=0)
    true_negatives: int = Field(default=0, ge=0)
    false_negatives: int = Field(default=0, ge=0)

    @property
    def support(self) -> int:
        """Total number of scored samples."""
        return (
            self.true_positives + self.false_positives + self.true_negatives + self.false_negatives
        )

    @property
    def positives(self) -> int:
        """Number of ground-truth positives."""
        return self.true_positives + self.false_negatives


class ClassificationMetrics(AegisModel):
    """Detection quality at a fixed operating point, plus threshold-free areas.

    `recall_at_fixed_fpr` is keyed by the FPR budget as a string so that the
    operating points are explicit in serialized output, e.g.
    ``{"0.001": 0.62, "0.01": 0.81}``.
    """

    precision: float = Field(..., ge=0.0, le=1.0)
    recall: float = Field(..., ge=0.0, le=1.0)
    f1: float = Field(..., ge=0.0, le=1.0)
    pr_auc: float | None = Field(default=None, ge=0.0, le=1.0, description="Average precision.")
    roc_auc: float | None = Field(default=None, ge=0.0, le=1.0)
    false_positive_rate: float = Field(..., ge=0.0, le=1.0)
    false_negative_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    recall_at_fixed_fpr: dict[str, float] = Field(
        default_factory=dict, description="FPR budget (as string) -> recall at that budget."
    )
    alert_rate: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Fraction of traffic flagged."
    )
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    counts: ConfusionCounts = Field(default_factory=ConfusionCounts)
    support: int = Field(default=0, ge=0)
    positive_support: int = Field(default=0, ge=0)


class LatencyMetrics(AegisModel):
    """Scoring latency. Required because a detector nobody can run is not a win."""

    mean_ms: float = Field(..., ge=0.0)
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    p99_ms: float | None = Field(default=None, ge=0.0)
    max_ms: float | None = Field(default=None, ge=0.0)
    samples: int = Field(default=0, ge=0)


class FidelityMetrics(AegisModel):
    """How plausible generated traffic is against the reference distribution.

    Applies only to synthetic data. An evasion achieved by producing
    unrealistic traffic is discarded, so these numbers gate Red Team claims.
    """

    marginal_distance: float | None = Field(
        default=None, ge=0.0, description="Mean per-column distributional distance (e.g. KS)."
    )
    correlation_delta: float | None = Field(
        default=None, ge=0.0, description="Difference between correlation structures."
    )
    discriminator_auc: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="AUC of a real-vs-synthetic classifier; 0.5 is indistinguishable.",
    )
    constraint_violation_rate: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Share of records breaking realism constraints."
    )
    duplicate_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    overall_fidelity_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Aggregate; 1.0 is perfectly realistic."
    )
    per_column: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(AegisModel):
    """A complete, self-describing evaluation record."""

    contract_version: str = Field(default=CONTRACT_VERSION)

    evaluation_id: str = Field(..., min_length=1)
    protocol: EvaluationProtocol = Field(..., description="How this was measured.")
    model_version: str = Field(..., min_length=1)
    dataset_id: str = Field(default="", description="Identifies the evaluated corpus.")
    split: DataSplit = Field(default=DataSplit.TEST)

    overall: ClassificationMetrics = Field(...)
    per_attack_family: dict[AttackFamily, ClassificationMetrics] = Field(default_factory=dict)
    latency: LatencyMetrics | None = Field(default=None)
    fidelity: FidelityMetrics | None = Field(
        default=None, description="Set only when synthetic data is involved."
    )

    round_index: int | None = Field(
        default=None, ge=0, description="Closed-loop round this result belongs to."
    )
    held_out_family: AttackFamily | None = Field(
        default=None, description="Required for LEAVE_ONE_ATTACK_FAMILY_OUT."
    )
    seed: int | None = Field(default=None)
    notes: str = Field(default="")
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_protocol_requirements(self) -> EvaluationResult:
        if (
            self.protocol is EvaluationProtocol.LEAVE_ONE_ATTACK_FAMILY_OUT
            and self.held_out_family is None
        ):
            msg = "held_out_family is required for LEAVE_ONE_ATTACK_FAMILY_OUT evaluations"
            raise ValueError(msg)
        if self.protocol is EvaluationProtocol.CLOSED_LOOP_ROUND and self.round_index is None:
            msg = "round_index is required for CLOSED_LOOP_ROUND evaluations"
            raise ValueError(msg)
        return self


__all__ = [
    "ClassificationMetrics",
    "ConfusionCounts",
    "EvaluationResult",
    "FidelityMetrics",
    "LatencyMetrics",
]
