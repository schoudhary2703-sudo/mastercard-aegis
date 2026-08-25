"""Evaluation harness.

Shared ownership: changes here need sign-off from both workstreams, because
this module decides what "better" means. The binding rules live in
docs/EVALUATION_RULES.md.
"""

from __future__ import annotations

from aegis.evaluate.adaptive_evasion import (
    AdaptiveEvasionConfrontationEvaluator,
    AdaptiveEvasionConfrontationReport,
    AdaptiveEvasionScenarioReport,
    build_adaptive_evasion_confrontation_report,
)
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
from aegis.evaluate.mule_confrontation import (
    MuleNetworkConfrontationEvaluator,
    MuleNetworkConfrontationReport,
    MuleScenarioConfrontationReport,
    TrainingOverlapScan,
    build_mule_network_confrontation_report,
    scan_training_overlap,
)

__all__ = [
    "AdaptiveEvasionConfrontationEvaluator",
    "AdaptiveEvasionConfrontationReport",
    "AdaptiveEvasionScenarioReport",
    "BaseEvaluator",
    "BustOutConfrontationEvaluator",
    "BustOutConfrontationReport",
    "ConfrontationValidationError",
    "EvasionRecord",
    "FraudEventAssessment",
    "MuleNetworkConfrontationEvaluator",
    "MuleNetworkConfrontationReport",
    "MuleScenarioConfrontationReport",
    "ScenarioConfrontationReport",
    "TrainingOverlapScan",
    "build_adaptive_evasion_confrontation_report",
    "build_bustout_confrontation_report",
    "build_mule_network_confrontation_report",
    "rank_hardest_evasions",
    "scan_training_overlap",
]
