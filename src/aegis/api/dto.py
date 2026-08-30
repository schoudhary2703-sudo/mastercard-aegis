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


# -- attack-lab experiment replay -----------------------------------------


class ReplayEventDTO(ApiModel):
    """One transaction a real detector really scored, read back off disk."""

    transaction_id: str
    sequence_index: int | None = None
    risk_score: float
    threshold: float | None = None
    action: str = ""
    predicted_label: int = 0
    ground_truth_label: int = 0
    is_fraud: bool = False
    caught: bool = False
    amount: float | None = None
    timestamp: str | None = None


class ExperimentStageDTO(ApiModel):
    """One defender generation's result on this family, for before/after."""

    label: str
    model_version: str = ""
    role: str = ""
    fraud_count: int = 0
    caught_count: int = 0
    escaped_count: int = 0
    recall: float = 0.0


class ExperimentParameterDTO(ApiModel):
    name: str
    value: Any = None
    mutable: bool = False


class ExperimentDTO(ApiModel):
    attack_family: str
    label: str
    headline: str = ""
    genai_angle: str = ""
    attack_name: str = ""
    blueprint_id: str = ""
    scenario_id: str = ""
    model_version: str = ""
    fraud_count: int = 0
    caught_count: int = 0
    escaped_count: int = 0
    recall: float = 0.0
    fidelity_score: float | None = None
    parameters: list[ExperimentParameterDTO] = []
    events: list[ReplayEventDTO] = []
    events_complete: bool = False
    events_note: str | None = None
    hardest_survivor: HardestEvasionDTO | None = None
    progression: list[ExperimentStageDTO] = []
    # The current core defender's result on this family. For a LOAFO family
    # this is NOT the replayed stream (which is the handicapped fold model),
    # so aggregating "how does the current defender do" must use this.
    current_defender: ExperimentStageDTO | None = None
    replayed_model_label: str = ""
    source_artifacts: list[str] = []


class ExperimentsResponseDTO(ApiModel):
    experiments: list[ExperimentDTO] = []
    meta: MetaDTO


# -- GenAI reasoning runs ---------------------------------------------------


class ProposedMutationDTO(ApiModel):
    """What the analyst asked for -- not necessarily what the bounds allowed."""

    parameter: str = ""
    direction: str = ""
    magnitude: float | None = None
    rationale: str = ""
    confidence: float | None = None


class GenAIRunDTO(ApiModel):
    run_id: str
    stage: str
    created_at: str | None = None
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    live: bool = False
    schema_valid: bool = False
    failure: str | None = None
    response: dict[str, Any] | None = None
    source_artifact: str = ""
    # Projections of `response` for compact rendering. Empty when the field
    # is absent from the artifact -- never a synthesized placeholder.
    attack_hypothesis: str = ""
    genai_enablement: str = ""
    blind_spot_hypothesis: str = ""
    evidence: list[str] = []
    observable_signals: list[str] = []
    confidence: float | None = None
    proposed_mutations: list[ProposedMutationDTO] = []


class AppliedMutationDTO(ApiModel):
    parameter: str
    direction: str = ""
    magnitude: float | None = None
    from_value: float | None = None
    to_value: float | None = None
    rationale: str = ""
    confidence: float | None = None


class RejectedMutationDTO(ApiModel):
    parameter: str = ""
    direction: str = ""
    magnitude: float | None = None
    reason: str = ""


class GenAIGuidedGenerationDTO(ApiModel):
    """One GenAI-guided next generation, with full provenance.

    `genai_guided` is computed server-side from complete provenance plus at
    least one surviving mutation -- the UI must not re-derive it, so a record
    lacking provenance can never be badged as GenAI-guided.
    """

    generation_id: str
    created_at: str | None = None
    attack_family: str | None = None
    genai_run_id: str = ""
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    live: bool = False
    seed: int | None = None
    source_confrontation_id: str = ""
    detector_model_version: str = ""
    blind_spot_hypothesis: str = ""
    applied_mutations: list[AppliedMutationDTO] = []
    rejected_mutations: list[RejectedMutationDTO] = []
    parent_blueprint_id: str = ""
    resulting_blueprint_id: str = ""
    scenario_id: str | None = None
    fraud_count: int | None = None
    caught_count: int | None = None
    escaped_count: int | None = None
    recall: float | None = None
    fidelity_score: float | None = None
    hardest_survivor: dict[str, Any] | None = None
    runtime_seconds: float | None = None
    dry_run: bool = True
    genai_guided: bool = False
    source_artifact: str = ""


class RecommendedParameterDTO(ApiModel):
    """One Attack Analyst recommendation checked against a blueprint's spec."""

    name: str
    recommended_value: bool | int | float | str | None = None
    unit: str | None = None
    rationale: str = ""
    actionable: bool = False
    reason: str = ""
    current_value: bool | int | float | str | None = None
    minimum: float | None = None
    maximum: float | None = None
    param_type: str = ""


class AttackRecommendationPreviewDTO(ApiModel):
    """Recommended vs actionable. `applied` is always False -- see the adapter."""

    blueprint_id: str = ""
    genai_run_id: str = ""
    recommended_count: int = 0
    actionable_count: int = 0
    parameters: list[RecommendedParameterDTO] = []
    applied: bool = False


class StageCoverageDTO(ApiModel):
    """One analyst stage for one family. `available` means live AND schema-valid."""

    available: bool = False
    run_id: str = ""
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    live: bool = False
    created_at: str = ""
    source_artifact: str = ""
    reason: str = ""


