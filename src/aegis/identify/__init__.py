"""Red Team: attack identification.

Owned by the Red Team workstream. Produces `AttackBlueprint` specifications.
"""

from __future__ import annotations

from aegis.identify.base import BaseAttackIdentifier, IdentificationContext
from aegis.identify.mule_network import (
    MULE_NETWORK_BLUEPRINT_PROMPT,
    MuleNetworkBlueprintIdentifier,
    build_mule_network_blueprint,
)
from aegis.identify.synthetic_identity import (
    SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT,
    SyntheticIdentityBlueprintIdentifier,
    build_synthetic_identity_blueprint,
)

__all__ = [
    "MULE_NETWORK_BLUEPRINT_PROMPT",
    "SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT",
    "BaseAttackIdentifier",
    "IdentificationContext",
    "MuleNetworkBlueprintIdentifier",
    "SyntheticIdentityBlueprintIdentifier",
    "build_mule_network_blueprint",
    "build_synthetic_identity_blueprint",
]
