"""Contract versioning.

`CONTRACT_VERSION` is bumped whenever a field is added, removed, renamed or
retyped in `aegis.shared.contracts`. Red Team and Blue Team artifacts record the
version they were produced under so that a mismatch is loud rather than silent.

Bump rules (semver-ish):
  * MAJOR - a field is removed, renamed, or changes meaning. Breaks both teams.
  * MINOR - an optional field is added. Backwards compatible.
  * PATCH - docs, validators, or defaults change without altering the shape.

Changing this file requires agreement from BOTH workstreams. See AGENTS.md.
"""

from __future__ import annotations

from typing import Final

CONTRACT_VERSION: Final[str] = "1.0.0"
"""Version of the cross-team data contracts in `aegis.shared.contracts`."""

SCHEMA_NAMESPACE: Final[str] = "aegis.contracts"
"""Stable namespace prefix used when contracts are exported as JSON Schema."""
