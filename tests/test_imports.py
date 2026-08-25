"""Every package imports cleanly and the public surface is what we think it is."""

from __future__ import annotations

import importlib

import pytest

MODULES = [
    "aegis",
    "aegis.shared",
    "aegis.shared.base",
    "aegis.shared.enums",
    "aegis.shared.types",
    "aegis.shared.version",
    "aegis.shared.contracts",
    "aegis.identify",
    "aegis.generate",
    "aegis.features",
    "aegis.defend",
    "aegis.evaluate",
    "aegis.loop",
    "aegis.api",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports(module_name):
    assert importlib.import_module(module_name) is not None


def test_contract_version_is_exposed():
    import aegis

    assert aegis.CONTRACT_VERSION.count(".") == 2


def test_contracts_public_surface():
    from aegis.shared import contracts

    expected = {
        "AttackBlueprint",
        "Transaction",
        "TransactionBatch",
        "DetectorOutput",
        "EvaluationResult",
        "EvasionFeedback",
    }
    assert expected.issubset(set(contracts.__all__))


def test_loop_exposes_attacker_evolution_without_retraining():
    """Phase 2 starts with attacker-only evolution; defender retraining stays absent."""
    import aegis.loop

    assert "evolve_bustout_round" in aegis.loop.__all__
    assert "AdaptiveRoundReport" in aegis.loop.__all__
    assert not any("retrain" in name.lower() for name in aegis.loop.__all__)
