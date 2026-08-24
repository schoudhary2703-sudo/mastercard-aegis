"""Generation configuration.

`AttackBlueprint` says *what* the attack is. `GenerationConfig` says *how much*
of it to produce, *when*, and *with which seed*. Splitting them means the same
blueprint can be realised as a small smoke batch or a full evaluation corpus
without editing the attack definition.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import Field, model_validator

from aegis.shared.base import AegisModel
from aegis.shared.enums import DataSplit


class GenerationConfig(AegisModel):
    """Inputs that control one generation run."""

    seed: int = Field(
        default=20260101, description="Required for reproducibility; record it in the batch."
    )
    n_scenarios: int = Field(default=1, ge=1, description="Number of attack instances to realise.")
    max_transactions: int | None = Field(
        default=None, ge=1, description="Hard cap on emitted transactions."
    )

    start_time: datetime = Field(
        default_factory=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        description="Simulation clock origin.",
    )
    time_horizon: timedelta = Field(
        default=timedelta(days=30), description="Window scenarios are spread across."
    )

    legitimate_ratio: float = Field(
        default=0.0,
        ge=0.0,
        lt=1.0,
        description="Share of benign cover traffic to interleave, 0 for attack-only batches.",
    )
    parameter_overrides: dict[str, Any] = Field(
        default_factory=dict, description="Overrides for declared blueprint parameters."
    )
    split: DataSplit = Field(
        default=DataSplit.UNASSIGNED,
        description="Partition to stamp on emitted transactions. Set by the harness.",
    )
    generation: int = Field(default=0, ge=0, description="Closed-loop generation index.")
    deterministic: bool = Field(
        default=True, description="If True, the same seed must yield an identical batch."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_horizon(self) -> GenerationConfig:
        if self.time_horizon.total_seconds() <= 0:
            msg = "time_horizon must be positive"
            raise ValueError(msg)
        return self


__all__ = ["GenerationConfig"]
