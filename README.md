# AEGIS

**Adversarial Evaluation & Generative Immune System for payments.**
Mastercard Innovation Challenge 2026.

## The problem

Fraud detectors trained once and left alone go stale: the pattern a model
was tuned against is not the pattern that shows up in production six months
later, because the people committing fraud adapt. Most fraud-detection
demos show a static model scoring a static test set and stop there -- which
never tests the thing that actually matters: **does the detector improve
when it sees new attacks, and does that improvement generalize, or is it
just memorizing what it was shown?**

## The AEGIS solution

AEGIS is a closed-loop red-team / blue-team system: a Red Team invents and
mutates synthetic fraud, a Blue Team detects it, and the loop feeds
successful evasions back into training as signal for the next round.

```
IDENTIFY -> GENERATE -> DEFEND -> EVALUATE -> EVOLVE -> RETRAIN
```

| Stage | Module | Consumes | Produces |
| --- | --- | --- | --- |
| IDENTIFY | `identify/` | `IdentificationContext` | `AttackBlueprint` |
| GENERATE | `generate/` | `AttackBlueprint` + `GenerationConfig` | `TransactionBatch` |
| FEATURES | `features/` | `Transaction[]` | feature matrix |
| DEFEND | `defend/` | feature matrix | `DetectorOutput` |
| EVALUATE | `evaluate/` | `DetectorOutput` + ground truth | `EvaluationResult` |
| EVOLVE | `loop/` | `EvasionFeedback` | mutated `AttackBlueprint` |
| RETRAIN | `defend/` | promoted hard positives | new `model_version` |

Every arrow is a **contract** (a frozen pydantic type in
`aegis.shared.contracts`), not a function call into another team's code --
see [`docs/CONTRACTS.md`](docs/CONTRACTS.md) and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

This repository has run that loop for real, on real PaySim data, through
three defender generations and a formal generalization benchmark -- not a
simulation of what the loop would produce. Every number cited below is
read from a persisted artifact on disk (`data/reports/final_benchmark_summary.json`),
never invented.

## Three attack families, deliberately fixed

| Family | What it is |
| --- | --- |
| `synthetic_identity_bustout` | A fabricated or blended identity builds ordinary payment history, then drains a sudden burst of high-value transfers. |
| `mule_network_structuring` | A coordinator account fans funds out across several mule accounts, layers them, and fans back in to a cash-out -- structured to keep any single transaction unremarkable. |
| `adaptive_detector_evasion` | An attack probes a frozen detector, reads which signals scored it, and mutates its own parameters to stay under threshold. |

