"""Runtime configuration for the API service.

Everything here is read from the environment so tests and CI can point the
service at a throwaway fixture directory instead of the real (git-ignored)
`data/` and `models/` trees.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# src/aegis/api/settings.py -> repo root is four parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings:
    """Resolved configuration for one process."""

    def __init__(self, *, artifacts_root: Path, cors_origins: list[str]) -> None:
        self.artifacts_root = artifacts_root
        self.cors_origins = cors_origins


def _default_cors_origins() -> list[str]:
    raw = os.environ.get("AEGIS_API_CORS_ORIGINS")
    if not raw:
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def load_settings() -> Settings:
    """Build a fresh `Settings` from the current environment.

    Not cached: tests mutate `AEGIS_ARTIFACTS_ROOT` between cases and expect a
    fresh read each time. `get_settings()` below is the cached, app-wide entry
    point; call `load_settings()` directly when you need an uncached read.
    """
    root_env = os.environ.get("AEGIS_ARTIFACTS_ROOT")
    root = Path(root_env).resolve() if root_env else _REPO_ROOT
    return Settings(artifacts_root=root, cors_origins=_default_cors_origins())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