class GuidedCoverageDTO(ApiModel):
    available: bool = False
    generation_id: str = ""
    scenario_id: str = ""
    applied_mutation_count: int = 0
    rejected_mutation_count: int = 0
    seed: int | None = None
    detector_model_version: str = ""
    fraud_count: int | None = None
    caught_count: int | None = None
    escaped_count: int | None = None
    recall: float | None = None
    fidelity_score: float | None = None
    runtime_seconds: float | None = None
    hardest_survivor_id: str = ""
    reason: str = ""


class FamilyCoverageDTO(ApiModel):
    attack_family: str
    label: str = ""
    attack_analyst: StageCoverageDTO
    blind_spot_analyst: StageCoverageDTO
    guided_generation: GuidedCoverageDTO
    has_live_genai: bool = False
    is_fully_covered: bool = False


class GenAIFamilySummaryDTO(ApiModel):
    """Per-family GenAI coverage, computed server-side from persisted artifacts."""

    summary_version: str = ""
    families: list[FamilyCoverageDTO] = []
    live_family_count: int = 0
    fully_covered_family_count: int = 0
    guided_family_count: int = 0
    limitations: list[str] = []


class GenAIResponseDTO(ApiModel):
    runs: list[GenAIRunDTO] = []
    attack_analyst: GenAIRunDTO | None = None
    blind_spot_analyst: GenAIRunDTO | None = None
    # Restricted to genuinely live calls, so the UI can badge "LIVE GENAI"
    # without ever promoting a recorded replay.
    live_attack_analyst: GenAIRunDTO | None = None
    live_blind_spot_analyst: GenAIRunDTO | None = None
    guided_generations: list[GenAIGuidedGenerationDTO] = []
    latest_guided_generation: GenAIGuidedGenerationDTO | None = None
    has_live_genai: bool = False
    # What the live Attack Analyst recommended vs what the canonical blueprint
    # would accept. Display-only; nothing is applied from it.
    attack_recommendations: AttackRecommendationPreviewDTO | None = None
    # Per-family coverage across the three deeply simulated families.
    family_coverage: GenAIFamilySummaryDTO | None = None
    meta: MetaDTO


# -- Fraud landscape: breadth taxonomy + generation scale ------------------


class TaxonomyEvidenceSourceDTO(ApiModel):
    title: str = ""
    url: str = ""


class TaxonomyScenarioDTO(ApiModel):
    """One catalogued attack. `deeply_simulated` is the only thing that
    licenses showing detector numbers for it."""

    id: str
    name: str = ""
    category: str = ""
    channels: list[str] = []
    rails: list[str] = []
    genai_abuse_mechanism: str = ""
    observable_signals: list[str] = []
    plausibility_evidence_note: str = ""
    evidence_sources: list[TaxonomyEvidenceSourceDTO] = []
    simulation_readiness: str = ""
    implementation_status: str = ""
    deeply_simulated: bool = False
    attack_family: str | None = None


class TaxonomyDTO(ApiModel):
    taxonomy_version: str = ""
    scope_note: str = ""
    total_attacks_identified: int | None = None
    deeply_simulated: int | None = None
    category_count: int = 0
    channel_count: int = 0
    rail_count: int = 0
    categories: list[str] = []
    channels: list[str] = []
    rails: list[str] = []
    scenarios: list[TaxonomyScenarioDTO] = []
    source_artifact: str = ""


class FidelityMetricDTO(ApiModel):
    name: str
    score: float | None = None


class FidelityComponentGroupDTO(ApiModel):
    group: str
    metrics: list[FidelityMetricDTO] = []


class GenerationScaleFamilyDTO(ApiModel):
    attack_family: str
    blueprint_id: str = ""
    generator_name: str = ""
    seed: int | None = None
    scenarios_generated: int | None = None
    transactions_generated: int | None = None
    fraud_transactions_generated: int | None = None
    generation_seconds: float | None = None
    throughput_transactions_per_second: float | None = None
    fidelity_excluding_constraints: float | None = None
    distributional_fidelity_score: float | None = None
    generator_reported_overall_fidelity_score: float | None = None
    constraint_valid_percentage: float | None = None
    constraint_violation_rate: float | None = None
    deterministic_verified: bool = False
    historical_scenario_id_overlap_count: int | None = None
    fidelity_components: list[FidelityComponentGroupDTO] = []
    limitations: list[str] = []


class GenerationScaleDTO(ApiModel):
    benchmark_version: str = ""
    benchmark_scope: str = ""
    platform: str = ""
    family_count: int | None = None
    total_scenarios: int | None = None
    total_transactions: int | None = None
    total_fraud_transactions: int | None = None
    total_generation_seconds: float | None = None
    aggregate_throughput_transactions_per_second: float | None = None
    all_constraints_valid: bool = False
    all_deterministic: bool = False
    historical_scenario_id_overlap_count: int | None = None
    families: list[GenerationScaleFamilyDTO] = []
    fidelity_caveat: str = ""
    source_artifact: str = ""


class LandscapeResponseDTO(ApiModel):
    """Breadth (what AEGIS identified) and scale (what it generated).

    Both halves are `None` until their artifact exists, so the UI reports
    "not produced yet" instead of rendering a zero.
    """

    taxonomy: TaxonomyDTO | None = None
    generation_scale: GenerationScaleDTO | None = None
    meta: MetaDTO


class FinalBenchmarkSummaryDTO(ApiModel):
    model_comparison: ModelComparisonDTO | None = None
    fresh_family_performance: list[FreshFamilyPerformanceDTO] = []
    loafo: LoafoBenchmarkDTO | None = None
    hardest_surviving_attacks: list[HardestEvasionDTO] = []
    limitations: list[str] = []
    claim_flags: dict[str, Any] = {}
    meta: MetaDTO
