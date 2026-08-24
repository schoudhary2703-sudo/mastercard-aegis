/**
 * Mirrors `docs/CONTRACTS.md` / `aegis.shared.contracts`, by hand.
 *
 * This is a UI-side re-declaration, not a codegen output: `web/` does not
 * import Python and computes nothing beyond formatting these shapes. If a
 * field here drifts from the real contract, the fix is to update this file
 * to match `docs/CONTRACTS.md` -- never the other way around.
 */

export type AttackFamily =
  | "synthetic_identity_bustout"
  | "mule_network_structuring"
  | "adaptive_detector_evasion";

export type TransactionType = "payment" | "transfer" | "cash_out" | "cash_in" | "debit";
export type Channel = "card_present" | "card_not_present" | "online" | "atm" | "p2p";
export type FraudLabel = 0 | 1 | -1; // legit / fraud / unknown
export type RecommendedAction = "approve" | "step_up" | "review" | "decline";
export type DataSplit = "train" | "val" | "test" | "closed_loop";
export type EvaluationProtocol =
  | "HOLD_OUT"
  | "CLOSED_LOOP_ROUND"
  | "LEAVE_ONE_ATTACK_FAMILY_OUT";
export type MutationDirection = "increase" | "decrease" | "set" | "jitter" | "resample";

export interface ParameterSpec {
  name: string;
  value: number | string | boolean;
  mutable: boolean;
  bounds?: [number, number];
}

export interface BehavioralStep {
  order: number;
  offset_seconds: number;
  description: string;
}

export interface AttackBlueprint {
  attack_id: string;
  attack_family: AttackFamily;
  description: string;
  objective: string;
  target_features: string[];
  sequence: BehavioralStep[];
  parameters: Record<string, ParameterSpec>;
  parent_blueprint_id: string | null;
  generation: number;
}

export interface Transaction {
  transaction_id: string;
  timestamp: string; // ISO-8601 UTC
  source_account_id: string;
  destination_account_id: string;
  amount: number;
  currency: string;
  transaction_type: TransactionType;
  channel: Channel;
  merchant_category?: string;
  country?: string;
  label: FraudLabel;
  attack_family: AttackFamily | null;
  is_synthetic: boolean;
  scenario_id: string;
  blueprint_id: string | null;
  generation: number;
  split: DataSplit;
}

export interface TransactionBatch {
  batch_id: string;
  seed: number;
  generator_name: string;
  generator_version: string;
  generation: number;
  transactions: Transaction[];
}

export interface SignalContribution {
  name: string;
  contribution: number; // signed
  value: number;
  direction: "increases_risk" | "decreases_risk";
  rank: number;
}

export interface DetectorOutput {
  transaction_id: string;
  risk_score: number; // [0, 1]
  predicted_label: FraudLabel;
  recommended_action: RecommendedAction;
  important_signals: SignalContribution[];
  model_version: string;
  threshold: number;
  policy_version: string;
  latency_ms: number;
}

export interface ConfusionCounts {
  true_positive: number;
  false_positive: number;
  true_negative: number;
  false_negative: number;
}

export interface ClassificationMetrics {
  precision: number;
  recall: number;
  f1: number;
  pr_auc: number;
  roc_auc: number;
  fpr: number;
  recall_at_fixed_fpr: Record<string, number>;
  alert_rate: number;
  threshold: number;
  confusion: ConfusionCounts;
}

export interface EvaluationResult {
  evaluation_id: string;
  protocol: EvaluationProtocol;
  overall: ClassificationMetrics;
  per_attack_family: Record<AttackFamily, ClassificationMetrics>;
  latency: { mean: number; p50: number; p95: number; p99: number; max: number };
  round_index: number | null;
  held_out_family: AttackFamily | null;
  model_version: string;
}

export interface ParameterMutation {
  parameter: string;
  direction: MutationDirection;
  current_value: number | string | boolean;
  proposed_value: number | string | boolean | null;
  magnitude: number;
  rationale: string;
  confidence: number;
  priority: number;
}

export interface EvasionFeedback {
  feedback_id: string;
  attack_family: AttackFamily;
  detector_score: number;
  detector_model_version: string;
  evaded: boolean;
  realism_score: number;
  is_credible_evasion: boolean;
  important_signals: string[];
  suggested_mutations: ParameterMutation[];
  round_index: number;
  generation: number;
  transaction_ids: string[];
}

export const ATTACK_FAMILIES: { id: AttackFamily; label: string; blurb: string }[] = [
  {
    id: "synthetic_identity_bustout",
    label: "Synthetic Identity Bust-Out",
    blurb: "Fabricated or blended identities nurtured into good standing, then drained.",
  },
  {
    id: "mule_network_structuring",
    label: "Mule Network Structuring",
    blurb: "Layered transfers across mule accounts, structured under reporting thresholds.",
  },
  {
    id: "adaptive_detector_evasion",
    label: "Adaptive Detector Evasion",
    blurb: "Attacks mutated in response to detector feedback to stay under the threshold.",
  },
];

export const ATTACK_FAMILY_LABEL: Record<AttackFamily, string> = Object.fromEntries(
  ATTACK_FAMILIES.map((f) => [f.id, f.label]),
) as Record<AttackFamily, string>;
