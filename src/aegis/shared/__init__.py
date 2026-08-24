"""Shared vocabulary for AEGIS.

`shared/` is the one package both workstreams depend on. It contains contracts,
enums, type aliases and small pure helpers - never model code, never generation
code. If something here needs pandas at import time, it is in the wrong place.
"""

from __future__ import annotations

from aegis.shared.enums import (
    AttackFamily,
    Channel,
    DataSplit,
    EvaluationProtocol,
    FraudLabel,
    MutationDirection,
    ParameterType,
    RecommendedAction,
    SignalDirection,
    TransactionType,
)
from aegis.shared.version import CONTRACT_VERSION, SCHEMA_NAMESPACE

__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_NAMESPACE",
    "AttackFamily",
    "Channel",
    "DataSplit",
    "EvaluationProtocol",
    "FraudLabel",
    "MutationDirection",
    "ParameterType",
    "RecommendedAction",
    "SignalDirection",
    "TransactionType",
]
