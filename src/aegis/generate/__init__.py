"""Red Team: attack realisation.

Owned by the Red Team workstream. Contains the generator interface and its
configuration contract. Concrete generators are added here in Phase 1.

This package must not import from `defend/` or `features/`.
"""

from __future__ import annotations

from aegis.generate.adaptive_evasion import (
    AdaptiveDetectorEvasionGenerator,
    AdaptiveEvasionConfigurationError,
    AdaptiveEvasionFidelitySummary,
    AdaptiveEvasionReferenceProfile,
)
from aegis.generate.base import BaseGenerator, BlueprintNotSupportedError
from aegis.generate.config import GenerationConfig
from aegis.generate.mule_network import (
    MuleNetworkConfigurationError,
    MuleNetworkFidelitySummary,
    MuleNetworkReferenceProfile,
    MuleNetworkStructuringGenerator,
)
from aegis.generate.paysim import (
    DEFAULT_PAYSIM_CURRENCY,
    DEFAULT_PAYSIM_EPOCH,
    PAYSIM_REQUIRED_COLUMNS,
    PaySimPreparationConfig,
    PaySimPreparationError,
    PaySimPreparationResult,
    PaySimRowError,
    PaySimSchemaError,
    PaySimSplitMode,
    map_paysim_row,
    prepare_paysim,
    validate_paysim_schema,
)
from aegis.generate.reference_snapshot import (
    GenerationReferenceSnapshot,
    SnapshotArtifact,
    build_reference_snapshot,
    sha256_file,
)
from aegis.generate.scale_benchmark import (
    FamilyGenerationBenchmark,
    GenerationBenchmarkCase,
    GenerationScaleBenchmark,
    run_generation_scale_benchmark,
)
from aegis.generate.synthetic_identity import (
    BustOutFidelitySummary,
    PaySimReferenceProfile,
    SyntheticIdentityBustOutGenerator,
    SyntheticIdentityConfigurationError,
    write_synthetic_identity_artifacts,
)

__all__ = [
    "DEFAULT_PAYSIM_CURRENCY",
    "DEFAULT_PAYSIM_EPOCH",
    "PAYSIM_REQUIRED_COLUMNS",
    "AdaptiveDetectorEvasionGenerator",
    "AdaptiveEvasionConfigurationError",
    "AdaptiveEvasionFidelitySummary",
    "AdaptiveEvasionReferenceProfile",
    "BaseGenerator",
    "BlueprintNotSupportedError",
    "BustOutFidelitySummary",
    "FamilyGenerationBenchmark",
    "GenerationBenchmarkCase",
    "GenerationConfig",
    "GenerationReferenceSnapshot",
    "GenerationScaleBenchmark",
    "MuleNetworkConfigurationError",
    "MuleNetworkFidelitySummary",
    "MuleNetworkReferenceProfile",
    "MuleNetworkStructuringGenerator",
    "PaySimPreparationConfig",
    "PaySimPreparationError",
    "PaySimPreparationResult",
    "PaySimReferenceProfile",
    "PaySimRowError",
    "PaySimSchemaError",
    "PaySimSplitMode",
    "SnapshotArtifact",
    "SyntheticIdentityBustOutGenerator",
    "SyntheticIdentityConfigurationError",
    "build_reference_snapshot",
    "map_paysim_row",
    "prepare_paysim",
    "run_generation_scale_benchmark",
    "sha256_file",
    "validate_paysim_schema",
    "write_synthetic_identity_artifacts",
]
