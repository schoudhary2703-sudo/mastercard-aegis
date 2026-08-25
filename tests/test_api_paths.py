"""`aegis.api.paths` -- slug validation and traversal rejection."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.api.paths import ArtifactPathError, resolve_within, safe_child_dirs, validate_slug


class TestValidateSlug:
    def test_accepts_plain_ids(self) -> None:
        assert validate_slug("confrontation-416e606888de1ffa") == "confrontation-416e606888de1ffa"
        assert validate_slug("xgboost-baseline-20260101") == "xgboost-baseline-20260101"
        assert (
            validate_slug("synthetic-identity-bustout-v1.g1_x")
            == "synthetic-identity-bustout-v1.g1_x"
        )

    @pytest.mark.parametrize(
        "value",
        [
            "../../etc/passwd",
            "..\\..\\windows\\system32",
            "a/b",
            "a\\b",
            "",
            ".",
            "..",
            "a" * 200,
        ],
    )
    def test_rejects_traversal_and_malformed_ids(self, value: str) -> None:
        with pytest.raises(ArtifactPathError):
            validate_slug(value)


class TestResolveWithin:
    def test_resolves_a_normal_child_path(self, tmp_path: Path) -> None:
        (tmp_path / "data").mkdir()
        result = resolve_within(tmp_path, "data")
        assert result == (tmp_path / "data").resolve()

    def test_rejects_dot_dot_escape(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        with pytest.raises(ArtifactPathError):
            resolve_within(root, "..", "outside.txt")

    def test_rejects_absolute_escape_via_multiple_parts(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        with pytest.raises(ArtifactPathError):
            resolve_within(root, "a", "..", "..", "b")


class TestSafeChildDirs:
    def test_missing_parent_returns_empty(self, tmp_path: Path) -> None:
        assert safe_child_dirs(tmp_path, "does/not/exist") == []

    def test_lists_only_directories_sorted_by_name(self, tmp_path: Path) -> None:
        base = tmp_path / "confrontations"
        (base / "b-dir").mkdir(parents=True)
        (base / "a-dir").mkdir(parents=True)
        (base / "not-a-dir.txt").write_text("x", encoding="utf-8")
        names = [p.name for p in safe_child_dirs(tmp_path, "confrontations")]
        assert names == ["a-dir", "b-dir"]
