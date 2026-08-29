# The GenAI reasoning layer

AEGIS uses a large language model for **reasoning**, at exactly two points in
the closed loop, and for nothing else. This document says where those two
points are, what the model is and is not allowed to produce, and how to run
each stage.

## Where GenAI sits

```
   research / fraud taxonomy
             |
             v
   [ GenAI: ATTACK ANALYST ]            <- reasoning
             |
             v
   structured attack blueprint / parameters
             |
             v
   deterministic constrained simulator  <- numbers  (aegis.generate)
             |
             v
   XGBoost defender                     <- numbers  (aegis.defend)
             |
             v
   evasion + fidelity feedback          <- numbers  (aegis.evaluate)
             |
             v
   [ GenAI: BLIND-SPOT ANALYST ]        <- reasoning
             |
             v
   bounded mutation proposal
             |
             v
   next simulation  (back to the simulator)
```

The two GenAI stages **bracket** the deterministic core. They never replace
any part of it.

### Stage 1 — Attack Analyst

Turns researched fraud-taxonomy material into an executable, structured
attack hypothesis.

| | |
| --- | --- |
| **Input** | Researched taxonomy scenario, payment context, known constraints, the simulator parameters that actually exist |
| **Output** | Attack family, attack hypothesis, how GenAI enables/amplifies the fraud, payment-system assumptions, observable signals, recommended simulator parameters, realism risks, safety constraints, confidence |
| **Code** | `aegis.genai.analysts.run_attack_analyst`, schema `AttackAnalystResponse` |

### Stage 2 — Blind-Spot Analyst

Reads a real detector's real failures and proposes bounded next-generation
attacks.

| | |
| --- | --- |
| **Input** | Blueprint id and family, detector version and threshold, missed/caught counts, the risk scores actually assigned, detector-visible signals, fidelity score, the parameters the blueprint declares mutable |
| **Output** | Blind-spot hypothesis, evidence, bounded mutation proposals, expected trade-offs, safety constraints, confidence |
| **Code** | `aegis.genai.analysts.run_blind_spot_analyst`, schema `BlindSpotAnalystResponse` |

Every input to this stage is read out of an artifact a previous pipeline run
already wrote. The stage never re-scores anything and never sees model
internals beyond the detector-visible signals the Blue Team already published.

## Why the numeric simulator stays deterministic

The critical design rule: **GenAI never generates transaction rows.**

Three reasons this is not negotiable here:

1. **Reproducibility.** Every generated corpus in this repo is reproducible
   from a seed (`AGENTS.md` §6, `GenerationConfig.deterministic`). A sampled
   language-model output is not, so a corpus containing model-authored rows
   could never be regenerated to check a number.
2. **Fidelity is a gate, not a vibe.** An evasion achieved with implausible
   traffic is discarded as a bug rather than counted as a finding
   (`docs/EVALUATION_RULES.md`). The simulators enforce
   `RealismConstraints` structurally; a free-text generator cannot.
3. **Leakage control.** The simulator's parameter surface is a declared,
   bounded set (`ParameterSpec`, with `mutable=False` for structural knobs).
   Reasoning that proposes *values* stays inside that surface by
   construction.

This is enforced, not just documented:

* `AttackAnalystResponse` returns `SimulatorParameterProposal` objects —
  name/value/rationale — and rejects parameter names that look like
  transaction payloads.
