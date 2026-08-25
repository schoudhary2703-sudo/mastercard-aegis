"""Final benchmark aggregation: one canonical summary over every completed
real result -- baseline v1, Defender v2, Defender v3, and the LOAFO
generalization benchmark.

Read-only, path-safe, and deliberately dumb: every number here is copied
straight out of an already-persisted artifact written by an earlier training
or benchmark run (`scripts/train_baseline_detector.py`,
`scripts/harden_defender.py`, `scripts/harden_defender_crossfamily.py`,
`scripts/run_loafo_benchmark.py`), or is one documented, already-used-
elsewhere formula applied to two such numbers (`fitness = (1 -
average_fraud_risk) * fidelity_score` -- the same formula `mule confrontation
metadata` and `adaptive_round.json` already record). Nothing here trains,
retrains, re-scores, or invents a number that is not traceable to a file on
disk.

Models are matched to their `baseline_v1` / `defender_v2` / `defender_v3`
role by which regression report they carry, not by directory name, so a
reseeded rerun under a different model_version is still found correctly:

* carries `regression_vs_v1_v2.json` -> Defender v3 (only the cross-family
  hardening script writes this file)
* carries `regression_vs_baseline.json` (and not the above) -> Defender v2
* neither -> baseline v1

LOAFO fold reports are discovered by globbing `models/loafo-*/loafo_fold_report.json`
rather than by hardcoding the three known fold directory names, for the same
reason.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis.api.paths import resolve_within
from aegis.api.reader import read_json

MODELS_DIR = "models"
LOAFO_SUMMARY_PATH = (MODELS_DIR, "loafo_summary.json")
LOAFO_FOLD_PREFIX = "loafo-"

LIMITATIONS: list[str] = [
    "Each LOAFO fold's fresh evaluation is one real synthetic scenario "
    "(3-12 fraud events), not a statistically powered sample -- recall "
    "numbers are directional, not confidence-interval-backed estimates.",
    "Defender v3's per-transaction risk scores were not persisted during "
    "LOAFO scoring, so average_fraud_risk_score/fitness are only available "
    "for each fold's own model, not for Defender v3's view of the same "
    "scenario (see each fresh_family_performance entry's defender_v3.note).",
    "Model comparison and fresh-family numbers each come from a single "
    "untouched PaySim test split and a single fresh scenario per family "
    "respectively -- neither is cross-validated.",
    "No claim of universal fraud detection: mule_network_structuring "
    "generalization was weak in the LOAFO benchmark even where the other "
    "two families generalized strongly -- see loafo.overall_verdict.",
]


def _read(root: Path, *parts: str) -> Any | None:
    return read_json(resolve_within(root, *parts))


def _discover_models(root: Path) -> dict[str, dict[str, Any]]:
    """Classify every `models/*/` directory into baseline_v1 / defender_v2 /
    defender_v3 by which regression report it carries. First match per role
    wins (deterministic: directories are visited in sorted order)."""
    models_dir = resolve_within(root, MODELS_DIR)
    result: dict[str, dict[str, Any]] = {}
    if not models_dir.is_dir():
        return result

    for child in sorted(p for p in models_dir.iterdir() if p.is_dir()):
        metadata = _read(root, MODELS_DIR, child.name, "metadata.json")
        if not isinstance(metadata, dict):
            continue
        has_v3_report = (child / "regression_vs_v1_v2.json").is_file()
        has_v2_report = (child / "regression_vs_baseline.json").is_file()
        role = "defender_v3" if has_v3_report else "defender_v2" if has_v2_report else "baseline_v1"
        if role in result:
            continue
        result[role] = {
            "dir_name": child.name,
            "metadata": metadata,
            "evaluation_test": _read(root, MODELS_DIR, child.name, "evaluation_test.json"),
            "evaluation_validation": _read(
                root, MODELS_DIR, child.name, "evaluation_validation.json"
            ),
            "regression_vs_v1_v2": _read(root, MODELS_DIR, child.name, "regression_vs_v1_v2.json"),
        }
    return result


def _discover_loafo_fold_reports(root: Path) -> list[tuple[str, dict[str, Any]]]:
    """`(model_dir_name, loafo_fold_report.json contents)` for every
    discovered LOAFO fold, sorted by directory name for determinism."""
    models_dir = resolve_within(root, MODELS_DIR)
    if not models_dir.is_dir():
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for child in sorted(
        p for p in models_dir.iterdir() if p.is_dir() and p.name.startswith(LOAFO_FOLD_PREFIX)
    ):
        report = _read(root, MODELS_DIR, child.name, "loafo_fold_report.json")
        if isinstance(report, dict):
            out.append((child.name, report))
    return out


def _model_comparison_entry(
    metrics: dict[str, Any],
    latency: dict[str, Any],
    recall_at_fpr: dict[str, Any],
    confusion: dict[str, Any],
    key: str,
    model_version: str,
) -> dict[str, Any]:
    def _m(field: str) -> Any:
        entry = metrics.get(field)
        return entry.get(key) if isinstance(entry, dict) else None

    return {
        "model_version": model_version,
        "precision": _m("precision"),
        "recall": _m("recall"),
        "f1": _m("f1"),
        "pr_auc": _m("pr_auc"),
        "roc_auc": _m("roc_auc"),
        "false_positive_rate": _m("false_positive_rate"),
        "threshold": _m("threshold"),
        "recall_at_fixed_fpr": {
            budget: (values.get(key) if isinstance(values, dict) else None)
            for budget, values in recall_at_fpr.items()
        },
        "latency_ms": latency.get(key) if isinstance(latency, dict) else None,
        "confusion": confusion.get(key) if isinstance(confusion, dict) else None,
    }


def _build_model_comparison(models: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Built from Defender v3's `regression_vs_v1_v2.json` alone -- that one
    file already carries all three models' metrics on the identical
    untouched PaySim test split, so re-deriving from three separate
    `evaluation_test.json` files would only add a chance of drift."""
    v3 = models.get("defender_v3")
    if not v3 or not isinstance(v3.get("regression_vs_v1_v2"), dict):
        return None
    report = v3["regression_vs_v1_v2"]
    metrics = report.get("metrics") or {}
    latency = report.get("latency_ms") or {}
    recall_at_fpr = report.get("recall_at_fixed_fpr") or {}
    confusion = report.get("confusion_matrix") or {}

    return {
        "split": report.get("split", "test"),
        "dataset_id": report.get("dataset_id", ""),
        "baseline_v1": _model_comparison_entry(
            metrics,
            latency,
            recall_at_fpr,
            confusion,
            "baseline_v1",
            str(report.get("baseline_v1_model_version", "")),
        ),
        "defender_v2": _model_comparison_entry(
            metrics,
            latency,
            recall_at_fpr,
            confusion,
            "defender_v2",
            str(report.get("defender_v2_model_version", "")),
        ),
        "defender_v3": _model_comparison_entry(
            metrics,
            latency,
            recall_at_fpr,
            confusion,
            "defender_v3_crossfamily",
            str(report.get("defender_v3_model_version", "")),
        ),
        "source_artifact": f"{MODELS_DIR}/{v3['dir_name']}/regression_vs_v1_v2.json",
    }


