# PaySim preparation

PaySim is the canonical payment world for AEGIS. This pipeline validates a
human-supplied PaySim CSV and writes reproducible canonical transactions. It
does not download PaySim, generate fraud, mix in IEEE-CIS or ULB, build
features, or train a detector.

## Command

From the repository root after installing the project:

```bash
python scripts/prepare_paysim.py data/raw/paysim/PS_20174392719_1491204439457_log.csv --seed 20260101
```

The source path is positional and may point anywhere on the local machine.
`--data-root` defaults to `data`; derived output always goes beneath its
`interim/` and `processed/` subdirectories. The default split mode is
`temporal`; use `--split-mode entity_isolated` for the strict robustness mode.
Run `--help` for ratio, currency, epoch, and data-root options.

PaySim does not declare a currency. Transactions therefore use neutral `XXX`
by default, recorded as `neutral_default` in the manifest. Supplying, for
example, `--currency INR` records `INR` as an `explicit_override`; it is an
experiment assumption, not a claim about the source. Step 1 defaults to
`2017-01-01T00:00:00+00:00`, and every step advances one hour. Use `--epoch`
to change that recorded assumption.

## Required source schema

The standard source columns are all required:

```text
step,type,amount,nameOrig,oldbalanceOrg,newbalanceOrig,nameDest,
oldbalanceDest,newbalanceDest,isFraud,isFlaggedFraud
```

Supported source `type` values are `PAYMENT`, `TRANSFER`, `CASH_IN`,
`CASH_OUT`, and `DEBIT`. Rows with invalid types, flags, identifiers, numeric
values, or negative amounts are rejected with their CSV row number.

## Canonical mapping

| PaySim source | Canonical `Transaction` | Notes |
| --- | --- | --- |
| Source row + stable digest | `transaction_id` | Deterministic for an unchanged source file. |
| `step` | `timestamp` | Fixed epoch + `(step - 1)` hours, UTC. |
| `nameOrig` | `source_account_id` | Preserved verbatim after trimming. |
| `nameDest` | `destination_account_id` | Preserved for graph edges. |
| `amount` | `amount` | Currency is neutral `XXX` or a recorded explicit override. |
| `type` | `transaction_type` | Normalized to the frozen lowercase enum. |
| none | `channel` | `unknown`; PaySim does not supply a channel field. |
| merchant-shaped `nameDest` | `merchant_id` | Set when the destination begins with `M`; destination remains populated. |
| `oldbalanceOrg` | `source_balance_before` | Direct mapping. |
| `newbalanceOrig` | `source_balance_after` | Direct mapping. |
| `oldbalanceDest` | `destination_balance_before` | Direct mapping. |
| `newbalanceDest` | `destination_balance_after` | Direct mapping. |
| `isFraud` | `label` | `0` stays legitimate and `1` stays fraud. |
| none | `attack_family` | Always `None`; source fraud is not an AEGIS attack blueprint. |
| none | `is_synthetic` | Always `False`. |
| preparation assignment | `split` | `train`, `validation`, `test`, or unassigned quarantine. |
| `step`, `type`, `isFlaggedFraud`, row number, entity kinds | `metadata` | Source provenance retained for audit/simulation context. |

No detector-visible derived features are produced. In particular,
`isFlaggedFraud` remains provenance metadata and must not be treated as a
model feature without an explicit future leakage review.

## Split methodology

The default target ratios are 70/15/15. Boundaries are chosen between complete
PaySim steps nearest the target cumulative row counts; a step is never divided
between partitions. Seeded stable tie-breaking makes equal-distance boundary
choices reproducible.

### `temporal` (default)

Every transaction is assigned from its step alone. Accounts and merchant-like
destinations may recur in later windows; those overlaps are reported in the
manifest and do not cause quarantine. This preserves the canonical population
while ensuring train contains no future rows and no transaction appears in
more than one split.

### `entity_isolated` (optional)

The pipeline profiles every source and destination entity over the full CSV. A
transaction enters a split only if both entities' first and last observed steps
are entirely inside that transaction's temporal window. Rows involving an
entity that crosses a boundary are written to `quarantine.jsonl` with an
exclusion reason and `split=unassigned`.

This robustness mode additionally guarantees no source or destination entity
appears in more than one evaluation split, but can reduce usable sample volume.

Both policies guarantee:

- train precedes validation, which precedes test;
- no transaction ID appears in more than one split;
- no row is silently discarded.

### Limitations

Temporal mode allows entity identity overlap, so account memorization remains a
possible evaluation risk; the reported source and destination overlap counts
make that limitation visible. Entity-isolated mode trades sample volume for a
stronger robustness experiment. Long-lived accounts and frequently reused
destinations may send many rows to quarantine, and its achieved split sizes can
differ materially from target ratios. Always report the mode and quarantine
rate. The quarantine artifact is not an evaluation set.

The splitter prevents corpus-level temporal/entity overlap; it does not replace
the downstream requirements that feature histories use strictly earlier events
and that encoders/scalers fit on train only.

## Artifacts

Each deterministic run is published atomically under:

```text
data/processed/paysim/paysim-<source-hash>-<config-hash>/
  train.jsonl
  validation.jsonl
  test.jsonl
  quarantine.jsonl
  summary.json
```

Every JSONL line validates as the frozen shared `Transaction` contract.
`summary.json` records source and artifact SHA-256 checksums, seed, ratios,
split mode, epoch/currency semantics, source schema, source statistics, and
per-split transaction/fraud/type/step/time statistics. It also reports all
pairwise source-account and destination-account overlap counts, quarantine
count/percentage, exclusion reasons, and artifact checksums. Existing run
directories are never overwritten.

SQLite entity-profile state exists only under `data/interim/paysim/` during a
run and is removed afterward. The raw CSV is opened read-only.