Exactly these three, on purpose -- see [Non-goals](#non-goals).

## Architecture

```
src/aegis/
  shared/        contracts, enums, types              shared, frozen
  identify/      blueprint proposal                    Red Team
  generate/      generator interface + 3 generators     Red Team
  features/      feature extractor (21 decision-time-safe columns)
  defend/        detector, action policy, hardening, metrics
  evaluate/      evaluator interface + confrontation reports
  loop/          attacker evolution (adaptive mutation)
  api/           read-only artifact API (FastAPI)
web/             judge-facing UI (React + Vite), real data + labeled mock demo
scripts/         reproducible entry points (train, confront, harden, benchmark)
data/            datasets and generated corpora (git-ignored, never committed)
models/          trained detector artifacts (git-ignored, never committed)
tests/           unit, integration, and contract tests
docs/            architecture, contracts, rules, this submission's own docs
```

`api/` and `web/` are **read-only consumers** of what the pipeline already
produced -- they compute nothing, retrain nothing, and never re-run a
generator or detector. See "Real API + UI" below.

## PaySim setup

The canonical payment world is [PaySim](https://www.kaggle.com/datasets/ealaxi/paysim1),
a public synthetic mobile-money simulator (chosen and locked -- see
[`docs/DATA_STRATEGY.md`](docs/DATA_STRATEGY.md)). It is not bundled (multi-GB
CSV); download it yourself and point the preparation script at it:

```bash
python scripts/prepare_paysim.py data/raw/paysim/<your-file>.csv --seed 20260101
```

This produces one deterministic, versioned `train.jsonl` /
`validation.jsonl` / `test.jsonl` split under `data/processed/paysim/<run-id>/`
-- entity- and time-based, never touched by a generator or a detector after
assignment (see [`docs/EVALUATION_RULES.md`](docs/EVALUATION_RULES.md) SS1).
Every training and confrontation script below reads from this one prepared
run, so every model in the progression is comparable on the identical
untouched test split.

## Blue defender progression: v1 -> v2 -> v3

| Version | What it is | Trained on |
| --- | --- | --- |
| **Baseline v1** (`xgboost-baseline-20260101`) | The first real detector: XGBoost over 19 decision-time-safe features. | PaySim train only. |
| **Defender v2** (`xgboost-hardened-r1-20260201`) | Promotes Round-0 and Adaptive-Round-1 bust-out false negatives into training-only hard positives, retrains. | PaySim train + bust-out hard positives. |
| **Defender v3** (`xgboost-hardened-crossfamily-20260301`) | **Cross-family hardening**: promotes prior real hard positives from all three families, retrains with two added features. | PaySim train + hard positives from all 3 families. |

**Cross-family hardening.** Before adding anything, the real mule-network
confrontation data was inspected against the existing 19 features: they
counted prior transaction *volume* per account but never distinct
*counterparties*, so a coordinator paying one destination six times and one
paying six distinct destinations once each looked identical -- exactly the
difference between ordinary payments and mule fan-out. Two columns were
added to close that specific gap: `source_distinct_destinations_before`,
`destination_distinct_sources_before` (21 columns total, same causal,
decision-time-safe rules as the other 19; see
[`docs/BASELINE_DETECTOR.md`](docs/BASELINE_DETECTOR.md)).

On the untouched PaySim test split:

| Metric | Baseline v1 | Defender v2 | Defender v3 |
| --- | --- | --- | --- |
| Precision | 92.9% | 93.1% | **93.8%** |
| Recall | 79.5% | 77.1% | 77.9% |
| F1 | 85.7% | 84.3% | 85.1% |
| FPR | 0.0254% | 0.0242% | **0.0216%** |
| Mean latency | 6.86ms | 12.28ms | 6.66ms |

Cross-family hardening improved precision, F1, and FPR versus Defender v2,
and closed most of v2's regression against baseline v1 on the *native*
task -- while adding training signal from two families v2 had never seen.
It does not fully recover baseline v1's recall. Full numbers, per-family
breakdowns, and confusion matrices:
[`data/reports/final_benchmark_summary.json`](data/reports/final_benchmark_summary.json)
(regenerate with `scripts/build_final_benchmark_summary.py`).

## LOAFO: does hardening generalize, or just memorize?

Cross-family hardening trains *with* all three families. To test whether
that training actually transfers to a family a detector has never seen at
all, AEGIS runs **Leave-One-Attack-Family-Out (LOAFO)**: three folds, each
trained on two families' hard positives with the third contributing **zero**
training rows, then scored on one fresh, real, previously-unseen scenario of
that held-out family (`scripts/run_loafo_benchmark.py`,
[`docs/EVALUATION_RULES.md`](docs/EVALUATION_RULES.md) SS6). Defender v3 is
scored on the identical fresh scenario as a memorization reference.

| Held out | Trained on | LOAFO recall | Defender v3 recall (same scenario) | Verdict |
| --- | --- | --- | --- | --- |
| `adaptive_detector_evasion` | Synthetic + Mule | 75% | 100% | strong |
| `mule_network_structuring` | Synthetic + Adaptive | **0%** | 42% | weak |
| `synthetic_identity_bustout` | Mule + Adaptive | 100% | 100% | strong |

Mean LOAFO recall: **58.3%**. Two of three families transfer well from the
other two; mule-network structuring does not transfer at all in this
benchmark. Generalization is **partial**, not universal -- see
[`docs/CLAIMS_AUDIT.md`](docs/CLAIMS_AUDIT.md) for exactly what is and is
not supported by this result.

## Real API + UI

`src/aegis/api/` (FastAPI) reads persisted artifacts under `models/` and
`data/` and serves them read-only:

```
GET /api/overview            GET /api/evaluation
GET /api/attacks              GET /api/attacks/:id
GET /api/detections/recent    GET /api/evolution
GET /api/hardest-evasions     GET /api/benchmark
```

`web/` (React + Vite) is a seven-screen UI. Every screen except the
interactive Co-Evolution demo now reads real data through
`web/src/api/client.ts`, labeled "Real pipeline data"; the client-side mock
demo (unrelated code, `web/src/mock/`) is kept alongside it and always
labeled "Simulated demo (not real data)" -- the two are never blended
without a label. `/final-benchmark` is the judge-facing summary: v1 vs v2
vs v3, recall by family, LOAFO results, hardest surviving attacks. See
[`docs/UI_DESIGN_SYSTEM.md`](docs/UI_DESIGN_SYSTEM.md).

## How to run locally

```bash
# 1. Python environment
python -m pip install -e ".[dev,api]"

# 2. PaySim data (see "PaySim setup" above) -- one-time, produces
#    data/processed/paysim/<run-id>/{train,validation,test}.jsonl
python scripts/prepare_paysim.py data/raw/paysim/<your-file>.csv --seed 20260101

# 3. Reproduce the defender progression (each writes to its own models/<version>/,
#    never overwriting a prior one) -- optional if you only want the UI, since
#    everything in this repo's own data/reports/final_benchmark_summary.json
#    was already produced by this exact sequence
python scripts/train_baseline_detector.py data/processed/paysim/<run-id> --seed 20260101 --low-memory
python scripts/harden_defender.py data/processed/paysim/<run-id> --low-memory
python scripts/harden_defender_crossfamily.py data/processed/paysim/<run-id> --low-memory
python scripts/run_loafo_benchmark.py data/processed/paysim/<run-id>
python scripts/build_final_benchmark_summary.py

# 4. API (terminal 1)
uvicorn aegis.api.app:app --reload --port 8000

# 5. UI (terminal 2)
cd web && npm install && npm run dev
```

Opens at `http://localhost:5173`; the dev server proxies `/api/*` to
`http://localhost:8000` with no CORS setup needed. See
[`web/README.md`](web/README.md).

```bash
python -m pytest        # or: make test / make check (lint + typecheck + test)
```

## Deployment notes

The live demo does **not** require the multi-GB PaySim CSV or a retraining
step -- it needs only the already-trained `models/` artifacts and
`data/reports/final_benchmark_summary.json`, served read-only by the API
behind a static frontend. Full plan, environment variables, and a
no-backend fallback path: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Limitations

* Not a claim of universal fraud detection. See
  [`docs/CLAIMS_AUDIT.md`](docs/CLAIMS_AUDIT.md) for the full audit of what
  is and is not supported.
* LOAFO's fresh evaluations are one real scenario per family (3-12 fraud
  events) -- directional evidence, not a statistically powered estimate.
  Mule-network structuring generalized weakly (0% LOAFO recall) even where
  the other two families generalized strongly.
* No production latency SLA is claimed; reported latency is mean/p50/p95
  scoring time over a fixed sample on one machine, not a load-tested figure.
* Multi-round self-play (retrain -> fresh Red generation -> retrain,
  repeated) beyond the sequence already run is not implemented.
* Cross-workstream boundaries in [`AGENTS.md`](AGENTS.md) remain binding:
  `identify/`, `generate/`, `loop/` are Red-owned; `defend/`, `features/`
  are Blue-owned; `shared/` is jointly owned and frozen; `api/`/`web/` are
  read-only consumers of both.

## Documentation

| Doc | Read it when |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | **Before writing any code.** Ownership and rules. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Understanding module boundaries and the API architecture. |
| [`docs/CONTRACTS.md`](docs/CONTRACTS.md) | Using or changing a shared type. |
| [`docs/EVALUATION_RULES.md`](docs/EVALUATION_RULES.md) | Producing any number. Binding. |
| [`docs/DATA_STRATEGY.md`](docs/DATA_STRATEGY.md) | Touching a dataset. Locked. |
| [`docs/BASELINE_DETECTOR.md`](docs/BASELINE_DETECTOR.md) | The detector, hardening rounds 1-3, and the feature set. |
| [`docs/SYNTHETIC_IDENTITY_BUSTOUT.md`](docs/SYNTHETIC_IDENTITY_BUSTOUT.md), [`docs/MULE_NETWORK_STRUCTURING.md`](docs/MULE_NETWORK_STRUCTURING.md), [`docs/ADAPTIVE_DETECTOR_EVASION.md`](docs/ADAPTIVE_DETECTOR_EVASION.md) | The three Red Team generators, one doc each. |
| [`docs/ADAPTIVE_ATTACK_EVOLUTION.md`](docs/ADAPTIVE_ATTACK_EVOLUTION.md), [`docs/RED_BLUE_CONFRONTATION.md`](docs/RED_BLUE_CONFRONTATION.md) | Adaptive evolution and the confrontation harness. |
| [`docs/UI_DESIGN_SYSTEM.md`](docs/UI_DESIGN_SYSTEM.md) | The UI's screens, real-vs-mock labeling, and visual language. |
| [`docs/DEMO_FLOW.md`](docs/DEMO_FLOW.md) | Running the judge demo. |
| [`docs/CLAIMS_AUDIT.md`](docs/CLAIMS_AUDIT.md) | What this submission does and does not claim. |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Deploying the demo. |
| [`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md) | Final submission steps. |

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

Runtime dependencies are pydantic, numpy, pandas, and xgboost; `fastapi` +
`uvicorn` behind the optional `api` extra. Nothing else, on purpose.

## Non-goals

Exactly three attack families -- do not add a fourth. Multi-round self-play
beyond the sequence already run, SDV/CTGAN, LangGraph, GRPO, cloud
infrastructure, authentication, databases, and Docker remain out of scope.
Cross-workstream boundaries are governed by [`AGENTS.md`](AGENTS.md).
