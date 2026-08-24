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
* `loop/` is the only package allowed to import from both sides. **Nothing may
  import from `loop/`** - that would create a cycle and re-couple the teams.
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
  loop/          closed-loop orchestration              (Phase 2, empty)
  api/           service layer                          (Phase 3, empty)
web/             demo UI                                (Phase 3, empty)
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

Phase 1 workstreams add implementations only inside their owned packages.
Canonical PaySim preparation and one deterministic Red Team generator
(synthetic identity / bust-out) are implemented; see
`docs/SYNTHETIC_IDENTITY_BUSTOUT.md`. The other Red Team families, adaptive
mutation, and closed-loop orchestration remain later-phase work.
