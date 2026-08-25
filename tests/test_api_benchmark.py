"""Tests for `aegis.api.benchmark` (aggregation) and `GET /api/benchmark`.

Uses a self-contained fixture tree (never the real, git-ignored `models/`)
so these tests pass in a fresh clone or CI with no training/LOAFO run
performed first, and so "no hard-coded metrics" can be proven by varying
the fixture and checking the output varies correspondingly.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aegis.api import settings as settings_module
from aegis.api.app import app
from aegis.api.benchmark import build_final_benchmark_summary

FIXED_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _classification_metrics(*, precision: float, recall: float) -> dict[str, Any]:
    return {
        "precision": precision,
        "recall": recall,
        "f1": round(2 * precision * recall / (precision + recall), 4)
        if (precision + recall)
        else 0.0,
        "pr_auc": 0.9,
        "roc_auc": 0.99,
        "false_positive_rate": 0.001,
        "recall_at_fixed_fpr": {"0.001": recall},
        "alert_rate": 0.004,
        "threshold": 0.99,
        "counts": {
            "true_positives": 3,
            "false_positives": 1,
            "true_negatives": 100,
            "false_negatives": 1,
        },
        "support": 105,
        "positive_support": 4,
    }


def write_model(
    root: Path, dir_name: str, *, model_version: str, precision: float, recall: float
) -> None:
    _write_json(
        root / "models" / dir_name / "metadata.json",
        {"model_version": model_version, "saved_at": "2026-01-01T00:00:00Z", "seed": 1},
    )
    _write_json(
        root / "models" / dir_name / "evaluation_test.json",
        {
            "evaluation_id": f"{model_version}-test",
            "protocol": "static_holdout",
            "model_version": model_version,
            "split": "test",
            "overall": _classification_metrics(precision=precision, recall=recall),
        },
    )


def write_defender_v3_regression(root: Path, v3_dir_name: str) -> None:
    _write_json(
        root / "models" / v3_dir_name / "regression_vs_v1_v2.json",
        {
            "dataset_id": "fixture-dataset",
            "split": "test",
            "baseline_v1_model_version": "fixture-baseline-v1",
            "defender_v2_model_version": "fixture-defender-v2",
            "defender_v3_model_version": "fixture-defender-v3",
            "metrics": {
                "precision": {
                    "baseline_v1": 0.93,
                    "defender_v2": 0.93,
                    "defender_v3_crossfamily": 0.94,
                },
                "recall": {
                    "baseline_v1": 0.79,
                    "defender_v2": 0.77,
                    "defender_v3_crossfamily": 0.78,
                },
                "f1": {"baseline_v1": 0.86, "defender_v2": 0.84, "defender_v3_crossfamily": 0.85},
                "pr_auc": {
                    "baseline_v1": 0.91,
                    "defender_v2": 0.90,
                    "defender_v3_crossfamily": 0.90,
                },
                "roc_auc": {
                    "baseline_v1": 0.999,
                    "defender_v2": 0.999,
                    "defender_v3_crossfamily": 0.999,
                },
                "false_positive_rate": {
                    "baseline_v1": 0.0003,
                    "defender_v2": 0.0002,
                    "defender_v3_crossfamily": 0.0002,
                },
                "threshold": {
                    "baseline_v1": 0.988,
                    "defender_v2": 0.99,
                    "defender_v3_crossfamily": 0.989,
                },
            },
            "recall_at_fixed_fpr": {
                "0.001": {"baseline_v1": 0.85, "defender_v2": 0.85, "defender_v3_crossfamily": 0.85}
            },
            "confusion_matrix": {
                "baseline_v1": {
                    "true_positives": 3187,
                    "false_positives": 242,
                    "true_negatives": 951492,
                    "false_negatives": 823,
                },
                "defender_v2": {
                    "true_positives": 3091,
                    "false_positives": 230,
                    "true_negatives": 951504,
                    "false_negatives": 919,
                },
                "defender_v3_crossfamily": {
                    "true_positives": 3124,
                    "false_positives": 206,
                    "true_negatives": 951528,
                    "false_negatives": 886,
                },
            },
            "latency_ms": {
                "baseline_v1": {"mean_ms": 6.8, "samples": 200},
                "defender_v2": {"mean_ms": 12.2, "samples": 200},
                "defender_v3_crossfamily": {"mean_ms": 6.6, "samples": 200},
            },
        },
    )


def write_defender_v2_regression(root: Path, v2_dir_name: str) -> None:
    _write_json(root / "models" / v2_dir_name / "regression_vs_baseline.json", {"notes": "fixture"})


def write_loafo_fold(
    root: Path,
    dir_name: str,
    *,
    fold_id: str,
    held_out_family: str,
    training_families: list[str],
    model_version: str,
    fraud_count: int,
    caught: int,
    evaded: int,
    recall: float,
    average_fraud_risk_score: float,
    fidelity_score: float,
    v3_recall: float,
    v3_true_positives: int,
    v3_false_negatives: int,
    hardest_evasions: list[dict[str, Any]] | None = None,
) -> None:
    report = {
        "fold_id": fold_id,
        "training_families": training_families,
        "held_out_family": held_out_family,
        "model_version": model_version,
        "model_dir": f"models/{dir_name}",
        "tuned_threshold": 0.99,
        "hard_positive_counts_by_family": {},
        "fresh_held_out_evaluation": {
            "scenario_id": f"{held_out_family}-fixture-scenario",
            "source_artifact": f"data/synthetic/loafo_evaluations/{fold_id}/fixture-confrontation",
            "fraud_count": fraud_count,
            "caught_count": caught,
            "evaded_count": evaded,
            "recall": recall,
            "average_fraud_risk_score": average_fraud_risk_score,
            "fidelity_score": fidelity_score,
            "hardest_evasions": hardest_evasions or [],
            "fold_model_evaluation": {
                "model_version": model_version,
                "overall": _classification_metrics(precision=1.0, recall=recall),
            },
            "defender_v3_evaluation": {
                "model_version": "fixture-defender-v3",
                "overall": {
                    **_classification_metrics(precision=1.0, recall=v3_recall),
                    "counts": {
                        "true_positives": v3_true_positives,
                        "false_positives": 0,
                        "true_negatives": 10,
                        "false_negatives": v3_false_negatives,
                    },
                },
            },
        },
    }
    _write_json(root / "models" / dir_name / "loafo_fold_report.json", report)


def write_loafo_summary(
    root: Path, per_family: dict[str, dict[str, Any]], *, mean_recall: float
) -> None:
    _write_json(
        root / "models" / "loafo_summary.json",
        {
            "held_out_recall_per_family": {k: v["loafo_recall"] for k, v in per_family.items()},
            "mean_loafo_recall": mean_recall,
            "defender_v3_recall_on_same_scenarios": {
                k: v["defender_v3_recall_same_scenario"] for k, v in per_family.items()
            },
            "per_family": per_family,
            "verdict_rubric": "fixture rubric",
        },
    )


def _hardest_evasion(*, transaction_id: str, hardness: float, family: str) -> dict[str, Any]:
    return {
        "rank": 1,
        "scenario_id": f"{family}-scenario",
        "transaction_id": transaction_id,
        "attack_family": family,
        "blueprint_id": f"{family}-v1",
        "generation": 0,
        "detector_risk_score": 0.1,
        "fidelity_score": 0.8,
        "hardness_score": hardness,
        "action": "approve",
        "detector_model_version": "fixture-model",
        "ground_truth_label": 1,
        "credible_evasion": True,
    }


def write_full_benchmark_fixture(root: Path) -> None:
    write_model(
        root, "baseline-v1", model_version="fixture-baseline-v1", precision=0.93, recall=0.79
    )
    write_model(
        root, "defender-v2", model_version="fixture-defender-v2", precision=0.93, recall=0.77
    )
    write_defender_v2_regression(root, "defender-v2")
    write_model(
        root, "defender-v3", model_version="fixture-defender-v3", precision=0.94, recall=0.78
    )
    write_defender_v3_regression(root, "defender-v3")

    write_loafo_fold(
        root,
        "loafo-fold-a",
        fold_id="fold-a",
        held_out_family="adaptive_detector_evasion",
        training_families=["synthetic_identity_bustout", "mule_network_structuring"],
        model_version="loafo-fold-a-fixture",
        fraud_count=4,
        caught=3,
        evaded=1,
        recall=0.75,
        average_fraud_risk_score=0.99,
        fidelity_score=0.81,
        v3_recall=1.0,
        v3_true_positives=4,
        v3_false_negatives=0,
        hardest_evasions=[
            _hardest_evasion(
                transaction_id="a-1", hardness=0.02, family="adaptive_detector_evasion"
            )
        ],
    )
    write_loafo_fold(
        root,
        "loafo-fold-b",
        fold_id="fold-b",
        held_out_family="mule_network_structuring",
        training_families=["synthetic_identity_bustout", "adaptive_detector_evasion"],
        model_version="loafo-fold-b-fixture",
        fraud_count=12,
        caught=0,
        evaded=12,
        recall=0.0,
        average_fraud_risk_score=0.25,
        fidelity_score=0.85,
        v3_recall=0.4167,
        v3_true_positives=5,
        v3_false_negatives=7,
        hardest_evasions=[
            _hardest_evasion(
                transaction_id="b-1", hardness=0.84, family="mule_network_structuring"
            ),
            _hardest_evasion(
                transaction_id="b-2", hardness=0.90, family="mule_network_structuring"
            ),
        ],
    )
    write_loafo_fold(
        root,
        "loafo-fold-c",
        fold_id="fold-c",
        held_out_family="synthetic_identity_bustout",
        training_families=["mule_network_structuring", "adaptive_detector_evasion"],
        model_version="loafo-fold-c-fixture",
        fraud_count=3,
        caught=3,
        evaded=0,
        recall=1.0,
        average_fraud_risk_score=0.997,
        fidelity_score=0.88,
        v3_recall=1.0,
        v3_true_positives=3,
        v3_false_negatives=0,
    )
    write_loafo_summary(
        root,
        {
            "adaptive_detector_evasion": {
                "fold_id": "fold-a",
                "training_families": ["synthetic_identity_bustout", "mule_network_structuring"],
                "loafo_recall": 0.75,
                "defender_v3_recall_same_scenario": 1.0,
                "verdict": "strong",
            },
            "mule_network_structuring": {
                "fold_id": "fold-b",
                "training_families": ["synthetic_identity_bustout", "adaptive_detector_evasion"],
                "loafo_recall": 0.0,
                "defender_v3_recall_same_scenario": 0.4167,
                "verdict": "weak",
            },
            "synthetic_identity_bustout": {
                "fold_id": "fold-c",
                "training_families": ["mule_network_structuring", "adaptive_detector_evasion"],
                "loafo_recall": 1.0,
                "defender_v3_recall_same_scenario": 1.0,
                "verdict": "strong",
            },
        },
        mean_recall=0.5833,
    )


# --- aggregation function, direct -------------------------------------------


class TestBuildFinalBenchmarkSummary:
    def test_full_fixture_produces_all_sections(self, tmp_path: Path) -> None:
        write_full_benchmark_fixture(tmp_path)
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)

        assert summary["model_comparison"] is not None
        assert len(summary["fresh_family_performance"]) == 3
        assert summary["loafo"] is not None
        assert len(summary["hardest_surviving_attacks"]) == 3
        assert summary["claim_flags"]["universal_fraud_detection"] is False

    def test_empty_root_degrades_to_empty_sections_without_raising(self, tmp_path: Path) -> None:
        (tmp_path / "models").mkdir()
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)

        assert summary["model_comparison"] is None
        assert summary["fresh_family_performance"] == []
        assert summary["loafo"] is None
        assert summary["hardest_surviving_attacks"] == []
        assert summary["claim_flags"] == {
            "universal_fraud_detection": False,
            "cross_family_generalization": "unknown",
        }

    def test_missing_root_does_not_raise(self, tmp_path: Path) -> None:
        summary = build_final_benchmark_summary(tmp_path / "does-not-exist", generated_at=FIXED_NOW)
        assert summary["model_comparison"] is None
        assert summary["loafo"] is None

    def test_deterministic_given_identical_inputs(self, tmp_path: Path) -> None:
        write_full_benchmark_fixture(tmp_path)
        first = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        second = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        assert first == second

    def test_models_are_classified_by_regression_report_not_directory_name(
        self, tmp_path: Path
    ) -> None:
        """Directory names are arbitrary fixture strings, not the real
        xgboost-baseline-* naming - proves role assignment is content-based."""
        write_full_benchmark_fixture(tmp_path)
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        comparison = summary["model_comparison"]
        assert comparison["baseline_v1"]["model_version"] == "fixture-baseline-v1"
        assert comparison["defender_v2"]["model_version"] == "fixture-defender-v2"
        assert comparison["defender_v3"]["model_version"] == "fixture-defender-v3"

    def test_loafo_folds_discovered_by_glob_not_hardcoded_names(self, tmp_path: Path) -> None:
        """Fixture fold directories (loafo-fold-a/b/c) do not match the real
        repo's loafo-synth-mule-*/loafo-synth-adaptive-*/loafo-mule-adaptive-*
        names - proves discovery is a generic prefix glob."""
        write_full_benchmark_fixture(tmp_path)
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        fold_ids = {entry["fold_id"] for entry in summary["fresh_family_performance"]}
        assert fold_ids == {"fold-a", "fold-b", "fold-c"}

    def test_hardest_surviving_attacks_sorted_by_hardness_descending(self, tmp_path: Path) -> None:
        write_full_benchmark_fixture(tmp_path)
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        scores = [row["hardness_score"] for row in summary["hardest_surviving_attacks"]]
        assert scores == sorted(scores, reverse=True)
        assert scores[0] == 0.90

    def test_hardest_surviving_attacks_respect_limit(self, tmp_path: Path) -> None:
        write_full_benchmark_fixture(tmp_path)
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        # 1 (fold a) + 2 (fold b) + 0 (fold c) = 3, well under the default limit.
        assert len(summary["hardest_surviving_attacks"]) == 3

    def test_fitness_uses_the_documented_formula(self, tmp_path: Path) -> None:
        write_full_benchmark_fixture(tmp_path)
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        fold_a = next(
            e
            for e in summary["fresh_family_performance"]
            if e["attack_family"] == "adaptive_detector_evasion"
        )
        expected = (1.0 - 0.99) * 0.81
        assert fold_a["fold_model"]["fitness"] == pytest.approx(expected)

    def test_defender_v3_per_family_omits_unavailable_risk_and_fitness(
        self, tmp_path: Path
    ) -> None:
        write_full_benchmark_fixture(tmp_path)
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        fold_a = next(
            e
            for e in summary["fresh_family_performance"]
            if e["attack_family"] == "adaptive_detector_evasion"
        )
        assert fold_a["defender_v3"]["average_fraud_risk_score"] is None
        assert fold_a["defender_v3"]["fitness"] is None
        assert fold_a["defender_v3"]["note"]
        # But its real caught/evaded/recall, derived from persisted counts, are present.
        assert fold_a["defender_v3"]["caught"] == 4
        assert fold_a["defender_v3"]["recall"] == pytest.approx(1.0)

    def test_overall_verdict_is_partial_when_family_verdicts_mixed(self, tmp_path: Path) -> None:
        write_full_benchmark_fixture(tmp_path)
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        assert summary["loafo"]["overall_verdict"] == "partial"
        assert summary["claim_flags"]["cross_family_generalization"] == "partial"
        assert summary["claim_flags"]["weakest_unseen_family"] == "mule_network_structuring"

    def test_overall_verdict_is_strong_when_all_families_strong(self, tmp_path: Path) -> None:
        write_full_benchmark_fixture(tmp_path)
        raw_summary_path = tmp_path / "models" / "loafo_summary.json"
        data = json.loads(raw_summary_path.read_text(encoding="utf-8"))
        for entry in data["per_family"].values():
            entry["verdict"] = "strong"
        raw_summary_path.write_text(json.dumps(data), encoding="utf-8")

        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        assert summary["loafo"]["overall_verdict"] == "strong"

    def test_output_varies_when_source_metrics_vary(self, tmp_path: Path) -> None:
        """Regression guard against hard-coding: changing only the source
        regression report's numbers must change the aggregated output by
        exactly that much, proving no value is a hardcoded literal."""
        write_full_benchmark_fixture(tmp_path)
        before = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)

        report_path = tmp_path / "models" / "defender-v3" / "regression_vs_v1_v2.json"
        data = json.loads(report_path.read_text(encoding="utf-8"))
        data["metrics"]["recall"]["defender_v3_crossfamily"] = 0.111
        report_path.write_text(json.dumps(data), encoding="utf-8")

        after = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        assert before["model_comparison"]["defender_v3"]["recall"] != 0.111
        assert after["model_comparison"]["defender_v3"]["recall"] == 0.111

    def test_limitations_are_non_empty_and_static_text_not_numbers(self, tmp_path: Path) -> None:
        write_full_benchmark_fixture(tmp_path)
        summary = build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)
        assert len(summary["limitations"]) >= 1
        assert all(isinstance(item, str) and item for item in summary["limitations"])

    def test_does_not_write_or_modify_any_model_artifact(self, tmp_path: Path) -> None:
        """Pure aggregation: calling it must never mutate a source file."""
        write_full_benchmark_fixture(tmp_path)
        models_dir = tmp_path / "models"
        before = {p: p.read_bytes() for p in models_dir.rglob("*") if p.is_file()}

        build_final_benchmark_summary(tmp_path, generated_at=FIXED_NOW)

        after = {p: p.read_bytes() for p in models_dir.rglob("*") if p.is_file()}
        assert before == after
        assert set(before) == set(after)  # no files added or removed either


# --- FastAPI endpoint ---------------------------------------------------


@pytest.fixture
def full_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    write_full_benchmark_fixture(tmp_path)
    monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
    settings_module.clear_settings_cache()
    client = TestClient(app)
    yield client
    settings_module.clear_settings_cache()


@pytest.fixture
def empty_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    (tmp_path / "models").mkdir()
    monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
    settings_module.clear_settings_cache()
    client = TestClient(app)
    yield client
    settings_module.clear_settings_cache()


class TestBenchmarkEndpoint:
    def test_returns_200_with_full_schema(self, full_client: TestClient) -> None:
        r = full_client.get("/api/benchmark")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) >= {
            "model_comparison",
            "fresh_family_performance",
            "loafo",
            "hardest_surviving_attacks",
            "limitations",
            "claim_flags",
            "meta",
        }
        assert body["meta"]["data_source"] == "real"

    def test_model_comparison_has_all_three_models(self, full_client: TestClient) -> None:
        r = full_client.get("/api/benchmark")
        comparison = r.json()["model_comparison"]
        assert comparison["baseline_v1"]["model_version"] == "fixture-baseline-v1"
        assert comparison["defender_v2"]["model_version"] == "fixture-defender-v2"
        assert comparison["defender_v3"]["model_version"] == "fixture-defender-v3"

    def test_loafo_section_has_three_families(self, full_client: TestClient) -> None:
        r = full_client.get("/api/benchmark")
        per_family = r.json()["loafo"]["per_family"]
        assert {row["attack_family"] for row in per_family} == {
            "synthetic_identity_bustout",
            "mule_network_structuring",
            "adaptive_detector_evasion",
        }

    def test_empty_root_returns_200_with_null_sections(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/benchmark")
        assert r.status_code == 200
        body = r.json()
        assert body["model_comparison"] is None
        assert body["loafo"] is None
        assert body["fresh_family_performance"] == []
        assert body["hardest_surviving_attacks"] == []

    def test_endpoint_does_not_mutate_fixture_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_full_benchmark_fixture(tmp_path)
        monkeypatch.setenv("AEGIS_ARTIFACTS_ROOT", str(tmp_path))
        settings_module.clear_settings_cache()
        client = TestClient(app)

        models_dir = tmp_path / "models"
        before = {p: p.read_bytes() for p in models_dir.rglob("*") if p.is_file()}
        client.get("/api/benchmark")
        after = {p: p.read_bytes() for p in models_dir.rglob("*") if p.is_file()}

        settings_module.clear_settings_cache()
        assert before == after
