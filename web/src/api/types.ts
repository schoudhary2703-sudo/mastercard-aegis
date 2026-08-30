/**
 * Response types for the AEGIS API, mirroring `src/aegis/api/dto.py` field
 * for field.
 *
 * Unlike `types/aegis.ts` (which hand-mirrors `aegis.shared.contracts` and
 * is used only by the client-side mock demo), these are the *authoritative*
 * shape of what the real backend returns -- there is no separate codegen
 * step at foundation stage, so keeping this file's fields in lockstep with
 * `dto.py` is what "strict frontend adapter" means here. If a field is
 * renamed in `dto.py`, it must be renamed here in the same change.
 */

export interface MetaDTO {
  generated_at: string;
  data_source: "real";
  artifacts_root: string;
}

export interface ConfusionCountsDTO {
  true_positives: number;
  false_positives: number;
  true_negatives: number;
  false_negatives: number;
}

export interface ClassificationMetricsDTO {
  precision: number;
  recall: number;
  f1: number;
  pr_auc: number | null;
  roc_auc: number | null;
  false_positive_rate: number;
  false_negative_rate: number | null;
  recall_at_fixed_fpr: Record<string, number>;
  alert_rate: number | null;
  threshold: number | null;
  counts: ConfusionCountsDTO;
  support: number;
  positive_support: number;
}

export interface LatencyMetricsDTO {
  mean_ms: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  max_ms: number | null;
  samples: number;
}

export interface EvaluationSummaryDTO {
  evaluation_id: string;
  protocol: string;
  model_version: string;
  dataset_id: string;
  split: string;
  overall: ClassificationMetricsDTO;
  per_attack_family: Record<string, ClassificationMetricsDTO>;
  latency: LatencyMetricsDTO | null;
  fidelity_score: number | null;
  round_index: number | null;
  held_out_family: string | null;
  notes: string;
  created_at: string | null;
  source_artifact: string;
}

export type ModelRole = "baseline_v1" | "defender_v2" | "defender_v3";

export interface ModelSummaryDTO {
  model_version: string;
  detector_name: string | null;
  threshold: number | null;
  action_policy: Record<string, unknown>;
  trained_at: string | null;
  seed: number | null;
  is_hardened: boolean;
  role: ModelRole;
  source_artifact: string;
  evaluation_test: EvaluationSummaryDTO | null;
  evaluation_validation: EvaluationSummaryDTO | null;
}

export interface RegressionMetricDeltaDTO {
  baseline_v1: number;
  defender_v2: number;
  delta: number;
}

export interface RegressionComparisonDTO {
  baseline_model_version: string;
  defender_v2_model_version: string;
  metrics: Record<string, RegressionMetricDeltaDTO>;
  confusion_matrix: Record<string, ConfusionCountsDTO>;
  notes: string;
  split: string | null;
  source_artifact: string;
}

export interface HardestEvasionDTO {
  rank: number | null;
  scenario_id: string;
  transaction_id: string;
  attack_family: string;
  blueprint_id: string;
  generation: number;
  detector_risk_score: number;
  fidelity_score: number | null;
  hardness_score: number | null;
  action: string;
  detector_model_version: string;
  ground_truth_label: number;
  credible_evasion: boolean;
  source_round: string;
  source_artifact: string;
}

export interface ConfrontationSummaryDTO {
  report_id: string;
  model_version: string;
  attack_families: string[];
  generations: number[];
  scenario_count: number;
  total_transactions: number;
  fraud_count: number;
  caught_count: number;
  evaded_count: number;
  fraud_recall: number;
  adaptive: boolean;
  hardest_evasions: HardestEvasionDTO[];
  source_artifact: string;
}

export interface AdaptiveRoundStageStatsDTO {
  fraud_recall: number;
  average_fraud_risk_score: number | null;
  fidelity_score: number | null;
  fitness: number | null;
  caught_count: number;
  evaded_count: number;
}

export interface AdaptiveRoundSummaryDTO {
  report_id: string;
  round_index: number;
  seed: number | null;
  model_version: string;
  parent_confrontation_id: string | null;
  candidate_count: number;
  selected_blueprint_id: string | null;
  before: AdaptiveRoundStageStatsDTO | null;
  after: AdaptiveRoundStageStatsDTO | null;
  deltas: Record<string, number>;
  hardest_surviving_evasions: HardestEvasionDTO[];
  source_artifact: string;
}

export interface HardeningSummaryDTO {
  run_id: string;
  hard_positive_count: number;
  fraud_count: number | null;
  source_scenarios: string[];
  excluded_scenario_ids: string[];
  tuned_threshold: number | null;
  source_artifact: string;
}

