import type { AttackBlueprint, AttackFamily } from "../types/aegis";

/** One canonical blueprint per in-scope family, generation 0. */
export const BASE_BLUEPRINTS: Record<AttackFamily, AttackBlueprint> = {
  synthetic_identity_bustout: {
    attack_id: "bp_synid_0001",
    attack_family: "synthetic_identity_bustout",
    description: "Blended identity nurtured over a dormancy period, then drained near the limit.",
    objective: "Maximize drained value before the account is flagged.",
    target_features: ["temporal.account_age_days", "graph.identity_similarity", "temporal.velocity_1h"],
    sequence: [
      { order: 0, offset_seconds: 0, description: "Open account, small legitimate-looking purchases." },
      { order: 1, offset_seconds: 3600 * 24 * 30, description: "Build credit standing over ~30 days." },
      { order: 2, offset_seconds: 3600 * 24 * 60, description: "Request limit increase." },
      { order: 3, offset_seconds: 3600 * 24 * 61, description: "Rapid drain via cash-out transactions." },
    ],
    parameters: {
      dormancy_days: { name: "dormancy_days", value: 30, mutable: true, bounds: [7, 90] },
      bustout_amount_ratio: { name: "bustout_amount_ratio", value: 0.92, mutable: true, bounds: [0.5, 1.0] },
      identity_blend_ratio: { name: "identity_blend_ratio", value: 0.4, mutable: true, bounds: [0.1, 0.9] },
      channel: { name: "channel", value: "card_not_present", mutable: false },
    },
    parent_blueprint_id: null,
    generation: 0,
  },
  mule_network_structuring: {
    attack_id: "bp_mule_0001",
    attack_family: "mule_network_structuring",
    description: "Funds layered across a mule account chain, each hop under the reporting threshold.",
    objective: "Move value through the network while no single hop trips a threshold rule.",
    target_features: ["graph.fan_out", "graph.fan_in", "temporal.velocity_1h", "amount"],
    sequence: [
      { order: 0, offset_seconds: 0, description: "Origin transfers to first-layer mule accounts." },
      { order: 1, offset_seconds: 900, description: "First-layer accounts forward to second layer." },
      { order: 2, offset_seconds: 1800, description: "Second-layer accounts consolidate to cash-out account." },
    ],
    parameters: {
      hop_count: { name: "hop_count", value: 3, mutable: true, bounds: [2, 6] },
      structuring_threshold_ratio: {
        name: "structuring_threshold_ratio",
        value: 0.88,
        mutable: true,
        bounds: [0.5, 0.99],
      },
      fan_out: { name: "fan_out", value: 4, mutable: true, bounds: [2, 12] },
      channel: { name: "channel", value: "p2p", mutable: false },
    },
    parent_blueprint_id: null,
    generation: 0,
  },
  adaptive_detector_evasion: {
    attack_id: "bp_evade_0001",
    attack_family: "adaptive_detector_evasion",
    description: "Attack parameters mutated round over round in response to detector feedback.",
    objective: "Stay below the detector's action threshold while preserving attack value.",
    target_features: ["temporal.velocity_1h", "graph.fan_out", "amount"],
    sequence: [
      { order: 0, offset_seconds: 0, description: "Probe with moderate-risk transaction." },
      { order: 1, offset_seconds: 600, description: "Adjust amount/timing based on observed score." },
      { order: 2, offset_seconds: 1200, description: "Execute at the calibrated evasion point." },
    ],
    parameters: {
      amount_jitter: { name: "amount_jitter", value: 0.12, mutable: true, bounds: [0.02, 0.4] },
      timing_spread_seconds: { name: "timing_spread_seconds", value: 600, mutable: true, bounds: [60, 3600] },
      velocity_cap: { name: "velocity_cap", value: 3, mutable: true, bounds: [1, 10] },
      channel: { name: "channel", value: "online", mutable: false },
    },
    parent_blueprint_id: null,
    generation: 0,
  },
};
