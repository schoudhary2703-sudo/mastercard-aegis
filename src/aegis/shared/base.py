"""Base model shared by every AEGIS contract.

Every contract inherits from `AegisModel` so that validation and serialization
behaviour is identical across modules. Two settings matter most:

* ``extra="forbid"`` - an unknown key is an error, not a silent no-op. This is
  what stops the two workstreams from drifting apart via undeclared fields.
* ``protected_namespaces=()`` - allows fields such as ``model_version`` that
  would otherwise collide with pydantic's reserved ``model_`` prefix.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class AegisModel(BaseModel):
    """Common configuration for all AEGIS contracts."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        validate_default=True,
        str_strip_whitespace=True,
        protected_namespaces=(),
        populate_by_name=True,
        ser_json_timedelta="float",
    )

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialize to a JSON string. Round-trips through `from_json`."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, payload: str | bytes) -> Any:
        """Deserialize from a JSON string produced by `to_json`."""
        return cls.model_validate_json(payload)
