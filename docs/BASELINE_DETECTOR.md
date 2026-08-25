# Baseline detector (Blue Team, Phase 1)

The first real detector: an XGBoost classifier over point-in-time-safe
transaction and account-history features, trained on processed PaySim
artifacts. This document covers what it is, how to run it, and its honest
limitations. It does not describe the adaptive loop, UI integration, or fraud
generation - those are out of scope for this phase.

## Model

`aegis.defend.XGBoostDetector` (`src/aegis/defend/xgboost_detector.py`) wraps
XGBoost's low-level `Booster` API directly - not the sklearn-compatible
wrapper - so the only new runtime dependency is `xgboost` itself.

* **Imbalance:** `scale_pos_weight` is computed automatically from the
  training split's fraud ratio (`n_negative / n_positive`) unless overridden.
* **Explanation:** `explain()` uses the booster's native
  `pred_contribs=True` output - exact Shapley-value contributions, not an
  approximation, and no extra library beyond `xgboost`.
* **Persistence:** `save(path)` writes `model.json` (XGBoost's native format)
  plus `metadata.json` (hyperparameters, seed, resolved `scale_pos_weight`,
  feature names, the action policy, contract version). `load(path)`
  reconstructs an identical detector; `tests/test_defend_xgboost.py` asserts
  score identity after a round trip.

## Features

`aegis.features.TemporalBaselineFeatureExtractor`
(`src/aegis/features/temporal.py`), namespace `temporal.*`, 21 columns as of
version `0.2.0` (used by Defender v3 onward; v1/v2 were trained on version
`0.1.0`'s 19 columns - see "Cross-family hardening (Defender v3)" below):

`amount`, `hour_of_day`, `source_balance_before`, `destination_balance_before`,
`has_destination`, `source_txn_count_before`, `destination_txn_count_before`,
`source_distinct_destinations_before`, `destination_distinct_sources_before`,
`source_velocity_1h`, `destination_velocity_1h`, `source_avg_amount_before`,
`amount_deviation_from_source_history`, `seconds_since_source_previous_txn`,
`seconds_since_destination_previous_txn`, and one-hot
`type_{payment,transfer,cash_in,cash_out,debit,refund}`.

**Removed (Phase 2 leakage fix):** `source_balance_delta` and
`destination_balance_delta`. Both were computed from `*_balance_after`,
which is the ledger's post-execution outcome, not information available to a
real-time authorization decision. They were not replaced by an equivalent -
removing them shrinks the feature set from 21 to 19 columns rather than
smuggling the same signal back in under a different name.

### Decision-time feature policy

Every emitted feature must be computable from **(a)** the current
transaction's own request-time fields, or **(b)** history strictly earlier
than it - nothing produced by executing the transaction, and nothing that is
fraud/provenance metadata. Concretely:

* **Allowed:** the request's own declared fields (amount, type, timestamp,
  pre-transaction balances - a payment request states the balance the
  account holds *before* it executes) and aggregates over strictly earlier
  transactions.
* **Forbidden:** `source_balance_after` / `destination_balance_after` (the
  outcome of executing this transaction) or any other field only known once
  the transaction has settled; `label`, `attack_family`, `blueprint_id`,
  `scenario_id`, `is_synthetic`, `generation`, and `metadata` (ground truth
  and simulation provenance, never predictors).

| Feature | Classification | Why it is available at scoring time |
| --- | --- | --- |
| `amount` | current-transaction-known | Declared on the authorization request itself. |
| `hour_of_day` | current-transaction-known | Derived from the request's own `timestamp`. |
| `source_balance_before` | current-transaction-known | The account's ledger balance *before* this request executes - known when the request arrives. |
| `destination_balance_before` | current-transaction-known | Same, for the destination account. |
| `has_destination` | current-transaction-known | Whether the request names a destination account at all. |
| `type_{payment,transfer,cash_in,cash_out,debit,refund}` | current-transaction-known | The request's own declared `transaction_type`; one-hot over a fixed, schema-known vocabulary. |
| `source_txn_count_before` | prior-history-derived | Count of the source account's transactions strictly earlier than this one. |
| `destination_txn_count_before` | prior-history-derived | Same, for the destination account. |
| `source_distinct_destinations_before` | prior-history-derived | Count of *distinct* destination accounts the source has paid strictly earlier than this one - not volume, counterparty fan-out. Added for Defender v3, see below. |
| `destination_distinct_sources_before` | prior-history-derived | Count of *distinct* source accounts that have paid the destination strictly earlier than this one - counterparty fan-in. Added for Defender v3, see below. |
| `source_velocity_1h` | prior-history-derived | Count of the source account's transactions in the 1h window strictly before this one. |
| `destination_velocity_1h` | prior-history-derived | Same, for the destination account. |
| `source_avg_amount_before` | prior-history-derived | Running mean of the source account's amounts, over strictly earlier transactions only. |
| `amount_deviation_from_source_history` | current-transaction-known + prior-history-derived | This request's own `amount` compared against `source_avg_amount_before` - both operands are available at scoring time. |
| `seconds_since_source_previous_txn` | current-transaction-known + prior-history-derived | This request's own `timestamp` minus the source account's last strictly-earlier transaction time. |
| `seconds_since_destination_previous_txn` | current-transaction-known + prior-history-derived | Same, for the destination account. |

Removed as post-transaction (not in the table because they no longer exist):
`source_balance_delta` (`source_balance_after - source_balance_before`),
`destination_balance_delta` (`destination_balance_after -
destination_balance_before`).

### Leakage safeguards

* The extractor never reads `label`, `attack_family`, `blueprint_id`,
  `scenario_id`, `is_synthetic`, `generation`, `metadata` (where PaySim's
  `isFlaggedFraud` lives as provenance), or `source_balance_after` /
  `destination_balance_after` (post-transaction outcomes). Enforced by
  `test_output_is_identical_regardless_of_label_or_metadata` and
  `test_post_transaction_balance_fields_never_affect_features`
  (`tests/test_features_temporal.py`) - the latter mutates only the `*_after`
  fields of a fixture sequence and asserts the extracted feature frame is
  byte-identical. `test_post_transaction_balance_deltas_are_not_emitted` is a
  regression guard against the two removed columns silently returning.
* All per-account running aggregates (count, 1h velocity, average amount,
  time-since-previous) come from a single **causal, chronologically-ordered
  pass** over exactly the rows given to one `transform()` call. A row's
  history reflects only strictly earlier rows in that same call; state
  updates after a row is recorded, never before. Enforced by
  `test_features_use_only_strictly_earlier_events`.
* `type_*` one-hot columns use the fixed `TransactionType` enum vocabulary,
  not something learned from data - column order is stable regardless of
  which types appear in a given split.
* `FraudLabel.UNKNOWN` rows are dropped before training and evaluation
  (`_labelled_only` in `scripts/train_baseline_detector.py`) - unknown is not
  treated as legitimate.

### Known simplification: no cross-split history carryover

Running per-account state does **not** persist between separate `transform`
calls. Transforming `validation` starts every account's counters at zero,
even if that account also appears in `train` earlier in time. This is a
deliberate trade-off: it keeps the extractor a pure function of its input,
trivial to test and unambiguously leakage-safe, at the cost of a "cold
start" for recurring accounts at the beginning of each split. A future
version could seed validation/test history from strictly-earlier train data
(temporal split mode only - `entity_isolated` mode makes this moot, since no
entity crosses a split boundary there at all).

## Class imbalance and thresholding

* Training: automatic `scale_pos_weight`.
* Threshold: `tune_threshold_for_f1` (`src/aegis/defend/metrics.py`) scans
  every observed validation score and picks the one maximizing F1 -
  exact, not grid-approximated. **Validation only, never test.**
* The tuned threshold becomes `ActionPolicy.label_threshold` /`step_up_at`,
  with `review_at`/`decline_at` scaled proportionally above it.

## Metrics

`src/aegis/defend/metrics.py` is a dependency-free (`numpy`-only) metrics
module - not a `src/aegis/evaluate/` implementation. **That package is
jointly owned by both workstreams and out of scope for this task**; adding a
concrete `BaseEvaluator` there without both teams' sign-off would violate
AGENTS.md. This module still produces real `EvaluationResult` contract
instances, tagged with `EvaluationProtocol.STATIC_HOLDOUT`, so every number is
traceable and versioned - it simply isn't wired through the (currently
unimplemented) evaluator interface.

