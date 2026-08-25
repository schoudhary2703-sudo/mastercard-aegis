# Adaptive attack evolution v1

Adaptive evolution v1 uses credible bust-out false negatives to explore new,
bounded attack blueprints and score fresh scenarios against the same frozen
Blue model. It does not promote hard positives, call `fit`, alter the action
policy, or implement the defender-retraining half of the closed loop.

## Flow and boundaries

```text
Round 0 confrontation artifacts
  ├─ confrontation.json
  ├─ blueprint.json
  ├─ transactions.jsonl
  └─ detector_outputs.jsonl
          │
          v
same saved detector ── explain Round 0 outputs without changing scores
          │
          v
EvasionFeedback[] ──> blind-spot analysis ──> bounded candidate blueprints
                                                    │
                   fresh seeds, generation=1 <──────┘
                                                    │
                                                    v
                                  fresh TransactionBatch candidates
                                                    │
                                                    v
                       train-fitted features ──> same detector and threshold
                                                    │
                                                    v
                      candidate fitness + Round 0/1 comparison + evasions
```

`aegis.loop` is the only AEGIS package that imports the public Red, feature,
Blue, and evaluation interfaces together. The executable script invokes that
orchestrator. No team implementation imports the loop or the other team.

The CLI loads an existing `XGBoostDetector` artifact. It never calls detector
`fit`, never writes the model directory, and verifies that its model version
and threshold match Round 0. The feature extractor is fitted on prepared
PaySim train only.

## Evidence and blind-spot analysis

Only successful evasions whose fidelity meets the frozen
`EvasionFeedback.is_credible_evasion` floor enter mutation evidence. Each
false negative becomes an `EvasionFeedback` carrying:

- original parent parameters;
- detector risk and threshold;
- model and scenario provenance;
- fidelity/realism score;
- detector-visible important signals; and
- the still-fraud transaction ID.

The original confrontation did not request explanations. The adaptive CLI
therefore re-scores the exact Round 0 transactions once with
`explain=True`. Before using those explanations it verifies that every risk
score, thresholded label, action, threshold, and transaction ID exactly
matches the committed confrontation. This is explanation enrichment against
the same frozen model, not retraining or re-evaluation with a new policy.

v1 maps only detector-visible features with a direct simulator relationship:

| Observed feature | Candidate control | Relationship used for exploration |
| --- | --- | --- |
| `temporal.amount` | `bustout_amount_multiplier` | larger multiplier generally raises amount |
| `temporal.amount_deviation_from_source_history` | `bustout_amount_multiplier` | larger multiplier generally raises deviation |
| `temporal.source_avg_amount_before` | `warmup_amount_mean` | larger warm-up mean raises history mean |
| `temporal.source_txn_count_before` | `warmup_transaction_count` | more warm-up rows raise prior count |
| `temporal.source_velocity_1h` | `bustout_window_hours` | a longer window generally lowers burst velocity |
| `temporal.destination_velocity_1h` | `destination_diversity` | more destinations generally lower per-destination velocity |
| `temporal.seconds_since_source_previous_txn` | `bustout_window_hours` | a longer window generally raises spacing |

Positive risk contributions vote for a bounded move that reduces the mapped
feature. Conflicting votes produce no direction. SHAP-style attribution is
associative, not a causal derivative, so the report describes the move as a
testable hypothesis rather than a learned truth.

Signal votes are weighted by each evasion's existing hardness components,
`(1 - risk_score) * fidelity_score`, so low-risk, realistic misses carry more
evidence than marginal ones. Original hardest-evasion ranks remain in feedback
metadata for traceability.

Round 0 normally contains only one blueprint parameter region. It cannot by
itself establish a statistical cross-region association such as “longer
warm-up always lowers risk.” When no mapped direction is supported, v1 uses
seeded symmetric local exploration across bounded mutable numeric parameters.
Those candidates are explicitly marked `symmetric_local_exploration`; the
report does not present them as blind-spot conclusions.

## Mutation algorithm

`generate_mutation_candidates()`:

1. reads only `AttackBlueprint.mutable_parameters()`;
2. considers numeric parameters with declared minimum and maximum bounds;
3. selects observed directions when available, otherwise deterministic
   symmetric exploration;
4. moves 8–24% of the declared range using a fixed magnitude schedule;
5. clamps to inclusive bounds and preserves integer/float types;
6. rejects unchanged and duplicate parameter maps;
7. leaves immutable parameters, behavioral steps, attack family, and realism
   constraints byte-equivalent; and
8. creates a deterministic child ID, `parent_blueprint_id`, `source=mutation`,
   and `generation=parent+1`.

Each Round 1 candidate uses a fresh seed and generates a complete scenario.
Warm-up and bust-out rows remain together in `test`; generated fraud remains
ground-truth `FRAUD` even when it evades.

## Fitness and selection

For each candidate:

```text
evasion_quality = 1 - average_fraud_risk_score
fitness = evasion_quality * overall_fidelity_score
```

This prevents a low-risk but unrealistic variant from winning purely on
evasion. Candidate order is descending fitness, ascending fraud risk,
descending fidelity, then candidate ID. The selected candidate is compared
with Round 0 using signed `Round 1 - Round 0` deltas for recall, average fraud
risk, fidelity, fitness, caught count, and evaded count.
Candidates below the frozen 0.5 realism floor remain recorded but cannot be
selected.

Candidate scenario results retain their contract-backed `EvaluationResult`.
Because the defender is not retrained, v1 correctly keeps the
`STATIC_HOLDOUT` protocol rather than claiming a `CLOSED_LOOP_ROUND`. Adaptive
candidate ID, average fraud risk, fitness, changes, and
`detector_retrained=false` are recorded in evaluation metadata.

## Command

After a confrontation run:

```bash
python scripts/run_adaptive_bustout_round.py \
  data/processed/paysim/<run-id> \
  data/synthetic/confrontations/<confrontation-id> \
  models/confrontations/<model-version> \
  --seed 20260102 \
  --candidate-count 4
```

The model directory must be the exact artifact used for Round 0. No model is
trained or downloaded by this command.

## Artifacts

The default output is gitignored:

```text
data/synthetic/adaptive_rounds/<adaptive-round-id>/
  adaptive_round.json
  blind_spot_analysis.json
  round_comparison.json
  parent_blueprint.json
  selected_blueprint.json
  hardest_surviving_evasions.json
  candidates/<candidate-id>/
    blueprint.json
    confrontation.json
    transactions.jsonl
    detector_outputs.jsonl
```

`adaptive_round.json` contains the parent and selected blueprints, all changed
parameters with evidence/rationale, every candidate's scenario/fraud/caught/
evaded/risk/fidelity/fitness metrics, Round 0/1 comparison, and deterministic
hardest-evasion ranking.

Existing output directories are never overwritten.

## Result status and limitations

No real PaySim run or production-trained model is available in this workspace.
The end-to-end test therefore uses small schema-compatible fixtures and marks
all results `integration_only=true`. Fixture outcomes prove deterministic
evolution, model immutability, scoring, and artifact serialization; they are
not efficacy claims.

v1 has three deliberate limits:

- no defender retraining or hard-positive promotion;
- no live LLM or detector-aware generator import; and
- no attack family other than synthetic identity / bust-out.

The artifacts are suitable evidence for a later defender-hardening phase, but
that phase must use newly generated post-retrain attacks and fresh seeds under
the binding evaluation rules.
