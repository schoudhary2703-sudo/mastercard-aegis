# Hackathon gap sprint evidence

This sprint broadens identification and demonstrates generation scale without
changing any detector, trained model, frontend, shared contract, or historical
benchmark result.

## Breadth taxonomy

`submission/artifacts/data/reports/attack_taxonomy.json` contains 14
evidence-backed scenarios across 8 categories and 18 channels. Exactly the
three existing `AttackFamily` values are `DEEP_SIMULATED`; the other 11 are
explicitly `IDENTIFIED_ONLY` and carry source URLs and readiness limits.

## Generation-scale benchmark

Run:

```bash
python scripts/run_generation_scale_benchmark.py
```

The persisted development-machine observation in
`submission/artifacts/data/reports/generation_scale_benchmark.json` generated
3,000 scenarios / 55,000 transactions, including 19,000 fraud-labelled
transactions. First-pass generation took 2.759 seconds in aggregate (about
19,931 transactions/second). All three repeated byte-stable fingerprints,
reported 100% constraint validity, and had zero overlap with historical
scenario IDs.

Fidelity is deliberately separate from validity. Per-family fidelity excluding
constraint validity was 0.8497 (synthetic identity), 0.8049 (mule network), and
0.7928 (adaptive evasion). These are descriptive similarities to train-only
PaySim statistics and declared simulator invariants, not real-world realism
certificates. The artifact retains amount, temporal, transaction-type, and
structural/topology components plus violation rates for every family.

## Fast GenAI-guided demo

Run:

```bash
python scripts/run_fast_genai_guided_demo.py
```

Observed runtime was 0.189 seconds inside the runner and 3.727 seconds
end-to-end including interpreter startup/imports. The run reused persisted live
artifact `blind_spot_analyst-4a31d071288af1f5`, accepted five bounded
mutations, rejected one, generated fresh scenario
`bustout-6f0ba72f-20261011-0000`, and scored it with unchanged frozen Defender
v3. One of three fraud transactions was caught; fidelity was 0.9032. This is a
new demo result, not a revision of any historical benchmark.

Freshness covers 4,463,654 training rows: 4,463,587 base PaySim rows are
disjoint by the frozen `paysim-` ID namespace and absence of scenario IDs, and
the 67 additional hard-positive rows are checked by exact transaction and
scenario membership from the hash-bound reference snapshot. The runner makes
no provider call and performs no fit or retrain.

## Multi-family GenAI input

`run_genai_analysis.py blind-spot --request-only` now prepares and validates
mule-network or adaptive-evasion requests without building a provider or using
credits. No live artifacts were fabricated or generated for those families.
