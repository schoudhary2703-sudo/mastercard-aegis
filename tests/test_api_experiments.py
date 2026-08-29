"""`/api/experiments` and `/api/genai` -- the two endpoints the redesigned
judge-facing UI reads.

Both are exercised against throwaway fixture trees, never the real
git-ignored artifacts, so they pass in a fresh clone. The assertions that
matter most are the honesty ones: a partial per-transaction stream must
report itself as partial, and an absent GenAI run must produce an empty
response rather than placeholder reasoning.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aegis.api import settings as settings_module
from aegis.api.app import app
from tests.api_fixtures import write_empty_fixture, write_full_fixture


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_loafo_fold_fixture(root: Path) -> None:
    """A LOAFO fold whose fresh scenario kept only its surviving evasions."""
    _write_json(
        root / "models" / "loafo-fixture-fold" / "loafo_fold_report.json",
        {
            "fold_id": "fold-fixture",
            "held_out_family": "mule_network_structuring",
            "model_version": "loafo-fixture-model",
            "training_families": ["synthetic_identity_bustout", "adaptive_detector_evasion"],
            "fresh_held_out_evaluation": {
                "scenario_id": "mule-fixture-scenario",
                "fraud_count": 4,
                "caught_count": 1,
                "evaded_count": 3,
                "recall": 0.25,
                "fidelity_score": 0.84,
                "hardest_evasions": [
                    {
                        "rank": 1,
                        "scenario_id": "mule-fixture-scenario",
                        "transaction_id": "mule-fixture-002",
                        "attack_family": "mule_network_structuring",
                        "blueprint_id": "mule-network-structuring-v1",
                        "generation": 0,
                        "detector_risk_score": 0.02,
                        "fidelity_score": 0.84,
                        "hardness_score": 0.81,
                        "action": "approve",
                        "detector_model_version": "loafo-fixture-model",
                        "ground_truth_label": 1,
                        "credible_evasion": True,
                        "sequence_index": 2,
                    }
                ],
                "defender_v3_evaluation": {
                    "model_version": "xgboost-hardened-v3-fixture",
                    "overall": {
                        "precision": 1.0,
                        "recall": 0.5,
                        "f1": 0.667,
                        "false_positive_rate": 0.0,
                        "counts": {
                            "true_positives": 2,
                            "false_positives": 0,
                            "true_negatives": 5,
                            "false_negatives": 2,
                        },
                    },
                },
            },
        },
    )


@pytest.fixture
def experiments_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    write_full_fixture(tmp_path)
    write_loafo_fold_fixture(tmp_path)
    monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
    settings_module.clear_settings_cache()
    yield TestClient(app)
    settings_module.clear_settings_cache()


@pytest.fixture
def empty_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    write_empty_fixture(tmp_path)
    monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
    settings_module.clear_settings_cache()
    yield TestClient(app)
    settings_module.clear_settings_cache()


class TestExperimentsEndpoint:
    def test_returns_one_experiment_per_available_family(
        self, experiments_client: TestClient
    ) -> None:
        r = experiments_client.get("/api/experiments")
        assert r.status_code == 200
        families = {e["attack_family"] for e in r.json()["experiments"]}
        assert "synthetic_identity_bustout" in families
        assert "mule_network_structuring" in families

    def test_confrontation_stream_is_complete_and_real(
        self, experiments_client: TestClient
    ) -> None:
        body = experiments_client.get("/api/experiments").json()
        bustout = next(
            e for e in body["experiments"] if e["attack_family"] == "synthetic_identity_bustout"
        )
        assert bustout["events_complete"] is True
        assert bustout["events_note"] is None
        # Every event is a scored transaction, not a generated one.
        assert len(bustout["events"]) > 0
        assert all("transaction_id" in ev and "risk_score" in ev for ev in bustout["events"])
        # Fraud rows are flagged, and caught implies fraud.
        assert any(ev["is_fraud"] for ev in bustout["events"])
        assert all(ev["is_fraud"] for ev in bustout["events"] if ev["caught"])

    def test_partial_loafo_stream_is_labelled_partial(
        self, experiments_client: TestClient
    ) -> None:
        """A fold that kept only its survivors must say so, not imply a full run."""
        body = experiments_client.get("/api/experiments").json()
        mule = next(
            e for e in body["experiments"] if e["attack_family"] == "mule_network_structuring"
        )
        assert mule["events_complete"] is False
        assert mule["events_note"]
        # 3 evaded but only 1 persisted -- the note must not claim otherwise.
        assert mule["escaped_count"] == 3
        assert len(mule["events"]) == 1
        assert "1 of 3" in mule["events_note"]

    def test_counters_match_the_persisted_report(self, experiments_client: TestClient) -> None:
        body = experiments_client.get("/api/experiments").json()
        mule = next(
            e for e in body["experiments"] if e["attack_family"] == "mule_network_structuring"
        )
        assert mule["fraud_count"] == 4
        assert mule["caught_count"] == 1
        assert mule["escaped_count"] == 3
        assert mule["recall"] == pytest.approx(0.25)

    def test_progression_carries_before_and_after(self, experiments_client: TestClient) -> None:
        body = experiments_client.get("/api/experiments").json()
        bustout = next(
            e for e in body["experiments"] if e["attack_family"] == "synthetic_identity_bustout"
        )
        labels = [p["label"] for p in bustout["progression"]]
        assert labels == ["Baseline v1", "Defender v2"]
        # Round-0 caught nothing; the hardened generation caught more.
        assert bustout["progression"][0]["caught_count"] == 0
        assert bustout["progression"][1]["caught_count"] > 0

    def test_current_defender_is_not_the_handicapped_fold_model(
        self, experiments_client: TestClient
    ) -> None:
        """The fold model had this family withheld from training and scores
        far worse by design. `current_defender` must report Defender v3's
        result instead, so a caller aggregating "how does the defender do"
        cannot accidentally sum in a deliberately crippled model."""
        body = experiments_client.get("/api/experiments").json()
        mule = next(
            e for e in body["experiments"] if e["attack_family"] == "mule_network_structuring"
        )
        # The replayed stream is the fold model's...
        assert mule["replayed_model_label"] == "LOAFO fold (family held out)"
        assert mule["caught_count"] == 1
        # ...but the current defender caught more of the same scenario.
        current = mule["current_defender"]
        assert current is not None
        assert current["role"] == "defender_v3"
        assert current["caught_count"] == 2
        assert current["escaped_count"] == 2
        assert current["caught_count"] > mule["caught_count"]

    def test_confrontation_current_defender_is_the_replayed_run(
        self, experiments_client: TestClient
    ) -> None:
        """For a full-stream family the replay and the current defender are
        the same run, so the two must agree exactly."""
        body = experiments_client.get("/api/experiments").json()
        bustout = next(
            e for e in body["experiments"] if e["attack_family"] == "synthetic_identity_bustout"
        )
        current = bustout["current_defender"]
        assert current is not None
        assert current["caught_count"] == bustout["caught_count"]
        assert current["fraud_count"] == bustout["fraud_count"]
        assert bustout["replayed_model_label"] == current["label"]

    def test_hardest_survivor_gets_provenance(self, experiments_client: TestClient) -> None:
        body = experiments_client.get("/api/experiments").json()
        mule = next(
            e for e in body["experiments"] if e["attack_family"] == "mule_network_structuring"
        )
        survivor = mule["hardest_survivor"]
        assert survivor is not None
        assert survivor["source_artifact"].endswith("loafo_fold_report.json")
        assert survivor["source_round"].startswith("loafo:")

    def test_empty_root_returns_empty_not_error(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/experiments")
        assert r.status_code == 200
        assert r.json()["experiments"] == []


class TestGenAIEndpoint:
    def test_no_runs_returns_empty_not_placeholder(self, empty_client: TestClient) -> None:
        """The honest-empty path: no GenAI run means no reasoning is shown."""
        r = empty_client.get("/api/genai")
        assert r.status_code == 200
        body = r.json()
        assert body["runs"] == []
        assert body["attack_analyst"] is None
        assert body["blind_spot_analyst"] is None

    def test_persisted_run_is_surfaced_with_provenance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_json(
            tmp_path / "data" / "genai" / "attack_analyst" / "attack_analyst-abc.json",
            {
                "run_id": "attack_analyst-abc",
                "stage": "attack_analyst",
                "created_at": "2026-08-01T00:00:00Z",
                "provenance": {
                    "provider": "anthropic",
                    "model": "claude-opus-5",
                    "prompt_version": "genai-prompts-v1",
                    "live": True,
                    "attempts": 1,
                    "source_artifacts": [],
                },
                "request": {},
                "response": {"attack_hypothesis": "fixture hypothesis", "confidence": 0.6},
                "schema_valid": True,
                "failure": None,
            },
        )
        monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
        settings_module.clear_settings_cache()
        client = TestClient(app)

        body = client.get("/api/genai").json()
        assert len(body["runs"]) == 1
        analyst = body["attack_analyst"]
        assert analyst is not None
        assert analyst["provider"] == "anthropic"
        assert analyst["model"] == "claude-opus-5"
        assert analyst["prompt_version"] == "genai-prompts-v1"
        assert analyst["live"] is True
        assert analyst["response"]["attack_hypothesis"] == "fixture hypothesis"
        settings_module.clear_settings_cache()

    def test_recorded_run_stays_marked_not_live(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_json(
            tmp_path / "data" / "genai" / "blind_spot_analyst" / "blind_spot-xyz.json",
            {
                "run_id": "blind_spot-xyz",
                "stage": "blind_spot_analyst",
                "created_at": "2026-08-02T00:00:00Z",
                "provenance": {
                    "provider": "recorded",
                    "model": "claude-opus-5",
                    "prompt_version": "genai-prompts-v1",
                    "live": False,
                    "attempts": 1,
                    "source_artifacts": [],
                },
                "request": {},
                "response": {"blind_spot_hypothesis": "fixture blind spot", "confidence": 0.5},
                "schema_valid": True,
                "failure": None,
            },
        )
        monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
        settings_module.clear_settings_cache()
        client = TestClient(app)

        blind = client.get("/api/genai").json()["blind_spot_analyst"]
        assert blind is not None
        assert blind["provider"] == "recorded"
        assert blind["live"] is False
        settings_module.clear_settings_cache()

    def test_empty_state_includes_the_live_and_guided_fields(
        self, empty_client: TestClient
    ) -> None:
        """Task-4 readiness: every field the UI needs exists and is honestly
        empty, so the panel renders "not run yet" rather than breaking."""
        body = empty_client.get("/api/genai").json()
        assert body["live_attack_analyst"] is None
        assert body["live_blind_spot_analyst"] is None
        assert body["guided_generations"] == []
        assert body["latest_guided_generation"] is None
        assert body["has_live_genai"] is False

    def test_recorded_run_is_never_offered_as_a_live_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A replay populates `blind_spot_analyst` but must leave the `live_*`
        slot empty -- the UI badges LIVE off the live slot only."""
        _write_json(
            tmp_path / "data" / "genai" / "blind_spot_analyst" / "recorded.json",
            {
                "run_id": "blind_spot-recorded",
                "stage": "blind_spot_analyst",
                "created_at": "2026-08-02T00:00:00Z",
                "provenance": {
                    "provider": "recorded",
                    "model": "claude-opus-5",
                    "prompt_version": "genai-prompts-v1",
                    "live": False,
                    "attempts": 1,
                    "source_artifacts": [],
                },
                "request": {},
                "response": {"blind_spot_hypothesis": "replayed", "confidence": 0.5},
                "schema_valid": True,
                "failure": None,
            },
        )
        monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
        settings_module.clear_settings_cache()
        body = TestClient(app).get("/api/genai").json()

        assert body["blind_spot_analyst"] is not None
        assert body["blind_spot_analyst"]["live"] is False
        assert body["live_blind_spot_analyst"] is None
        assert body["has_live_genai"] is False
        settings_module.clear_settings_cache()

    def test_live_run_populates_the_live_slot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_json(
            tmp_path / "data" / "genai" / "attack_analyst" / "live.json",
            {
                "run_id": "attack_analyst-live",
                "stage": "attack_analyst",
                "created_at": "2026-08-05T00:00:00Z",
                "provenance": {
                    "provider": "anthropic",
                    "model": "claude-opus-5",
                    "prompt_version": "genai-prompts-v1",
                    "live": True,
                    "attempts": 1,
                    "source_artifacts": [],
                },
                "request": {},
                "response": {
                    "attack_hypothesis": "Nurture then burst.",
                    "genai_enablement": "Drafting warm-up cheaply.",
                    "observable_signals": ["temporal.amount"],
                    "confidence": 0.6,
                },
                "schema_valid": True,
                "failure": None,
            },
        )
        monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
        settings_module.clear_settings_cache()
        body = TestClient(app).get("/api/genai").json()

        live = body["live_attack_analyst"]
        assert live is not None
        assert live["live"] is True
        assert body["has_live_genai"] is True
        # Projections the UI renders as one-liners.
        assert live["attack_hypothesis"] == "Nurture then burst."
        assert live["genai_enablement"] == "Drafting warm-up cheaply."
        assert live["observable_signals"] == ["temporal.amount"]
        settings_module.clear_settings_cache()

    def test_guided_generation_is_exposed_with_provenance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_json(
            tmp_path / "data" / "genai" / "guided_generations" / "gen-1.json",
            {
                "generation_id": "gen-1",
                "created_at": "2026-08-10T00:00:00Z",
                "attack_family": "synthetic_identity_bustout",
                "provenance": {
                    "genai_run_id": "blind_spot-abc",
                    "provider": "anthropic",
                    "model": "claude-opus-5",
                    "prompt_version": "genai-prompts-v1",
                    "live": True,
                    "seed": 20260101,
                    "source_confrontation_id": "confrontation-test",
                    "detector_model_version": "xgboost-hardened-crossfamily-20260301",
                },
                "blind_spot_hypothesis": "velocity under-weights fan-out",
                "applied_mutations": [
                    {
                        "parameter": "destination_diversity",
                        "direction": "increase",
                        "magnitude": 0.2,
                        "from_value": 3.0,
                        "to_value": 5.0,
                        "rationale": "spread the burst",
                        "confidence": 0.6,
                    }
                ],
                "rejected_mutations": [],
                "parent_blueprint_id": "synthetic-identity-bustout-v1",
                "resulting_blueprint_id": "synthetic-identity-bustout-v1-g1-abc123",
                "scenario_id": "bustout-guided-0001",
                "fraud_count": 3,
                "caught_count": 1,
                "escaped_count": 2,
                "recall": 0.3333,
                "dry_run": False,
            },
        )
        monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
        settings_module.clear_settings_cache()
        body = TestClient(app).get("/api/genai").json()

        gen = body["latest_guided_generation"]
        assert gen is not None
        assert gen["genai_guided"] is True
        assert gen["seed"] == 20260101
        assert gen["scenario_id"] == "bustout-guided-0001"
        assert gen["caught_count"] == 1 and gen["escaped_count"] == 2
        mutation = gen["applied_mutations"][0]
        assert mutation["parameter"] == "destination_diversity"
        assert mutation["from_value"] == 3.0 and mutation["to_value"] == 5.0
        settings_module.clear_settings_cache()

    def test_guided_generation_without_provenance_is_not_labelled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Served, but never badged GenAI-guided -- nothing to audit."""
        _write_json(
            tmp_path / "data" / "genai" / "guided_generations" / "gen-2.json",
            {
                "generation_id": "gen-2",
                "created_at": "2026-08-11T00:00:00Z",
                "provenance": {"provider": "", "model": "", "prompt_version": ""},
                "applied_mutations": [
                    {"parameter": "destination_diversity", "direction": "increase"}
                ],
                "dry_run": True,
            },
        )
        monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
        settings_module.clear_settings_cache()
        body = TestClient(app).get("/api/genai").json()

        assert body["latest_guided_generation"]["genai_guided"] is False
        settings_module.clear_settings_cache()

    def test_guided_generations_dir_is_not_read_as_an_analyst_stage(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_json(
            tmp_path / "data" / "genai" / "guided_generations" / "gen-3.json",
            {
                "generation_id": "gen-3",
                "provenance": {"provider": "anthropic", "model": "m", "prompt_version": "v"},
                "applied_mutations": [],
            },
        )
        monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
        settings_module.clear_settings_cache()
        body = TestClient(app).get("/api/genai").json()

        assert body["runs"] == []
        assert body["attack_analyst"] is None
        assert len(body["guided_generations"]) == 1
        settings_module.clear_settings_cache()

    def test_failed_run_is_not_promoted_as_the_latest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A schema failure must never be shown as the analyst's output."""
        _write_json(
            tmp_path / "data" / "genai" / "attack_analyst" / "attack_analyst-bad.json",
            {
                "run_id": "attack_analyst-bad",
                "stage": "attack_analyst",
                "created_at": "2026-08-09T00:00:00Z",
                "provenance": {
                    "provider": "anthropic",
                    "model": "claude-opus-5",
                    "prompt_version": "genai-prompts-v1",
                    "live": True,
                    "attempts": 2,
                    "source_artifacts": [],
                },
                "request": {},
                "response": None,
                "schema_valid": False,
                "failure": "schema_error: not JSON",
            },
        )
        monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
        settings_module.clear_settings_cache()
        client = TestClient(app)

        body = client.get("/api/genai").json()
        assert len(body["runs"]) == 1
        assert body["attack_analyst"] is None
        settings_module.clear_settings_cache()
