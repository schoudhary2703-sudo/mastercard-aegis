"""Blue Team: detection, scoring, decisioning.

Owned by the Blue Team workstream. Contains the detector interface and the
score-to-action policy. Concrete detectors are added here in Phase 1.

This package must not import from `generate/`, `identify/` or `loop/`.
"""

from __future__ import annotations

from aegis.defend.acceptance import (
    AcceptanceCheck,
    AcceptanceCriteria,
    AcceptanceDecision,
    evaluate_acceptance,
)
from aegis.defend.base import BaseDetector, NotFittedError
from aegis.defend.hard_positives import (
    HardPositiveArtifact,
    HardPositivePromotion,
    HardPositiveSource,
    HardPositiveValidationError,
    ScenarioProvenance,
    assert_no_duplicate_transaction_ids,
    assert_no_id_overlap_with_jsonl,
    promote_hard_positives,
    promoted_sample_weights,
    write_hard_positive_artifact,
)
from aegis.defend.policy import DEFAULT_ACTION_POLICY, ActionPolicy
from aegis.defend.xgboost_detector import XGBoostDetector

__all__ = [
    "DEFAULT_ACTION_POLICY",
    "AcceptanceCheck",
    "AcceptanceCriteria",
    "AcceptanceDecision",
    "ActionPolicy",
    "BaseDetector",
    "HardPositiveArtifact",
    "HardPositivePromotion",
    "HardPositiveSource",
    "HardPositiveValidationError",
    "NotFittedError",
    "ScenarioProvenance",
    "XGBoostDetector",
    "assert_no_duplicate_transaction_ids",
    "assert_no_id_overlap_with_jsonl",
    "evaluate_acceptance",
    "promote_hard_positives",
    "promoted_sample_weights",
    "write_hard_positive_artifact",
]
