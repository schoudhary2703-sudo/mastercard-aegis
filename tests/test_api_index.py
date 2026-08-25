"""`aegis.api.index` -- artifact discovery and lineage resolution."""

from __future__ import annotations

from pathlib import Path

from aegis.api.index import ArtifactIndex
from tests.api_fixtures import (
    BASELINE_VERSION,
    HARDENED_VERSION,
    write_empty_fixture,
    write_full_fixture,
)


class TestEmptyArtifactsRoot:
    def test_discovery_does_not_raise_on_empty_root(self, tmp_path: Path) -> None:
        write_empty_fixture(tmp_path)
        index = ArtifactIndex(tmp_path)
        assert index.models == []
        assert index.confrontations == []
        assert index.adaptive_rounds == []
        assert index.hardening_runs == []

    def test_discovery_does_not_raise_on_missing_root(self, tmp_path: Path) -> None:
        index = ArtifactIndex(tmp_path / "does-not-exist-at-all")
        assert index.models == []
        assert index.baseline_model() is None
        assert index.hardened_model() is None


class TestFullFixtureDiscovery:
    def test_discovers_both_models(self, tmp_path: Path) -> None:
        write_full_fixture(tmp_path)
        index = ArtifactIndex(tmp_path)
        versions = {m.model_version for m in index.models}
        assert versions == {BASELINE_VERSION, HARDENED_VERSION}

    def test_baseline_and_hardened_are_distinguished_by_handoff_presence(
        self, tmp_path: Path
    ) -> None:
        write_full_fixture(tmp_path)
        index = ArtifactIndex(tmp_path)
        baseline = index.baseline_model()
        hardened = index.hardened_model()
        assert baseline is not None and baseline.model_version == BASELINE_VERSION
        assert hardened is not None and hardened.model_version == HARDENED_VERSION
        assert baseline.is_hardened is False
        assert hardened.is_hardened is True

    def test_discovers_confrontations_and_adaptive_rounds(self, tmp_path: Path) -> None:
        write_full_fixture(tmp_path)
        index = ArtifactIndex(tmp_path)
        assert len(index.confrontations) == 2
        assert len(index.adaptive_rounds) == 2

    def test_adaptive_round_candidates_are_discovered(self, tmp_path: Path) -> None:
        write_full_fixture(tmp_path)
        index = ArtifactIndex(tmp_path)
        round1 = index.adaptive_round_by_id("adaptive-round-1-fixture")
        assert round1 is not None
        assert len(round1.candidates) == 1

    def test_lineage_links_round0_to_adaptive1(self, tmp_path: Path) -> None:
        write_full_fixture(tmp_path)
        index = ArtifactIndex(tmp_path)
        baseline = index.baseline_model()
        assert baseline is not None
        round0 = index.earliest_confrontation_for_model(baseline.model_version, adaptive=False)
        assert round0 is not None
        assert round0.report_id == "confrontation-round0"
        adaptive1 = index.adaptive_round_by_parent(round0.report_id)
        assert adaptive1 is not None
        assert adaptive1.report_id == "adaptive-round-1-fixture"

    def test_lineage_links_fresh_confrontation_to_generation2(self, tmp_path: Path) -> None:
        write_full_fixture(tmp_path)
        index = ArtifactIndex(tmp_path)
        hardened = index.hardened_model()
        assert hardened is not None
        fresh = index.earliest_confrontation_for_model(hardened.model_version, adaptive=False)
        assert fresh is not None
        assert fresh.report_id == "confrontation-fresh"
        gen2 = index.adaptive_round_by_parent(fresh.report_id)
        assert gen2 is not None
        assert gen2.report_id == "adaptive-round-1-gen2-fixture"

    def test_hardening_run_is_discovered_with_streamed_count(self, tmp_path: Path) -> None:
        write_full_fixture(tmp_path)
        index = ArtifactIndex(tmp_path)
        assert len(index.hardening_runs) == 1
        assert index.hardening_runs[0].hard_positive_count == 4


class TestMalformedArtifactTolerance:
    def test_one_malformed_model_dir_does_not_break_discovery_of_others(
        self, tmp_path: Path
    ) -> None:
        write_full_fixture(tmp_path)
        # Corrupt the baseline model's metadata.json.
        bad = tmp_path / "models" / BASELINE_VERSION / "metadata.json"
        bad.write_text("{this is not json", encoding="utf-8")

        index = ArtifactIndex(tmp_path)
        versions = {m.model_version for m in index.models}
        # The corrupted model is skipped; the hardened one is still discovered.
        assert versions == {HARDENED_VERSION}

    def test_malformed_confrontation_report_is_skipped(self, tmp_path: Path) -> None:
        write_full_fixture(tmp_path)
        bad = (
            tmp_path
            / "data"
            / "synthetic"
            / "confrontations"
            / "confrontation-round0"
            / "confrontation.json"
        )
        bad.write_text("not json at all", encoding="utf-8")

        index = ArtifactIndex(tmp_path)
        report_ids = {c.report_id for c in index.confrontations}
        assert report_ids == {"confrontation-fresh"}

    def test_missing_optional_hardest_evasions_file_is_tolerated(self, tmp_path: Path) -> None:
        write_full_fixture(tmp_path)
        (
            tmp_path
            / "data"
            / "synthetic"
            / "confrontations"
            / "confrontation-round0"
            / "hardest_evasions.json"
        ).unlink()

        index = ArtifactIndex(tmp_path)
        round0 = index.confrontation_by_id("confrontation-round0")
        assert round0 is not None
        # confrontation.json itself still carries hardest_evasions inline, so
        # the ConfrontationArtifact's own `hardest_evasions` field (populated
        # from the standalone file) is empty but discovery does not fail.
        assert round0.hardest_evasions == []
