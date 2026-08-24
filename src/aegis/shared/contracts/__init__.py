"""Frozen cross-team data contracts.

Everything both workstreams exchange is defined here and nowhere else. Import
from this package, not from the submodules, so that internal reorganisation
does not break callers::

    from aegis.shared.contracts import Transaction, DetectorOutput

Changing anything in this package requires a `CONTRACT_VERSION` bump and
agreement from both workstreams. See AGENTS.md.
"""

from __future__ import annotations

from aegis.shared.contracts.attack import (
    AttackBlueprint,
    BehavioralStep,
    ParameterSpec,
    RealismConstraints,
)
from aegis.shared.contracts.detector import (
    DetectorOutput,
    DetectorOutputBatch,
    SignalContribution,
)
from aegis.shared.contracts.evaluation import (
    ClassificationMetrics,
    ConfusionCounts,
    EvaluationResult,
    FidelityMetrics,
    LatencyMetrics,
)
from aegis.shared.contracts.feedback import EvasionFeedback, ParameterMutation
from aegis.shared.contracts.transaction import (
    FEATURE_NAMESPACE_SEPARATOR,
    Transaction,
    TransactionBatch,
)

__all__ = [
    "FEATURE_NAMESPACE_SEPARATOR",
    "AttackBlueprint",
    "BehavioralStep",
    "ClassificationMetrics",
    "ConfusionCounts",
    "DetectorOutput",
    "DetectorOutputBatch",
    "EvaluationResult",
    "EvasionFeedback",
    "FidelityMetrics",
    "LatencyMetrics",
    "ParameterMutation",
    "ParameterSpec",
    "RealismConstraints",
    "SignalContribution",
    "Transaction",
    "TransactionBatch",
]
