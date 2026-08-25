# Architecture

## The loop

```
        +---------------------------------------------------------------+
        |                                                               |
        v                                                               |
   IDENTIFY  ->  GENERATE  ->  [FEATURES]  ->  DEFEND  ->  EVALUATE  ->  EVOLVE
   identify/     generate/     features/       defend/     evaluate/     loop/
        ^                                                                  |
        |                            RETRAIN                               |
        +------------------------------------------------------------------+
```

Each arrow is a **contract**, not a function call into another team's code:

| Stage | Module | Consumes | Produces |
| --- | --- | --- | --- |
| IDENTIFY | `identify/` | `IdentificationContext` | `AttackBlueprint` |
| GENERATE | `generate/` | `AttackBlueprint` + `GenerationConfig` | `TransactionBatch` |
| FEATURES | `features/` | `Transaction[]` | feature matrix (`pd.DataFrame`) |
| DEFEND | `defend/` | feature matrix | `DetectorOutput` |
| EVALUATE | `evaluate/` | `DetectorOutput` + ground truth | `EvaluationResult` |
| EVOLVE | `loop/` | `EvasionFeedback` | mutated `AttackBlueprint` (generation + 1) |
| RETRAIN | `defend/` | promoted hard positives | new `model_version` |

## Why it is split this way

The Red Team and the Blue Team are built **in parallel, by separate agents**.
The only way that works is if neither can see inside the other. So:

* Everything crossing a team boundary is a pydantic model in
  `aegis.shared.contracts`, with `extra="forbid"` - an undeclared field is an
  error, not a silent private channel.
* Every module boundary is an ABC with two or three methods. A detector is
  anything with `fit` and `score`; a generator is anything that can turn a
  blueprint into transactions. Neither names a library.
* Feedback flows one way, through one type. `EvasionFeedback` is the *only*
  route from Blue Team back to Red Team. There is no shared mutable state, no
  registry, no callback.
* `Transaction.features` is an open, namespaced map. The Blue Team can add
  fifty derived features without a contract change and without the Red Team
  knowing they exist.

## Dependency rules

```
shared/   <- imported by everyone, imports nobody
identify/ -> shared
generate/ -> shared
features/ -> shared
defend/   -> shared
evaluate/ -> shared
loop/     -> shared, and (uniquely) both teams' packages
api/      -> shared, and read-only views of results
```

* `shared/` must never import from any other AEGIS package.
* `defend/` must never import `generate/`, `identify/` or `loop/`.
* `generate/` must never import `defend/` or `features/`.
* `loop/` is the only AEGIS package allowed to import from both sides. No AEGIS
  package imports from `loop/`; integration entry-point scripts may invoke it.
* `api/` and `web/` are read-only consumers of contracts. They compute nothing.

Import direction is the architecture. If a task seems to require breaking one
of these rules, the contract is wrong - fix the contract, do not add the import.

## Repository layout

```
src/aegis/
  shared/        contracts, enums, type aliases        (shared, frozen)
    contracts/     AttackBlueprint, Transaction, DetectorOutput,
                   EvaluationResult, EvasionFeedback
  identify/      blueprint proposal interface           (Red Team)
  generate/      generator interface + GenerationConfig (Red Team)
  features/      feature extractor interface            (shared, Blue-led)
  defend/        detector interface + action policy     (Blue Team)
  evaluate/      evaluator interface                    (shared, sign-off)
  loop/          attacker evolution orchestration       (Phase 2 v1)
  api/           read-only artifact index + FastAPI     (Phase 3, integration owner)
web/             demo UI + typed real-data client       (Phase 3, integration owner)
data/            datasets and generated corpora         (git-ignored)
scripts/         reproducible entry points
tests/           contract and interface tests
docs/            architecture, contracts, rules
```

`src/aegis/<module>/` is the logical `<module>/` from the project brief. The
`src/` layout gives one import root (`aegis.*`), so the two workstreams cannot
collide on a top-level package name and an editable install behaves like a real
one.

## Current implementation boundary