def _fitness(average_risk: Any, fidelity: Any) -> float | None:
    if not isinstance(average_risk, (int, float)) or not isinstance(fidelity, (int, float)):
        return None
    return (1.0 - float(average_risk)) * float(fidelity)


def _build_fresh_family_performance(
    fold_reports: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for dir_name, report in fold_reports:
        fresh = report.get("fresh_held_out_evaluation") or {}
        fold_overall = (fresh.get("fold_model_evaluation") or {}).get("overall") or {}
        v3_evaluation = fresh.get("defender_v3_evaluation") or {}
        v3_overall = v3_evaluation.get("overall") or {}
        v3_counts = v3_overall.get("counts") or {}
        average_risk = fresh.get("average_fraud_risk_score")
        fidelity = fresh.get("fidelity_score")

        out.append(
            {
                "attack_family": report.get("held_out_family"),
                "fold_id": report.get("fold_id"),
                "training_families": report.get("training_families") or [],
                "fraud_count": fresh.get("fraud_count"),
                "fidelity_score": fidelity,
                "fold_model": {
                    "model_version": report.get("model_version"),
                    "recall": fresh.get("recall", fold_overall.get("recall")),
                    "caught": fresh.get("caught_count"),
                    "evaded": fresh.get("evaded_count"),
                    "average_fraud_risk_score": average_risk,
                    "fitness": _fitness(average_risk, fidelity),
                    "note": None,
                },
                "defender_v3": {
                    "model_version": v3_evaluation.get("model_version"),
                    "recall": v3_overall.get("recall"),
                    "caught": v3_counts.get("true_positives"),
                    "evaded": v3_counts.get("false_negatives"),
                    "average_fraud_risk_score": None,
                    "fitness": None,
                    "note": (
                        "Per-transaction risk scores were not persisted for Defender v3's "
                        "scoring pass on this scenario; only aggregate precision/recall/counts "
                        "are available."
                    ),
                },
                "source_artifact": f"{MODELS_DIR}/{dir_name}/loafo_fold_report.json",
            }
        )
    return sorted(out, key=lambda entry: str(entry["attack_family"]))


def _build_loafo(
    root: Path, fold_reports: list[tuple[str, dict[str, Any]]]
) -> dict[str, Any] | None:
    summary = _read(root, *LOAFO_SUMMARY_PATH)
    if not isinstance(summary, dict):
        return None
    per_family_raw = summary.get("per_family") or {}

    per_family: list[dict[str, Any]] = []
    verdicts: list[str] = []
    for family, entry in per_family_raw.items():
        if not isinstance(entry, dict):
            continue
        verdict = str(entry.get("verdict", "unknown"))
        verdicts.append(verdict)
        per_family.append(
            {
                "attack_family": family,
                "fold_id": entry.get("fold_id"),
                "training_families": entry.get("training_families") or [],
                "loafo_recall": entry.get("loafo_recall"),
                "defender_v3_recall_same_scenario": entry.get("defender_v3_recall_same_scenario"),
                "verdict": verdict,
            }
        )
    per_family.sort(key=lambda entry: str(entry["attack_family"]))

    if not verdicts:
        overall_verdict = "unknown"
    elif all(v == "strong" for v in verdicts):
        overall_verdict = "strong"
    elif all(v == "weak" for v in verdicts):
        overall_verdict = "weak"
    else:
        overall_verdict = "partial"

    return {
        "mean_loafo_recall": summary.get("mean_loafo_recall"),
        "overall_verdict": overall_verdict,
        "verdict_rubric": summary.get("verdict_rubric", ""),
        "per_family": per_family,
        "source_artifact": "/".join(LOAFO_SUMMARY_PATH),
    }


def _build_hardest_surviving_attacks(
    fold_reports: list[tuple[str, dict[str, Any]]], *, limit: int = 15
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for dir_name, report in fold_reports:
        fresh = report.get("fresh_held_out_evaluation") or {}
        source_artifact = f"{MODELS_DIR}/{dir_name}/loafo_fold_report.json"
        fold_id = report.get("fold_id", dir_name)
        for evasion in fresh.get("hardest_evasions") or []:
            if not isinstance(evasion, dict):
                continue
            row = dict(evasion)
            row.setdefault("source_round", f"loafo:{fold_id}")
            row.setdefault("source_artifact", source_artifact)
            out.append(row)
    out.sort(
        key=lambda row: (
            row["hardness_score"] if isinstance(row.get("hardness_score"), (int, float)) else 0.0
        ),
        reverse=True,
    )
    return out[:limit]


def _claim_flags(loafo: dict[str, Any] | None) -> dict[str, Any]:
    if not loafo or not loafo.get("per_family"):
        return {"universal_fraud_detection": False, "cross_family_generalization": "unknown"}
    weakest = min(loafo["per_family"], key=lambda entry: entry.get("loafo_recall") or 0.0)
    return {
        "universal_fraud_detection": False,
        "cross_family_generalization": loafo["overall_verdict"],
        "weakest_unseen_family": weakest["attack_family"],
    }


def build_final_benchmark_summary(
    root: Path, *, generated_at: datetime | None = None
) -> dict[str, Any]:
    """Aggregate every completed real result under `root` into one canonical,
    deterministic (modulo `meta.generated_at`) summary dict."""
    models = _discover_models(root)
    model_comparison = _build_model_comparison(models)

    fold_reports = _discover_loafo_fold_reports(root)
    fresh_family_performance = _build_fresh_family_performance(fold_reports)
    loafo = _build_loafo(root, fold_reports)
    hardest_surviving_attacks = _build_hardest_surviving_attacks(fold_reports)

    stamp = generated_at or datetime.now(timezone.utc)
    return {
        "model_comparison": model_comparison,
        "fresh_family_performance": fresh_family_performance,
        "loafo": loafo,
        "hardest_surviving_attacks": hardest_surviving_attacks,
        "limitations": LIMITATIONS,
        "claim_flags": _claim_flags(loafo),
        "meta": {
            "generated_at": stamp.isoformat(),
            "data_source": "real",
            "artifacts_root": str(root),
        },
    }
