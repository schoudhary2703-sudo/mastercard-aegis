# Data strategy (locked)

This decision is **locked** for the current phase. Changing it requires an
explicit architecture decision, not a pull request.

## Primary: PaySim

PaySim is the canonical payment world. All generation, feature engineering and
evaluation happen in its schema and its account universe.

Why: it is agent-based and mobile-money shaped, so it has the two things this
project needs and card-transaction datasets lack - **account-to-account edges**
(mule networks are only expressible with a source and a destination) and a
**time axis** over the same accounts (bust-out is a trajectory, not a point).

* Location: `data/raw/paysim/`
* Maps onto `Transaction` directly: `type` -> `transaction_type`,
  `nameOrig` -> `source_account_id`, `nameDest` -> `destination_account_id`,
  `oldbalanceOrg`/`newbalanceOrig` -> `source_balance_before`/`_after`,
  `isFraud` -> `label`. The `step` column becomes `timestamp` via a fixed
  epoch offset chosen once and recorded.
* Preparation command, complete mapping, artifacts, default temporal split and
  optional entity-isolated robustness split are documented in
  [`PAYSIM_PREPARATION.md`](PAYSIM_PREPARATION.md).

## Secondary: IEEE-CIS (later, as a feature reference)

Used as a **feature-engineering reference and secondary benchmark** only - it
is rich in card-not-present, device and identity signals that PaySim does not
carry, which is useful for designing the synthetic-identity feature set.

Not used yet. Not merged with PaySim.

## Tertiary: ULB Credit Card Fraud (later, for imbalance sanity)

Used only to sanity-check that the detection stack behaves under extreme class
imbalance (~0.17% positives) and that the metric code is not silently broken.
Its features are PCA components, so nothing learned there transfers.

Not used yet.

## Rules

1. **Do not merge the three datasets.** They have different entities, different
   schemas and different fraud definitions. A merged corpus would make every
   metric uninterpretable.
2. **One canonical world per experiment.** An `EvaluationResult` covers exactly
   one dataset, named in `dataset_id`.
3. **No dataset is downloaded by the foundation**, and no script downloads one
   silently. Fetch is a human step; scripts print the URL and destination.
4. **Raw is immutable.** Nothing writes into `data/raw/`. Derived artifacts go
   to `data/interim/`, `data/processed/` and `data/synthetic/round_<n>/`.
5. **Nothing under `data/` is committed** except `README.md` and `.gitkeep`.
6. **Synthetic never silently mixes with real.** Every generated record carries
   `is_synthetic=True`; any corpus mixing the two records the ratio in its
   metadata.
