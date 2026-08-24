"""`BaseDetector` - the interface every AEGIS detector implements.

Two abstract methods only:

    fit(X_train, y_train, meta=None) -> Self
    score(X) -> ndarray of calibrated risk scores in [0, 1]

Everything else - thresholding, action banding, assembling `DetectorOutput` -
is provided here so that all detectors behave identically at the boundary and
implementations stay small.

Deliberately absent: any concrete model. No gradient boosting, no anomaly
model, no graph model. Those arrive in Phase 1, as subclasses.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from aegis.defend.policy import DEFAULT_ACTION_POLICY, ActionPolicy
from aegis.shared.contracts import DetectorOutput, SignalContribution
from aegis.shared.enums import FraudLabel

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np
    import pandas as pd


class NotFittedError(RuntimeError):
    """Raised when `score` is called before `fit`."""


class BaseDetector(ABC):
    """Abstract fraud detector.

    Contract for implementers:

    * `fit` must be deterministic given the same data, seed and hyper-parameters.
    * `score` must return one float per input row, in [0, 1], in input order.
    * `score` must not mutate `X`.
    * `feature_names` must reflect the columns the model actually consumed.
    * No implementation may read `AttackBlueprint`, `attack_family`, or any
      column derived from the label. See docs/EVALUATION_RULES.md.
    """

    #: Identifies the trained artifact. Implementations should make this
    #: specific enough to distinguish retraining rounds, e.g. "lgbm-r3-20260824".
    model_version: str = "base-detector-v0"

    #: Human-readable implementation name, independent of the trained version.
    name: str = "base"

    def __init__(self, action_policy: ActionPolicy | None = None) -> None:
        self.action_policy: ActionPolicy = action_policy or DEFAULT_ACTION_POLICY
        self._is_fitted: bool = False
        self._feature_names: list[str] = []

    # -- required -----------------------------------------------------------
    @abstractmethod
    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series | np.ndarray,
        meta: dict[str, Any] | None = None,
    ) -> BaseDetector:
        """Train the detector and return self.

        Args:
            X_train: Feature matrix produced by a `BaseFeatureExtractor`.
            y_train: Binary labels aligned with `X_train` rows.
            meta: Optional side-channel, e.g. sample weights, group ids for
                grouped splits, or the round index. Never labels in disguise.
        """

    @abstractmethod
    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Return calibrated fraud probabilities in [0, 1], one per row."""

    # -- provided -----------------------------------------------------------
    @property
    def is_fitted(self) -> bool:
        """Whether `fit` has completed successfully."""
        return self._is_fitted

    @property
    def feature_names(self) -> list[str]:
        """Columns the fitted model consumes, in order."""
        return list(self._feature_names)

    def explain(self, X: pd.DataFrame) -> list[list[SignalContribution]]:
        """Per-row signal attributions.

        Default is empty - attribution is optional at the interface level but
        required for the closed loop, so any detector used in a loop round must
        override this.
        """
        return [[] for _ in range(len(X))]

    def predict(
        self,
        X: pd.DataFrame,
        transaction_ids: list[str],
        *,
        explain: bool = False,
    ) -> list[DetectorOutput]:
        """Score `X` and assemble `DetectorOutput` records.

        This is the method the rest of the system calls. Implementations should
        not need to override it.
        """
        if not self._is_fitted:
            msg = f"{type(self).__name__}.predict called before fit"
            raise NotFittedError(msg)
        if len(transaction_ids) != len(X):
            msg = (
                f"transaction_ids length {len(transaction_ids)} does not match "
                f"feature matrix length {len(X)}"
            )
            raise ValueError(msg)

        scores = self.score(X)
        signals = self.explain(X) if explain else [[] for _ in range(len(X))]
        policy = self.action_policy

        outputs: list[DetectorOutput] = []
        for txn_id, raw_score, row_signals in zip(transaction_ids, scores, signals, strict=True):
            risk = float(raw_score)
            label = FraudLabel.FRAUD if risk >= policy.label_threshold else FraudLabel.LEGITIMATE
            outputs.append(
                DetectorOutput(
                    transaction_id=txn_id,
                    risk_score=risk,
                    predicted_label=label,
                    recommended_action=policy.action_for(risk),
                    important_signals=list(row_signals),
                    model_version=self.model_version,
                    threshold=policy.label_threshold,
                    policy_version=policy.policy_version,
                )
            )
        return outputs

    def save(self, path: str) -> None:
        """Persist the fitted model. Optional; override where needed."""
        msg = f"{type(self).__name__} does not implement save()"
        raise NotImplementedError(msg)

    @classmethod
    def load(cls, path: str) -> BaseDetector:
        """Restore a fitted model. Optional; override where needed."""
        msg = f"{cls.__name__} does not implement load()"
        raise NotImplementedError(msg)


__all__ = ["BaseDetector", "NotFittedError"]
