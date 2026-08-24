"""Red Team: attack realisation.

Owned by the Red Team workstream. Contains the generator interface and its
configuration contract. Concrete generators are added here in Phase 1.

This package must not import from `defend/` or `features/`.
"""

from __future__ import annotations

from aegis.generate.base import BaseGenerator, BlueprintNotSupportedError
from aegis.generate.config import GenerationConfig
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

__all__ = [
    "DEFAULT_PAYSIM_CURRENCY",
    "DEFAULT_PAYSIM_EPOCH",
    "PAYSIM_REQUIRED_COLUMNS",
    "BaseGenerator",
    "BlueprintNotSupportedError",
    "GenerationConfig",
    "PaySimPreparationConfig",
    "PaySimPreparationError",
    "PaySimPreparationResult",
    "PaySimRowError",
    "PaySimSchemaError",
    "PaySimSplitMode",
    "map_paysim_row",
    "prepare_paysim",
    "validate_paysim_schema",
]
