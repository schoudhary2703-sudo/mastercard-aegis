# AEGIS

**Adversarial Evaluation & Generative Immune System for payments.**
Mastercard Innovation Challenge 2026.

A closed-loop red-team / blue-team payment security system. A Red Team invents
and mutates fraud; a Blue Team detects it; the loop feeds successful evasions
back as training signal.

```
IDENTIFY -> GENERATE -> DEFEND -> EVALUATE -> EVOLVE -> RETRAIN
```

> **Status: Blue Hardening Round 1.** Contracts, canonical PaySim preparation,
> the first Red and Blue implementations, their confrontation, and
> attacker-only adaptive evolution v1 are complete. Defender retraining now
> exists for one round: `scripts/harden_defender.py` promotes Round-0 and
> Adaptive-Round-1 false negatives into training-only hard positives and
> retrains a `xgboost-hardened-r1-*` artifact alongside the frozen baseline.
> Multi-round self-play (retrain -> fresh Red generation -> retrain) is not
> implemented. Workstream boundaries and evaluation rules remain binding; see
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
  loop/        attacker evolution             Phase 2 v1 (no retraining)
  api/         read-only artifact API        Phase 3, integration owner
web/           demo UI + real-data client    Phase 3, integration owner
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
| [`docs/SYNTHETIC_IDENTITY_BUSTOUT.md`](docs/SYNTHETIC_IDENTITY_BUSTOUT.md) | Generating the first Red Team family. |
| [`docs/ADAPTIVE_ATTACK_EVOLUTION.md`](docs/ADAPTIVE_ATTACK_EVOLUTION.md) | Evolving bust-out variants against a frozen detector. |
| [`docs/BASELINE_DETECTOR.md`](docs/BASELINE_DETECTOR.md) "Blue Hardening Round 1" | Promoting hard positives and retraining the defender. |

## Non-goals

Still not added: the other two attack generators, multi-round self-play
(retraining after each new Red generation, repeatedly), SDV / CTGAN,
LangGraph, or GRPO. Cross-workstream components remain governed by
`AGENTS.md`; cloud infrastructure, authentication, databases, and Docker
remain out of scope.
