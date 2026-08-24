import { makeRng, range } from "./rng";
import type { DetectorOutput, RecommendedAction, SignalContribution, Transaction } from "../types/aegis";

const SIGNAL_POOL: Record<string, string[]> = {
  synthetic_identity_bustout: ["temporal.account_age_days", "graph.identity_similarity", "temporal.velocity_1h"],
  mule_network_structuring: ["graph.fan_out", "graph.fan_in", "temporal.velocity_1h"],
  adaptive_detector_evasion: ["temporal.velocity_1h", "graph.fan_out", "amount"],
};

const THRESHOLD = 0.5;

function actionFor(score: number): RecommendedAction {
  if (score < 0.35) return "approve";
  if (score < THRESHOLD) return "step_up";
  if (score < 0.75) return "review";
  return "decline";
}

/**
 * Mock scoring heuristic standing in for `defend/BaseDetector.predict()`.
 * `defenderStrength` in [0,1] simulates round-over-round hardening: it is a
 * demo dial, not a trained model.
 */
export function scoreTransactions(
  transactions: Transaction[],
  opts: { modelVersion: string; defenderStrength: number; seed: number },
): DetectorOutput[] {
  const rng = makeRng(opts.seed);
  const strength = Math.min(1, Math.max(0, opts.defenderStrength));

  return transactions.map((txn) => {
    const isFraud = txn.label === 1;
    const noise = range(rng, -0.08, 0.08);
    const amountSignal = Math.min(txn.amount / 9000, 1) * 0.15;

    let score: number;
    if (isFraud) {
      score = 0.28 + strength * 0.6 + amountSignal + noise;
    } else {
      score = 0.08 + (1 - strength) * 0.12 + noise * 0.5;
    }
    score = Math.min(0.99, Math.max(0.01, score));

    const family = txn.attack_family ?? "adaptive_detector_evasion";
    const pool = SIGNAL_POOL[family];
    const important_signals: SignalContribution[] = pool.map((name, i) => ({
      name,
      contribution: Math.round((score * range(rng, 0.15, 0.4)) * 1000) / 1000,
      value: Math.round(range(rng, 1, 12) * 10) / 10,
      direction: "increases_risk",
      rank: i + 1,
    }));

    return {
      transaction_id: txn.transaction_id,
      risk_score: Math.round(score * 1000) / 1000,
      predicted_label: score >= THRESHOLD ? 1 : 0,
      recommended_action: actionFor(score),
      important_signals,
      model_version: opts.modelVersion,
      threshold: THRESHOLD,
      policy_version: "policy-v0",
      latency_ms: Math.round(range(rng, 8, 40) * 10) / 10,
    };
  });
}
