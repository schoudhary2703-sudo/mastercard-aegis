"""Builds API response DTOs from a discovered `ArtifactIndex`.

This module contains all of the "which artifact means what" logic: which
model is the baseline, which confrontation is round-0 versus the fresh
post-hardening confrontation, which adaptive round follows which
confrontation. That lineage is derived from real fields already on the
artifacts (`model_version`, `parent_confrontation_id`, presence of
`generation2_handoff.json`) -- nothing here is hardcoded to a specific
report id, so it keeps working as later rounds are produced.

Every number returned is read straight from an artifact or is a plain sum /
ratio of numbers already on that artifact (e.g. aggregate `fraud_recall`
across a confrontation's scenarios). Nothing is invented or simulated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis.api.benchmark import build_final_benchmark_summary
from aegis.api.dto import (
    AdaptiveRoundStageStatsDTO,
    AdaptiveRoundSummaryDTO,
    AttackDetailDTO,
    AttacksResponseDTO,
    AttackSummaryDTO,
    ClassificationMetricsDTO,
    ConfrontationSummaryDTO,
    ConfusionCountsDTO,
    DetectionRecordDTO,
    EvaluationResponseDTO,
    EvaluationSummaryDTO,
    EvolutionResponseDTO,
    EvolutionStageDTO,
    FinalBenchmarkSummaryDTO,
    HardeningSummaryDTO,
    HardestEvasionDTO,
    HardestEvasionsResponseDTO,
    LatencyMetricsDTO,
    MetaDTO,
    ModelSummaryDTO,
    OverviewResponseDTO,
    RecentDetectionsResponseDTO,
    RegressionComparisonDTO,
    RegressionMetricDeltaDTO,
)
from aegis.api.index import (
    ADAPTIVE_ROUNDS_DIR,
    CONFRONTATIONS_DIR,
    HARDENING_DIR,
    LOAFO_FOLD_PREFIX,
    MODELS_DIR,
    AdaptiveRoundArtifact,
    ArtifactIndex,
    ConfrontationArtifact,
    HardeningArtifact,
    ModelArtifact,
)
from aegis.api.paths import resolve_within
from aegis.api.reader import iter_jsonl
from aegis.api.settings import Settings, get_settings
from aegis.shared.enums import AttackFamily

# ---------------------------------------------------------------------------
# index access
# ---------------------------------------------------------------------------


def build_index(settings: Settings | None = None) -> ArtifactIndex:
    """Discover the current artifact set. Cheap enough to call per-request:
    the artifact set here is a handful of small JSON/JSONL files, not a data
    lake, and re-reading avoids ever serving a stale in-memory snapshot."""
    s = settings or get_settings()
    return ArtifactIndex(s.artifacts_root)


def _meta(settings: Settings) -> MetaDTO:
    return MetaDTO(
        generated_at=datetime.now(timezone.utc).isoformat(),
        artifacts_root=str(settings.artifacts_root),
    )


def _saved_at_key(m: ModelArtifact) -> str:
    return str((m.metadata or {}).get("saved_at", m.model_version))


# ---------------------------------------------------------------------------
# leaf converters (artifact JSON -> DTO), all tolerant of missing/odd shapes
# ---------------------------------------------------------------------------


def _evaluation_summary(
    d: dict[str, Any] | None, source_artifact: str
) -> EvaluationSummaryDTO | None:
    if not isinstance(d, dict) or not isinstance(d.get("overall"), dict):
        return None
    try:
        fidelity = d.get("fidelity")
        fidelity_score = (
            fidelity.get("overall_fidelity_score") if isinstance(fidelity, dict) else None
        )
        per_family_raw = d.get("per_attack_family") or {}
        per_family = {
            str(k): ClassificationMetricsDTO(**v)
            for k, v in per_family_raw.items()
            if isinstance(v, dict)
        }
        latency = d.get("latency")
        return EvaluationSummaryDTO(
            evaluation_id=str(d.get("evaluation_id", "")),
            protocol=str(d.get("protocol", "")),
            model_version=str(d.get("model_version", "")),
            dataset_id=str(d.get("dataset_id", "")),
            split=str(d.get("split", "")),
            overall=ClassificationMetricsDTO(**d["overall"]),
            per_attack_family=per_family,
            latency=LatencyMetricsDTO(**latency) if isinstance(latency, dict) else None,
            fidelity_score=fidelity_score,
            round_index=d.get("round_index"),
            held_out_family=d.get("held_out_family"),
            notes=str(d.get("notes", "")),
            created_at=str(d.get("created_at")) if d.get("created_at") else None,
            source_artifact=source_artifact,
        )
    except (TypeError, ValueError):
        return None


def _model_summary(m: ModelArtifact) -> ModelSummaryDTO:
    metadata = m.metadata or {}
    action_policy = metadata.get("action_policy")
    action_policy = action_policy if isinstance(action_policy, dict) else {}
    return ModelSummaryDTO(
        model_version=m.model_version,
        detector_name=metadata.get("detector_name"),
        threshold=action_policy.get("label_threshold"),
        action_policy=action_policy,
        trained_at=metadata.get("saved_at"),
        seed=metadata.get("seed"),
        is_hardened=m.is_hardened,
        role=m.role,
        source_artifact=f"{MODELS_DIR}/{m.source_artifact}",
        evaluation_test=_evaluation_summary(
            m.evaluation_test, f"{MODELS_DIR}/{m.source_artifact}/evaluation_test.json"
        ),
        evaluation_validation=_evaluation_summary(
            m.evaluation_validation, f"{MODELS_DIR}/{m.source_artifact}/evaluation_validation.json"
        ),
    )


def _regression_summary(
    d: dict[str, Any] | None, source_artifact: str
) -> RegressionComparisonDTO | None:
    if not isinstance(d, dict):
        return None
    try:
        metrics: dict[str, RegressionMetricDeltaDTO] = {}
        for key, value in (d.get("metrics") or {}).items():
            if isinstance(value, dict) and {"baseline_v1", "defender_v2", "delta"} <= value.keys():
                metrics[key] = RegressionMetricDeltaDTO(**value)
        confusion: dict[str, ConfusionCountsDTO] = {}
        for key, value in (d.get("confusion_matrix") or {}).items():
            if isinstance(value, dict):
                confusion[key] = ConfusionCountsDTO(
                    true_positives=int(value.get("true_positives", 0)),
                    false_positives=int(value.get("false_positives", 0)),
                    true_negatives=int(value.get("true_negatives", 0)),
                    false_negatives=int(value.get("false_negatives", 0)),
                )
        return RegressionComparisonDTO(
            baseline_model_version=str(d.get("baseline_model_version", "")),
            defender_v2_model_version=str(d.get("defender_v2_model_version", "")),
            metrics=metrics,
            confusion_matrix=confusion,
            notes=str(d.get("notes", "")),
            split=d.get("split"),
            source_artifact=source_artifact,
        )
    except (TypeError, ValueError):
        return None


def _hardest_evasion(
    d: dict[str, Any], *, source_round: str, source_artifact: str
) -> HardestEvasionDTO | None:
    try:
        return HardestEvasionDTO(
            rank=d.get("rank"),
            scenario_id=str(d["scenario_id"]),
            transaction_id=str(d["transaction_id"]),
            attack_family=str(d["attack_family"]),
            blueprint_id=str(d["blueprint_id"]),
            generation=int(d.get("generation", 0)),
            detector_risk_score=float(d["detector_risk_score"]),
            fidelity_score=d.get("fidelity_score"),
            hardness_score=d.get("hardness_score"),
            action=str(d.get("action", "")),
            detector_model_version=str(d.get("detector_model_version", "")),
            ground_truth_label=int(d.get("ground_truth_label", 1)),
            credible_evasion=bool(d.get("credible_evasion", False)),
            source_round=source_round,
            source_artifact=source_artifact,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _stage_stats(d: Any) -> AdaptiveRoundStageStatsDTO | None:
    if not isinstance(d, dict):
        return None
    try:
        return AdaptiveRoundStageStatsDTO(
            fraud_recall=float(d.get("fraud_recall", 0.0)),
            average_fraud_risk_score=d.get("average_fraud_risk_score"),
            fidelity_score=d.get("fidelity_score"),
            fitness=d.get("fitness"),
            caught_count=int(d.get("caught_count", 0)),
            evaded_count=int(d.get("evaded_count", 0)),
        )
    except (TypeError, ValueError):
        return None


def _confrontation_summary(
    c: ConfrontationArtifact, *, source_round: str
) -> ConfrontationSummaryDTO:
    scenario_reports = [
        sr for sr in (c.report.get("scenario_reports") or []) if isinstance(sr, dict)
    ]
    families = sorted(
        {str(sr["attack_family"]) for sr in scenario_reports if sr.get("attack_family")}
    )
    generations = sorted(
        {int(sr["generation"]) for sr in scenario_reports if isinstance(sr.get("generation"), int)}
    )
    fraud_count = sum(int(sr.get("fraudulent_bustout_count", 0)) for sr in scenario_reports)
    caught_count = sum(int(sr.get("caught_fraud_count", 0)) for sr in scenario_reports)
    evaded_count = sum(int(sr.get("evaded_fraud_count", 0)) for sr in scenario_reports)
    fraud_recall = caught_count / fraud_count if fraud_count else 0.0

    hardest_source = f"{CONFRONTATIONS_DIR}/{c.source_artifact}/confrontation.json"
    hardest = [
        h
        for h in (
            _hardest_evasion(row, source_round=source_round, source_artifact=hardest_source)
            for row in c.hardest_evasions
            if isinstance(row, dict)
        )
        if h is not None
    ]

    return ConfrontationSummaryDTO(
        report_id=c.report_id,
        model_version=c.model_version,
        attack_families=families,
        generations=generations,
        scenario_count=len(scenario_reports),
        total_transactions=c.transaction_count,
        fraud_count=fraud_count,
        caught_count=caught_count,
        evaded_count=evaded_count,
        fraud_recall=fraud_recall,
        adaptive=c.is_adaptive,
        hardest_evasions=hardest,
        source_artifact=f"{CONFRONTATIONS_DIR}/{c.source_artifact}",
    )


def _adaptive_round_summary(
    a: AdaptiveRoundArtifact, *, source_round: str
) -> AdaptiveRoundSummaryDTO:
    report = a.report
    comparison_raw = report.get("comparison")
    comparison: dict[str, Any] = comparison_raw if isinstance(comparison_raw, dict) else {}
    deltas = {
        key: float(value)
        for key, value in comparison.items()
        if key.endswith("_delta") and isinstance(value, (int, float))
    }
    hardest_raw = report.get("hardest_surviving_evasions")
    hardest_source = f"{ADAPTIVE_ROUNDS_DIR}/{a.source_artifact}/adaptive_round.json"
    hardest = [
        h
        for h in (
            _hardest_evasion(row, source_round=source_round, source_artifact=hardest_source)
            for row in (hardest_raw if isinstance(hardest_raw, list) else [])
            if isinstance(row, dict)
        )
        if h is not None
    ]

    return AdaptiveRoundSummaryDTO(
        report_id=a.report_id,
        round_index=a.round_index,
        seed=report.get("seed"),
        model_version=a.model_version,
        parent_confrontation_id=a.parent_confrontation_id,
        candidate_count=len(a.candidates),
        selected_blueprint_id=a.selected_candidate_id,
        before=_stage_stats(comparison.get("round0")),
        after=_stage_stats(comparison.get("round1")),
        deltas=deltas,
        hardest_surviving_evasions=hardest,
        source_artifact=f"{ADAPTIVE_ROUNDS_DIR}/{a.source_artifact}",
    )


def _hardening_summary(h: HardeningArtifact, handoff: dict[str, Any]) -> HardeningSummaryDTO:
    prov = h.provenance or {}
    scenarios_raw = prov.get("scenarios")
    scenarios: list[Any] = scenarios_raw if isinstance(scenarios_raw, list) else []
    excluded = handoff.get("excluded_scenario_ids")
    return HardeningSummaryDTO(
        run_id=h.run_id,
        hard_positive_count=h.hard_positive_count,
        fraud_count=prov.get("fraud_count"),
        source_scenarios=[
            str(s["scenario_id"]) for s in scenarios if isinstance(s, dict) and s.get("scenario_id")
        ],
        excluded_scenario_ids=[str(x) for x in excluded] if isinstance(excluded, list) else [],
        tuned_threshold=handoff.get("tuned_threshold"),
        source_artifact=f"{HARDENING_DIR}/{h.run_id}/provenance.json",
    )


# ---------------------------------------------------------------------------
# lineage labeling -- derived from real fields, not hardcoded ids
# ---------------------------------------------------------------------------


def _confrontation_source_round(index: ArtifactIndex, c: ConfrontationArtifact) -> str:
    baseline = index.baseline_model()
    hardened = index.hardened_model()
    if baseline and c.model_version == baseline.model_version and not c.is_adaptive:
        return "round-0"
    if hardened and c.model_version == hardened.model_version and not c.is_adaptive:
        return "fresh-confrontation"
    return c.model_version or "confrontation"


def _adaptive_round_source_round(index: ArtifactIndex, a: AdaptiveRoundArtifact) -> str:
    baseline = index.baseline_model()
    hardened = index.hardened_model()
    if baseline and a.model_version == baseline.model_version:
        return "adaptive-round-1"
    if hardened and a.model_version == hardened.model_version:
        return "generation-2"
    return f"adaptive-round-{a.round_index}"


def _match_hardening_run(index: ArtifactIndex) -> HardeningArtifact | None:
    # LOAFO fold hardening runs (`data/hardening/loafo-fold-*`) promote hard
    # positives for a fold model, not for the core Defender v2 hardening
    # story this stage narrates -- exclude them so a fold run never gets
    # picked over the real `hard-positives-r1-*` run just because its id
    # happens to sort later.
    core_runs = [r for r in index.hardening_runs if not r.run_id.startswith(LOAFO_FOLD_PREFIX)]
    if not core_runs:
        return None
    # Only one hardening round exists at foundation stage; take the most
    # recently named run if more ever appear.
    return sorted(core_runs, key=lambda h: h.run_id)[-1]


def _all_hardest_evasions(index: ArtifactIndex) -> list[HardestEvasionDTO]:
    out: list[HardestEvasionDTO] = []
    for c in index.confrontations:
        out.extend(
            _confrontation_summary(
                c, source_round=_confrontation_source_round(index, c)
            ).hardest_evasions
        )
    for a in index.adaptive_rounds:
        out.extend(
            _adaptive_round_summary(
                a, source_round=_adaptive_round_source_round(index, a)
            ).hardest_surviving_evasions
        )
    out.sort(key=lambda h: h.hardness_score if h.hardness_score is not None else 0.0, reverse=True)
    return out


# ---------------------------------------------------------------------------
# top-level builders (one per endpoint)
# ---------------------------------------------------------------------------


def build_overview(index: ArtifactIndex, settings: Settings) -> OverviewResponseDTO:
    models = [_model_summary(m) for m in sorted(index.models, key=_saved_at_key)]
    current = index.current_defender_model()
    regression = None
    for m in index.models:
        if m.regression_vs_baseline:
            regression = _regression_summary(
                m.regression_vs_baseline,
                f"{MODELS_DIR}/{m.source_artifact}/regression_vs_baseline.json",
            )
            break
    return OverviewResponseDTO(
        attack_families_in_scope=[f.value for f in AttackFamily],
        models=models,
        current_model=_model_summary(current) if current else None,
        regression=regression,
        confrontation_count=len(index.confrontations),
        adaptive_round_count=len(index.adaptive_rounds),
        hardest_evasions_preview=_all_hardest_evasions(index)[:3],
        meta=_meta(settings),
    )


def build_evolution(index: ArtifactIndex, settings: Settings) -> EvolutionResponseDTO:
    baseline = index.baseline_model()
    hardened = index.hardened_model()
    stages: list[EvolutionStageDTO] = []

    if baseline:
        stages.append(
            EvolutionStageDTO(
                stage="baseline_v1",
                label="Baseline v1",
                status="real",
                model=_model_summary(baseline),
            )
        )
    else:
        stages.append(
            EvolutionStageDTO(stage="baseline_v1", label="Baseline v1", status="not_run_yet")
        )

    round0 = (
        index.earliest_confrontation_for_model(baseline.model_version, adaptive=False)
        if baseline
        else None
    )
    if round0:
        stages.append(
            EvolutionStageDTO(
                stage="round_0_attack",
                label="Round-0 attack",
                status="real",
                confrontation=_confrontation_summary(round0, source_round="round-0"),
            )
        )
    else:
        stages.append(
            EvolutionStageDTO(stage="round_0_attack", label="Round-0 attack", status="not_run_yet")
        )

    adaptive1 = index.adaptive_round_by_parent(round0.report_id) if round0 else None
    if adaptive1:
        stages.append(
            EvolutionStageDTO(
                stage="adaptive_red",
                label="Adaptive Red (Round 1)",
                status="real",
                adaptive_round=_adaptive_round_summary(adaptive1, source_round="adaptive-round-1"),
            )
        )
    else:
        stages.append(
            EvolutionStageDTO(
                stage="adaptive_red", label="Adaptive Red (Round 1)", status="not_run_yet"
            )
        )

    if hardened:
        handoff = hardened.generation2_handoff or {}
        hardening_run = _match_hardening_run(index)
        regression_source = f"{MODELS_DIR}/{hardened.source_artifact}/regression_vs_baseline.json"
        stages.append(
            EvolutionStageDTO(
                stage="defender_v2_hardening",
                label="Defender v2 hardening",
                status="real",
                model=_model_summary(hardened),
                regression=_regression_summary(hardened.regression_vs_baseline, regression_source),
                hardening=_hardening_summary(hardening_run, handoff) if hardening_run else None,
            )
        )
    else:
        stages.append(
            EvolutionStageDTO(
                stage="defender_v2_hardening", label="Defender v2 hardening", status="not_run_yet"
            )
        )

    fresh = (
        index.earliest_confrontation_for_model(hardened.model_version, adaptive=False)
        if hardened
        else None
    )
    if fresh:
        stages.append(
            EvolutionStageDTO(
                stage="fresh_confrontation",
                label="Fresh Defender-v2 confrontation",
                status="real",
                confrontation=_confrontation_summary(fresh, source_round="fresh-confrontation"),
            )
        )
    else:
        stages.append(
            EvolutionStageDTO(
                stage="fresh_confrontation",
                label="Fresh Defender-v2 confrontation",
                status="not_run_yet",
            )
        )

    gen2 = index.adaptive_round_by_parent(fresh.report_id) if fresh else None
    if gen2:
        stages.append(
            EvolutionStageDTO(
                stage="generation_2_adaptation",
                label="Generation-2 comparison",
                status="real",
                adaptive_round=_adaptive_round_summary(gen2, source_round="generation-2"),
            )
        )
    else:
        stages.append(
            EvolutionStageDTO(
                stage="generation_2_adaptation",
                label="Generation-2 comparison",
                status="not_run_yet",
            )
        )

    return EvolutionResponseDTO(
        stages=stages, narrative=_build_narrative(stages), meta=_meta(settings)
    )


def _build_narrative(stages: list[EvolutionStageDTO]) -> list[str]:
    by_stage = {s.stage: s for s in stages}
    lines: list[str] = []

    round0 = by_stage.get("round_0_attack")
    if round0 and round0.confrontation:
        c = round0.confrontation
        lines.append(
            f"Round-0: baseline v1 caught {c.caught_count}/{c.fraud_count} fraudulent bust-out "
            f"transactions in this scenario ({c.fraud_recall * 100:.0f}% recall)."
        )

    hardening = by_stage.get("defender_v2_hardening")
    if hardening and hardening.regression:
        f1 = hardening.regression.metrics.get("f1")
        recall = hardening.regression.metrics.get("recall")
        if f1 is not None and recall is not None:
            direction = "declined" if f1.delta < 0 else "improved"
            lines.append(
                f"On the untouched PaySim test split, Defender v2 {direction} overall F1 by "
                f"{abs(f1.delta) * 100:.2f} points and recall by "
                f"{abs(recall.delta) * 100:.2f} points versus baseline v1 -- hardening against "
                "specific hard positives was not free."
            )

    fresh = by_stage.get("fresh_confrontation")
    if fresh and fresh.confrontation:
        c = fresh.confrontation
        lines.append(
            f"Fresh confrontation: Defender v2 caught {c.caught_count}/{c.fraud_count} fraudulent "
            f"transactions from a newly generated bust-out scenario it was not trained on "
            f"({c.fraud_recall * 100:.0f}% recall)."
        )
        if c.evaded_count > 0:
            lines.append(
                f"{c.evaded_count} fraudulent transaction(s) still evaded Defender v2 in that "
                "fresh scenario -- improved, but not robustly hardened, against this attack "
                "family."
            )
        else:
            lines.append(
                "Defender v2 caught every fraudulent transaction in this one fresh scenario; "
                "this is not a claim of universal fraud detection across unseen attacks."
            )

    if not lines:
        lines.append(
            "No closed-loop cycle has produced real artifacts yet. Run the pipeline scripts "
            "(scripts/train_baseline_detector.py, scripts/run_bustout_confrontation.py, "
            "scripts/run_adaptive_bustout_round.py, scripts/harden_defender.py) to populate "
            "this view."
        )

    return lines


def build_evaluation(index: ArtifactIndex, settings: Settings) -> EvaluationResponseDTO:
    evaluations: list[EvaluationSummaryDTO] = []
    regression = None
    for m in sorted(index.models, key=_saved_at_key):
        summary = _model_summary(m)
        if summary.evaluation_validation:
            evaluations.append(summary.evaluation_validation)
        if summary.evaluation_test:
            evaluations.append(summary.evaluation_test)
        if regression is None and m.regression_vs_baseline:
            regression = _regression_summary(
                m.regression_vs_baseline,
                f"{MODELS_DIR}/{m.source_artifact}/regression_vs_baseline.json",
            )
    return EvaluationResponseDTO(
        evaluations=evaluations, regression=regression, meta=_meta(settings)
    )


def build_hardest_evasions(
    index: ArtifactIndex, settings: Settings, *, limit: int = 25
) -> HardestEvasionsResponseDTO:
    all_hardest = _all_hardest_evasions(index)
    return HardestEvasionsResponseDTO(
        evasions=all_hardest[:limit],
        total_available=len(all_hardest),
        limit=limit,
        meta=_meta(settings),
    )


def build_attacks(index: ArtifactIndex, settings: Settings) -> AttacksResponseDTO:
    seen: dict[str, AttackSummaryDTO] = {}

    def register(blueprint: Any, source_artifact: str, appearance: str) -> None:
        if not isinstance(blueprint, dict) or not blueprint.get("attack_id"):
            return
        attack_id = str(blueprint["attack_id"])
        existing = seen.get(attack_id)
        if existing:
            if appearance not in existing.appearances:
                existing.appearances.append(appearance)
            return
        seen[attack_id] = AttackSummaryDTO(
            attack_id=attack_id,
            attack_family=str(blueprint.get("attack_family", "")),
            generation=int(blueprint.get("generation", 0)),
            parent_blueprint_id=blueprint.get("parent_blueprint_id"),
            name=blueprint.get("name"),
            description=blueprint.get("description"),
            objective=blueprint.get("objective"),
            appearances=[appearance],
            source_artifact=source_artifact,
        )

    for c in index.confrontations:
        register(
            c.blueprint, f"{CONFRONTATIONS_DIR}/{c.source_artifact}/blueprint.json", c.report_id
        )
    for a in index.adaptive_rounds:
        register(
            a.report.get("selected_blueprint"),
            f"{ADAPTIVE_ROUNDS_DIR}/{a.source_artifact}/adaptive_round.json",
            a.report_id,
        )
        register(
            a.report.get("parent_blueprint"),
            f"{ADAPTIVE_ROUNDS_DIR}/{a.source_artifact}/adaptive_round.json",
            a.report_id,
        )
        for cand in a.candidates:
            register(
                cand.blueprint,
                f"{ADAPTIVE_ROUNDS_DIR}/{a.source_artifact}/candidates/{cand.candidate_id}/blueprint.json",
                cand.candidate_id,
            )

    attacks = sorted(seen.values(), key=lambda a: (a.generation, a.attack_id))
    return AttacksResponseDTO(attacks=attacks, meta=_meta(settings))


def build_attack_detail(
    index: ArtifactIndex, attack_id: str, settings: Settings
) -> AttackDetailDTO | None:
    blueprint: dict[str, Any] | None = None
    source_artifact = ""
    appearances: list[str] = []
    confrontation_results: list[ConfrontationSummaryDTO] = []

    for c in index.confrontations:
        if isinstance(c.blueprint, dict) and c.blueprint.get("attack_id") == attack_id:
            blueprint = blueprint or c.blueprint
            if not source_artifact:
                source_artifact = f"{CONFRONTATIONS_DIR}/{c.source_artifact}/blueprint.json"
            if c.report_id not in appearances:
                appearances.append(c.report_id)
            confrontation_results.append(
                _confrontation_summary(c, source_round=_confrontation_source_round(index, c))
            )

    for a in index.adaptive_rounds:
        for field_value in (a.report.get("selected_blueprint"), a.report.get("parent_blueprint")):
            if isinstance(field_value, dict) and field_value.get("attack_id") == attack_id:
                blueprint = blueprint or field_value
                if not source_artifact:
                    source_artifact = (
                        f"{ADAPTIVE_ROUNDS_DIR}/{a.source_artifact}/adaptive_round.json"
                    )
                if a.report_id not in appearances:
                    appearances.append(a.report_id)
        for cand in a.candidates:
            if isinstance(cand.blueprint, dict) and cand.blueprint.get("attack_id") == attack_id:
                blueprint = blueprint or cand.blueprint
                if not source_artifact:
                    source_artifact = (
                        f"{ADAPTIVE_ROUNDS_DIR}/{a.source_artifact}/candidates/"
                        f"{cand.candidate_id}/blueprint.json"
                    )
                if cand.candidate_id not in appearances:
                    appearances.append(cand.candidate_id)

    if blueprint is None:
        return None

    sequence = blueprint.get("sequence")
    parameters = blueprint.get("parameters")
    return AttackDetailDTO(
        attack_id=attack_id,
        attack_family=str(blueprint.get("attack_family", "")),
        generation=int(blueprint.get("generation", 0)),
        parent_blueprint_id=blueprint.get("parent_blueprint_id"),
        name=blueprint.get("name"),
        description=blueprint.get("description"),
        objective=blueprint.get("objective"),
        appearances=appearances,
        source_artifact=source_artifact,
        target_features=[
            str(x) for x in blueprint.get("target_features", []) if isinstance(x, str)
        ],
        sequence=[s for s in sequence if isinstance(s, dict)] if isinstance(sequence, list) else [],
        parameters=parameters if isinstance(parameters, dict) else {},
        confrontation_results=confrontation_results,
    )


def _load_transactions_by_id(
    root: Path, relative_path: str, *, limit: int = 5000
) -> dict[str, dict[str, Any]]:
    path = resolve_within(root, relative_path)
    return {
        str(row["transaction_id"]): row
        for row in iter_jsonl(path, limit=limit)
        if row.get("transaction_id")
    }


def build_recent_detections(
    index: ArtifactIndex, settings: Settings, *, limit: int = 50
) -> RecentDetectionsResponseDTO:
    records: list[DetectionRecordDTO] = []
    total_available = 0

    # No wall-clock timestamp is recorded at the report level, so "recent"
    # falls back to report id, descending -- a stable, real ordering key.
    for c in sorted(index.confrontations, key=lambda c: c.report_id, reverse=True):
        total_available += c.detector_output_count
        if len(records) >= limit:
            continue
        txns = _load_transactions_by_id(
            index.root, f"{CONFRONTATIONS_DIR}/{c.source_artifact}/transactions.jsonl"
        )
        outputs_path = resolve_within(
            index.root, CONFRONTATIONS_DIR, c.source_artifact, "detector_outputs.jsonl"
        )
        for row in iter_jsonl(outputs_path, limit=limit - len(records)):
            txn = txns.get(str(row.get("transaction_id", "")))
            try:
                records.append(
                    DetectionRecordDTO(
                        transaction_id=str(row["transaction_id"]),
                        scenario_id=txn.get("scenario_id") if txn else None,
                        risk_score=float(row["risk_score"]),
                        predicted_label=int(row.get("predicted_label", 0)),
                        recommended_action=str(row.get("recommended_action", "")),
                        ground_truth_label=txn.get("label") if txn else None,
                        model_version=str(row.get("model_version", "")),
                        attack_family=txn.get("attack_family") if txn else None,
                        is_synthetic=bool(txn.get("is_synthetic", False)) if txn else False,
                        timestamp=txn.get("timestamp") if txn else None,
                        source_artifact=f"{CONFRONTATIONS_DIR}/{c.source_artifact}/detector_outputs.jsonl",
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
            if len(records) >= limit:
                break

    return RecentDetectionsResponseDTO(
        detections=records, total_available=total_available, limit=limit, meta=_meta(settings)
    )


def build_benchmark(settings: Settings) -> FinalBenchmarkSummaryDTO:
    """The final, judge-facing benchmark summary: baseline v1, Defender v2,
    Defender v3, and the LOAFO generalization benchmark. `aegis.api.benchmark`
    does the actual artifact discovery/aggregation; this only wraps its
    result in the response DTO."""
    raw = build_final_benchmark_summary(settings.artifacts_root)
    raw["meta"] = _meta(settings).model_dump(mode="json")
    return FinalBenchmarkSummaryDTO(**raw)