All three attack families are implemented end-to-end: `identify/`,
`generate/`, and `evaluate/` each have a module per family
(`synthetic_identity`, `mule_network`, `adaptive_evasion`), on top of
canonical PaySim preparation and the baseline detector. Attacker-only
adaptive evolution lives in `loop/` (`adaptive.py` for bounded bust-out
mutation, `adaptive_evasion.py` for the adaptive-evasion family); each
mutates blueprints and scores fresh variants against a frozen detector. See
`docs/SYNTHETIC_IDENTITY_BUSTOUT.md`, `docs/MULE_NETWORK_STRUCTURING.md`,
`docs/ADAPTIVE_DETECTOR_EVASION.md`, and `docs/ADAPTIVE_ATTACK_EVOLUTION.md`.

Three defender generations exist, each retraining the RETRAIN stage above
alongside (never over) the prior one:

* **Blue Hardening Round 1** (`scripts/harden_defender.py`,
  `aegis.defend.hard_positives`) promotes the Round-0 confrontation's and
  the selected Adaptive-Round-1 candidate's false negatives into a
  training-only hard-positive set and retrains `xgboost-hardened-r1-*`
  (Defender v2). See "Blue Hardening Round 1" in `docs/BASELINE_DETECTOR.md`.
* **Cross-family hardening** (`scripts/harden_defender_crossfamily.py`)
  generalizes that to Defender v3: it promotes prior real hard positives
  from all three attack families into one combined training-only set and
  retrains `xgboost-hardened-crossfamily-*`. It also adds two
  decision-time-safe, distinct-counterparty features
  (`TemporalBaselineFeatureExtractor` 0.1.0 -> 0.2.0) after inspecting the
  existing 19 columns against a real mule-network confrontation and finding
  they could not represent counterparty fan-out/fan-in. See "Cross-family
  hardening (Defender v3)" in `docs/BASELINE_DETECTOR.md`.
* **LOAFO** (`scripts/run_loafo_benchmark.py`) runs
  Leave-One-Attack-Family-Out: three fold models, each trained with one
  family's hard positives completely withheld, scored on a fresh
  never-seen scenario of that family, against Defender v3 as a memorization
  reference. See `docs/EVALUATION_RULES.md` SS6.

Not yet done: multi-round self-play (retrain -> fresh Red generation ->
retrain, repeated beyond the sequence already run) -- see README
"Limitations".

`api/` reads those persisted artifacts (models, confrontations, adaptive
rounds, hardening runs, LOAFO fold reports) through a discovery/lineage
layer (`aegis.api.index`, `aegis.api.benchmark`) and serves them read-only
over FastAPI (`aegis.api.app`): the first closed-loop cycle (Baseline v1 ->
Round-0 attack -> Adaptive Red -> Defender v2 hardening -> fresh
confrontation -> Generation-2 adaptation) plus the final benchmark (v1 vs
v2 vs v3, per-family fresh performance, LOAFO generalization). `web/`
consumes those endpoints through a typed client (`web/src/api/`) on
Overview, Co-Evolution, Evaluation, and Final Benchmark, clearly labeled
"Real pipeline data"; the original mock demo (`web/src/mock/`) is kept
alongside it, labeled "Simulated demo", and is not yet removed. See "API
architecture" below.

## API architecture (`src/aegis/api/`)

```
paths.py    slug validation + traversal-safe path resolution
reader.py   fault-tolerant JSON/JSONL reading (missing/malformed -> None, never raises)
index.py    discovers models/, data/synthetic/confrontations/**,
            data/synthetic/adaptive_rounds/**, data/hardening/** and
            resolves lineage between them from real fields already on
            those artifacts (model_version, parent_confrontation_id,
            presence of generation2_handoff.json) -- nothing is hardcoded
            to a specific report id
dto.py      response models. Where an artifact embeds a real
            aegis.shared.contracts type (EvaluationResult, AttackBlueprint)
            the DTO mirrors its fields exactly; the report-level shapes
            (confrontation.json, adaptive_round.json, hardening
            provenance) have no shared-contract equivalent, so a bespoke
            adapter DTO is used instead of changing shared/
service.py  builds DTOs from the index; only computes plain aggregates
            (sums, ratios) of numbers already on an artifact
app.py      FastAPI routes (GET-only)
```

Every artifact under `data/` and `models/` is git-ignored, so
`tests/test_api_*.py` build a throwaway fixture tree
(`tests/api_fixtures.py`) rather than depending on a pipeline run having
happened first; the endpoints degrade to an explicit empty/"not run yet"
state instead of erroring when no artifacts exist yet.
