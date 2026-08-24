# Contracts

Everything the two workstreams exchange lives in `aegis.shared.contracts`.
Import from the package, not the submodules:

```python
from aegis.shared.contracts import AttackBlueprint, Transaction, DetectorOutput
```

All contracts inherit `AegisModel`, which sets `extra="forbid"` and
`validate_assignment=True`. An unknown key raises; a bad assignment raises.

## Versioning

`aegis.shared.version.CONTRACT_VERSION` is stamped onto every contract instance
and must be bumped whenever a field is added, removed, renamed or retyped.

| Change | Bump | Effect |
| --- | --- | --- |
| Remove / rename / re-mean a field | MAJOR | Breaks both teams. Needs both sign-offs. |
| Add an optional field | MINOR | Backwards compatible. |
| Docs, validators, defaults | PATCH | Shape unchanged. |

---

## AttackBlueprint

Declarative description of an attack. Data, not code.

| Field | Notes |
| --- | --- |
| `attack_id` | Stable identifier. |
| `attack_family` | One of the three in-scope families. |
| `description`, `objective` | Both required, both non-empty. |
| `target_features` | Detector-visible features the attack aims to influence. |
| `sequence` | `BehavioralStep[]`, ordered by `order` then `offset_seconds`. Times are **relative** to scenario start, never absolute. |
| `parameters` | `dict[str, ParameterSpec]`. `mutable=False` marks a structural knob the optimizer may not touch. |
| `realism_constraints` | Amount, currency, channel, velocity, hour and sequence-length bounds. |
| `parent_blueprint_id`, `generation` | Lineage across closed-loop rounds. |
| `metadata` | Free-form. |

Helpers: `ordered_sequence()`, `mutable_parameters()`, `default_parameters()`.

**`defend/` must never read a blueprint.** That is target leakage.

## Transaction

The single record type for real and synthetic events alike.

Core: `transaction_id`, `timestamp` (tz-aware, coerced to UTC),
`source_account_id`, `destination_account_id`, `amount`, `currency` (ISO-4217,
uppercased), `transaction_type`, `channel`.

Context: `merchant_id`, `merchant_category`, `device_id`, `country`, and the
four optional PaySim-shaped balance fields.

Labelling: `label` (`FraudLabel`: 0 / 1 / -1) and `attack_family`.
**`UNKNOWN` means unlabelled, never legitimate** - `is_fraud` is True only for
an explicit `FRAUD`.

Provenance: `is_synthetic`, `scenario_id`, `blueprint_id`, `step_id`,
`sequence_index`, `generation`.

Partitioning: `split`, assigned by the evaluation harness and by nobody else.

**Extension point:** `features: dict[str, FeatureValue]`, a namespaced open map.

```python
txn = txn.with_features("temporal", {"velocity_1h": 3})
txn = txn.with_features("graph", {"fan_out": 5})
# -> {"temporal.velocity_1h": 3, "graph.fan_out": 5}
```

Derived behavioural and network features go **here**, never into new top-level
fields. That is what keeps the schema decoupled from any one detector.
`to_flat_record()` lifts them to the top level for a DataFrame.

`TransactionBatch` wraps a list plus provenance: `seed`, `generator_name`,
`generator_version`, `scenario_ids`, `split`, `generation`. A batch that cannot
be regenerated from its `seed` is not a valid artifact.

## DetectorOutput

The only thing the system sees from a detector.

`transaction_id`, `risk_score` (calibrated, `[0, 1]`), `predicted_label`,
`recommended_action` (`approve` / `step_up` / `review` / `decline`),
`important_signals`, `model_version`, plus `threshold`, `policy_version`,
`latency_ms`.

`SignalContribution` carries `name`, signed `contribution`, `value`,
`direction`, `rank`. Ranks must be unique. Signal names must be
**detector-visible feature names** - never blueprint parameters.

`BaseDetector.predict()` assembles these for you from `score()` and the
`ActionPolicy`; implementations should not need to override it.

## EvaluationResult

Self-describing performance record. `protocol` is mandatory - a metric without
its protocol is not interpretable.

* `overall`: `ClassificationMetrics` - precision, recall, F1, PR-AUC, ROC-AUC,
  FPR, `recall_at_fixed_fpr` (keyed by FPR budget as a string, e.g. `"0.001"`),
  `alert_rate`, `threshold`, and raw `ConfusionCounts`.
* `per_attack_family`: the same metrics per family.
* `latency`: mean / p50 / p95 / p99 / max.
* `fidelity`: `FidelityMetrics` - only when synthetic data is involved.
* `round_index` (required for `CLOSED_LOOP_ROUND`), `held_out_family`
  (required for `LEAVE_ONE_ATTACK_FAMILY_OUT`) - both enforced by validators.

## EvasionFeedback

The one channel from Blue Team back to Red Team.

`attack_family`, `original_parameters`, `detector_score`,
`detector_model_version`, `evaded`, `realism_score`, `important_signals`,
`suggested_mutations`, `round_index`, `generation`, `transaction_ids`.

`ParameterMutation` proposes one change: `parameter`, `direction`
(`increase` / `decrease` / `set` / `jitter` / `resample`), `current_value`,
`proposed_value` (required for `set`), `magnitude`, `rationale`, `confidence`,
`priority`. Proposals are advisory; `loop/` decides, and
`AttackBlueprint.mutable_parameters()` decides what is even legal.

`is_credible_evasion` is True only when the attack evaded **and** realism was
measured and acceptable. An evasion achieved by generating implausible traffic
is a bug, not a finding.

## Enums

`AttackFamily` (3, do not extend), `TransactionType`, `Channel`, `FraudLabel`,
`RecommendedAction`, `DataSplit`, `EvaluationProtocol`, `MutationDirection`,
`ParameterType`, `SignalDirection`.

Adding a member is MINOR; removing or renaming one is MAJOR.
