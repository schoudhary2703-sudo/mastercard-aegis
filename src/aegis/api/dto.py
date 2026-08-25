"""API response DTOs.

These are deliberately **not** `aegis.shared.contracts` models re-exported
verbatim. Most of what this API serves (`confrontation.json`,
`adaptive_round.json`, hardening `provenance.json`, round comparisons) are
script-level *reports*, not cross-team contracts -- there is no shared type
for "a confrontation report" to re-export. Where an artifact does embed a
real contract (`EvaluationResult`, `AttackBlueprint`, `DetectorOutput`), the
DTOs below mirror that contract's field names and shape exactly, so no
renaming happens between what `aegis.shared.contracts` defines and what the
API returns.

This is the adapter layer called for in the integration brief: it exists so
`web/` never has to hand-parse raw artifact JSON, and so a shape change in a
script's report format is absorbed here instead of rippling into the UI.

Every DTO that represents a real, on-disk result carries `source_artifact`
(the artifact directory or file it was read from) so the UI can show
provenance and so "real" is a verifiable claim, not a label.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base for all response DTOs. Permissive: artifacts evolve; the API
    should degrade by omission, not by refusing to serve a whole report
    because one script added a field."""

    model_config = ConfigDict(extra="ignore")


class MetaDTO(ApiModel):
    generated_at: str
    data_source: Literal["real"] = "real"
    artifacts_root: str


# -- shared metric shapes (mirror aegis.shared.contracts.evaluation) --------


class ConfusionCountsDTO(ApiModel):
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0


class ClassificationMetricsDTO(ApiModel):
    precision: float
    recall: float
    f1: float
    pr_auc: float | None = None
    roc_auc: float | None = None
    false_positive_rate: float
    false_negative_rate: float | None = None
    recall_at_fixed_fpr: dict[str, float] = {}
    alert_rate: float | None = None
    threshold: float | None = None
    counts: ConfusionCountsDTO = ConfusionCountsDTO()
    support: int = 0
    positive_support: int = 0


class LatencyMetricsDTO(ApiModel):
    mean_ms: float
    p50_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None
    max_ms: float | None = None
    samples: int = 0


class EvaluationSummaryDTO(ApiModel):
    evaluation_id: str
    protocol: str
    model_version: str
    dataset_id: str = ""
    split: str
    overall: ClassificationMetricsDTO
    per_attack_family: dict[str, ClassificationMetricsDTO] = {}
    latency: LatencyMetricsDTO | None = None
    fidelity_score: float | None = None
    round_index: int | None = None
    held_out_family: str | None = None
    notes: str = ""
    created_at: str | None = None
    source_artifact: str


class ModelSummaryDTO(ApiModel):
    model_version: str
    detector_name: str | None = None
    threshold: float | None = None
    action_policy: dict[str, Any] = {}
    trained_at: str | None = None
    seed: int | None = None
    is_hardened: bool = False
    role: Literal["baseline_v1", "defender_v2", "defender_v3"] = "baseline_v1"
    source_artifact: str
    evaluation_test: EvaluationSummaryDTO | None = None
    evaluation_validation: EvaluationSummaryDTO | None = None


class RegressionMetricDeltaDTO(ApiModel):
    baseline_v1: float
    defender_v2: float
    delta: float


class RegressionComparisonDTO(ApiModel):
    baseline_model_version: str
    defender_v2_model_version: str
    metrics: dict[str, RegressionMetricDeltaDTO] = {}
    confusion_matrix: dict[str, ConfusionCountsDTO] = {}
    notes: str = ""
    split: str | None = None
    source_artifact: str


# -- attacks / evasions -------------------------------------------------


class HardestEvasionDTO(ApiModel):
    rank: int | None = None
    scenario_id: str
    transaction_id: str
    attack_family: str
    blueprint_id: str
    generation: int = 0
    detector_risk_score: float
    fidelity_score: float | None = None
    hardness_score: float | None = None
    action: str
    detector_model_version: str
    ground_truth_label: int
    credible_evasion: bool = False
    source_round: str
    source_artifact: str


class ConfrontationSummaryDTO(ApiModel):
    report_id: str
    model_version: str
    attack_families: list[str] = []
    generations: list[int] = []
    scenario_count: int
    total_transactions: int
    fraud_count: int
    caught_count: int
    evaded_count: int
    fraud_recall: float
    adaptive: bool
    hardest_evasions: list[HardestEvasionDTO] = []
    source_artifact: str


class AdaptiveRoundStageStatsDTO(ApiModel):
    fraud_recall: float
    average_fraud_risk_score: float | None = None
    fidelity_score: float | None = None
    fitness: float | None = None
    caught_count: int = 0
    evaded_count: int = 0


class AdaptiveRoundSummaryDTO(ApiModel):
    report_id: str
    round_index: int
    seed: int | None = None
    model_version: str
    parent_confrontation_id: str | None = None
    candidate_count: int
    selected_blueprint_id: str | None = None
    before: AdaptiveRoundStageStatsDTO | None = None
    after: AdaptiveRoundStageStatsDTO | None = None
    deltas: dict[str, float] = {}
    hardest_surviving_evasions: list[HardestEvasionDTO] = []
    source_artifact: str


