"""Evaluation harness.

Shared ownership: changes here need sign-off from both workstreams, because
this module decides what "better" means. The binding rules live in
docs/EVALUATION_RULES.md.
"""

from __future__ import annotations

from aegis.evaluate.base import BaseEvaluator
from aegis.evaluate.confrontation import (
    BustOutConfrontationEvaluator,
    BustOutConfrontationReport,
    ConfrontationValidationError,
    EvasionRecord,
    FraudEventAssessment,
    ScenarioConfrontationReport,
    build_bustout_confrontation_report,
    rank_hardest_evasions,
)

__all__ = [
    "BaseEvaluator",
    "BustOutConfrontationEvaluator",
    "BustOutConfrontationReport",
    "ConfrontationValidationError",
    "EvasionRecord",
    "FraudEventAssessment",
    "ScenarioConfrontationReport",
    "build_bustout_confrontation_report",
    "rank_hardest_evasions",
]