export interface AttackSummaryDTO {
  attack_id: string;
  attack_family: string;
  generation: number;
  parent_blueprint_id: string | null;
  name: string | null;
  description: string | null;
  objective: string | null;
  appearances: string[];
  source_artifact: string;
}

export interface AttackDetailDTO extends AttackSummaryDTO {
  target_features: string[];
  sequence: Record<string, unknown>[];
  parameters: Record<string, unknown>;
  confrontation_results: ConfrontationSummaryDTO[];
}

export interface DetectionRecordDTO {
  transaction_id: string;
  scenario_id: string | null;
  risk_score: number;
  predicted_label: number;
  recommended_action: string;
  ground_truth_label: number | null;
  model_version: string;
  attack_family: string | null;
  is_synthetic: boolean;
  timestamp: string | null;
  source_artifact: string;
}

export interface OverviewResponseDTO {
  attack_families_in_scope: string[];
  models: ModelSummaryDTO[];
  current_model: ModelSummaryDTO | null;
  regression: RegressionComparisonDTO | null;
  confrontation_count: number;
  adaptive_round_count: number;
  hardest_evasions_preview: HardestEvasionDTO[];
  meta: MetaDTO;
}

export interface AttacksResponseDTO {
  attacks: AttackSummaryDTO[];
  meta: MetaDTO;
}

export interface RecentDetectionsResponseDTO {
  detections: DetectionRecordDTO[];
  total_available: number;
  limit: number;
  meta: MetaDTO;
}

export type EvolutionStageName =
  | "baseline_v1"
  | "round_0_attack"
  | "adaptive_red"
  | "defender_v2_hardening"
  | "fresh_confrontation"
  | "generation_2_adaptation";

export interface EvolutionStageDTO {
  stage: EvolutionStageName;
  label: string;
  status: "real" | "not_run_yet";
  model: ModelSummaryDTO | null;
  confrontation: ConfrontationSummaryDTO | null;
  adaptive_round: AdaptiveRoundSummaryDTO | null;
  regression: RegressionComparisonDTO | null;
  hardening: HardeningSummaryDTO | null;
}

export interface EvolutionResponseDTO {
  stages: EvolutionStageDTO[];
  narrative: string[];
  meta: MetaDTO;
}

export interface EvaluationResponseDTO {
  evaluations: EvaluationSummaryDTO[];
  regression: RegressionComparisonDTO | null;
  meta: MetaDTO;
}

export interface HardestEvasionsResponseDTO {
  evasions: HardestEvasionDTO[];
  total_available: number;
  limit: number;
  meta: MetaDTO;
}

// -- final benchmark (baseline v1 / Defender v2 / Defender v3 / LOAFO) ------

export interface ModelComparisonEntryDTO {
  model_version: string;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  pr_auc: number | null;
  roc_auc: number | null;
  false_positive_rate: number | null;
  recall_at_fixed_fpr: Record<string, number>;
  threshold: number | null;
  latency_ms: Record<string, unknown> | null;
  confusion: Record<string, number> | null;
}

export interface ModelComparisonDTO {
  split: string;
  dataset_id: string;
  baseline_v1: ModelComparisonEntryDTO | null;
  defender_v2: ModelComparisonEntryDTO | null;
  defender_v3: ModelComparisonEntryDTO | null;
  source_artifact: string;
}

export interface FamilyModelPerformanceDTO {
  model_version: string | null;
  recall: number | null;
  caught: number | null;
  evaded: number | null;
  average_fraud_risk_score: number | null;
  fitness: number | null;
  note: string | null;
}

export interface FreshFamilyPerformanceDTO {
  attack_family: string;
  fold_id: string;
  training_families: string[];
  fraud_count: number;
  fidelity_score: number | null;
  fold_model: FamilyModelPerformanceDTO;
  defender_v3: FamilyModelPerformanceDTO;
  source_artifact: string;
}

export interface LoafoFamilyResultDTO {
  attack_family: string;
  fold_id: string;
  training_families: string[];
  loafo_recall: number;
  defender_v3_recall_same_scenario: number;
  verdict: "strong" | "partial" | "weak" | string;
}

export interface LoafoBenchmarkDTO {
  mean_loafo_recall: number;
  overall_verdict: "strong" | "partial" | "weak" | "unknown" | string;
  verdict_rubric: string;
  per_family: LoafoFamilyResultDTO[];
  source_artifact: string;
}

export interface FinalBenchmarkSummaryDTO {
  model_comparison: ModelComparisonDTO | null;
  fresh_family_performance: FreshFamilyPerformanceDTO[];
  loafo: LoafoBenchmarkDTO | null;
  hardest_surviving_attacks: HardestEvasionDTO[];
  limitations: string[];
  claim_flags: Record<string, unknown>;
  meta: MetaDTO;
}