class HardeningSummaryDTO(ApiModel):
    run_id: str
    hard_positive_count: int
    fraud_count: int | None = None
    source_scenarios: list[str] = []
    excluded_scenario_ids: list[str] = []
    tuned_threshold: float | None = None
    source_artifact: str


class AttackSummaryDTO(ApiModel):
    attack_id: str
    attack_family: str
    generation: int = 0
    parent_blueprint_id: str | None = None
    name: str | None = None
    description: str | None = None
    objective: str | None = None
    appearances: list[str] = []
    source_artifact: str


class AttackDetailDTO(AttackSummaryDTO):
    target_features: list[str] = []
    sequence: list[dict[str, Any]] = []
    parameters: dict[str, Any] = {}
    confrontation_results: list[ConfrontationSummaryDTO] = []


class DetectionRecordDTO(ApiModel):
    transaction_id: str
    scenario_id: str | None = None
    risk_score: float
    predicted_label: int
    recommended_action: str
    ground_truth_label: int | None = None
    model_version: str
    attack_family: str | None = None
    is_synthetic: bool = False
    timestamp: str | None = None
    source_artifact: str


# -- top-level responses --------------------------------------------------


class OverviewResponseDTO(ApiModel):
    attack_families_in_scope: list[str]
    models: list[ModelSummaryDTO]
    current_model: ModelSummaryDTO | None = None
    regression: RegressionComparisonDTO | None = None
    confrontation_count: int
    adaptive_round_count: int
    hardest_evasions_preview: list[HardestEvasionDTO] = []
    meta: MetaDTO


class AttacksResponseDTO(ApiModel):
    attacks: list[AttackSummaryDTO]
    meta: MetaDTO


class RecentDetectionsResponseDTO(ApiModel):
    detections: list[DetectionRecordDTO]
    total_available: int
    limit: int
    meta: MetaDTO


class EvolutionStageDTO(ApiModel):
    stage: str
    label: str
    status: Literal["real", "not_run_yet"]
    model: ModelSummaryDTO | None = None
    confrontation: ConfrontationSummaryDTO | None = None
    adaptive_round: AdaptiveRoundSummaryDTO | None = None
    regression: RegressionComparisonDTO | None = None
    hardening: HardeningSummaryDTO | None = None


class EvolutionResponseDTO(ApiModel):
    stages: list[EvolutionStageDTO]
    narrative: list[str]
    meta: MetaDTO


class EvaluationResponseDTO(ApiModel):
    evaluations: list[EvaluationSummaryDTO]
    regression: RegressionComparisonDTO | None = None
    meta: MetaDTO


class HardestEvasionsResponseDTO(ApiModel):
    evasions: list[HardestEvasionDTO]
    total_available: int
    limit: int
    meta: MetaDTO


# -- final benchmark (baseline v1 / Defender v2 / Defender v3 / LOAFO) ------


class ModelComparisonEntryDTO(ApiModel):
    model_version: str
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    pr_auc: float | None = None
    roc_auc: float | None = None
    false_positive_rate: float | None = None
    recall_at_fixed_fpr: dict[str, float] = {}
    threshold: float | None = None
    latency_ms: dict[str, Any] | None = None
    confusion: dict[str, int] | None = None


class ModelComparisonDTO(ApiModel):
    split: str
    dataset_id: str = ""
    baseline_v1: ModelComparisonEntryDTO | None = None
    defender_v2: ModelComparisonEntryDTO | None = None
    defender_v3: ModelComparisonEntryDTO | None = None
    source_artifact: str


class FamilyModelPerformanceDTO(ApiModel):
    model_version: str | None = None
    recall: float | None = None
    caught: int | None = None
    evaded: int | None = None
    average_fraud_risk_score: float | None = None
    fitness: float | None = None
    note: str | None = None


class FreshFamilyPerformanceDTO(ApiModel):
    attack_family: str
    fold_id: str
    training_families: list[str] = []
    fraud_count: int
    fidelity_score: float | None = None
    fold_model: FamilyModelPerformanceDTO
    defender_v3: FamilyModelPerformanceDTO
    source_artifact: str


class LoafoFamilyResultDTO(ApiModel):
    attack_family: str
    fold_id: str
    training_families: list[str] = []
    loafo_recall: float
    defender_v3_recall_same_scenario: float
    verdict: str


class LoafoBenchmarkDTO(ApiModel):
    mean_loafo_recall: float
    overall_verdict: str
    verdict_rubric: str = ""
    per_family: list[LoafoFamilyResultDTO] = []
    source_artifact: str


class FinalBenchmarkSummaryDTO(ApiModel):
    model_comparison: ModelComparisonDTO | None = None
    fresh_family_performance: list[FreshFamilyPerformanceDTO] = []
    loafo: LoafoBenchmarkDTO | None = None
    hardest_surviving_attacks: list[HardestEvasionDTO] = []
    limitations: list[str] = []
    claim_flags: dict[str, Any] = {}
    meta: MetaDTO
