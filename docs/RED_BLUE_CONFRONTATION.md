# First Red/Blue confrontation

This phase proves one contract-preserving path from the approved synthetic
identity / bust-out generator to the approved XGBoost baseline detector. It is
a single static confrontation: it does not mutate a blueprint, promote hard
positives, retrain after scoring, emit `EvasionFeedback`, or import
`aegis.loop`.

## Data flow

```text
prepared PaySim train.jsonl ──> fit temporal extractor + baseline detector
prepared PaySim validation.jsonl ──> tune decision threshold only
prepared PaySim test.jsonl ──> existing baseline static-holdout check

fresh bust-out AttackBlueprint + seed
  └─> TransactionBatch (entire scenario stamped test)
      └─> TemporalBaselineFeatureExtractor.transform
          └─> XGBoostDetector.predict
              └─> DetectorOutput[]
                  └─> BustOutConfrontationEvaluator
                      ├─> EvaluationResult
                      ├─> scenario caught/evaded report
                      └─> structured and ranked evasions
```

Package import direction remains intact. `aegis.evaluate.confrontation`
imports only frozen shared contracts. The additive script is the orchestration
boundary that imports the public Red, feature, and Blue interfaces. Neither
team implementation imports the other.

The script reuses `run_baseline_pipeline`, then loads the persisted detector
artifact before scoring. The feature extractor is fitted on train only. The
generated scenario starts after the latest prepared artifact timestamp and is
never added to detector training.

## Evaluation rules

Each `scenario_id` is indivisible. The evaluator rejects:

- generated transaction IDs or scenario IDs present in detector training;
- a scenario spanning multiple splits;
- a scored scenario in train, validation, or unassigned split;
- duplicate, missing, or unexpected detector output IDs;
- mixed detector model versions or thresholds; and
- unknown ground-truth or predicted labels.

Detector outputs are joined to truth by `transaction_id`, never row position.
The generated batch is stamped `test`; no split reassignment happens during
scoring.

For a ground-truth fraud event:

- **caught** means `DetectorOutput.predicted_label == FRAUD`;
- **evaded** means the thresholded predicted label is `LEGITIMATE`.

The recommended action is reported independently. An approved or stepped-up
event is not relabelled: every successful evasion retains
`ground_truth_label=FRAUD` in both the event assessment and evasion record.

Every scenario includes an `EvaluationResult` using the
`STATIC_HOLDOUT` protocol. This is intentionally not a
`CLOSED_LOOP_ROUND`, because no adaptation or post-score retraining occurs.

## Hardest evasions

Only successful false negatives enter the ranking. Each gets:

```text
hardness_score = (1 - detector_risk_score) * overall_fidelity_score
```

Records sort by descending hardness score, then ascending risk, descending
fidelity, scenario ID, and transaction ID. The last two keys make ties stable.
The report keeps both the unranked successful-evasion records and a ranked,
UI-ready copy. `credible_evasion` follows the frozen feedback contract's
current fidelity floor (`overall_fidelity_score >= 0.5`); low-fidelity misses
remain recorded but are visibly not credible.

## Command

First prepare a local PaySim CSV as documented in
[`PAYSIM_PREPARATION.md`](PAYSIM_PREPARATION.md), then run:

```bash
python scripts/run_bustout_confrontation.py \
  data/processed/paysim/<run-id> \
  --seed 20260101
```

Optional controls include `--num-boost-round`, `--latency-sample-size`,
`--reference-max-rows`, `--output-dir`, and `--model-output-dir`. No dataset is
downloaded automatically.

The default report directory is:

```text
data/synthetic/confrontations/<confrontation-id>/
  blueprint.json
  transactions.jsonl
  detector_outputs.jsonl
  confrontation.json
  evasions.jsonl
  hardest_evasions.json
```

Model artifacts remain under `models/confrontations/`. Both locations are
gitignored. Existing confrontation report directories are never overwritten.

## Result status and limitations

No processed PaySim dataset or trained model was present during implementation.
The automated end-to-end test therefore trains on a small contract-shaped
fixture and marks its report `integration_only=true` with
`data_basis=synthetic_fixture`. Fixture scores prove wiring and accounting
only; they are not PaySim or real-world efficacy measurements.

The temporal extractor intentionally starts scenario history cold and then
builds state causally from the scenario's warm-up rows. This matches the
approved baseline's no-cross-transform-state behavior. The first confrontation
produces evidence suitable for a future adaptive round, but does not start that
round.