* `BoundedMutationProposal.magnitude` is capped at
  `MAX_MUTATION_MAGNITUDE` (0.25, matching the top of the deterministic
  optimizer's own step schedule), with at most `MAX_MUTATION_PROPOSALS` per
  run.
* `enforce_mutation_bounds` rejects — never clamps — any proposal naming a
  parameter the blueprint did not declare mutable. Silently shrinking an
  out-of-bounds request would let the model steer the search space while
  looking compliant on disk.
* Every response model inherits `extra="forbid"`, so an undeclared field is
  a validation error rather than a side channel.

## How GenAI closes the loop

The blind-spot stage is what makes this a loop rather than a pipeline. Real
detector failures — which transactions were missed, at what risk scores,
against which signals — are fed back as reasoning input, and the result is a
*bounded proposal* for the next generation of attacks. The deterministic
optimizer in `aegis.loop` remains the thing that applies mutations; the GenAI
proposal is advisory input to it, subject to the same `mutable_parameters`
check the optimizer applies to its own proposals.

## Configuration

| Variable | Meaning |
| --- | --- |
| `ANTHROPIC_API_KEY` | Required for live runs. Never commit it. |
| `AEGIS_GENAI_PROVIDER` | `anthropic` (default) or `recorded`. |
| `AEGIS_GENAI_MODEL` | Override the model id (default `claude-opus-5`). |

Install the optional extra:

```bash
python -m pip install -e ".[genai]"
```

**If no API key is present, the layer fails loudly.** There is no fallback
that produces default reasoning text. The only offline path is
`--provider recorded`, which replays a previously persisted run artifact and
stamps it `live: false` — so a replay can never be mistaken for a fresh model
call in the artifact record.

## Running a stage

Analyze one taxonomy scenario (Attack Analyst):

```bash
python scripts/run_genai_analysis.py attack-analyst --scenario synthetic-identity-bustout
```

Analyze one real persisted evasion (Blind-Spot Analyst):

```bash
python scripts/run_genai_analysis.py blind-spot --confrontation-dir submission/artifacts/data/synthetic/confrontations/confrontation-416e606888de1ffa
```

The same input path accepts mule-network and adaptive-evasion confrontation
directories because all three persist the common blueprint, confrontation and
hardest-evasion evidence needed by the request builder. Inspect either request
without building a provider or spending API credits:

```bash
python scripts/run_genai_analysis.py blind-spot \
  --confrontation-dir data/synthetic/mule_confrontations/<run-id> \
  --request-only
python scripts/run_genai_analysis.py blind-spot \
  --confrontation-dir data/synthetic/adaptive_evasion_confrontations/<run-id> \
  --request-only
```

Omit `--request-only` only when a human explicitly wants a live analysis. No
live mule or adaptive artifact is included or implied by this input support.

Run the judge-window path using the already-persisted live bust-out artifact,
hash-bound train-only reference statistics and frozen Defender v3:

```bash
python scripts/run_fast_genai_guided_demo.py
```

This path still validates mutation bounds and freshness. Base PaySim rows are
proven disjoint by their frozen `paysim-` ID namespace and absence of scenario
IDs; the 67 additional Defender v3 training rows are checked by exact persisted
transaction/scenario membership. It does not call a GenAI provider or retrain.

Replay a prior run with no network or key:

```bash
python scripts/run_genai_analysis.py --provider recorded --recorded-artifact data/genai/attack_analyst/<run-id>.json attack-analyst --scenario synthetic-identity-bustout
```

Neither subcommand trains, retrains, or re-scores anything.

## Artifacts

Every run — success *or* failure — is written to
`data/genai/<stage>/<run_id>.json`:

```json
{
  "run_id": "attack_analyst-<hash>",
  "stage": "attack_analyst",
  "created_at": "...",
  "provenance": {
    "provider": "anthropic",
    "model": "claude-opus-5",
    "prompt_version": "genai-prompts-v1",
    "live": true,
    "request_id": "req_...",
    "latency_ms": 4210.3,
    "attempts": 1,
    "source_artifacts": ["taxonomy:synthetic-identity-bustout"]
  },
  "request": { "...": "the exact input" },
  "response": { "...": "the validated structured output" },
  "schema_valid": true,
  "failure": null,
  "raw_response_text": null
}
```

A failed run keeps `response: null`, `schema_valid: false`, a populated
`failure`, and the raw text that failed to validate — so a stage that did not
work leaves visible evidence rather than an absent file that could be read as
"not run yet". `run_id` is derived from the request plus prompt version and
model, so re-running the same analysis with the same instrument is idempotent
on disk, and changing either the prompt version or the model produces a
distinct artifact.

## What we claim, and what we do not

Supported:

> GenAI performs attack ideation, blueprint reasoning, and detector
> blind-spot analysis. Deterministic simulators generate reproducible
> synthetic transactions, and XGBoost performs detection.

Not claimed:

* GenAI directly generated transaction rows — it does not; the simulators do.
* GenAI automatically discovers unlimited attacks — the family scope is fixed
  at three, and proposals are bounded per run.
* Production-grade autonomous fraud optimization — this is a bounded research
  loop over synthetic data, not an autonomous system.