// -- attack-lab experiment replay -------------------------------------------

export interface ReplayEventDTO {
  transaction_id: string;
  sequence_index: number | null;
  risk_score: number;
  threshold: number | null;
  action: string;
  predicted_label: number;
  ground_truth_label: number;
  is_fraud: boolean;
  caught: boolean;
  amount: number | null;
  timestamp: string | null;
}

export interface ExperimentStageDTO {
  label: string;
  model_version: string;
  role: string;
  fraud_count: number;
  caught_count: number;
  escaped_count: number;
  recall: number;
}

export interface ExperimentParameterDTO {
  name: string;
  value: unknown;
  mutable: boolean;
}

export interface ExperimentDTO {
  attack_family: string;
  label: string;
  headline: string;
  genai_angle: string;
  attack_name: string;
  blueprint_id: string;
  scenario_id: string;
  model_version: string;
  fraud_count: number;
  caught_count: number;
  escaped_count: number;
  recall: number;
  fidelity_score: number | null;
  parameters: ExperimentParameterDTO[];
  events: ReplayEventDTO[];
  events_complete: boolean;
  events_note: string | null;
  hardest_survivor: HardestEvasionDTO | null;
  progression: ExperimentStageDTO[];
  /** Current core defender's result on this family. For a LOAFO family this is
   * NOT the replayed stream (which is the handicapped fold model). */
  current_defender: ExperimentStageDTO | null;
  replayed_model_label: string;
  source_artifacts: string[];
}

export interface ExperimentsResponseDTO {
  experiments: ExperimentDTO[];
  meta: MetaDTO;
}

// -- GenAI reasoning runs ---------------------------------------------------

export interface GenAIRunDTO {
  run_id: string;
  stage: string;
  created_at: string | null;
  provider: string;
  model: string;
  prompt_version: string;
  live: boolean;
  schema_valid: boolean;
  failure: string | null;
  response: Record<string, unknown> | null;
  source_artifact: string;
  attack_hypothesis: string;
  genai_enablement: string;
  blind_spot_hypothesis: string;
  evidence: string[];
  observable_signals: string[];
  confidence: number | null;
  proposed_mutations: ProposedMutationDTO[];
}

export interface ProposedMutationDTO {
  parameter: string;
  direction: string;
  magnitude: number | null;
  rationale: string;
  confidence: number | null;
}

export interface AppliedMutationDTO {
  parameter: string;
  direction: string;
  magnitude: number | null;
  from_value: number | null;
  to_value: number | null;
  rationale: string;
  confidence: number | null;
}

export interface RejectedMutationDTO {
  parameter: string;
  direction: string;
  magnitude: number | null;
  reason: string;
}

export interface GenAIGuidedGenerationDTO {
  generation_id: string;
  created_at: string | null;
  attack_family: string | null;
  genai_run_id: string;
  provider: string;
  model: string;
  prompt_version: string;
  live: boolean;
  seed: number | null;
  source_confrontation_id: string;
  detector_model_version: string;
  blind_spot_hypothesis: string;
  applied_mutations: AppliedMutationDTO[];
  rejected_mutations: RejectedMutationDTO[];
  parent_blueprint_id: string;
  resulting_blueprint_id: string;
  scenario_id: string | null;
  fraud_count: number | null;
  caught_count: number | null;
  escaped_count: number | null;
  recall: number | null;
  fidelity_score: number | null;
  hardest_survivor: Record<string, unknown> | null;
  /** Wall-clock of the run itself, when it was measured. */
  runtime_seconds: number | null;
  dry_run: boolean;
  /** Server-computed: complete provenance AND at least one applied mutation.
   * Never re-derive this in the UI. */
  genai_guided: boolean;
  source_artifact: string;
}

export interface GenAIResponseDTO {
  runs: GenAIRunDTO[];
  attack_analyst: GenAIRunDTO | null;
  blind_spot_analyst: GenAIRunDTO | null;
  /** Restricted to genuinely live calls. Badge "LIVE GENAI" off these only. */
  live_attack_analyst: GenAIRunDTO | null;
  live_blind_spot_analyst: GenAIRunDTO | null;
  guided_generations: GenAIGuidedGenerationDTO[];
  latest_guided_generation: GenAIGuidedGenerationDTO | null;
  has_live_genai: boolean;
  /** Recommended vs actionable. Server-computed; `applied` is always false. */
  attack_recommendations: AttackRecommendationPreviewDTO | null;
  /** Per-family coverage across the three deeply simulated families. */
  family_coverage: GenAIFamilySummaryDTO | null;
  meta: MetaDTO;
}

