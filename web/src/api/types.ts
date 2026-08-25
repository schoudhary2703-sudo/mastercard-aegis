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

export interface ModelSummaryDTO {
  model_version: string;
  detector_name: string | null;
  threshold: number | null;
  action_policy: Record<string, unknown>;
  trained_at: string | null;
  seed: number | null;
  is_hardened: boolean;
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
