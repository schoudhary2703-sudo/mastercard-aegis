# Synthetic identity / bust-out simulator

This is AEGIS's first implemented Red Team attack family. It generates a
behavioral sequence in the canonical `Transaction` contract: a low-history
persona establishes moderate legitimate-looking activity, pauses, and then
executes a short bounded bust-out. It does not call a detector, mutate from
feedback, use a live LLM, or implement either remaining attack family.

## Blueprint

`build_synthetic_identity_blueprint()` returns the canonical
`AttackBlueprint`. Its ordered steps are:

1. `identity-onboarding`: establish a low-history persona;
2. `warmup-history`: build explicitly legitimate payment history;
3. `trust-transition`: leave a configurable pause;
4. `bust-out`: concentrate elevated transfers and cash-outs into a short
   window.

| Parameter | Default | Bounds | Meaning |
| --- | ---: | ---: | --- |
| `warmup_transaction_count` | 12 | 4–40 | Legitimate history events. |
| `warmup_amount_mean` | 75 | 10–500 | Target bounded warm-up mean. |
| `warmup_amount_stddev` | 25 | 1–200 | Warm-up amount dispersion. |
| `warmup_duration_days` | 21 | 7–90 | Time used to build history. |
| `account_age_days` | 14 | 1–60 | Account-age/history proxy at observation start. |
| `bustout_amount_multiplier` | 8 | 3–20 | Bust-out target relative to warm-up mean. |
| `bustout_transaction_count` | 3 | 1–8 | Fraudulent transactions in the burst. |
| `bustout_window_hours` | 6 | 1–24 | Duration of the burst. |
| `destination_diversity` | 3 | 1–8 | Size of the payee/cash-out pool. |
| `transition_delay_hours` | 24 | 1–168 | Pause between warm-up and fraud. |
| `warmup_transfer_probability` | 0.25 | 0.05–0.75 | Transfer share in warm-up type sampling. |
| `randomness_seed_offset` | 0 | 0–1,000,000 | Structural supplement to the run seed. |

The realism constraints cap amounts at 10,000 units, use the mobile channel,
limit the scenario to 5–48 transaction events, and allow no more than 25
involved accounts. Generator overrides are checked against the declared
`ParameterSpec` bounds; undeclared, mistyped, and out-of-range values fail.

The constant `SYNTHETIC_IDENTITY_BLUEPRINT_PROMPT` describes the exact future
LLM task. `SyntheticIdentityBlueprintIdentifier` proves the existing
identification interface can produce the blueprint without an LLM. No API key,
network service, agent framework, or unvalidated LLM output is required.

## Generation

`SyntheticIdentityBustOutGenerator` is a `BaseGenerator` implementation that
supports only `synthetic_identity_bustout`.

For each scenario it:

1. resolves and validates blueprint defaults plus run overrides;
2. seeds NumPy from the recorded generation seed, immutable seed offset, and
   scenario index;
3. schedules jittered, strictly chronological warm-up events over the warm-up
   duration;
4. samples bounded warm-up amounts and PaySim-shaped operation types;
5. waits for the transition delay;
6. schedules bounded transfers/cash-outs inside the bust-out window;
7. maintains deterministic source and destination balance trajectories; and
8. returns a deterministic `TransactionBatch`, including deterministic batch,
   transaction, scenario, and account identifiers.

Warm-up rows have `label=LEGITIMATE`; bust-out rows have `label=FRAUD`. Every
row is synthetic and carries scenario, blueprint, step, sequence, split, and
generation provenance. The frozen contract prohibits `attack_family` on a
legitimate row, so warm-up rows use `attack_family=None` and retain the family
under `metadata["synthetic.attack_family"]`. Fraud rows carry the top-level
`SYNTHETIC_IDENTITY_BUSTOUT` family.

A `max_transactions` value that would truncate the behavioral sequence is
rejected. A scenario whose declared duration exceeds `GenerationConfig`'s
horizon is also rejected.

## PaySim reference strategy

With `--reference-dir`, the CLI streams only
`<prepared-run>/train.jsonl`. It uses explicitly legitimate train rows to
derive:

- amount mean and sample standard deviation;
- transaction-type probabilities; and
- dominant currency.

Validation and test artifacts are never read. The derived amount moments are
clipped into the blueprint's declared bounds before generation. This is a
lightweight reference, not a claim that the simulator reproduces PaySim's full
joint distribution.

Without a local prepared run, the simulator uses documented bounded fallback
assumptions: mean 75, standard deviation 25, neutral currency `XXX`, and an
explicit PaySim-shaped type mix. The batch and fidelity report mark the basis
as `bounded_fallback` and state that statistical fidelity was not measured.

## Fidelity summary

Every generated batch stores a descriptive fidelity summary in
`batch.metadata["fidelity"]`. The CLI writes the same summary to
`scenario.json`. It reports:

- observed and reference warm-up amount moments and their normalized
  similarity;
- transaction-type total-variation similarity;
- temporal-spacing reasonableness;
- warm-up and fraud counts plus fraud proportion;
- transition sharpness (bust-out mean / warm-up mean);
- closeness to the configured bust-out multiplier;
- realism-constraint violation rate; and
- a simple aggregate diagnostic score.

These values describe simulator behavior. They are not detector metrics, an
`EvaluationResult`, or evidence of evasion.

## CLI

Generate one fallback-based scenario:

```bash
python scripts/generate_bustout.py --seed 42
```

Use a prepared PaySim run and explicit parameter overrides:

```bash
python scripts/generate_bustout.py \
  --seed 42 \
  --reference-dir data/processed/paysim/<run-id> \
  --set warmup_transaction_count=16 \
  --set bustout_amount_multiplier=6.5
```

The default output is:

```text
data/synthetic/round_0/synthetic-identity-bustout-seed-42-<batch-hash>/
  transactions.jsonl
  scenario.json
```

`transactions.jsonl` contains canonical `Transaction` JSON objects.
`scenario.json` contains the blueprint, batch provenance, parameter values,
reference profile, transaction checksum, and fidelity summary. Existing output
directories are never overwritten.

Use `--round-index`, `--data-root`, `--currency`, `--start-time`, and repeated
`--set NAME=VALUE` options as needed. `--time-horizon-days` can expand the
generation clock for longer warm-up overrides. The CLI always generates
exactly one scenario in this phase.

## Limitations

- Identity attributes are represented through persona/account provenance and
  an age proxy; no external identity dataset is invented.
- Amount and type matching uses lightweight marginal moments, not CTGAN, SDV,
  or a joint generative model.
- The model does not know detector thresholds or consume detector feedback.
- Generated scenarios are not automatically mixed into PaySim or assigned to
  an evaluation split; the evaluation harness owns those decisions.
- Only synthetic identity / bust-out is implemented.
