import { BASE_BLUEPRINTS } from "./blueprints";
import { id, makeRng, pick, range } from "./rng";
import type { AttackBlueprint, AttackFamily, Transaction, TransactionBatch } from "../types/aegis";

const CHANNELS_BY_FAMILY: Record<AttackFamily, Transaction["channel"][]> = {
  synthetic_identity_bustout: ["card_not_present", "online"],
  mule_network_structuring: ["p2p", "online"],
  adaptive_detector_evasion: ["online", "card_not_present", "p2p"],
};

const TXN_TYPE_BY_FAMILY: Record<AttackFamily, Transaction["transaction_type"][]> = {
  synthetic_identity_bustout: ["cash_out", "payment"],
  mule_network_structuring: ["transfer", "cash_out"],
  adaptive_detector_evasion: ["payment", "transfer"],
};

/**
 * Turns a blueprint + seed into a deterministic mock TransactionBatch.
 * This is a UI fixture generator, not a fraud simulator: it produces shapes
 * that exercise the demo, not statistically-grounded fraud behaviour.
 */
export function generateBatch(
  blueprint: AttackBlueprint,
  opts: { seed: number; count?: number; generation?: number; legitimateRatio?: number },
): TransactionBatch {
  const { seed, count = 24, generation = blueprint.generation, legitimateRatio = 0.35 } = opts;
  const rng = makeRng(seed);
  const scenarioId = id(rng, "scenario");
  const now = Date.UTC(2026, 7, 24, 9, 0, 0);

  const transactions: Transaction[] = Array.from({ length: count }, (_, i) => {
    const isFraud = rng() > legitimateRatio;
    const amount = isFraud
      ? range(rng, 400, 9800) * (blueprint.parameters.bustout_amount_ratio?.value as number | undefined ?? 1)
      : range(rng, 8, 650);
    return {
      transaction_id: id(rng, "txn"),
      timestamp: new Date(now + i * range(rng, 20_000, 900_000)).toISOString(),
      source_account_id: id(rng, "acct"),
      destination_account_id: id(rng, "acct"),
      amount: Math.round(amount * 100) / 100,
      currency: "USD",
      transaction_type: pick(rng, TXN_TYPE_BY_FAMILY[blueprint.attack_family]),
      channel: pick(rng, CHANNELS_BY_FAMILY[blueprint.attack_family]),
      merchant_category: isFraud ? undefined : pick(rng, ["grocery", "retail", "utilities", "travel"]),
      country: pick(rng, ["US", "US", "US", "GB", "CA"]),
      label: isFraud ? 1 : 0,
      attack_family: isFraud ? blueprint.attack_family : null,
      is_synthetic: true,
      scenario_id: scenarioId,
      blueprint_id: isFraud ? blueprint.attack_id : null,
      generation,
      split: "closed_loop",
    };
  });

  return {
    batch_id: id(rng, "batch"),
    seed,
    generator_name: "mock-fixture-generator",
    generator_version: "0.1.0-mock",
    generation,
    transactions,
  };
}

export function generateBatchForFamily(
  family: AttackFamily,
  opts: { seed: number; count?: number; generation?: number },
): TransactionBatch {
  return generateBatch(BASE_BLUEPRINTS[family], opts);
}
