# AGENTS.md

Rules for any Claude / Codex agent working in this repository. **Read this
before writing code.** These rules exist because the Red Team and the Blue Team
are implemented **in parallel, by separate agents**, in the same repo.

---

## 1. Folder ownership

| Path | Owner | May edit |
| --- | --- | --- |
| `src/aegis/shared/**` | **Both, jointly** | Only with explicit cross-team agreement. Frozen by default. |
| `src/aegis/identify/**` | **Red Team** | Red Team only. |
| `src/aegis/generate/**` | **Red Team** | Red Team only. |
| `src/aegis/defend/**` | **Blue Team** | Blue Team only. |
| `src/aegis/features/**` | **Blue Team (lead)** | Blue Team edits; Red Team reads `feature_names`. |
| `src/aegis/evaluate/**` | **Both, jointly** | Needs sign-off from both. Decides what "better" means. |
| `src/aegis/loop/**` | **Integration owner** | Phase 2. Not before both teams have working implementations. |
| `src/aegis/api/**`, `web/**` | **Integration owner** | Phase 3. |
| `tests/**` | Whoever owns the code under test | Add tests beside your module; do not edit another team's tests. |
| `docs/**`, `README.md`, `AGENTS.md` | **Both** | Update when your change makes them wrong. |
| `scripts/**` | Shared | Additive only; do not repurpose an existing script. |
| `data/**` | Nobody | Git-ignored. Never commit data. |

### The rule

**Do not modify a module outside your assigned ownership unless the task
explicitly requires it.** If your task appears to require it:

1. Stop.
2. Say what you would need to change and why.
3. Do not "just add a field" to a shared contract to unblock yourself.

An undeclared cross-team edit is worse than a blocked task: the other agent is
working from the version you silently changed.

## 2. Contracts are frozen

`src/aegis/shared/contracts/` is the interface between two agents who cannot
see each other's work. Changing it changes the ground under someone else.

* Any field added, removed, renamed or retyped requires a `CONTRACT_VERSION`
  bump in `src/aegis/shared/version.py` and both teams' agreement.
* All contracts set `extra="forbid"`. Do **not** relax this to smuggle a field
  through - if you need a field, declare it or use the `metadata` map.
* Need to attach derived features to a transaction? Use
  `Transaction.features` with your namespace (`temporal.*`, `graph.*`).
  **Never add a top-level field for a feature.**
* Need to pass something one-off? Use the `metadata` dict on the relevant
  contract. It is untyped on purpose and nothing may depend on its shape.

## 3. Import direction is the architecture

```
shared/   imports nothing from aegis
identify/ generate/ features/ defend/ evaluate/  ->  shared only
loop/     ->  shared + both teams  (the ONLY package allowed to)
nothing   ->  loop/
```

* `defend/` importing `generate/` is a bug, not a shortcut.
* `generate/` importing `defend/` is a bug and also **cheating** - the only
  feedback channel is `EvasionFeedback`.
* If a task seems to require a forbidden import, the contract is wrong. Raise
  it; do not add the import.

## 4. Leakage rules are binding

Read [`docs/EVALUATION_RULES.md`](docs/EVALUATION_RULES.md) in full before
producing any number. In short:

* A detector never reads `attack_family`, `blueprint_id`, `step_id`,
  `scenario_id`, `is_synthetic`, `generation` or any `AttackBlueprint`.
* Feature extractors use the current row and **strictly earlier** events only.
  Encoders and scalers fit on train only.
* A model is never evaluated on samples just added to its training set.
* Closed-loop evaluation uses attacks generated **after** the retrain, with a
  fresh seed.
* Splits are assigned once, by the harness, by entity and time.

## 5. Scope discipline

* **Exactly three attack families.** Do not add a fourth. Do not add a member
  to `AttackFamily`.
* **No speculative implementation.** If the task says foundation, build
  foundation. Do not add a model "so the tests look better".
* **No fake implementations.** A stub that returns plausible-looking numbers is
  worse than no stub - it will end up in a demo. Test doubles live in
  `tests/conftest.py` and stay trivial.
* **Do not add dependencies casually.** Runtime deps are pydantic, numpy,
  pandas. A new runtime dependency needs a reason in the PR description.
  Library choices (LightGBM vs XGBoost, SDV vs custom) belong to the owning
  workstream and are made at Phase 1, not before.

## 6. Reproducibility

* Every generator run records its `seed` on the `TransactionBatch`.
* Every evaluation records `seed` and `model_version`.
* `GenerationConfig.deterministic=True` means the same seed produces an
  identical batch. If your generator cannot honour that, say so explicitly.
* Never seed from wall-clock time.

## 7. Definition of done

Before you finish a task:

```bash
make check        # ruff + mypy + pytest
make verify       # contract surface smoke check
```

Plus:

* New public behaviour has a test.
* You did not edit a module you do not own.
* You did not change `CONTRACT_VERSION` without saying so prominently.
* You updated the doc your change made wrong.
* Your final report says which files you changed and which rules, if any, you
  had to bend.

## 8. Working style

* Prefer a small, obvious change to a clever one. Two agents have to read this.
* Docstrings say **why**, not what. The signature already says what.
* If you are unsure whether something is your module, it is not.
* If a rule here blocks something genuinely necessary, say so in your report
  rather than working around it quietly.
