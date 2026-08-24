import type {
  AttackFamily,
  ClassificationMetrics,
  ConfusionCounts,
  DetectorOutput,
  EvaluationResult,
  Transaction,
} from "../types/aegis";
import { ATTACK_FAMILIES } from "../types/aegis";

/** Confusion + derived metrics for one (transactions, detector outputs) pair. Mock only. */
function classify(transactions: Transaction[], outputs: Map<string, DetectorOutput>): ClassificationMetrics {
  const confusion: ConfusionCounts = { true_positive: 0, false_positive: 0, true_negative: 0, false_negative: 0 };
  let alerts = 0;

  for (const txn of transactions) {
    const out = outputs.get(txn.transaction_id);
    if (!out) continue;
    const predicted = out.predicted_label === 1;
    const actual = txn.label === 1;
    if (out.recommended_action !== "approve") alerts += 1;
    if (predicted && actual) confusion.true_positive += 1;
    else if (predicted && !actual) confusion.false_positive += 1;
    else if (!predicted && actual) confusion.false_negative += 1;
    else confusion.true_negative += 1;
  }

  const { true_positive: tp, false_positive: fp, true_negative: tn, false_negative: fn } = confusion;
  const precision = tp + fp > 0 ? tp / (tp + fp) : 0;
  const recall = tp + fn > 0 ? tp / (tp + fn) : 0;
  const f1 = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;
  const fpr = fp + tn > 0 ? fp / (fp + tn) : 0;

  return {
    precision,
    recall,
    f1,
    pr_auc: Math.min(1, precision * 0.9 + recall * 0.1),
    roc_auc: Math.min(1, 0.5 + recall * 0.4 - fpr * 0.3),
    fpr,
    recall_at_fixed_fpr: { "0.01": Math.max(0, recall - 0.05), "0.05": recall },
    alert_rate: transactions.length > 0 ? alerts / transactions.length : 0,
    threshold: 0.5,
    confusion,
  };
}

export function buildEvaluationResult(args: {
  evaluationId: string;
  transactions: Transaction[];
  outputs: DetectorOutput[];
  roundIndex: number;
  modelVersion: string;
}): EvaluationResult {
  const outMap = new Map(args.outputs.map((o) => [o.transaction_id, o]));
  const overall = classify(args.transactions, outMap);

  const per_attack_family = Object.fromEntries(
    ATTACK_FAMILIES.map(({ id: family }) => {
      const subset = args.transactions.filter((t) => t.attack_family === family || t.label === 0);
      return [family, classify(subset, outMap)];
    }),
  ) as Record<AttackFamily, ClassificationMetrics>;

  const latencies = args.outputs.map((o) => o.latency_ms).sort((a, b) => a - b);
  const at = (p: number) => latencies[Math.min(latencies.length - 1, Math.floor(p * latencies.length))] ?? 0;

  return {
    evaluation_id: args.evaluationId,
    protocol: "CLOSED_LOOP_ROUND",
    overall,
    per_attack_family,
    latency: {
      mean: latencies.reduce((a, b) => a + b, 0) / (latencies.length || 1),
      p50: at(0.5),
      p95: at(0.95),
      p99: at(0.99),
      max: latencies[latencies.length - 1] ?? 0,
    },
    round_index: args.roundIndex,
    held_out_family: null,
    model_version: args.modelVersion,
  };
}
