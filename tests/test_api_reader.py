"""`aegis.api.reader` -- tolerant JSON/JSONL reading."""

from __future__ import annotations

from pathlib import Path

from aegis.api.reader import count_jsonl_rows, iter_jsonl, read_json


class TestReadJson:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert read_json(tmp_path / "does-not-exist.json") is None

    def test_malformed_json_returns_none_not_raise(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        assert read_json(path) is None

    def test_valid_json_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "good.json"
        path.write_text('{"a": 1, "b": [1, 2, 3]}', encoding="utf-8")
        assert read_json(path) == {"a": 1, "b": [1, 2, 3]}

    def test_directory_path_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "a_dir").mkdir()
        assert read_json(tmp_path / "a_dir") is None


class TestIterJsonl:
    def test_missing_file_yields_nothing(self, tmp_path: Path) -> None:
        assert list(iter_jsonl(tmp_path / "missing.jsonl")) == []

    def test_skips_malformed_lines_and_keeps_streaming(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_text('{"id": 1}\nnot json\n{"id": 2}\n\n{"id": 3}\n', encoding="utf-8")
        rows = list(iter_jsonl(path))
        assert [r["id"] for r in rows] == [1, 2, 3]

    def test_limit_stops_after_n_valid_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_text("\n".join(f'{{"id": {i}}}' for i in range(100)), encoding="utf-8")
        rows = list(iter_jsonl(path, limit=5))
        assert [r["id"] for r in rows] == [0, 1, 2, 3, 4]

    def test_skips_non_object_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_text('[1, 2, 3]\n{"id": 1}\n', encoding="utf-8")
        rows = list(iter_jsonl(path))
        assert rows == [{"id": 1}]


class TestCountJsonlRows:
    def test_missing_file_counts_zero(self, tmp_path: Path) -> None:
        assert count_jsonl_rows(tmp_path / "missing.jsonl") == 0

    def test_counts_only_well_formed_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_text('{"id": 1}\nnot json\n{"id": 2}\n\n', encoding="utf-8")
        assert count_jsonl_rows(path) == 2

    def test_never_materializes_full_content_in_return_value(self, tmp_path: Path) -> None:
        # Regression guard: this must return an int, not a list of rows.
        path = tmp_path / "rows.jsonl"
        path.write_text('{"id": 1}\n', encoding="utf-8")
        result = count_jsonl_rows(path)
        assert isinstance(result, int)
