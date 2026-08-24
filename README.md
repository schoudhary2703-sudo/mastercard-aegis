# AEGIS

**Adversarial Evaluation & Generative Immune System for payments.**
Mastercard Innovation Challenge 2026.

A closed-loop red-team / blue-team payment security system. A Red Team invents
and mutates fraud; a Blue Team detects it; the loop feeds successful evasions
back as training signal.

```
IDENTIFY -> GENERATE -> DEFEND -> EVALUATE -> EVOLVE -> RETRAIN
```

> **Status: foundation only.** This repository currently contains contracts,
> interfaces, tests and rules. There is no fraud generator, no detector, no ML
> training, no closed-loop algorithm and no UI. That is deliberate - see
> [Non-goals](#non-goals).

## Scope

Exactly three attack families, deliberately. Do not add more.

| Family | What it is |
| --- | --- |
| `synthetic_identity_bustout` | Fabricated or blended identities nurtured into good standing, then drained. |
| `mule_network_structuring` | Layered transfers across mule accounts, structured under reporting thresholds. |
| `adaptive_detector_evasion` | Attacks mutated in response to detector feedback to stay under the threshold. |

## Quickstart

```bash
python -m pip install -e ".[dev]"   # or: make install-dev
python scripts/verify_setup.py      # or: make verify
python -m pytest                    # or: make test
```

Then read [`AGENTS.md`](AGENTS.md) before writing any code.

## Architecture at a glance

Every arrow in the loop is a **contract**, not a call into another team's code.

| Stage | Module | Consumes | Produces |
| --- | --- | --- | --- |
| IDENTIFY | `identify/` | `IdentificationContext` | `AttackBlueprint` |
| GENERATE | `generate/` | `AttackBlueprint` + `GenerationConfig` | `TransactionBatch` |
| FEATURES | `features/` | `Transaction[]` | feature matrix |
| DEFEND | `defend/` | feature matrix | `DetectorOutput` |
| EVALUATE | `evaluate/` | `DetectorOutput` + truth | `EvaluationResult` |
| EVOLVE | `loop/` | `EvasionFeedback` | mutated `AttackBlueprint` |

The Red Team and Blue Team are built in parallel by separate agents, so neither
may see inside the other. Full rules in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Layout

```
src/aegis/
  shared/      contracts, enums, types      shared, frozen
    contracts/   AttackBlueprint, Transaction, DetectorOutput,
                 EvaluationResult, EvasionFeedback
  identify/    blueprint proposal            Red Team
  generate/    generator interface           Red Team
  features/    feature extractor interface   shared, Blue-led
  defend/      detector + action policy      Blue Team
  evaluate/    evaluator interface           shared, needs sign-off
  loop/        closed-loop orchestration     Phase 2 (empty)
  api/         service layer                 Phase 3 (empty)
web/           demo UI                       Phase 3 (empty)
data/          datasets, generated corpora   git-ignored
scripts/       reproducible entry points
tests/         contract + interface tests
docs/          architecture, contracts, rules
```

`src/aegis/<module>/` is the logical `<module>/` from the brief. The `src/`
layout gives both workstreams one import root (`aegis.*`) with no top-level
name collisions.

## How a future workstream plugs in

**Blue Team - a new detector.** Subclass `BaseDetector`, implement two methods.
`predict()` assembles `DetectorOutput` for you.

```python
from aegis.defend import BaseDetector

class MyDetector(BaseDetector):
    name = "my-detector"
    model_version = "my-detector-r1"

    def fit(self, X_train, y_train, meta=None):
        ...
        self._feature_names = list(X_train.columns)
        self._is_fitted = True
        return self

    def score(self, X):
        ...  # ndarray of calibrated probabilities in [0, 1]
```

**Red Team - a new generator.** Subclass `BaseGenerator` and implement
`stream()`. `generate()` wraps it into a provenanced `TransactionBatch`.

```python
from aegis.generate import BaseGenerator

class MyGenerator(BaseGenerator):
    name = "my-generator"
    supported_families = ("mule_network_structuring",)

    def stream(self, blueprint, config):
        for step in blueprint.ordered_sequence():
            yield Transaction(...)  # is_synthetic=True, scenario_id, blueprint_id
```

**Features.** Subclass `BaseFeatureExtractor`, namespace every emitted column
(`temporal.*`, `graph.*`), fit on train only.

Nothing above requires either team to read the other's code. That is the point.

## Development

| Command | Does |
| --- | --- |
| `make install-dev` | Editable install with dev tooling. |
| `make test` | Run the test suite. |
| `make lint` | `ruff check .` |
| `make format` | `ruff format .` + autofix. |
| `make typecheck` | `mypy` (strict on `src/`). |
| `make check` | Lint + typecheck + test. |
| `make verify` | Smoke-check the install and contract surface. |

Runtime dependencies are pydantic, numpy and pandas. Nothing else, on purpose -
ML and generative libraries are added by the workstream that needs them.

## Documentation

| Doc | Read it when |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | **Before writing any code.** Ownership and rules. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Understanding module boundaries. |
| [`docs/CONTRACTS.md`](docs/CONTRACTS.md) | Using or changing a shared type. |
| [`docs/EVALUATION_RULES.md`](docs/EVALUATION_RULES.md) | Producing any number. Binding. |
| [`docs/DATA_STRATEGY.md`](docs/DATA_STRATEGY.md) | Touching a dataset. Locked. |

## Non-goals

Not in this repository, and not to be added without an explicit decision:
fraud generation logic, trained models, XGBoost / LightGBM, SDV / CTGAN,
LangGraph, GRPO, TGN / GNN, Streamlit / React, the closed-loop algorithm, cloud
infrastructure, authentication, databases, Docker.
