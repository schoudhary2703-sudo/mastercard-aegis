"""Red Team: attack realisation.

Owned by the Red Team workstream. Contains the generator interface and its
configuration contract. Concrete generators are added here in Phase 1.

This package must not import from `defend/` or `features/`.
"""

from __future__ import annotations

from aegis.generate.base import BaseGenerator, BlueprintNotSupportedError
from aegis.generate.config import GenerationConfig

__all__ = ["BaseGenerator", "BlueprintNotSupportedError", "GenerationConfig"]
