"""`BaseFeatureExtractor` - the boundary between raw events and model input.

Feature extraction is shared infrastructure: the Blue Team consumes it, and the
Red Team reads `feature_names` to know what a detector can see. Implementations
go here, not inside a detector, so that two detectors can be compared on an
identical feature matrix.

Deliberately absent: temporal aggregations, graph construction, TGN/GNN
embeddings. Phase 1 work.

Leakage rule: an extractor must compute each row's features from that row and
from *strictly earlier* events only. Any aggregate that peeks at future
transactions, or at the label, is a defect. See docs/EVALUATION_RULES.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from aegis.shared.contracts import Transaction

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


class BaseFeatureExtractor(ABC):
    """Abstract transaction-to-feature-matrix transformer."""

    #: Namespace prepended to every emitted feature name, e.g. "temporal".
    namespace: str = "base"

    #: Implementation version, recorded alongside trained models.
    version: str = "0.1.0"

    def __init__(self) -> None:
        self._is_fitted: bool = False
        self._feature_names: list[str] = []

    @abstractmethod
    def fit(
        self, transactions: Sequence[Transaction], meta: dict[str, Any] | None = None
    ) -> BaseFeatureExtractor:
        """Learn any state the transform needs (encodings, vocabularies, scalers).

        Must be fitted on training data only.
        """

    @abstractmethod
    def transform(self, transactions: Sequence[Transaction]) -> pd.DataFrame:
        """Return one feature row per input transaction, in input order."""

    def fit_transform(
        self, transactions: Sequence[Transaction], meta: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        """Fit on `transactions` and transform them in one call."""
        return self.fit(transactions, meta).transform(transactions)

    @property
    def is_fitted(self) -> bool:
        """Whether `fit` has completed successfully."""
        return self._is_fitted

    @property
    def feature_names(self) -> list[str]:
        """Names of the columns `transform` emits, in order."""
        return list(self._feature_names)


__all__ = ["BaseFeatureExtractor"]