export interface StageCoverageDTO {
  /** Live AND schema-valid. A recorded replay never sets this. */
  available: boolean;
  run_id: string;
  provider: string;
  model: string;
  prompt_version: string;
  live: boolean;
  created_at: string;
  source_artifact: string;
  reason: string;
}

export interface GuidedCoverageDTO {
  available: boolean;
  generation_id: string;
  scenario_id: string;
  applied_mutation_count: number;
  rejected_mutation_count: number;
  seed: number | null;
  detector_model_version: string;
  fraud_count: number | null;
  caught_count: number | null;
  escaped_count: number | null;
  recall: number | null;
  fidelity_score: number | null;
  runtime_seconds: number | null;
  hardest_survivor_id: string;
  reason: string;
}

export interface FamilyCoverageDTO {
  attack_family: string;
  label: string;
  attack_analyst: StageCoverageDTO;
  blind_spot_analyst: StageCoverageDTO;
  guided_generation: GuidedCoverageDTO;
  has_live_genai: boolean;
  is_fully_covered: boolean;
}

export interface GenAIFamilySummaryDTO {
  summary_version: string;
  families: FamilyCoverageDTO[];
  live_family_count: number;
  fully_covered_family_count: number;
  guided_family_count: number;
  limitations: string[];
}

export interface RecommendedParameterDTO {
  name: string;
  recommended_value: string | number | boolean | null;
  unit: string | null;
  rationale: string;
  actionable: boolean;
  reason: string;
  current_value: string | number | boolean | null;
  minimum: number | null;
  maximum: number | null;
  param_type: string;
}

export interface AttackRecommendationPreviewDTO {
  blueprint_id: string;
  genai_run_id: string;
  recommended_count: number;
  actionable_count: number;
  parameters: RecommendedParameterDTO[];
  /** Always false: recommendations are surfaced, never auto-applied. */
  applied: boolean;
}

export interface TaxonomyEvidenceSourceDTO {
  title: string;
  url: string;
}

export interface TaxonomyScenarioDTO {
  id: string;
  name: string;
  category: string;
  channels: string[];
  rails: string[];
  genai_abuse_mechanism: string;
  observable_signals: string[];
  plausibility_evidence_note: string;
  evidence_sources: TaxonomyEvidenceSourceDTO[];
  simulation_readiness: string;
  implementation_status: string;
  /** The only flag that licenses showing detector numbers for an entry. */
  deeply_simulated: boolean;
  attack_family: string | null;
}

export interface TaxonomyDTO {
  taxonomy_version: string;
  scope_note: string;
  total_attacks_identified: number | null;
  deeply_simulated: number | null;
  category_count: number;
  channel_count: number;
  rail_count: number;
  categories: string[];
  channels: string[];
  rails: string[];
  scenarios: TaxonomyScenarioDTO[];
  source_artifact: string;
}

export interface FidelityMetricDTO {
  name: string;
  score: number | null;
}

export interface FidelityComponentGroupDTO {
  group: string;
  metrics: FidelityMetricDTO[];
}

export interface GenerationScaleFamilyDTO {
  attack_family: string;
  blueprint_id: string;
  generator_name: string;
  seed: number | null;
  scenarios_generated: number | null;
  transactions_generated: number | null;
  fraud_transactions_generated: number | null;
  generation_seconds: number | null;
  throughput_transactions_per_second: number | null;
  fidelity_excluding_constraints: number | null;
  distributional_fidelity_score: number | null;
  generator_reported_overall_fidelity_score: number | null;
  constraint_valid_percentage: number | null;
  constraint_violation_rate: number | null;
  deterministic_verified: boolean;
  historical_scenario_id_overlap_count: number | null;
  fidelity_components: FidelityComponentGroupDTO[];
  limitations: string[];
}

export interface GenerationScaleDTO {
  benchmark_version: string;
  benchmark_scope: string;
  platform: string;
  family_count: number | null;
  total_scenarios: number | null;
  total_transactions: number | null;
  total_fraud_transactions: number | null;
  total_generation_seconds: number | null;
  aggregate_throughput_transactions_per_second: number | null;
  all_constraints_valid: boolean;
  all_deterministic: boolean;
  historical_scenario_id_overlap_count: number | null;
  families: GenerationScaleFamilyDTO[];
  fidelity_caveat: string;
  source_artifact: string;
}

export interface LandscapeResponseDTO {
  taxonomy: TaxonomyDTO | null;
  generation_scale: GenerationScaleDTO | null;
  meta: MetaDTO;
}
