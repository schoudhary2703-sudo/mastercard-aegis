"""Builds a small, self-contained artifact tree for `aegis.api` tests.

`data/` and `models/` are git-ignored (see AGENTS.md: "data/** ... Never
commit data"), so API tests cannot depend on the real repo artifacts being
present in a fresh clone or CI. This module writes a minimal but
structurally faithful fixture tree instead: same directory layout, same
field names, values small enough to read at a glance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASELINE_VERSION = "xgboost-baseline-fixture"
HARDENED_VERSION = "xgboost-hardened-fixture"
DEFENDER_V3_VERSION = "xgboost-hardened-v3-fixture"
LOAFO_FOLD_VERSION = "loafo-fixture-fold"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _classification_metrics(*, precision: float, recall: float) -> dict[str, Any]:
    return {
        "precision": precision,
        "recall": recall,
        "f1": (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0,
        "pr_auc": 0.9,
        "roc_auc": 0.99,
        "false_positive_rate": 0.001,
        "false_negative_rate": round(1 - recall, 4),
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


def _evaluation_result(
    *, model_version: str, split: str, precision: float, recall: float
) -> dict[str, Any]:
    return {
        "evaluation_id": f"{model_version}-{split}",
        "protocol": "static_holdout",
        "model_version": model_version,
        "dataset_id": "fixture-dataset",
        "split": split,
        "overall": _classification_metrics(precision=precision, recall=recall),
        "per_attack_family": {},
        "latency": {
            "mean_ms": 5.0,
            "p50_ms": 5.0,
            "p95_ms": 6.0,
            "p99_ms": 7.0,
            "max_ms": 8.0,
            "samples": 10,
        },
        "fidelity": None,
        "round_index": None,
        "held_out_family": None,
        "seed": 1,
        "notes": "fixture",
        "created_at": "2026-01-01T00:00:00Z",
        "metadata": {},
    }


def _blueprint(*, attack_id: str, generation: int, parent: str | None) -> dict[str, Any]:
    return {
        "contract_version": "1.0.0",
        "attack_id": attack_id,
        "attack_family": "synthetic_identity_bustout",
        "name": "Fixture bust-out",
        "description": "A fixture blueprint.",
        "objective": "Test the artifact reader.",
        "target_features": ["temporal.velocity_24h"],
        "sequence": [{"step_id": "warmup", "order": 0, "offset_seconds": 0.0}],
        "parameters": {},
        "parent_blueprint_id": parent,
        "generation": generation,
        "metadata": {},
    }


def _hardest_evasion(
    *, scenario_id: str, transaction_id: str, model_version: str, rank: int
) -> dict[str, Any]:
    return {
        "rank": rank,
        "scenario_id": scenario_id,
        "transaction_id": transaction_id,
        "attack_family": "synthetic_identity_bustout",
        "blueprint_id": "synthetic-identity-bustout-v1",
        "generation": 0,
        "detector_risk_score": 0.2,
        "action": "approve",
        "detector_model_version": model_version,
        "ground_truth_label": 1,
        "fidelity_score": 0.8,
        "credible_evasion": True,
        "hardness_score": 0.7,
    }


def _confrontation_report(
    *, report_id: str, model_version: str, scenario_id: str, caught: int, evaded: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    total_fraud = caught + evaded
    events: list[dict[str, Any]] = []
    for i in range(caught):
        events.append(
            {
                "transaction_id": f"{scenario_id}-bustout-{i:03d}",
                "sequence_index": i,
                "risk_score": 0.99,
                "predicted_label": 1,
                "action": "review",
                "caught": True,
                "ground_truth_label": 1,
                "model_version": model_version,
            }
        )
    for i in range(evaded):
        idx = caught + i
        events.append(
            {
                "transaction_id": f"{scenario_id}-bustout-{idx:03d}",
                "sequence_index": idx,
                "risk_score": 0.2,
                "predicted_label": 0,
                "action": "approve",
                "caught": False,
                "ground_truth_label": 1,
                "model_version": model_version,
            }
        )
    scenario_report = {
        "scenario_id": scenario_id,
        "split": "test",
        "total_transactions": total_fraud + 2,
        "legitimate_warmup_transaction_count": 2,
        "fraudulent_bustout_count": total_fraud,
        "caught_fraud_count": caught,
        "evaded_fraud_count": evaded,
        "fraud_recall": caught / total_fraud if total_fraud else 0.0,
        "fraudulent_events": events,
        "model_version": model_version,
        "attack_family": "synthetic_identity_bustout",
        "blueprint_id": "synthetic-identity-bustout-v1",
        "generation": 0,
        "batch_id": f"batch-{scenario_id}",
        "generator_name": "synthetic-identity-bustout",
        "generator_version": "1.0.0",
        "seed": 1,
    }
    hardest = [
        _hardest_evasion(
            scenario_id=scenario_id,
            transaction_id=e["transaction_id"],
            model_version=model_version,
            rank=i + 1,
        )
        for i, e in enumerate(e for e in events if not e["caught"])
    ]
    return {
        "report_id": report_id,
        "training_dataset_id": "fixture-dataset",
        "training_transaction_count": 1000,
        "data_basis": "processed_paysim",
        "integration_only": False,
        "model_version": model_version,
        "generated_batch_id": f"batch-{scenario_id}",
        "scenario_reports": [scenario_report],
        "successful_evasions": hardest,
        "hardest_evasions": hardest,
        "metadata": {"adaptive": False, "retrained_after_scoring": False},
    }, events


def write_full_fixture(root: Path) -> None:
    """A complete lineage: baseline -> round-0 -> adaptive-1 -> hardened ->
    fresh confrontation -> generation-2, plus one hardening run."""

    # -- models --
    _write_json(
        root / "models" / BASELINE_VERSION / "metadata.json",
        {
            "action_policy": {
                "decline_at": 0.999,
                "label_threshold": 0.99,
                "policy_version": "policy-v0",
                "review_at": 0.995,
                "step_up_at": 0.99,
            },
            "contract_version": "1.0.0",
            "detector_name": "xgboost-baseline",
            "feature_names": ["temporal.amount"],
            "model_version": BASELINE_VERSION,
            "saved_at": "2026-01-01T00:00:00Z",
            "seed": 1,
        },
    )
    _write_json(
        root / "models" / BASELINE_VERSION / "evaluation_test.json",
        _evaluation_result(
            model_version=BASELINE_VERSION, split="test", precision=0.93, recall=0.80
        ),
    )
    _write_json(
        root / "models" / BASELINE_VERSION / "evaluation_validation.json",
        _evaluation_result(
            model_version=BASELINE_VERSION, split="validation", precision=0.77, recall=0.77
        ),
    )

    _write_json(
        root / "models" / HARDENED_VERSION / "metadata.json",
        {
            "action_policy": {
                "decline_at": 0.9998,
                "label_threshold": 0.9899,
                "policy_version": "policy-v0",
                "review_at": 0.995,
                "step_up_at": 0.9899,
            },
            "contract_version": "1.0.0",
            "detector_name": "xgboost-baseline",
            "feature_names": ["temporal.amount"],
            "model_version": HARDENED_VERSION,
            "saved_at": "2026-02-01T00:00:00Z",
            "seed": 2,
        },
    )
    _write_json(
        root / "models" / HARDENED_VERSION / "evaluation_test.json",
        _evaluation_result(
            model_version=HARDENED_VERSION, split="test", precision=0.93, recall=0.77
        ),
    )
    _write_json(
        root / "models" / HARDENED_VERSION / "evaluation_validation.json",
        _evaluation_result(
            model_version=HARDENED_VERSION, split="validation", precision=0.78, recall=0.75
        ),
    )
    _write_json(
        root / "models" / HARDENED_VERSION / "regression_vs_baseline.json",
        {
            "baseline_model_version": BASELINE_VERSION,
            "defender_v2_model_version": HARDENED_VERSION,
            "confusion_matrix": {
                "baseline_v1": {
                    "true_positives": 3,
                    "false_positives": 1,
                    "true_negatives": 100,
                    "false_negatives": 1,
                },
                "defender_v2": {
                    "true_positives": 2,
                    "false_positives": 1,
                    "true_negatives": 100,
                    "false_negatives": 2,
                },
            },
            "metrics": {
                "f1": {"baseline_v1": 0.86, "defender_v2": 0.84, "delta": -0.02},
                "recall": {"baseline_v1": 0.80, "defender_v2": 0.77, "delta": -0.03},
            },
            "latency_ms": {},
            "recall_at_fixed_fpr": {},
            "split": "test",
            "support": {"baseline_v1": 105, "defender_v2": 105},
            "notes": "fixture regression",
        },
    )
    _write_json(
        root / "models" / HARDENED_VERSION / "generation2_handoff.json",
        {
            "defender_version": HARDENED_VERSION,
            "excluded_scenario_ids": ["bustout-round0-0000"],
            "excluded_transaction_ids": [],
            "instructions": "fixture instructions",
            "model_dir": f"models/{HARDENED_VERSION}",
            "rules": "docs/EVALUATION_RULES.md",
            "tuned_threshold": 0.9899,
            "trained_on": {
                "hard_positive_sources": [],
                "processed_dir": "data/processed/paysim/fixture",
            },
        },
    )

    # -- round-0 confrontation (baseline, 0 caught / 3 evaded) --
    round0_id = "confrontation-round0"
    round0_report, round0_events = _confrontation_report(
        report_id=round0_id,
        model_version=BASELINE_VERSION,
        scenario_id="bustout-round0-0000",
        caught=0,
        evaded=3,
    )
    round0_dir = root / "data" / "synthetic" / "confrontations" / round0_id
    _write_json(round0_dir / "confrontation.json", round0_report)
    _write_json(
        round0_dir / "blueprint.json",
        _blueprint(attack_id="synthetic-identity-bustout-v1", generation=0, parent=None),
    )
    _write_json(round0_dir / "hardest_evasions.json", round0_report["hardest_evasions"])
    _write_jsonl(
        round0_dir / "transactions.jsonl",
        [
            {
                "transaction_id": e["transaction_id"],
                "scenario_id": "bustout-round0-0000",
                "label": 1,
                "attack_family": "synthetic_identity_bustout",
                "is_synthetic": True,
                "timestamp": "2026-01-01T00:00:00Z",
            }
            for e in round0_events
        ],
    )
    _write_jsonl(
        round0_dir / "detector_outputs.jsonl",
        [
            {
                "transaction_id": e["transaction_id"],
                "risk_score": e["risk_score"],
                "predicted_label": e["predicted_label"],
                "recommended_action": e["action"],
                "model_version": BASELINE_VERSION,
            }
            for e in round0_events
        ],
    )
    _write_jsonl(round0_dir / "evasions.jsonl", [e for e in round0_events if not e["caught"]])

    # -- adaptive round 1 (parent = round-0) --
    adaptive1_id = "adaptive-round-1-fixture"
    adaptive1_dir = root / "data" / "synthetic" / "adaptive_rounds" / adaptive1_id
    selected_blueprint = _blueprint(
        attack_id="synthetic-identity-bustout-v1-g1-fixture",
        generation=1,
        parent="synthetic-identity-bustout-v1",
    )
    _write_json(
        adaptive1_dir / "adaptive_round.json",
        {
            "report_id": adaptive1_id,
            "round_index": 1,
            "seed": 2,
            "model_version": BASELINE_VERSION,
            "detector_retrained": False,
            "threshold_changed": False,
            "integration_only": False,
            "data_basis": "processed_paysim",
            "parent_confrontation_id": round0_id,
            "parent_blueprint": _blueprint(
                attack_id="synthetic-identity-bustout-v1", generation=0, parent=None
            ),
            "candidate_results": [],
            "selected_candidate_id": selected_blueprint["attack_id"],
            "selected_blueprint": selected_blueprint,
            "hardest_surviving_evasions": [
                _hardest_evasion(
                    scenario_id="bustout-adaptive1-0000",
                    transaction_id="bustout-adaptive1-0000-bustout-000",
                    model_version=BASELINE_VERSION,
                    rank=1,
                )
            ],
            "comparison": {
                "round0": {
                    "fraud_recall": 0.0,
                    "average_fraud_risk_score": 0.5,
                    "fidelity_score": 0.8,
                    "fitness": 0.3,
                    "caught_count": 0,
                    "evaded_count": 3,
                },
                "round1": {
                    "fraud_recall": 0.0,
                    "average_fraud_risk_score": 0.4,
                    "fidelity_score": 0.9,
                    "fitness": 0.4,
                    "caught_count": 0,
                    "evaded_count": 3,
                },
                "fraud_recall_delta": 0.0,
                "average_fraud_risk_delta": -0.1,
                "fidelity_delta": 0.1,
                "fitness_delta": 0.1,
                "caught_count_delta": 0,
                "evaded_count_delta": 0,
            },
            "metadata": {"attacker_evolution_only": True},
        },
    )
    cand_dir = adaptive1_dir / "candidates" / selected_blueprint["attack_id"]
    _write_json(cand_dir / "blueprint.json", selected_blueprint)

    # -- fresh confrontation (hardened model, 2 caught / 1 evaded) --
    fresh_id = "confrontation-fresh"
    fresh_report, fresh_events = _confrontation_report(
        report_id=fresh_id,
        model_version=HARDENED_VERSION,
        scenario_id="bustout-fresh-0000",
        caught=2,
        evaded=1,
    )
    fresh_dir = root / "data" / "synthetic" / "confrontations" / fresh_id
    _write_json(fresh_dir / "confrontation.json", fresh_report)
    _write_json(
        fresh_dir / "blueprint.json",
        _blueprint(attack_id="synthetic-identity-bustout-v1", generation=0, parent=None),
    )
    _write_json(fresh_dir / "hardest_evasions.json", fresh_report["hardest_evasions"])
    _write_jsonl(
        fresh_dir / "transactions.jsonl",
        [
            {
                "transaction_id": e["transaction_id"],
                "scenario_id": "bustout-fresh-0000",
                "label": 1,
                "attack_family": "synthetic_identity_bustout",
                "is_synthetic": True,
                "timestamp": "2026-02-01T00:00:00Z",
            }
            for e in fresh_events
        ],
    )
    _write_jsonl(
        fresh_dir / "detector_outputs.jsonl",
        [
            {
                "transaction_id": e["transaction_id"],
                "risk_score": e["risk_score"],
                "predicted_label": e["predicted_label"],
                "recommended_action": e["action"],
                "model_version": HARDENED_VERSION,
            }
            for e in fresh_events
        ],
    )
    _write_jsonl(fresh_dir / "evasions.jsonl", [e for e in fresh_events if not e["caught"]])

    # -- generation-2 adaptive round (parent = fresh confrontation) --
    gen2_id = "adaptive-round-1-gen2-fixture"
    gen2_dir = root / "data" / "synthetic" / "adaptive_rounds" / gen2_id
    gen2_blueprint = _blueprint(
        attack_id="synthetic-identity-bustout-v1-g1-gen2-fixture",
        generation=1,
        parent="synthetic-identity-bustout-v1",
    )
    _write_json(
        gen2_dir / "adaptive_round.json",
        {
            "report_id": gen2_id,
            "round_index": 1,
            "seed": 3,
            "model_version": HARDENED_VERSION,
            "detector_retrained": False,
            "threshold_changed": False,
            "integration_only": False,
            "data_basis": "processed_paysim",
            "parent_confrontation_id": fresh_id,
            "selected_candidate_id": gen2_blueprint["attack_id"],
            "selected_blueprint": gen2_blueprint,
            "hardest_surviving_evasions": [],
            "comparison": {
                "round0": {"fraud_recall": 0.67, "caught_count": 2, "evaded_count": 1},
                "round1": {"fraud_recall": 0.33, "caught_count": 1, "evaded_count": 2},
                "fraud_recall_delta": -0.34,
                "caught_count_delta": -1,
                "evaded_count_delta": 1,
            },
            "metadata": {"attacker_evolution_only": True},
        },
    )

    # -- hardening run --
    hardening_dir = root / "data" / "hardening" / "hard-positives-fixture"
    _write_jsonl(
        hardening_dir / "hard_positives.jsonl",
        [{"transaction_id": f"hard-{i}", "label": 0} for i in range(4)],
    )
    _write_json(
        hardening_dir / "provenance.json",
        {
            "fraud_count": 3,
            "fraud_transaction_ids": [],
            "row_count": 4,
            "scenarios": [
                {
                    "artifact_dir": str(round0_dir),
                    "scenario_id": "bustout-round0-0000",
                    "source_round": "round-0",
                }
            ],
        },
    )


def add_defender_v3_and_loafo_fold(root: Path) -> None:
    """Layer a Defender v3 model, one LOAFO fold model, and one LOAFO-fold
    hardening run on top of `write_full_fixture`'s baseline/hardened pair --
    exercises that LOAFO fold artifacts are excluded from core model/
    hardening-run classification (`aegis.api.index`, `aegis.api.service`)."""
    _write_json(
        root / "models" / DEFENDER_V3_VERSION / "metadata.json",
        {
            "action_policy": {
                "decline_at": 0.9997,
                "label_threshold": 0.9899,
                "policy_version": "policy-v0",
                "review_at": 0.995,
                "step_up_at": 0.9899,
            },
            "contract_version": "1.0.0",
            "detector_name": "xgboost-baseline",
            "feature_names": ["temporal.amount"],
            "model_version": DEFENDER_V3_VERSION,
            "saved_at": "2026-03-01T00:00:00Z",
            "seed": 3,
        },
    )
    _write_json(
        root / "models" / DEFENDER_V3_VERSION / "evaluation_test.json",
        _evaluation_result(
            model_version=DEFENDER_V3_VERSION, split="test", precision=0.94, recall=0.78
        ),
    )
    _write_json(
        root / "models" / DEFENDER_V3_VERSION / "evaluation_validation.json",
        _evaluation_result(
            model_version=DEFENDER_V3_VERSION, split="validation", precision=0.8, recall=0.76
        ),
    )
    _write_json(
        root / "models" / DEFENDER_V3_VERSION / "regression_vs_v1_v2.json",
        {"notes": "fixture cross-family regression"},
    )

    # A LOAFO fold model dir carries its own metadata.json (like the real
    # repo's `models/loafo-*/`) -- it must still be excluded from
    # `ArtifactIndex.models` despite looking like a model directory.
    _write_json(
        root / "models" / LOAFO_FOLD_VERSION / "metadata.json",
        {
            "contract_version": "1.0.0",
            "detector_name": "xgboost-baseline",
            "model_version": LOAFO_FOLD_VERSION,
            "saved_at": "2026-04-01T00:00:00Z",
            "seed": 4,
        },
    )
    _write_json(
        root / "models" / LOAFO_FOLD_VERSION / "loafo_fold_report.json",
        {"fold_id": "fold-fixture", "held_out_family": "mule_network_structuring"},
    )

    # A LOAFO-fold hardening run whose id sorts *after* the core
    # "hard-positives-fixture" run -- proves the core run is still selected
    # by role, not by "last id alphabetically".
    loafo_hardening_dir = root / "data" / "hardening" / "loafo-fold-z-fixture"
    _write_jsonl(
        loafo_hardening_dir / "hard_positives.jsonl",
        [{"transaction_id": f"loafo-hard-{i}", "label": 0} for i in range(2)],
    )
    _write_json(
        loafo_hardening_dir / "provenance.json",
        {"fraud_count": 99, "fraud_transaction_ids": [], "row_count": 2, "scenarios": []},
    )


def write_empty_fixture(root: Path) -> None:
    """No artifacts at all -- exercises the "nothing has run yet" path."""
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "models").mkdir(parents=True, exist_ok=True)
