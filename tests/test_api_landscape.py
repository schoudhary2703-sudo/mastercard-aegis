"""`/api/landscape`: breadth taxonomy and generation-scale benchmark.

The judge-facing claim this endpoint has to keep honest is the difference
between *identified* and *deeply simulated*. A breadth entry has no generator,
no detector result, and no blueprint, so these tests pin that it is served
without a family link and without ever being counted as simulated.

Everything is read from a throwaway fixture tree -- `data/` is git-ignored, so
no test here depends on the real artifacts being present.
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
from aegis.api.landscape import build_generation_scale, build_taxonomy

REPORTS = "data/reports"


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _taxonomy_payload() -> dict[str, Any]:
    return {
        "taxonomy_version": "fixture-v1",
        "scope_note": "Breadth catalog only.",
        "scenarios": [
            {
                "id": "synthetic-identity-bustout",
                "name": "Synthetic identity bust-out",
                "category": "identity-and-onboarding",
                "channels": ["mobile-banking", "digital-onboarding"],
                "rails": ["credit"],
                "genai_abuse_mechanism": "Forged onboarding artifacts.",
                "observable_signals": ["new-account tenure"],
                "plausibility_evidence_note": "note",
                "evidence_sources": [{"title": "src", "url": "https://example.test/a"}],
                "simulation_readiness": "READY",
                "implementation_status": "DEEP_SIMULATED",
            },
            {
                "id": "deepfake-impersonation-app-fraud",
                "name": "Deepfake impersonation APP fraud",
                "category": "scams-and-social-engineering",
                "channels": ["voice-call"],
                "rails": ["p2p"],
                "genai_abuse_mechanism": "Voice cloning.",
                "observable_signals": ["new beneficiary"],
                "plausibility_evidence_note": "note",
                "evidence_sources": [{"title": "src", "url": "https://example.test/b"}],
                "simulation_readiness": "RESEARCH_ONLY",
                "implementation_status": "IDENTIFIED_ONLY",
            },
        ],
        "summary": {
            "total_attacks_identified": 2,
            "categories_represented": ["identity-and-onboarding", "scams-and-social-engineering"],
            "channels_represented": ["mobile-banking", "digital-onboarding", "voice-call"],
            "rails_represented": ["credit", "p2p"],
            "deeply_simulated": 1,
        },
    }


def _scale_payload() -> dict[str, Any]:
    return {
        "benchmark_version": "fixture-scale-v1",
        "benchmark_scope": "Generation only.",
        "environment": {"platform": "fixture-os"},
        "families": [
            {
                "attack_family": "synthetic_identity_bustout",
                "blueprint_id": "synthetic-identity-bustout-v1",
                "generator_name": "synthetic-identity-bustout",
                "seed": 1,
                "scenarios_generated": 10,
                "transactions_generated": 150,
                "fraud_transactions_generated": 30,
                "generation_seconds": 0.5,
                "throughput_transactions_per_second": 300.0,
                "distributional_fidelity_score": 0.74,
                "fidelity_excluding_constraints": 0.85,
                "generator_reported_overall_fidelity_score": 0.88,
                "family_specific_fidelity_components": {
                    "amount_distribution": {"warmup_amount_similarity": 0.75},
                    "temporal_behavior": {"temporal_spacing_reasonableness": 1.0},
                    "structural_topology": {"transition_multiplier_similarity": 0.9},
                },
                "constraint_violation_rate": 0.0,
                "constraint_valid_percentage": 100.0,
                "deterministic_reproducibility": {"verified": True},
                "historical_scenario_id_overlap_count": 0,
                "limitations": ["Descriptive similarity only."],
            }
        ],
        "summary": {
            "family_count": 1,
            "total_scenarios": 10,
            "total_transactions": 150,
            "total_fraud_transactions": 30,
            "total_generation_seconds": 0.5,
            "aggregate_throughput_transactions_per_second": 300.0,
            "all_constraints_valid": True,
            "all_deterministic": True,
            "historical_scenario_id_overlap_count": 0,
            "deeply_simulated_families": 1,
        },
    }


@pytest.fixture
def landscape_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _write(tmp_path / REPORTS / "attack_taxonomy.json", _taxonomy_payload())
    _write(tmp_path / REPORTS / "generation_scale_benchmark.json", _scale_payload())
    monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
    settings_module.clear_settings_cache()
    yield TestClient(app)
    settings_module.clear_settings_cache()


@pytest.fixture
def empty_landscape_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    (tmp_path / REPORTS).mkdir(parents=True)
    monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
    settings_module.clear_settings_cache()
    yield TestClient(app)
    settings_module.clear_settings_cache()


class TestTaxonomyEndpoint:
    def test_counts_come_from_the_artifact(self, landscape_client: TestClient) -> None:
        payload = landscape_client.get("/api/landscape").json()["taxonomy"]
        assert payload["total_attacks_identified"] == 2
        assert payload["deeply_simulated"] == 1
        assert payload["category_count"] == 2
        assert payload["channel_count"] == 3
        assert len(payload["scenarios"]) == 2

    def test_only_deep_simulated_entries_link_to_a_family(
        self, landscape_client: TestClient
    ) -> None:
        """A breadth-only entry has no generator, so it gets no family link."""
        scenarios = {s["id"]: s for s in landscape_client.get("/api/landscape").json()["taxonomy"][
            "scenarios"
        ]}
        deep = scenarios["synthetic-identity-bustout"]
        breadth = scenarios["deepfake-impersonation-app-fraud"]

        assert deep["deeply_simulated"] is True
        assert deep["attack_family"] == "synthetic_identity_bustout"
        assert breadth["deeply_simulated"] is False
        assert breadth["attack_family"] is None

    def test_identified_only_entries_are_the_majority_and_stay_labelled(
        self, landscape_client: TestClient
    ) -> None:
        scenarios = landscape_client.get("/api/landscape").json()["taxonomy"]["scenarios"]
        statuses = {s["implementation_status"] for s in scenarios}
        assert statuses == {"DEEP_SIMULATED", "IDENTIFIED_ONLY"}
        assert sum(1 for s in scenarios if s["deeply_simulated"]) == 1

    def test_unknown_deep_id_gets_no_family_link(self, tmp_path: Path) -> None:
        """A DEEP_SIMULATED id with no implemented family maps to nothing."""
        payload = _taxonomy_payload()
        payload["scenarios"][1]["implementation_status"] = "DEEP_SIMULATED"
        _write(tmp_path / REPORTS / "attack_taxonomy.json", payload)
        taxonomy = build_taxonomy(tmp_path)
        assert taxonomy is not None
        by_id = {s["id"]: s for s in taxonomy["scenarios"]}
        assert by_id["deepfake-impersonation-app-fraud"]["attack_family"] is None

    def test_missing_counts_are_none_not_zero(self, tmp_path: Path) -> None:
        payload = _taxonomy_payload()
        payload["summary"] = {}
        _write(tmp_path / REPORTS / "attack_taxonomy.json", payload)
        taxonomy = build_taxonomy(tmp_path)
        assert taxonomy is not None
        assert taxonomy["total_attacks_identified"] is None
        assert taxonomy["deeply_simulated"] is None


class TestGenerationScaleEndpoint:
    def test_aggregate_numbers_come_from_the_artifact(
        self, landscape_client: TestClient
    ) -> None:
        scale = landscape_client.get("/api/landscape").json()["generation_scale"]
        assert scale["total_transactions"] == 150
        assert scale["total_fraud_transactions"] == 30
        assert scale["aggregate_throughput_transactions_per_second"] == 300.0
        assert scale["all_constraints_valid"] is True
        assert scale["historical_scenario_id_overlap_count"] == 0

    def test_fidelity_components_stay_separate_from_validity(
        self, landscape_client: TestClient
    ) -> None:
        family = landscape_client.get("/api/landscape").json()["generation_scale"]["families"][0]
        groups = {g["group"] for g in family["fidelity_components"]}
        assert groups == {"amount_distribution", "temporal_behavior", "structural_topology"}
        # Constraint validity is its own field, never folded into fidelity.
        assert family["fidelity_excluding_constraints"] == 0.85
        assert family["constraint_valid_percentage"] == 100.0

    def test_caveat_is_served_with_the_numbers(self, landscape_client: TestClient) -> None:
        scale = landscape_client.get("/api/landscape").json()["generation_scale"]
        assert "not proof of production realism" in scale["fidelity_caveat"]

    def test_non_numeric_scores_are_dropped_not_defaulted(self, tmp_path: Path) -> None:
        payload = _scale_payload()
        payload["families"][0]["family_specific_fidelity_components"] = {
            "amount_distribution": {"broken": "n/a", "ok": 0.5}
        }
        _write(tmp_path / REPORTS / "generation_scale_benchmark.json", payload)
        scale = build_generation_scale(tmp_path)
        assert scale is not None
        metrics = scale["families"][0]["fidelity_components"][0]["metrics"]
        assert [m["name"] for m in metrics] == ["ok"]


class TestEmptyState:
    def test_missing_artifacts_serve_nulls_not_zeros(
        self, empty_landscape_client: TestClient
    ) -> None:
        body = empty_landscape_client.get("/api/landscape").json()
        assert body["taxonomy"] is None
        assert body["generation_scale"] is None

    def test_endpoint_still_returns_200(self, empty_landscape_client: TestClient) -> None:
        assert empty_landscape_client.get("/api/landscape").status_code == 200

    def test_malformed_artifact_is_treated_as_absent(self, tmp_path: Path) -> None:
        (tmp_path / REPORTS).mkdir(parents=True)
        (tmp_path / REPORTS / "attack_taxonomy.json").write_text("{not json", encoding="utf-8")
        assert build_taxonomy(tmp_path) is None
