# Evaluation rules

**Binding on both workstreams.** These rules exist because a closed loop is
unusually easy to fool: the system that generates the test set and the system
that trains on it are in the same repository. A result that breaks any rule
below is discarded, however good it looks.

Every reported number must come out of an `EvaluationResult` carrying the
`EvaluationProtocol` that produced it.

---

## 1. Train, validation and test stay separated

Every transaction carries a `split` field (`train` / `validation` / `test` /
`holdout`). It is assigned **once**, by the evaluation harness, and never
reassigned by a generator, a detector or a feature extractor.

* Splitting is by **entity and time**, not by row. All transactions of one
  `scenario_id` land in the same split; likewise all transactions of an account
  involved in that scenario. Splitting a mule ring across train and test leaks
  the ring's structure.
* Thresholds, calibration and early stopping are tuned on **validation** only.
* `holdout` is touched once, at the end, for the final reported figure.

## 2. Previous-round false negatives may become hard positives

Attacks that evaded detection in round *n* are the most valuable training
signal available, and may be promoted into the round *n+1* **training** set.

* Promotion is explicit: the records are re-stamped `split=train` and the move
  is recorded in the round's metadata.
* Promoted records must be removed from every evaluation set they previously
  belonged to. A record may never be in train and test simultaneously.
* Promotion never runs backwards: a round *n* result is not restated after the
  round *n+1* promotion.

## 3. A model is never evaluated on samples just added to its training set

This is the direct corollary of rule 2 and the single easiest way to
accidentally report a fake improvement. After retraining on promoted hard
positives, the retrained model's score on those exact records is
**meaningless** and must not be reported.

## 4. Closed-loop evaluation uses newly generated attacks

A `CLOSED_LOOP_ROUND` result must be computed on attacks generated **after**
the retrain, from the mutated blueprints of that round, with a fresh seed.

Ordering within a round is fixed:

```
generate(round n) -> score -> evaluate -> feedback -> mutate -> retrain
                                                                   |
                                        generate(round n+1, new seed)
                                                                   |
                                                       score -> evaluate
```

Reusing round *n* attack samples to evaluate the round *n+1* model is a
violation, even with a different seed on the sampler.

## 5. No target leakage, no future leakage

* A detector must never read `attack_family`, `blueprint_id`, `step_id`,
  `scenario_id`, `is_synthetic`, `generation` or any `AttackBlueprint`. These
  are provenance and ground truth, not features.
* A feature extractor computes each row's features from that row and from
  **strictly earlier** events. Any aggregate, encoding or scaler fitted across
  the whole corpus (including test rows) is future leakage.
* Encoders, scalers and vocabularies are fitted on **train** only and applied
  to validation and test.
* The generator must not read detector internals. The only permitted feedback
  channel is `EvasionFeedback` -> `loop/` -> mutated `AttackBlueprint`.

## 6. Leave-One-Attack-Family-Out is supported from the start

`LEAVE_ONE_ATTACK_FAMILY_OUT` withholds one of the three families from training
entirely and evaluates on it, to measure generalization to unseen attacks.
`EvaluationResult.held_out_family` is mandatory for this protocol - the
contract enforces it.

Because there are three families, LOAFO produces three runs. Report all three;
reporting only the best one is not a result.

---

## Additional standing requirements

* **Realism gates evasion.** An evasion with `realism_score` unmeasured or
  below the agreed floor is not counted as an evasion. `EvasionFeedback.
  is_credible_evasion` encodes the current floor.
* **Metrics are imbalance-aware.** Accuracy is not reported. PR-AUC, recall at
  a fixed FPR budget, and per-family breakdowns are the headline numbers.
* **Fixed FPR budgets** are agreed once and reused: `0.001`, `0.005`, `0.01`.
  They are the keys of `ClassificationMetrics.recall_at_fixed_fpr`.
* **Seeds are recorded.** Every batch records `seed`; every evaluation records
  `seed` and `model_version`. An unreproducible number is not reportable.
* **Alignment by id.** Detector outputs are joined to ground truth by
  `transaction_id`, never by row position.
* **Unlabelled is not legitimate.** `FraudLabel.UNKNOWN` rows are excluded from
  metrics, not counted as negatives.
