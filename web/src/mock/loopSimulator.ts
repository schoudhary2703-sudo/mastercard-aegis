import { BASE_BLUEPRINTS } from "./blueprints";
import { generateBatch } from "./generateBatch";
import { buildEvaluationResult } from "./metrics";
import { scoreTransactions } from "./mockDetector";
import { id, makeRng, range } from "./rng";
import type {
  AttackBlueprint,
  AttackFamily,
  DetectorOutput,
  EvaluationResult,
  EvasionFeedback,
  ParameterMutation,
  Transaction,
  TransactionBatch,
} from "../types/aegis";

export interface RoundRecord {
  roundIndex: number;
  generation: number;
  modelVersion: string;
  defenderStrength: number;
  attackFamily: AttackFamily;
  blueprint: AttackBlueprint;
  batch: TransactionBatch;
  outputs: DetectorOutput[];
  evaluation: EvaluationResult;
  feedback: EvasionFeedback;
}

const MUTABLE_DIRECTIONS = ["increase", "decrease", "jitter"] as const;

function mutateBlueprint(previous: AttackBlueprint, feedback: EvasionFeedback | null): AttackBlueprint {
  const nextGeneration = previous.generation + 1;
  const parameters = { ...previous.parameters };

  if (feedback) {
    for (const mutation of feedback.suggested_mutations) {
      const current = parameters[mutation.parameter];
      if (!current || !current.mutable) continue;
      parameters[mutation.parameter] = { ...current, value: mutation.proposed_value ?? current.value };
    }
  }

  return {
    ...previous,
    attack_id: `${previous.attack_id.split("_g")[0]}_g${nextGeneration}`,
    parameters,
    parent_blueprint_id: previous.attack_id,
    generation: nextGeneration,
  };
}

function buildFeedback(
  transactions: Transaction[],
  outputs: DetectorOutput[],
  blueprint: AttackBlueprint,
  roundIndex: number,
  seed: number,
): EvasionFeedback {
  const rng = makeRng(seed);
  const outMap = new Map(outputs.map((o) => [o.transaction_id, o]));
  const fraud = transactions.filter((t) => t.label === 1);
  const evadedTxns = fraud.filter((t) => outMap.get(t.transaction_id)?.recommended_action === "approve");
  const evaded = evadedTxns.length > 0;
  const avgScore =
    fraud.length > 0
      ? fraud.reduce((sum, t) => sum + (outMap.get(t.transaction_id)?.risk_score ?? 0), 0) / fraud.length
      : 0;

  const mutableParams = Object.values(blueprint.parameters).filter((p) => p.mutable);
  const suggested_mutations: ParameterMutation[] = mutableParams.slice(0, 3).map((p, i) => {
    const direction = MUTABLE_DIRECTIONS[Math.floor(range(rng, 0, MUTABLE_DIRECTIONS.length))];
    const numeric = typeof p.value === "number";
    const proposed =
      numeric && direction === "increase"
        ? Math.round((p.value as number) * 1.15 * 1000) / 1000
        : numeric && direction === "decrease"
          ? Math.round((p.value as number) * 0.85 * 1000) / 1000
          : p.value;
    return {
      parameter: p.name,
      direction,
      current_value: p.value,
      proposed_value: proposed,
      magnitude: Math.round(range(rng, 0.1, 0.3) * 100) / 100,
      rationale: evaded
        ? `Detector under-weighted ${p.name}; widen it while evasion holds.`
        : `Detector keyed on ${p.name}; adjust to reduce signal strength.`,
      confidence: Math.round(range(rng, 0.55, 0.9) * 100) / 100,
      priority: i + 1,
    };
  });

  return {
    feedback_id: id(rng, "feedback"),
    attack_family: blueprint.attack_family,
    detector_score: Math.round(avgScore * 1000) / 1000,
    detector_model_version: outputs[0]?.model_version ?? "unknown",
    evaded,
    realism_score: Math.round(range(rng, 0.72, 0.96) * 100) / 100,
    is_credible_evasion: evaded,
    important_signals: [...new Set(outputs.flatMap((o) => o.important_signals.map((s) => s.name)))].slice(0, 4),
    suggested_mutations,
    round_index: roundIndex,
    generation: blueprint.generation,
    transaction_ids: evadedTxns.map((t) => t.transaction_id),
  };
}

/**
 * Advances the closed loop by exactly one round: mutate blueprint from the
 * previous round's feedback, generate a batch, score it, evaluate, and
 * derive the next feedback. Pure function of the previous round -- no
 * hidden state -- so the Co-Evolution screen can replay or reset freely.
 */
export function runRound(family: AttackFamily, previous: RoundRecord | null): RoundRecord {
  const roundIndex = previous ? previous.roundIndex + 1 : 0;
  const blueprint = previous ? mutateBlueprint(previous.blueprint, previous.feedback) : BASE_BLUEPRINTS[family];
  const seed = 20260101 + roundIndex * 97 + family.length;

  const batch = generateBatch(blueprint, { seed, count: 28, generation: blueprint.generation });
  const defenderStrength = Math.min(0.92, 0.18 + roundIndex * 0.13);
  const modelVersion = `detector-v${roundIndex + 1}`;

  const outputs = scoreTransactions(batch.transactions, {
    modelVersion,
    defenderStrength,
    seed: seed + 1,
  });

  const evaluation = buildEvaluationResult({
    evaluationId: `eval_${family}_r${roundIndex}`,
    transactions: batch.transactions,
    outputs,
    roundIndex,
    modelVersion,
  });

  const feedback = buildFeedback(batch.transactions, outputs, blueprint, roundIndex, seed + 2);

  return { roundIndex, generation: blueprint.generation, modelVersion, defenderStrength, attackFamily: family, blueprint, batch, outputs, evaluation, feedback };
}
