"""`BaseEvaluator` - produces `EvaluationResult` records.

Evaluation is deliberately a separate module owned by neither team alone: if
the Blue Team both trains and scores itself, the numbers stop meaning anything.
Every reported metric must come from an implementation of this interface.

Deliberately absent: metric computation. Phase 1 work.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from aegis.shared.contracts import DetectorOutput, EvaluationResult, Transaction
from aegis.shared.enums import EvaluationProtocol


class BaseEvaluator(ABC):
    """Abstract evaluator.

    Contract for implementers:

    * `protocol` must describe how the inputs were produced and is copied onto
      the returned `EvaluationResult`.
    * `outputs` and `ground_truth` must be aligned by `transaction_id`, not by
      position - a silent misalignment is the easiest way to fake a good score.
    * Any transaction whose label is `UNKNOWN` must be excluded, not treated as
      legitimate.
    """

    name: str = "base"
    protocol: EvaluationProtocol = EvaluationProtocol.STATIC_HOLDOUT

    @abstractmethod
    def evaluate(
        self,
        outputs: Sequence[DetectorOutput],
        ground_truth: Sequence[Transaction],
        meta: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Score detector outputs against ground truth."""


__all__ = ["BaseEvaluator"]
