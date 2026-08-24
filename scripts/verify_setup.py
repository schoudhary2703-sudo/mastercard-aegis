#!/usr/bin/env python3
"""Smoke-check the AEGIS installation.

Confirms the package imports, the contracts are constructible, and the
interfaces are present. Run this first in any new environment or agent session:

    python scripts/verify_setup.py

Exits non-zero on the first failure so it is usable in CI.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

CHECK = "[ok]"
CROSS = "[FAIL]"


def main() -> int:
    try:
        import aegis
        from aegis.defend import DEFAULT_ACTION_POLICY, BaseDetector
        from aegis.evaluate import BaseEvaluator
        from aegis.features import BaseFeatureExtractor
        from aegis.generate import BaseGenerator, GenerationConfig
        from aegis.identify import BaseAttackIdentifier
        from aegis.shared import contracts
        from aegis.shared.enums import AttackFamily, RecommendedAction
    except Exception as exc:
        print(f"{CROSS} import failed: {exc}")
        return 1

    print(f"{CHECK} aegis {aegis.__version__} (contract {aegis.CONTRACT_VERSION})")
    print(f"{CHECK} python {sys.version.split()[0]}")

    # Contracts construct.
    txn = contracts.Transaction(
        transaction_id="verify-1",
        timestamp=datetime.now(timezone.utc),
        source_account_id="acct-a",
        destination_account_id="acct-b",
        amount=10.0,
    )
    restored = contracts.Transaction.from_json(txn.to_json())
    if restored != txn:
        print(f"{CROSS} Transaction did not survive a JSON round trip")
        return 1
    print(f"{CHECK} contracts: {len(contracts.__all__)} exported, round trip clean")

    # Interfaces are abstract.
    interfaces = [
        BaseDetector,
        BaseGenerator,
        BaseFeatureExtractor,
        BaseAttackIdentifier,
        BaseEvaluator,
    ]
    for interface in interfaces:
        if not getattr(interface, "__abstractmethods__", None):
            print(f"{CROSS} {interface.__name__} has no abstract methods")
            return 1
    print(f"{CHECK} interfaces: {', '.join(i.__name__ for i in interfaces)}")

    # Scope guard: exactly three attack families.
    families = [f.value for f in AttackFamily]
    if len(families) != 3:
        print(f"{CROSS} expected 3 attack families, found {len(families)}: {families}")
        return 1
    print(f"{CHECK} attack families: {', '.join(families)}")

    actions = [a.value for a in RecommendedAction]
    print(f"{CHECK} actions: {', '.join(actions)}")
    print(f"{CHECK} default policy: {DEFAULT_ACTION_POLICY.policy_version}")
    print(f"{CHECK} generation config seed default: {GenerationConfig().seed}")

    print("\nFoundation looks healthy. Next: read AGENTS.md before writing code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
