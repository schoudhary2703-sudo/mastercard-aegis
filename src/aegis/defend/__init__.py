"""Blue Team: detection, scoring, decisioning.

Owned by the Blue Team workstream. Contains the detector interface and the
score-to-action policy. Concrete detectors are added here in Phase 1.

This package must not import from `generate/`, `identify/` or `loop/`.
"""

from __future__ import annotations

from aegis.defend.base import BaseDetector, NotFittedError
from aegis.defend.policy import DEFAULT_ACTION_POLICY, ActionPolicy

__all__ = ["DEFAULT_ACTION_POLICY", "ActionPolicy", "BaseDetector", "NotFittedError"]
