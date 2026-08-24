"""Shared fixtures.

The dummy detector and generator here exist to prove the *interfaces* are
subclassable. They are test doubles, not implementations: the detector returns a
constant score and the generator emits a fixed-shape sequence. Neither belongs
in `src/`, and neither should be extended into something that looks like a real
model.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import pytest

from aegis.defend import BaseDetector
from aegis.features import BaseFeatureExtractor
from aegis.generate import BaseGenerator, GenerationConfig
from aegis.shared.contracts import (
    AttackBlueprint,
    BehavioralStep,
    ParameterSpec,
    RealismConstraints,
    Transaction,
)
from aegis.shared.enums import (
    AttackFamily,
    Channel,
    FraudLabel,
    ParameterType,
    TransactionType,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class ConstantDetector(BaseDetector):
    """Returns a fixed score. Proves the interface can be subclassed."""

    name = "constant"
    model_version = "constant-v0"

    def __init__(self, constant: float = 0.9) -> None:
        super().__init__()
        self.constant = constant

    def fit(self, X_train, y_train, meta=None):
        self._feature_names = list(X_train.columns)
        self._is_fitted = True
        return self

    def score(self, X):
        return np.full(len(X), self.constant, dtype=float)


class FixedSequenceGenerator(BaseGenerator):
    """Emits `n_scenarios` two-transaction scenarios. No fraud logic."""

    name = "fixed-sequence"
    version = "0.0.1"

    def stream(self, blueprint: AttackBlueprint, config: GenerationConfig) -> Iterator[Transaction]:
        for scenario in range(config.n_scenarios):
            scenario_id = f"{blueprint.attack_id}-s{scenario}"
            for index, step in enumerate(blueprint.ordered_sequence()):
                yield Transaction(
                    transaction_id=f"{scenario_id}-t{index}",
                    timestamp=config.start_time + timedelta(seconds=step.offset_seconds),
                    source_account_id=f"acct-src-{scenario}",
                    destination_account_id=f"acct-dst-{scenario}",
                    amount=100.0 + index,
                    currency="USD",
                    transaction_type=TransactionType.TRANSFER,
                    channel=step.channel or Channel.ONLINE_BANKING,
                    label=FraudLabel.FRAUD,
                    attack_family=blueprint.attack_family,
                    is_synthetic=True,
                    scenario_id=scenario_id,
                    blueprint_id=blueprint.attack_id,
                    step_id=step.step_id,
                    sequence_index=index,
                    split=config.split,
                    generation=config.generation,
                )


class PassthroughExtractor(BaseFeatureExtractor):
    """Emits amount and hour-of-day. Proves the extractor interface works."""

    namespace = "basic"

    def fit(self, transactions: Sequence[Transaction], meta: dict[str, Any] | None = None):
        self._feature_names = ["basic.amount", "basic.hour"]
        self._is_fitted = True
        return self

    def transform(self, transactions: Sequence[Transaction]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "basic.amount": [t.amount for t in transactions],
                "basic.hour": [t.timestamp.hour for t in transactions],
            }
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def blueprint() -> AttackBlueprint:
    return AttackBlueprint(
        attack_id="bp-mule-001",
        attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
        name="Layered structuring",
        description="Funds split across mule accounts below the reporting threshold.",
        objective="Move funds to a cash-out account without triggering a structuring alert.",
        target_features=["temporal.velocity_24h", "graph.fan_out"],
        sequence=[
            BehavioralStep(
                step_id="fan-out",
                order=0,
                action="split_transfer",
                channel=Channel.ONLINE_BANKING,
                offset_seconds=0.0,
                repeat=4,
            ),
            BehavioralStep(
                step_id="cash-out",
                order=1,
                action="cash_out",
                channel=Channel.ATM,
                offset_seconds=86400.0,
            ),
        ],
        parameters={
            "split_count": ParameterSpec(
                name="split_count",
                param_type=ParameterType.INT,
                default=4,
                minimum=2,
                maximum=12,
            ),
            "threshold_margin": ParameterSpec(
                name="threshold_margin",
                param_type=ParameterType.FLOAT,
                default=0.85,
                minimum=0.5,
                maximum=0.99,
                unit="ratio",
            ),
            "family": ParameterSpec(
                name="family",
                param_type=ParameterType.STRING,
                default="mule",
                mutable=False,
            ),
        },
        realism_constraints=RealismConstraints(
            min_amount=10.0,
            max_amount=9000.0,
            allowed_currencies=["USD"],
            active_hours_utc=[9, 10, 11, 12, 13, 14, 15, 16, 17],
        ),
    )


@pytest.fixture
def transaction() -> Transaction:
    return Transaction(
        transaction_id="txn-0001",
        timestamp=T0,
        source_account_id="acct-a",
        destination_account_id="acct-b",
        amount=2500.0,
        currency="usd",
        transaction_type=TransactionType.TRANSFER,
        channel=Channel.ONLINE_BANKING,
        label=FraudLabel.FRAUD,
        attack_family=AttackFamily.MULE_NETWORK_STRUCTURING,
        is_synthetic=True,
        scenario_id="scn-1",
        blueprint_id="bp-mule-001",
    )


@pytest.fixture
def detector() -> ConstantDetector:
    return ConstantDetector()


@pytest.fixture
def generator() -> FixedSequenceGenerator:
    return FixedSequenceGenerator()
