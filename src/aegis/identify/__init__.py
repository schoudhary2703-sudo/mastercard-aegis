"""Red Team: attack identification.

Owned by the Red Team workstream. Produces `AttackBlueprint` specifications.
"""

from __future__ import annotations

from aegis.identify.adaptive_evasion import (
    ADAPTIVE_EVASION_BLUEPRINT_PROMPT,
    AdaptiveEvasionBlueprintIdentifier,
    build_adaptive_evasion_blueprint,
)
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
from aegis.identify.taxonomy import (
    FraudScenario,
    FraudTaxonomy,
    ImplementationStatus,
    SimulationReadiness,
    TaxonomySummary,
    build_fraud_taxonomy,
)

__all__ = [
    "ADAPTIVE_EVASION_BLUEPRINT_PROMPT",
    "MULE_NETWORK_BLUEPRINT_PROMPT",
    "SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT",
    "AdaptiveEvasionBlueprintIdentifier",
    "BaseAttackIdentifier",
    "FraudScenario",
    "FraudTaxonomy",
    "IdentificationContext",
    "ImplementationStatus",
    "MuleNetworkBlueprintIdentifier",
    "SimulationReadiness",
    "SyntheticIdentityBlueprintIdentifier",
    "TaxonomySummary",
    "build_adaptive_evasion_blueprint",
    "build_fraud_taxonomy",
    "build_mule_network_blueprint",
    "build_synthetic_identity_blueprint",
]
