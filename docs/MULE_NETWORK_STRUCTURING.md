# Mule-network / structuring simulator

This is AEGIS attack family 2. It generates a benchmark-only account graph in
the canonical `Transaction` schema. The simulator does not encode real account
details, jurisdiction-specific thresholds, or operational laundering advice.
Its purpose is to measure whether a detector can recognize coordinated graph
behavior when individual synthetic transactions remain bounded.

## Blueprint and stages

`build_mule_network_blueprint()` produces the canonical
`mule_network_structuring` blueprint. Its sequence is:

1. `network-context`: legitimate payments establish strictly earlier temporal
   history for the synthetic coordinator and mule accounts;
2. `source-allocation`: one synthetic coordinator fans funds out to distinct
   entry mules;
3. `layering`: transfers traverse every declared synthetic graph layer; and
4. `fan-in-cashout`: bounded exit-stage mule sources consolidate into distinct
   synthetic destinations, with a bounded cash-out probability.

Context rows are explicitly `LEGITIMATE` and therefore have no top-level
`attack_family`. Fraud rows are always `FRAUD` and carry
`MULE_NETWORK_STRUCTURING`, blueprint, scenario, sequence, split, and generation
provenance. Graph roles, stage, layer index, reference basis, and safety scope
live in `Transaction.metadata`; no shared-contract extension is needed.

| Parameter | Default | Bounds | Meaning |
| --- | ---: | ---: | --- |
| `mule_account_count` | 6 | 3–12 | Synthetic intermediary accounts. |
| `fan_out` | 3 | 2–6 | Distinct entry mules. |
| `fan_in` | 2 | 1–4 | Distinct mule sources in the exit stage. |
| `transfer_count` | 12 | 6–32 | Total fraudulent graph movements. |
| `transfer_amount_mean` | 500 | 100–2,000 | Bounded synthetic transfer target. |
| `transfer_amount_stddev` | 150 | 5–800 | Transfer amount dispersion. |
| `per_transfer_cap` | 9,500 | 500–10,000 | Benchmark cap, not a real reporting threshold. |
| `inter_transfer_delay_minutes` | 45 | 5–360 | Target spacing between fraud events. |
| `layering_depth` | 2 | 1–4 | Required mule-to-mule graph layers. |
| `destination_diversity` | 4 | 2–10 | Distinct synthetic exit destinations. |
| `temporal_spread_hours` | 24 | 2–168 | Maximum fraud-stage span. |
| `source_allocation_concentration` | 0.45 | 0.20–0.70 | Share directed to the first entry mule. |
| `cash_out_probability` | 0.25 | 0–0.75 | Exit-stage PaySim `cash_out` probability. |
| `context_transaction_count_per_account` | 2 | 1–5 | Legitimate history events per graph account. |
| `context_duration_days` | 7 | 2–30 | Context-history window. |
| `context_amount_mean` | 75 | 10–500 | Bounded context amount target. |
| `context_amount_stddev` | 25 | 1–200 | Context amount dispersion. |
| `randomness_seed_offset` | 0 | 0–1,000,000 | Immutable supplement to the recorded run seed. |

All parameters except `randomness_seed_offset` are bounded and mutable for a
future adaptive round. Cross-parameter validation also requires fan-out and
fan-in not to exceed the mule count, enough fraud events to cover every stage,
the mean not to exceed the cap, and the complete graph to fit the declared
sequence and generation horizon.

## Determinism and graph behavior

The generator seeds NumPy from the recorded run seed, immutable seed offset,
and scenario index. Scenario, transaction, account, and batch identifiers are
derived deterministically from the blueprint and seed. A different seed gives
a disjoint scenario namespace.

Context events are ordered over the configured context window. Fraud events
start later and are strictly ordered. Inter-event delays receive bounded seeded
jitter and are rescaled only when necessary to fit the declared temporal
spread. Allocation amounts implement the declared synthetic concentration;
layer and exit amounts use bounded normal sampling. Synthetic balances evolve
causally in timestamp order.

## TRAIN-only bounded-memory reference

`MuleNetworkReferenceProfile.from_processed_paysim()` opens only
`train.jsonl`. It streams one transaction at a time and retains constant-size
Welford accumulators and counters for:

- legitimate amount mean and sample standard deviation;
- legitimate transfer amount mean and sample standard deviation;
- legitimate transaction-type probabilities;
- dominant currency; and
- latest TRAIN timestamp.

Fraud rows are excluded from reference moments. Every input row must still be
stamped `train`; a validation/test row fails the profile. Validation and test
files are never opened. The confrontation freshness audit performs a second
bounded-memory JSONL scan that retains only the small generated ID sets and any
overlap found, rather than loading millions of TRAIN transactions.

## Fidelity

Each batch records `MuleNetworkFidelitySummary` under
`batch.metadata["fidelity"]`. It reports:

- amount-distribution similarity to legitimate TRAIN transfers;
- transfer/cash-out type similarity;
- temporal-spacing reasonableness;
- observed versus declared fan-out and fan-in;
- mule-account reuse;
- exit-destination diversity;
- allocation-concentration and per-transfer-cap consistency;
- realism-constraint violation rate; and
- the unweighted average diagnostic `overall_fidelity_score`.

The graph dimensions measure simulator consistency, not prevalence in real
financial crime. Amount and operation-type checks are lightweight marginals,
not a joint-distribution or statistical-realism claim.

## Frozen-detector confrontation

Run from the repository root:

```bash
python scripts/run_mule_network_confrontation.py \
  data/processed/paysim/<run-id> \
  models/xgboost-hardened-r1-20260201 \
  --seed <fresh-seed>
```

The command has no training path. It loads the model, fits the schema-known
temporal extractor with no rows, scores a TEST-stamped scenario, builds a
`STATIC_HOLDOUT` `EvaluationResult`, checks the model and metadata hashes before
and after, and writes confrontation artifacts under
`data/synthetic/mule_confrontations/`.

## Adaptive compatibility and limits

All mutable controls are bounded numeric `ParameterSpec` values. Blueprints and
transactions preserve parent/generation lineage, and the confrontation exports
credible `EvasionRecord` rows compatible with the existing hardness and fitness
definitions:

```text
hardness = (1 - event_risk) * overall_fidelity_score
fitness = (1 - average_fraud_risk) * overall_fidelity_score
```

The current bust-out adaptive orchestrator remains family-specific, so this
phase does not run a mule adaptive round. A later generic orchestrator can use
these parameters, provenance, evasions, and fitness without changing shared
contracts.
