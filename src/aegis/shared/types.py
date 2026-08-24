"""Type aliases shared across modules.

Keeping these in one place means a change to, say, the accepted feature-matrix
type does not require edits in both the Red Team and Blue Team packages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:  # pragma: no cover - import-time only for type checkers
    import numpy as np
    import pandas as pd

TransactionId: TypeAlias = str
AccountId: TypeAlias = str
ScenarioId: TypeAlias = str
BlueprintId: TypeAlias = str
AttackId: TypeAlias = str
ModelVersion: TypeAlias = str

FeatureValue: TypeAlias = float | int | bool | str | None
"""Value type permitted in the open `Transaction.features` map.

Derived behavioural and network features are attached here so the transaction
schema is never coupled to one detector's feature set.
"""

FeatureMap: TypeAlias = dict[str, FeatureValue]
Metadata: TypeAlias = dict[str, Any]

FeatureMatrix: TypeAlias = "pd.DataFrame"
"""Canonical feature-matrix type exchanged between `features/` and `defend/`."""

LabelVector: TypeAlias = "pd.Series | np.ndarray"
"""Canonical label vector type consumed by `BaseDetector.fit`."""

ScoreVector: TypeAlias = "np.ndarray"
"""Canonical output of `BaseDetector.score`: float risk scores in [0, 1]."""

__all__ = [
    "AccountId",
    "AttackId",
    "BlueprintId",
    "FeatureMap",
    "FeatureMatrix",
    "FeatureValue",
    "LabelVector",
    "Metadata",
    "ModelVersion",
    "ScenarioId",
    "ScoreVector",
    "TransactionId",
]
