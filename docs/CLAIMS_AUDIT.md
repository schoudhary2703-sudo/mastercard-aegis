# Claims audit

What this submission supports, what it suggests but does not prove, what it
is explicitly limited by, and what it must never be described as. Every
number below is read from
[`data/reports/final_benchmark_summary.json`](../data/reports/final_benchmark_summary.json)
(regenerate with `scripts/build_final_benchmark_summary.py`); none is
invented. Use this document to check any sentence before it goes in a
slide, a script, or a write-up.

---

## Supported claims

Backed by a persisted `EvaluationResult` (or equivalent real artifact) on
the untouched PaySim test split or a real confrontation, reproducible by
rerunning the cited script.

* **AEGIS runs a real, working closed red-team/blue-team loop** -- three
  attack-family generators, a trained XGBoost detector, real confrontation
  reports, real hard-positive promotion, and real retraining, not a
  simulated or scripted narrative. Evidence: `models/`,
  `data/synthetic/confrontations/`, `data/hardening/`.
* **Defender v3 (cross-family hardening) improves precision, F1, and false
  positive rate over Defender v2 on the untouched PaySim test split**:
  precision 93.1% -> 93.8%, F1 84.3% -> 85.1%, FPR 0.0242% -> 0.0216%.
  Evidence: `regression_vs_v1_v2.json`, `model_comparison` in the final
  benchmark summary.
* **Defender v3 has the lowest false positive rate of the three model
  generations** (0.0216%, versus 0.0254% for v1 and 0.0242% for v2).
* **The mule-network confrontation data shows a real structural gap in the
  original 19-feature set** (no distinct-counterparty signal, only
  transaction-volume counts) -- the two features added for v3
  (`source_distinct_destinations_before`, `destination_distinct_sources_before`)
  are a direct, evidenced response to that gap, not a speculative addition.
  Evidence: `docs/BASELINE_DETECTOR.md` "Cross-family feature addition",
  `tests/test_features_temporal.py`.
* **LOAFO generalization is real, measured, and partial**: mean recall
  58.3% across three folds, each trained with the held-out family
  contributing zero rows, each scored on one fresh, real, previously-unseen
  scenario. Two of three families generalized strongly (bust-out 100%,
  adaptive-evasion 75%); one did not (mule-network 0%). Evidence:
  `models/loafo_summary.json`, each fold's `loafo_fold_report.json`.
* **Every LOAFO fold's held-out family contributed verifiably zero training
  rows**, every fresh scenario was verified to have zero id overlap with
  any prior artifact, and every model's file hash was verified unchanged
  before/after scoring -- these are asserted and tested
  (`tests/test_loafo_benchmark.py`), not just claimed in prose.
* **The real API and UI serve exactly what is on disk, computed live, with
  every real section clearly labeled** ("Real pipeline data" vs.
  "Simulated demo (not real data)"), and degrade to an explicit error or
  empty state rather than a silent or fabricated fallback when an artifact
  is missing. Evidence: `tests/test_api_*.py`, `web/src/components/real/`.

## Directional findings

Real numbers, but from a sample too small, too narrow, or too indirect to
generalize beyond "this is what we observed here."

* **Cross-family hardening's native-test-split improvement is one training
  run**, not an average over repeated seeds -- the direction (v3 > v2 on
  F1/precision/FPR) is real, but the exact magnitude (e.g. "+0.8 F1
  points") should be treated as a single observation, not a confidence
  interval.
* **Each LOAFO fold's fresh evaluation is one real scenario** (3-12 fraud
  events; see "Scenario counts are small" below) -- the 0%/75%/100%
  per-family recall figures are exact for that scenario, not an estimate
  of the true per-family recall rate.
* **The mule-network 0% LOAFO result is consistent with, but does not
  prove, "distinct-counterparty features require mule-specific training
  exposure to activate"** -- that is a plausible explanation consistent
  with the evidence (the features exist in every fold's 21-column schema;
  only the fold trained *with* mule data used them effectively), not an
  ablation-tested conclusion. No ablation removing the two new features was
  run.
* **Hardest-surviving-attack rankings (hardness = `(1 - risk) x fidelity`)**
  identify which real transactions were hardest for a given model in a
  given confrontation; they are a ranking within that confrontation, not a
  claim about attack difficulty in general.

