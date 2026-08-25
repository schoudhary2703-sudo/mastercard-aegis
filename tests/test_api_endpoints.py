"""End-to-end tests for the FastAPI routes in `aegis.api.app`.

Each test points `AEGIS_ARTIFACTS_ROOT` at a throwaway fixture tree (see
`tests/api_fixtures.py`) rather than the real, git-ignored `data/`/`models/`
directories, so these tests pass in a fresh clone or CI with no pipeline run
performed first.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aegis.api import settings as settings_module
from aegis.api.app import app
from tests.api_fixtures import (
    BASELINE_VERSION,
    DEFENDER_V3_VERSION,
    HARDENED_VERSION,
    add_defender_v3_and_loafo_fold,
    write_empty_fixture,
    write_full_fixture,
)


@pytest.fixture
def full_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    write_full_fixture(tmp_path)
    monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
    settings_module.clear_settings_cache()
    client = TestClient(app)
    yield client
    settings_module.clear_settings_cache()


@pytest.fixture
def v3_and_loafo_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    write_full_fixture(tmp_path)
    add_defender_v3_and_loafo_fold(tmp_path)
    monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
    settings_module.clear_settings_cache()
    client = TestClient(app)
    yield client
    settings_module.clear_settings_cache()


@pytest.fixture
def empty_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    write_empty_fixture(tmp_path)
    monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
    settings_module.clear_settings_cache()
    client = TestClient(app)
    yield client
    settings_module.clear_settings_cache()


class TestHealth:
    def test_health(self, full_client: TestClient) -> None:
        r = full_client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestOverview:
    def test_full_fixture_reports_both_models_and_real_flag(self, full_client: TestClient) -> None:
        r = full_client.get("/api/overview")
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["data_source"] == "real"
        versions = {m["model_version"] for m in body["models"]}
        assert versions == {BASELINE_VERSION, HARDENED_VERSION}
        assert body["confrontation_count"] == 2
        assert body["adaptive_round_count"] == 2
        assert sorted(body["attack_families_in_scope"]) == sorted(
            ["synthetic_identity_bustout", "mule_network_structuring", "adaptive_detector_evasion"]
        )

    def test_empty_root_returns_empty_not_error(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/overview")
        assert r.status_code == 200
        body = r.json()
        assert body["models"] == []
        assert body["confrontation_count"] == 0
        assert body["adaptive_round_count"] == 0
        assert body["hardest_evasions_preview"] == []
        assert body["regression"] is None

    def test_loafo_fold_excluded_and_v3_is_current_model(
        self, v3_and_loafo_client: TestClient
    ) -> None:
        r = v3_and_loafo_client.get("/api/overview")
        assert r.status_code == 200
        body = r.json()
        versions = {m["model_version"] for m in body["models"]}
        # Exactly the three core lineage models -- the LOAFO fold model does
        # not count as a fourth "model trained".
        assert versions == {BASELINE_VERSION, HARDENED_VERSION, DEFENDER_V3_VERSION}
        assert body["current_model"] is not None
        assert body["current_model"]["model_version"] == DEFENDER_V3_VERSION
        assert body["current_model"]["role"] == "defender_v3"


class TestEvolutionHardeningRunSelection:
    def test_hardening_stage_ignores_loafo_fold_run(
        self, v3_and_loafo_client: TestClient
    ) -> None:
        r = v3_and_loafo_client.get("/api/evolution")
        assert r.status_code == 200
        stages = {s["stage"]: s for s in r.json()["stages"]}
        hardening = stages["defender_v2_hardening"]["hardening"]
        assert hardening is not None
        # Must resolve to the real Defender v2 hardening run, not the
        # LOAFO-fold run whose id sorts later alphabetically.
        assert hardening["run_id"] == "hard-positives-fixture"


class TestAttacks:
    def test_lists_blueprints_from_confrontations_and_adaptive_rounds(
        self, full_client: TestClient
    ) -> None:
        r = full_client.get("/api/attacks")
        assert r.status_code == 200
        attack_ids = {a["attack_id"] for a in r.json()["attacks"]}
        assert "synthetic-identity-bustout-v1" in attack_ids
        assert "synthetic-identity-bustout-v1-g1-fixture" in attack_ids
        assert "synthetic-identity-bustout-v1-g1-gen2-fixture" in attack_ids

    def test_empty_root_returns_empty_list(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/attacks")
        assert r.status_code == 200
        assert r.json()["attacks"] == []

    def test_attack_detail_for_known_id(self, full_client: TestClient) -> None:
        r = full_client.get("/api/attacks/synthetic-identity-bustout-v1")
        assert r.status_code == 200
        body = r.json()
        assert body["attack_id"] == "synthetic-identity-bustout-v1"
        # Both fixture confrontations attack with this same base blueprint id.
        report_ids = {c["report_id"] for c in body["confrontation_results"]}
        assert report_ids == {"confrontation-round0", "confrontation-fresh"}

    def test_attack_detail_404_for_unknown_id(self, full_client: TestClient) -> None:
        r = full_client.get("/api/attacks/does-not-exist-anywhere")
        assert r.status_code == 404

    @pytest.mark.parametrize("bad_id", ["..%2F..%2Fetc%2Fpasswd", "a%2Fb", "%2e%2e"])
    def test_attack_detail_rejects_path_traversal_attempts(
        self, full_client: TestClient, bad_id: str
    ) -> None:
        r = full_client.get(f"/api/attacks/{bad_id}")
        assert r.status_code in (400, 404)


class TestEvolution:
    def test_full_fixture_has_all_six_real_stages(self, full_client: TestClient) -> None:
        r = full_client.get("/api/evolution")
        assert r.status_code == 200
        body = r.json()
        stages = {s["stage"]: s["status"] for s in body["stages"]}
        assert stages == {
            "baseline_v1": "real",
            "round_0_attack": "real",
            "adaptive_red": "real",
            "defender_v2_hardening": "real",
            "fresh_confrontation": "real",
            "generation_2_adaptation": "real",
        }
        assert len(body["narrative"]) > 0
        # Honest wording required by the integration brief.
        assert any(
            "not robustly hardened" in line or "declined" in line for line in body["narrative"]
        )
        assert not any("100%" in line and "always" in line for line in body["narrative"])

    def test_empty_root_marks_every_stage_not_run_yet(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/evolution")
        assert r.status_code == 200
        body = r.json()
        statuses = {s["status"] for s in body["stages"]}
        assert statuses == {"not_run_yet"}
        for stage in body["stages"]:
            assert stage["model"] is None
            assert stage["confrontation"] is None
            assert stage["adaptive_round"] is None
        assert (
            "has not run" in body["narrative"][0]
            or "have not run" in body["narrative"][0]
            or "no closed-loop" in body["narrative"][0].lower()
        )

    def test_defender_v2_stage_carries_regression_and_hardening(
        self, full_client: TestClient
    ) -> None:
        r = full_client.get("/api/evolution")
        body = r.json()
        stage = next(s for s in body["stages"] if s["stage"] == "defender_v2_hardening")
        assert stage["regression"] is not None
        assert stage["regression"]["baseline_model_version"] == BASELINE_VERSION
        assert stage["regression"]["defender_v2_model_version"] == HARDENED_VERSION
        assert stage["hardening"] is not None
        assert stage["hardening"]["hard_positive_count"] == 4


class TestEvaluation:
    def test_returns_evaluations_for_both_models_plus_regression(
        self, full_client: TestClient
    ) -> None:
        r = full_client.get("/api/evaluation")
        assert r.status_code == 200
        body = r.json()
        model_versions = {e["model_version"] for e in body["evaluations"]}
        assert model_versions == {BASELINE_VERSION, HARDENED_VERSION}
        splits = {e["split"] for e in body["evaluations"]}
        assert splits == {"test", "validation"}
        assert body["regression"] is not None

    def test_empty_root_returns_empty_evaluations(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/evaluation")
        assert r.status_code == 200
        assert r.json()["evaluations"] == []
        assert r.json()["regression"] is None


class TestHardestEvasions:
    def test_sorted_descending_by_hardness_and_respects_limit(
        self, full_client: TestClient
    ) -> None:
        r = full_client.get("/api/hardest-evasions?limit=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["evasions"]) == 2
        assert body["limit"] == 2
        assert body["total_available"] >= 2
        scores = [e["hardness_score"] for e in body["evasions"] if e["hardness_score"] is not None]
        assert scores == sorted(scores, reverse=True)

    def test_each_evasion_carries_provenance_fields(self, full_client: TestClient) -> None:
        r = full_client.get("/api/hardest-evasions")
        for e in r.json()["evasions"]:
            assert e["source_round"]
            assert e["source_artifact"]
            assert e["detector_model_version"]

    def test_empty_root_returns_empty(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/hardest-evasions")
        assert r.status_code == 200
        assert r.json()["evasions"] == []
        assert r.json()["total_available"] == 0


class TestRecentDetections:
    def test_respects_limit_query_param(self, full_client: TestClient) -> None:
        r = full_client.get("/api/detections/recent?limit=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["detections"]) <= 2
        assert body["limit"] == 2

    def test_joins_transaction_context_onto_detector_output(self, full_client: TestClient) -> None:
        r = full_client.get("/api/detections/recent?limit=50")
        body = r.json()
        assert body["total_available"] > 0
        joined = [d for d in body["detections"] if d["scenario_id"] is not None]
        assert len(joined) > 0

    def test_empty_root_returns_empty(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/detections/recent")
        assert r.status_code == 200
        assert r.json()["detections"] == []
        assert r.json()["total_available"] == 0

    def test_limit_out_of_range_is_rejected(self, full_client: TestClient) -> None:
        r = full_client.get("/api/detections/recent?limit=0")
        assert r.status_code == 422
        r = full_client.get("/api/detections/recent?limit=100000")
        assert r.status_code == 422
