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


def test_loop_has_no_logic_yet():
    """`loop/` is a placeholder at foundation stage; guard against drift."""
    import aegis.loop

    assert aegis.loop.__all__ == []