## Limitations

Explicit constraints on how far any result above can be read.

* **No universal fraud-detection claim.** No result in this repository
  claims or implies that any AEGIS defender detects fraud in general, in
  production, on real (non-synthetic) traffic, or against attack patterns
  outside the three implemented families. Every number is scoped to PaySim
  and to these three families.
* **LOAFO generalization is partial, not general.** 58.3% mean recall
  across three folds, with one family at 0%, is evidence of *partial*
  transfer -- it is not evidence that AEGIS-hardened detectors generalize
  to unseen fraud patterns as a rule.
* **Mule-network structuring is the weakest unseen-family case.** A LOAFO
  fold trained without any mule-network hard positives caught 0 of 12
  fraudulent transactions in a fresh mule scenario, even though Defender
  v3 (trained *with* mule data) caught 5 of 12 (42%) of the identical
  scenario. This is the least favorable real result in this submission and
  must not be omitted when citing LOAFO's mean or the two strong folds.
* **Scenario counts are small.** Every fresh LOAFO evaluation is one
  generated scenario: 4 fraud events (adaptive-evasion), 12 (mule), 3
  (bust-out). Recall figures of 75%, 0%, and 100% are exact counts on
  those scenarios (3/4, 0/12, 3/3 respectively), not statistically powered
  estimates -- a single additional caught or missed transaction would
  change the reported percentage by 8-33 points depending on the family.
  Treat every LOAFO recall figure as directional.
* **Fidelity is descriptive, not a correctness guarantee.** `fidelity_score`
  measures how closely a generated scenario's statistical properties (warm-up
  amount distribution, transaction-type mix, transition sharpness) match
  real PaySim traffic -- it is a realism signal for the Red Team's own
  generator, not a certification that a scenario is representative of real
  fraud, and not a measure of the *detector's* correctness.
* **No production latency SLA claim.** Reported latency (mean/p50/p95/p99/max,
  e.g. Defender v3's 6.66ms mean) is measured over a fixed sample of scoring
  calls on one development machine during evaluation, not a load-tested,
  concurrency-tested, or infrastructure-representative figure. It supports
  "this detector scores a transaction in single-digit milliseconds on this
  machine," nothing about production throughput, tail latency under load, or
  any contractual SLA.
* **No cross-validation.** Model-comparison numbers come from a single
  train/validation/test split; LOAFO folds are not repeated with different
  seeds or splits. Reported figures are not averaged over folds in the
  cross-validation sense (LOAFO's three "folds" are three different
  held-out *families*, not a k-fold split of one dataset).
* **Synthetic data throughout.** All fraud examples, in all three families,
  are synthetically generated by AEGIS's own generators against a PaySim
  reference distribution -- none are real fraud cases. Native PaySim
  test-split metrics use PaySim's own labels, which are themselves
  synthetic (PaySim is a simulator, not captured real transactions).

## Claims we must NOT make

Sentences that a reader could reasonably infer from the numbers above but
that this evidence does not support. Do not say or write these.

* "AEGIS detects fraud" / "AEGIS solves fraud detection" (unqualified,
  without "on PaySim, for these three synthetic attack families").
* "Defender v3 generalizes to unseen attacks" (unqualified -- it generalizes
  *partially*, and specifically failed to generalize to mule-network
  structuring in this benchmark).
* "Cross-family hardening fixes the mule-network blind spot" -- it does
  not: the LOAFO fold trained without mule data still caught 0 of 12.
  Cross-family hardening improved the *native test split* and two of three
  *held-out-family* results; it did not fix the third.
* "This is production-ready" / any readiness, deployment-safety, or
  compliance claim beyond "a read-only demo API and UI over synthetic
  benchmark artifacts" (see `docs/DEPLOYMENT.md` for exactly what is and
  is not deployed).
* Any specific latency, throughput, or uptime guarantee.
* Any claim of statistical significance for a LOAFO recall figure (p-values,
  confidence intervals) -- none were computed, and a single-scenario sample
  does not support one.
* "The model never has false positives" or any zero-error claim -- FPR is
  low (0.0216% for v3) but non-zero; confusion counts in the benchmark
  summary show real false positives at every model generation.
