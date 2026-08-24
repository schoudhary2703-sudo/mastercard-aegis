"""AEGIS - closed-loop AI red-team / blue-team payment security system.

Top-level package. Import contracts and interfaces from their own packages::

    from aegis.shared.contracts import AttackBlueprint, Transaction
    from aegis.defend import BaseDetector
    from aegis.generate import BaseGenerator, GenerationConfig

Nothing heavier than pydantic is imported at package-import time, so `import
aegis` stays fast and dependency-light for both workstreams.
"""

from __future__ import annotations

from aegis.shared.version import CONTRACT_VERSION

__version__ = "0.1.0"

__all__ = ["CONTRACT_VERSION", "__version__"]
