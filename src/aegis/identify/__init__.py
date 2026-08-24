"""Red Team: attack identification.

Owned by the Red Team workstream. Produces `AttackBlueprint` specifications.
"""

from __future__ import annotations

from aegis.identify.base import BaseAttackIdentifier, IdentificationContext
from aegis.identify.synthetic_identity import (
    SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT,
    SyntheticIdentityBlueprintIdentifier,
    build_synthetic_identity_blueprint,
)

__all__ = [
    "SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT",
    "BaseAttackIdentifier",
    "IdentificationContext",
    "SyntheticIdentityBlueprintIdentifier",
    "build_synthetic_identity_blueprint",
]