Computed: precision, recall, F1, PR-AUC (sklearn's step-function definition),
ROC-AUC (Mann-Whitney rank-sum identity, tie-aware), false positive rate,
recall at fixed FPR budgets `{0.001, 0.005, 0.01}`, confusion counts, alert
rate, and latency (mean/p50/p95/p99/max over a deterministic single-row
sample). All formulas are checked against hand-computed examples in
`tests/test_defend_metrics.py`.

## Architecture note: why the pipeline lives in `scripts/`, not `defend/`

`docs/ARCHITECTURE.md` restricts every package under `src/aegis/` to
importing `shared` only (`loop/` is the sole exception, and it's out of scope
here). Training end-to-end necessarily needs both `features/` (to build the
matrix) and `defend/` (to fit and score) - so that sequencing lives in
`scripts/train_baseline_detector.py` itself, which is the one place allowed
to depend on both. All actual logic - feature computation, model training,
metric math - still lives in `src/aegis/`; the script only sequences calls
and handles paths/CLI, per `scripts/README.md`.

## Running it

```bash
python -m pip install -e ".[dev]"
python scripts/prepare_paysim.py data/raw/paysim/<your-file>.csv --seed 20260101
python scripts/train_baseline_detector.py data/processed/paysim/<run-dir> --seed 20260101
```

Writes `models/xgboost-baseline-<seed>/` (override with `--output-dir`)
containing `model.json`, `metadata.json`, `evaluation_validation.json`, and
`evaluation_test.json`. `--help` lists all options (`--num-boost-round`,
`--latency-sample-size`).

## Blue Hardening Round 1

`scripts/harden_defender.py` (logic in `aegis.defend.hard_positives`)
implements `docs/ARCHITECTURE.md`'s RETRAIN stage and
`docs/EVALUATION_RULES.md` SS2/SS3 for the first time: it promotes every
scenario transaction (legitimate warm-up **and** fraudulent bust-out rows -
the warm-up rows are kept so the fraud rows' history-derived features are not
computed from a cold start) from the frozen Round-0 confrontation and the
selected Adaptive-Round-1 candidate into a training-only hard-positive set,
re-stamps `split=train`, and retrains a `xgboost-hardened-r1-<seed>` artifact
via the same low-memory pipeline described above - validation and test are
read, materialized, and scored exactly as in the plain baseline run; only
train gains the promoted rows.

Two things this deliberately does *not* do, per SS3/SS4: it never reports
Defender v2's score on the hard positives it was just trained on, and it
never claims a win from anything but the untouched PaySim test split
(`regression_vs_baseline.json`, written next to the new model artifact,
holds that baseline-v1-vs-Defender-v2 comparison). It also never generates or
mutates an attack - `generation2_handoff.json`, written alongside the model,
is the explicit, unmodified-script interface (`run_bustout_confrontation.py
--reuse-model-dir`, then `run_adaptive_bustout_round.py`) a fresh Red
generation-2 round should confront Defender v2 with next.

## Cross-family hardening (Defender v3)

`scripts/harden_defender_crossfamily.py` generalizes Blue Hardening Round 1
from one attack family to all three implemented so far. It promotes prior
real false negatives from:

1. `synthetic_identity_bustout` - the same Round-0 confrontation and selected
   Adaptive-Round-1 candidate Defender v2 used.
2. `mule_network_structuring` - the one real confrontation run against
   Defender v2 (`data/synthetic/mule_confrontations/`).
3. `adaptive_detector_evasion` - the one real confrontation run against
   Defender v2 (`data/synthetic/adaptive_evasion_confrontations/`).

into one combined, training-only hard-positive set, and retrains
`xgboost-hardened-crossfamily-<seed>` via the identical low-memory pipeline,
validation-only threshold tuning, and untouched-test evaluation used for
v1/v2. `aegis.defend.hard_positives.promote_hard_positives` needed **no
changes** - it already reads `attack_family`/`blueprint_id`/`generation`/
`scenario_id` off the promoted `Transaction` rows themselves and never
special-cased bust-out.

Deliberately **not** promoted: the bust-out "fresh confrontation" and
"generation-2" artifacts generated *against Defender v2*
(`confrontation-9ad4e08145771e39`,
`adaptive-round-1-10758c69cc2b51d5`) - those are reserved for the fresh,
post-v3 Red evaluation this script does not perform
(`docs/EVALUATION_RULES.md` SS4); promoting them now would consume the only
genuinely fresh bust-out evaluation available for that later step.

### Feature change: distinct-counterparty columns (v3 only)

Before adding anything, the mule confrontation's real transaction graph was
inspected against the existing 19 columns: it showed one coordinator account
paying several distinct mule accounts, and those accounts layering funds on
to further distinct accounts before a fan-in cash-out. `source_txn_count_before`
/ `destination_txn_count_before` count prior transaction *volume* per
account, never *distinct counterparties* - a source paying one destination
six times and a source paying six distinct destinations once each were
indistinguishable, even though only the latter is the fan-out pattern that
defines mule-network structuring. That is a structural gap the 19 columns
cannot close by retraining alone, not a training-data-volume problem.

Two columns were added to close exactly that gap, nothing more:
`source_distinct_destinations_before` and `destination_distinct_sources_before`
(cumulative distinct-counterparty counts, added to `_CausalHistoryState`
alongside the existing per-account state - see
`tests/test_features_temporal.py`'s
`test_fan_out_to_distinct_destinations_is_counted_separately_from_repeat_volume`
for the concrete before/after this closes). They follow every existing rule:
strictly-prior-only, no future edges, no labels, no post-transaction fields,
deterministic, and bounded in memory by distinct-account count (a `set` per
account, same order of memory as the existing `src_recent`/`dst_recent`
deques - not a transaction graph). `TemporalBaselineFeatureExtractor.version`
moved `0.1.0` -> `0.2.0` to mark the change. v1's and v2's frozen artifacts
are data already on disk and are unaffected; only future runs (v3 onward)
see 21 columns. Because the column set changed, v3's validation/test feature
arrays are always materialized fresh - `harden_defender.py`'s
`_maybe_reuse_baseline_features` optimization is deliberately **not** reused
in the cross-family script, since copying v1/v2's cached 19-column arrays
would silently score v3 on the wrong-shaped input.

### Three-way regression, not a cross-family-attack claim

`regression_vs_v1_v2.json`, written next to the new model artifact, compares
v1, v2, and v3 on the untouched PaySim test split only - precision, recall,
F1, PR-AUC, ROC-AUC, FPR, recall at fixed FPR budgets, confusion matrix,
threshold, and latency, for all three. This is a **static-holdout**
regression check, not evidence of cross-family attack improvement: per
`docs/EVALUATION_RULES.md` SS4, that requires a fresh Red confrontation
against the now-frozen v3 in each family, which is a separate, later step.
`codex_handoff.json`, written alongside it, lists every excluded scenario and
transaction id across all three families plus the fresh-seed requirement for
that step, and explicitly defers Leave-One-Attack-Family-Out (SS6).

## LOAFO generalization benchmark

`scripts/run_loafo_benchmark.py` implements `docs/EVALUATION_RULES.md` SS6
(Leave-One-Attack-Family-Out): three folds, each trained on two families'
prior hard positives with the third family contributing **zero** training
rows, then scored on one genuinely fresh scenario of that held-out family.
The question it answers is different from the cross-family regression above:
not "does the untouched PaySim number move" but "does a detector that has
never seen this family's pattern catch any of it at all" - generalization,
not memorization.

```
Fold A: train synthetic_identity_bustout + mule_network_structuring
        hold out adaptive_detector_evasion -> models/loafo-synth-mule-20260401/
Fold B: train synthetic_identity_bustout + adaptive_detector_evasion
        hold out mule_network_structuring  -> models/loafo-synth-adaptive-20260402/
Fold C: train mule_network_structuring + adaptive_detector_evasion
        hold out synthetic_identity_bustout -> models/loafo-mule-adaptive-20260403/
```

Each fold's fresh held-out scenario is generated and scored via the
existing, unmodified confrontation scripts
(`run_bustout_confrontation`/`run_mule_network_confrontation`/
`run_adaptive_evasion_confrontation`) against the fold's own frozen model, at
a seed used nowhere else in the repo. Defender v3 (trained *with* all three
families) is scored on the identical fresh scenario as a memorization
reference, so the two numbers are directly comparable. Both fold and v3
results are real `EvaluationResult`s tagged `LEAVE_ONE_ATTACK_FAMILY_OUT`
(`aegis.defend.metrics.build_evaluation_result` gained a small, additive
`held_out_family` passthrough for this - existing `STATIC_HOLDOUT` callers
are unaffected since it defaults to `None`).

Every fold verifies, not just claims: the held-out family's absence from
actual promoted provenance (not just from the source list); zero id overlap
between the fresh scenario and every prior artifact under `data/synthetic/`
and `data/hardening/` (a snapshot taken immediately before generation); and
that the fold model's and Defender v3's `model.json`/`metadata.json` are
byte-identical before and after scoring. `models/loafo_summary.json`
aggregates all three folds' held-out recall, the same-scenario Defender v3
comparison, and a disclosed strong/partial/weak rubric (see the script's
`build_summary` for the exact thresholds - a methodological choice, not a
fact about the data).

One real per-fold optimization: unlike `harden_defender.py`'s original
baseline-feature-reuse helper (which copied a cached feature array without
checking its schema), `_maybe_reuse_v3_features` here verifies the cached
schema's `feature_names` match the current extractor's exactly before ever
copying - safe here because every LOAFO fold and Defender v3 share the same
21-column (`0.2.0`) schema, unlike the v1/v2-vs-v3 case in the cross-family
script above.

## Limitations

* No cross-split history carryover (see above).
* Threshold tuning optimizes F1 only; a production deployment might instead
  target a specific FPR budget from `recall_at_fixed_fpr`.
* `hour_of_day` is the only temporal feature beyond raw timestamps-derived
  aggregates; day-of-week / seasonality are not modeled.
* No hyperparameter search - `DEFAULT_HYPERPARAMETERS` in
  `xgboost_detector.py` are reasonable defaults, not tuned.
* The balance-delta features removed in the Phase 2 leakage fix
  (`source_balance_delta`, `destination_balance_delta`) were, in the
  original PaySim fraud-detection literature, some of the more predictive
  signals - PaySim's synthetic fraud pattern (drain an account, leave its
  post-transaction balance near zero) shows up strongly in the *after*
  balance. Removing them is expected to reduce measured recall/precision
  versus a version that used them; that is the correct trade for a decision
  that must be made before the transaction settles, not a regression to
  chase back.
* The distinct-counterparty columns (Defender v3) are trained on exactly one
  real mule confrontation scenario and one real adaptive-evasion
  confrontation scenario - enough to prove the feature is wired correctly
  and leakage-safe, not enough to expect the trained model to generalize.
  Whether v3 actually catches more mule/adaptive-evasion attacks is an open
  question the fresh, post-v3 Red confrontation (not yet run) will answer.
* `TemporalBaselineFeatureExtractor` moved to version `0.2.0` for v3; a
  literal byte-for-byte re-run of the v1/v2 training commands against
  today's code would now produce 21-column features, not the 19 those two
  frozen artifacts recorded. This is expected - the version field exists to
  track exactly this - but no automated reproducibility check for v1/v2
  specifically exists in this repo.
