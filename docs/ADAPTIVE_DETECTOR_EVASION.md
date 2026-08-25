# Adaptive detector-evasion benchmark

Attack family 3 is a synthetic-only, single-step feedback benchmark. It is not
an unrestricted optimizer and does not target a real payment system.

## Flow

```text
TRAIN-only streaming reference
  -> deterministic parent blueprint and probe (seed N)
  -> frozen detector output with detector-visible attributions
  -> credible false negatives as EvasionFeedback only
  -> one bounded child mutation (seed N+1, at most two parameters)
  -> fresh child scenario (seed N+2)
  -> STATIC_HOLDOUT evaluation against the same frozen detector
```

The probe is feedback evidence, not the reported evaluation sample. The final
child uses a new scenario ID and transaction IDs. No detector fit, threshold
change, model write, or Blue retraining path exists in the runner.

## Scenario and parameters

The scenario is deliberately distinct from identity bust-out and mule graphs:
one synthetic source builds ordinary context, pauses, and emits a small bounded
set of fraud-labelled transfers/cash-outs. It has no identity lifecycle, trust
build followed by a drain, or multi-mule layering graph.

| Parameter | Default | Bounds | Mutable |
| --- | ---: | ---: | --- |
| `context_transaction_count` | 10 | 4–30 | yes |
| `context_duration_days` | 14 | 3–45 | yes |
| `context_amount_mean` | 75 | 10–500 | yes |
| `context_amount_stddev` | 25 | 1–200 | yes |
| `fraud_transaction_count` | 4 | 2–8 | yes |
| `fraud_amount_mean` | 1,000 | 100–3,000 | yes |
| `fraud_amount_stddev` | 250 | 20–1,000 | yes |
| `per_transaction_cap` | 5,000 | 500–10,000 | yes |
| `history_blend_ratio` | 0.60 | 0.20–0.90 | yes |
| `inter_event_delay_hours` | 6 | 0.5–48 | yes |
| `destination_diversity` | 4 | 1–8 | yes |
| `transfer_probability` | 0.75 | 0.25–1.0 | yes |
| `amount_jitter_ratio` | 0.08 | 0.01–0.25 | yes |
| `timestamp_jitter_minutes` | 15 | 0–120 | yes |
| `max_parameter_changes` | 2 | 1–3 | no |
| `randomness_seed_offset` | 0 | 0–1,000,000 | no |

The immutable mutation budget guarantees that one feedback step changes at
most two parameters. Each move is a fixed 12% of the declared range and is
clamped to the inclusive bounds. The child records parent ID, generation,
mutation seed, feedback IDs, and changed values.

## Attribution guidance

Only `SignalContribution` values already present in `DetectorOutput` are
mapped to simulator controls. Examples include amount to fraud amount mean,
amount deviation to history blending, velocity to pacing, and destination
velocity to destination diversity. The mapping is a testable simulator
hypothesis, not access to model internals or a causal claim. When no mapped
signal exists, one deterministic bounded fallback move is used.

## Reference and fidelity

`AdaptiveEvasionReferenceProfile` streams only legitimate TRAIN rows with
constant-memory Welford accumulators and type/currency counters. Validation and
test artifacts are never opened. A separate bounded-memory scan verifies both
probe and child IDs against TRAIN.

Fidelity reports context and fraud amount similarity, operation-type
similarity, temporal pacing, history-blend consistency, destination diversity,
perturbation-budget compliance, and constraint violations. The aggregate is a
descriptive mean, not evidence of real-world evasion capability. Survivors are
credible only at fidelity `>= 0.5`.

## Command

```bash
python scripts/run_adaptive_evasion_confrontation.py \
  data/processed/paysim/<run-id> \
  models/xgboost-hardened-r1-20260201 \
  --seed <fresh-probe-seed>
```

The reported fitness is:

```text
(1 - average_fraud_risk) * overall_fidelity_score
```
