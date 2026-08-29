from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aegis.generate import (
    GenerationBenchmarkCase,
    GenerationConfig,
    SyntheticIdentityBustOutGenerator,
    run_generation_scale_benchmark,
)
from aegis.identify import build_synthetic_identity_blueprint
from aegis.shared.enums import AttackFamily, DataSplit


def _case(seed: int = 20261001) -> GenerationBenchmarkCase:
    return GenerationBenchmarkCase(
        family=AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT,
        generator=SyntheticIdentityBustOutGenerator(),
        blueprint=build_synthetic_identity_blueprint(),
        config=GenerationConfig(
            seed=seed,
            n_scenarios=2,
            start_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
            time_horizon=timedelta(days=120),
            split=DataSplit.TEST,
            deterministic=True,
        ),
    )


def test_scale_benchmark_separates_fidelity_from_constraint_validity() -> None:
    result = run_generation_scale_benchmark([_case()])
    family = result.families[0]
    assert family.transactions_generated == 30
    assert family.fraud_transactions_generated == 6
    assert family.constraint_valid_percentage == 100.0
    assert family.distributional_fidelity_score != family.constraint_valid_percentage / 100.0
    assert family.deterministic_reproducibility.verified is True
    assert result.summary.all_deterministic is True


def test_scale_benchmark_rejects_historical_scenario_overlap() -> None:
    case = _case()
    batch = case.generator.generate(case.blueprint, case.config)
    with pytest.raises(ValueError, match="historical scenario"):
        run_generation_scale_benchmark(
            [case], historical_scenario_ids={batch.scenario_ids[0]}
        )
