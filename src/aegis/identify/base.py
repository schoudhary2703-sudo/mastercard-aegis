"""`BaseAttackIdentifier` - proposes attack blueprints.

Turns threat descriptions (analyst notes, typology write-ups, prior evasions)
into `AttackBlueprint` objects. It produces *specifications*, never
transactions - that is `generate/`'s job.

Deliberately absent: any LLM call, any agent framework. Phase 1 work.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import Field

from aegis.shared.base import AegisModel
from aegis.shared.contracts import AttackBlueprint
from aegis.shared.enums import AttackFamily


class IdentificationContext(AegisModel):
    """Input to blueprint proposal."""

    target_families: list[AttackFamily] = Field(
        default_factory=list, description="Families to propose for; empty means all in-scope."
    )
    threat_notes: list[str] = Field(
        default_factory=list, description="Free-text typology or intel snippets."
    )
    observed_feature_names: list[str] = Field(
        default_factory=list,
        description="Detector-visible feature names, so proposals can target them.",
    )
    max_blueprints: int = Field(default=5, ge=1)
    seed: int = Field(default=20260101)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseAttackIdentifier(ABC):
    """Abstract blueprint proposer.

    Contract for implementers: every returned blueprint must declare an
    in-scope `attack_family`, a non-empty `objective`, and `ParameterSpec`
    entries for anything the closed loop is expected to tune.
    """

    name: str = "base"
    version: str = "0.1.0"

    @abstractmethod
    def propose(self, context: IdentificationContext) -> list[AttackBlueprint]:
        """Return candidate attack blueprints for the given context."""


__all__ = ["BaseAttackIdentifier", "IdentificationContext"]
