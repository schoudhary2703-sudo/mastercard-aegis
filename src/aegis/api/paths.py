"""Safe filesystem access for the artifact-reading layer.

Every path the API touches is derived from a pre-built `ArtifactIndex`
(`index.py`), never straight from a URL segment. These helpers are the
defense-in-depth layer underneath that: even a programming mistake that lets
an unvalidated id reach the filesystem cannot escape `artifacts_root`.
"""

from __future__ import annotations

import re
from pathlib import Path

# Artifact ids and directory names observed in this project are short,
# URL-safe slugs (report ids, model versions, blueprint/candidate ids).
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ArtifactPathError(ValueError):
    """A requested path is invalid or would escape the artifacts root."""


def validate_slug(value: str, *, field: str = "id") -> str:
    """Reject anything that is not a plain, single-segment identifier.

    Blocks path separators, `..`, absolute paths, and empty/oversized values
    before they ever reach a filesystem call.
    """
    if not isinstance(value, str) or not _SLUG_RE.match(value):
        msg = f"invalid {field}: {value!r}"
        raise ArtifactPathError(msg)
    return value


def resolve_within(root: Path, *parts: str) -> Path:
    """Join `parts` onto `root` and confirm the result stays inside it.

    Applied even to paths built from already-validated slugs, so a future
    caller that forgets to validate still cannot traverse out via a crafted
    directory name on disk.
    """
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_root):
        msg = f"path escapes artifacts root: {parts!r}"
        raise ArtifactPathError(msg)
    return candidate


def safe_child_dirs(root: Path, relative: str) -> list[Path]:
    """List immediate subdirectories of `root/relative`, sorted by name.

    Returns an empty list if the parent directory does not exist -- a
    workstream that has not produced artifacts yet is not an error.
    """
    parent = resolve_within(root, relative)
    if not parent.is_dir():
        return []
    return sorted((p for p in parent.iterdir() if p.is_dir()), key=lambda p: p.name)
