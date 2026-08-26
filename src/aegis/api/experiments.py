"""Per-family experiment replays, assembled from persisted artifacts.

This is what the Attack Lab screen replays. Nothing here simulates, scores,
or generates anything: every event is a transaction that a real detector
really scored in a run that already happened, read back off disk.

Two shapes of evidence exist in this repo, and they are *not* equally
complete -- so this module reports which one it used rather than blurring
them together:

* **Full confrontation streams** (`data/synthetic/confrontations/<id>/`) keep
  `transactions.jsonl` + `detector_outputs.jsonl`, so every transaction in
  the scenario -- warm-up and fraud alike -- can be replayed in order. Only
  the synthetic-identity bust-out family has these.
* **LOAFO fold reports** (`models/loafo-*/loafo_fold_report.json`) keep the
  aggregate counts plus the *surviving evasions* only. The other two families
  have these, so their replay covers the fraud that got through but not the
  transactions that were caught.

`events_complete` and `events_note` carry that distinction to the UI, which
labels it. A partial stream is shown as partial.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aegis.api.index import LOAFO_FOLD_PREFIX, MODELS_DIR, ArtifactIndex
from aegis.api.paths import resolve_within
from aegis.api.reader import iter_jsonl, read_json
from aegis.shared.enums import AttackFamily

CONFRONTATIONS_DIR = "data/synthetic/confrontations"

FAMILY_LABEL: dict[str, str] = {
    AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value: "Synthetic Identity / Bust-out",
    AttackFamily.MULE_NETWORK_STRUCTURING.value: "Mule Network / Structuring",
    AttackFamily.ADAPTIVE_DETECTOR_EVASION.value: "Adaptive Detector Evasion",
}

# One line each. These describe the *typology* and how generative tooling
# lowers its cost -- research description, not a measurement of this system.
FAMILY_HEADLINE: dict[str, str] = {
    AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value: (
        "A fabricated identity builds ordinary payment history, then drains it in a burst."
    ),
    AttackFamily.MULE_NETWORK_STRUCTURING.value: (
        "Funds fan out across mule accounts, layer, and re-converge -- each hop unremarkable."
    ),
    AttackFamily.ADAPTIVE_DETECTOR_EVASION.value: (
        "The attack probes the detector, reads what scored it, and mutates to stay under threshold."
    ),
}

FAMILY_GENAI_ANGLE: dict[str, str] = {
    AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value: (
        "GenAI drafts plausible warm-up behaviour at scale, so the benign phase is cheap."
    ),
    AttackFamily.MULE_NETWORK_STRUCTURING.value: (
        "GenAI reasons about topology to keep every single hop below notice."
    ),
    AttackFamily.ADAPTIVE_DETECTOR_EVASION.value: (
        "GenAI turns detector feedback into the next parameter guess far faster than a human."
    ),
}

_ROLE_LABEL: dict[str, str] = {
    "baseline_v1": "Baseline v1",
    "defender_v2": "Defender v2",
    "defender_v3": "Defender v3",
}


def _is_fraud_row(txn: dict[str, Any] | None) -> bool:
    return bool(txn and int(txn.get("label", 0)) == 1)


def _with_provenance(
    row: dict[str, Any] | None, *, source_round: str, source_artifact: str
) -> dict[str, Any] | None:
    """Stamp a raw hardest-evasion row with where it came from.

    The rows persisted inside a confrontation/fold report do not carry their
    own provenance -- it is implied by the file they live in -- but
    `HardestEvasionDTO` requires it, so it is attached here rather than
    loosening the DTO.
    """
    if not isinstance(row, dict):
        return None
    stamped = dict(row)
    stamped.setdefault("source_round", source_round)
    stamped.setdefault("source_artifact", source_artifact)
    return stamped


def _bustout_experiment(root: Path, index: ArtifactIndex) -> dict[str, Any] | None:
    """Replay the bust-out family from its full confrontation streams.

    Three confrontations exist -- one per defender generation against the same
    blueprint -- so this also yields the before/after progression the evasion
    story needs. The replayed stream is the newest generation's.
    """
    role_by_version = {m.model_version: m.role for m in index.models}
    ordered = sorted(
        (c for c in index.confrontations if not c.is_adaptive),
        key=lambda c: (
            list(_ROLE_LABEL).index(role_by_version.get(c.model_version, "baseline_v1")),
            c.report_id,
        ),
    )
    if not ordered:
        return None

    progression: list[dict[str, Any]] = []
    for c in ordered:
        reports = [s for s in (c.report.get("scenario_reports") or []) if isinstance(s, dict)]
        fraud = sum(int(s.get("fraudulent_bustout_count", 0)) for s in reports)
        caught = sum(int(s.get("caught_fraud_count", 0)) for s in reports)
        escaped = sum(int(s.get("evaded_fraud_count", 0)) for s in reports)
        role = role_by_version.get(c.model_version, "baseline_v1")
        progression.append(
            {
                "label": _ROLE_LABEL.get(role, role),
                "model_version": c.model_version,
                "role": role,
                "fraud_count": fraud,
                "caught_count": caught,
                "escaped_count": escaped,
                "recall": (caught / fraud) if fraud else 0.0,
            }
        )

    # The replayed run and the current defender's result are the same thing
    # for this family: the newest generation's confrontation.
    current_defender = progression[-1]

    latest = ordered[-1]
    scenario_reports = [
        s for s in (latest.report.get("scenario_reports") or []) if isinstance(s, dict)
    ]
    first_scenario = scenario_reports[0] if scenario_reports else {}

    txn_path = resolve_within(
        root, CONFRONTATIONS_DIR, latest.source_artifact, "transactions.jsonl"
    )
    out_path = resolve_within(
        root, CONFRONTATIONS_DIR, latest.source_artifact, "detector_outputs.jsonl"
    )
    by_id = {str(t["transaction_id"]): t for t in iter_jsonl(txn_path) if t.get("transaction_id")}

    events: list[dict[str, Any]] = []
    for i, row in enumerate(iter_jsonl(out_path)):
        txn_id = str(row.get("transaction_id", ""))
        txn = by_id.get(txn_id)
        is_fraud = _is_fraud_row(txn)
        predicted = int(row.get("predicted_label", 0))
        events.append(
            {
                "transaction_id": txn_id,
                "sequence_index": i,
                "risk_score": float(row.get("risk_score", 0.0)),
                "threshold": row.get("threshold"),
                "action": str(row.get("recommended_action", "")),
                "predicted_label": predicted,
                "ground_truth_label": int(txn.get("label", 0)) if txn else 0,
                "is_fraud": is_fraud,
                "caught": bool(is_fraud and predicted == 1),
                "amount": txn.get("amount") if txn else None,
                "timestamp": txn.get("timestamp") if txn else None,
            }
        )

    blueprint = latest.blueprint if isinstance(latest.blueprint, dict) else {}
    parameters = [
        {"name": name, "value": spec.get("default"), "mutable": bool(spec.get("mutable"))}
        for name, spec in (blueprint.get("parameters") or {}).items()
        if isinstance(spec, dict)
    ]

    hardest = [h for h in latest.hardest_evasions if isinstance(h, dict)]
    fidelity = (first_scenario.get("fidelity_summary") or {}).get("overall_fidelity_score")

    return {
        "attack_family": AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value,
        "label": FAMILY_LABEL[AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value],
        "headline": FAMILY_HEADLINE[AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value],
        "genai_angle": FAMILY_GENAI_ANGLE[AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value],
        "attack_name": str(blueprint.get("name") or blueprint.get("attack_id") or "Bust-out"),
        "blueprint_id": str(blueprint.get("attack_id", "")),
        "scenario_id": str(first_scenario.get("scenario_id", "")),
        "model_version": latest.model_version,
        "fraud_count": progression[-1]["fraud_count"],
        "caught_count": progression[-1]["caught_count"],
        "escaped_count": progression[-1]["escaped_count"],
        "recall": progression[-1]["recall"],
        "fidelity_score": fidelity,
        "parameters": parameters,
        "events": events,
        "events_complete": True,
        "events_note": None,
        "hardest_survivor": _with_provenance(
            hardest[0] if hardest else None,
            source_round=_ROLE_LABEL.get(
                role_by_version.get(latest.model_version, ""), "confrontation"
            ),
            source_artifact=f"{CONFRONTATIONS_DIR}/{latest.source_artifact}/confrontation.json",
        ),
        "progression": progression,
        "current_defender": current_defender,
        "replayed_model_label": current_defender["label"],
        "source_artifacts": [f"{CONFRONTATIONS_DIR}/{latest.source_artifact}"],
    }


def _loafo_experiment(root: Path, dir_name: str, report: dict[str, Any]) -> dict[str, Any] | None:
    """Replay a LOAFO fold's fresh held-out scenario.

    Only the surviving evasions are persisted for these folds, so the event
    list covers the fraud that got through. `events_complete=False` says so.
    """
    family = str(report.get("held_out_family", ""))
    if family not in FAMILY_LABEL:
        return None
    fresh = report.get("fresh_held_out_evaluation") or {}
    fraud = int(fresh.get("fraud_count", 0) or 0)
    caught = int(fresh.get("caught_count", 0) or 0)
    escaped = int(fresh.get("evaded_count", 0) or 0)

    hardest = [h for h in (fresh.get("hardest_evasions") or []) if isinstance(h, dict)]
    events = [
        {
            "transaction_id": str(h.get("transaction_id", "")),
            "sequence_index": h.get("sequence_index"),
            "risk_score": float(h.get("detector_risk_score", 0.0)),
            "threshold": None,
            "action": str(h.get("action", "")),
            "predicted_label": 0,
            "ground_truth_label": int(h.get("ground_truth_label", 1)),
            "is_fraud": True,
            "caught": False,
            "amount": None,
            "timestamp": None,
        }
        for h in hardest
    ]
    events.sort(key=lambda e: (e["sequence_index"] is None, e["sequence_index"]))

    v3_eval = fresh.get("defender_v3_evaluation") or {}
    v3_overall = v3_eval.get("overall") or {}
    v3_counts = v3_overall.get("counts") or {}
    progression = [
        {
            "label": "LOAFO fold (family held out)",
            "model_version": str(report.get("model_version", "")),
            "role": "loafo_fold",
            "fraud_count": fraud,
            "caught_count": caught,
            "escaped_count": escaped,
            "recall": float(fresh.get("recall", 0.0) or 0.0),
        },
        {
            "label": "Defender v3 (trained on it)",
            "model_version": str(v3_eval.get("model_version", "")),
            "role": "defender_v3",
            "fraud_count": fraud,
            "caught_count": int(v3_counts.get("true_positives", 0) or 0),
            "escaped_count": int(v3_counts.get("false_negatives", 0) or 0),
            "recall": float(v3_overall.get("recall", 0.0) or 0.0),
        },
    ]

    note = (
        f"{len(events)} of {escaped} surviving evasion(s) persisted for this fold; "
        "caught transactions were not retained per-transaction."
        if escaped
        else "No fraud survived this fold, so there are no per-transaction evasions to replay."
    )

    return {
        "attack_family": family,
        "label": FAMILY_LABEL[family],
        "headline": FAMILY_HEADLINE[family],
        "genai_angle": FAMILY_GENAI_ANGLE[family],
        "attack_name": FAMILY_LABEL[family],
        "blueprint_id": str(hardest[0].get("blueprint_id", "")) if hardest else "",
        "scenario_id": str(fresh.get("scenario_id", "")),
        "model_version": str(report.get("model_version", "")),
        "fraud_count": fraud,
        "caught_count": caught,
        "escaped_count": escaped,
        "recall": float(fresh.get("recall", 0.0) or 0.0),
        "fidelity_score": fresh.get("fidelity_score"),
        "parameters": [],
        "events": events,
        "events_complete": False,
        "events_note": note,
        "hardest_survivor": _with_provenance(
            hardest[0] if hardest else None,
            source_round=f"loafo:{report.get('fold_id', dir_name)}",
            source_artifact=f"{MODELS_DIR}/{dir_name}/loafo_fold_report.json",
        ),
        "progression": progression,
        # The replayed stream is the FOLD model's (that family held out of
        # training). The current core defender's result on the same scenario
        # is a different, better number -- kept separate so a caller can
        # aggregate "how does Defender v3 do" without silently mixing in a
        # deliberately handicapped fold model.
        "current_defender": progression[1],
        "replayed_model_label": progression[0]["label"],
        "source_artifacts": [f"{MODELS_DIR}/{dir_name}/loafo_fold_report.json"],
    }


def build_experiments(root: Path, index: ArtifactIndex) -> list[dict[str, Any]]:
    """One replayable experiment per attack family, ordered for the demo."""
    out: list[dict[str, Any]] = []

    bustout = _bustout_experiment(root, index)
    if bustout:
        out.append(bustout)

    models_dir = resolve_within(root, MODELS_DIR)
    if models_dir.is_dir():
        for child in sorted(
            p for p in models_dir.iterdir() if p.is_dir() and p.name.startswith(LOAFO_FOLD_PREFIX)
        ):
            report = read_json(child / "loafo_fold_report.json")
            if not isinstance(report, dict):
                continue
            # The bust-out family already has a richer full-stream replay above.
            if report.get("held_out_family") == AttackFamily.SYNTHETIC_IDENTITY_BUSTOUT.value:
                continue
            experiment = _loafo_experiment(root, child.name, report)
            if experiment:
                out.append(experiment)

    order = [f.value for f in AttackFamily]
    out.sort(key=lambda e: order.index(e["attack_family"]))
    return out


__all__ = [
    "FAMILY_GENAI_ANGLE",
    "FAMILY_HEADLINE",
    "FAMILY_LABEL",
    "build_experiments",
]
