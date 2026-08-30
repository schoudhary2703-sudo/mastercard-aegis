# AEGIS — `model-betterment` handoff

**Branch:** `model-betterment` (2 commits ahead of `master`)
**Written:** 2026-08-30 · **Submission deadline:** 2026-08-31
**Status:** 589 passed, 14 skipped, ruff clean. Everything committed.

This document is for whoever picks up the detection-model work next. It covers
what was wrong, what has been fixed, what is half-finished, and what to do with
the time that is left.

---

## 1. Why this branch exists

A review of the Blue Team detector against the challenge's judging criteria
found one problem that outweighs all the others.

**The closed loop currently makes the model worse.** From the shipped
`submission/artifacts/data/reports/final_benchmark_summary.json`:

| Model | F1 | Recall | PR-AUC | Precision | FPR |
|---|---|---|---|---|---|
| baseline_v1 | **0.8568** | **0.7948** | **0.9089** | 0.9294 | 0.00025 |
| defender_v2 | 0.8433 | 0.7708 | 0.9008 | 0.9307 | 0.00024 |
| defender_v3 | 0.8512 | 0.7791 | 0.9036 | **0.9381** | **0.00022** |

After two hardening rounds, v3 is still *below* the untouched baseline on F1,
recall and PR-AUC. The brief says the best solutions "turn their own simulated
attacks into the training ground for a stronger defense" — the artifact
currently demonstrates the opposite, and a judge reading this table will see it.

Two root causes, both now addressed in code:

1. Promotion added **6–22 fraud rows, unweighted**, to a training split holding
   thousands of positives. That is below the noise floor of retraining — the
   observed deltas were variance, not learning.
2. `harden_defender.py` computed a regression report and **never read it**.
   Nothing could decline a bad model.

A second, independent finding: the operating point was throwing away recall.
`tune_threshold_for_f1` settles at 0.9894 → recall 0.779 at FPR 0.0002, while
the same model's own `recall_at_fixed_fpr` shows **0.933 available at FPR
0.005**. F1 is the wrong objective for a 0.42%-positive split; real payment
systems fix a false-positive budget from review capacity and take the most
recall inside it.

---

## 2. What is DONE (committed, tested)

### `3c572bc` — operating point, early stopping, latency

**FPR-budget thresholding** — `src/aegis/defend/metrics.py`
- New `threshold_at_fpr_budget(y_true, scores, budget)`.
- Proved against an independent brute-force sweep; asserted never to breach its
  budget; asserted to recover exactly the recall `recall_at_fpr` reports.
- Now the **pipeline default** (`--threshold-rule fpr_budget`, budget 0.005).
  `--threshold-rule f1` reproduces the frozen v1/v2 fits for like-for-like
  comparison.
- Each run writes `threshold_selection.json` beside the model recording which
  rule produced the threshold.

**Early stopping** — `src/aegis/defend/xgboost_detector.py`
- `eval_metric: aucpr` was declared but `xgb.train` was called with no `evals`,
  so it was never computed and 300 rounds was a fixed guess.
- `fit` now accepts `meta={"eval_set": (X_val, y_val)}`, stops on
  `early_stopping_rounds` (default 30), and persists `best_iteration` so
  `score`/`explain` use the selected trees — not the overfit tail XGBoost keeps.
- `--no-early-stopping` reproduces the old fixed-300-round fits.

**Scoring latency** — same file
- `score()` built a fresh `DMatrix` per call; that fixed overhead dominates
  single-row scoring, which is the shape of a live authorization decision.
- Now `inplace_predict` on a float64 array. Measured on a 21-feature,
  300-round booster: **DMatrix 4.93 ms → DataFrame 3.39 ms → float64 array
  0.86 ms**.
- float64 (not float32) deliberately: the in-memory training path feeds float64
  and a narrowing cast could move a value across a split threshold. Scores are
  **bit-identical** to the DMatrix path, NaN features included — locked by test.

### `7541263` — hard-positive weighting, acceptance gate

**`promoted_sample_weights`** — `src/aegis/defend/hard_positives.py`
- Solves for the weight giving promoted fraud rows a target share of total
  positive gradient mass (default 5%): `w = share·P / (H·(1−share))`.
- A *share*, not a fixed multiplier — stable as the loop scales from 22
  promoted rows to 2,200.
- Clamped at 1.0: promotion can never *reduce* a row's influence.
- Promoted legitimate warm-up rows stay at 1.0 (they exist to give the fraud
  rows realistic account history; they are ordinary negatives).
- Wired through **both** training paths via `meta={"sample_weight": ...}`.

**`src/aegis/defend/acceptance.py`** (new module)
- `evaluate_acceptance(incumbent=, candidate=, criteria=)` → `AcceptanceDecision`
  with per-check evidence and a one-line `summary`.
- Gates **PR-AUC, ROC-AUC, recall@operating-budget**. Tolerance 0.002.
- Deliberately does **not** gate precision/F1/confusion counts — they move with
  the threshold, which legitimately differs between candidate and incumbent, so
  gating them would reward threshold choice over model quality.

---

## 3. What is NOT done — start here

### 3a. Wire the acceptance gate  ✅ DONE

Wired in both `scripts/harden_defender.py` and
`scripts/harden_defender_crossfamily.py`, with 12 tests in
`tests/test_defend_acceptance.py`. Suite is **601 passed, 14 skipped**, ruff clean.

What shipped, and one deviation from the plan below:

* Each run writes `acceptance.json` beside the model and prints the verdict.
* `HardenDefenderResult` / `CrossFamilyHardenResult` expose `.accepted`.
* The CLI **exits non-zero on rejection**, having written every artifact first,
  so a regression cannot ship silently but the rejection stays inspectable.
  `--allow-regression` overrides the exit code without rewriting the verdict —
  it is also what reproduces the historical v1→v2→v3 artifacts.
* `--acceptance-tolerance` and `--operating-fpr-budget` are exposed.

**Deviation — the cross-family gate compares against BOTH v1 and v2.** Gating
only against the generation being replaced is exactly how v3 shipped: run
against the real artifacts, `v3 vs v2` **accepts** (+0.0027 PR-AUC) while
`v3 vs v1` **rejects** (−0.0053 PR-AUC, −0.0067 recall@0.5%). Each round only
ever had to beat the round before it, so the loop drifted below its own
baseline one tolerable step at a time. `.accepted` now requires both.

Verified against the shipped artifacts — this is the evidence for the claim:

| Comparison | Verdict | Why |
|---|---|---|
| v2 vs v1 | **REJECT** | PR-AUC −0.0081, recall@0.5% −0.0057 |
| v3 vs v2 | ACCEPT | all three gated metrics within tolerance |
| v3 vs v1 | **REJECT** | PR-AUC −0.0053, recall@0.5% −0.0067 |

`test_gate_rejects_the_two_regressions_that_actually_shipped` pins this.

<details>
<summary>Original plan, kept for reference</summary>

`acceptance.py` is written and exported but **nothing calls it, and it has no
tests.** This is the single most valuable remaining task: it is what lets you
say "our loop has a gate" instead of "our loop shipped two regressions."

In `scripts/harden_defender.py`, after `_build_regression_report` (~line 205):

```python
from aegis.defend import AcceptanceCriteria, evaluate_acceptance

decision = evaluate_acceptance(
    incumbent=baseline_evaluation,
    candidate=training_result.test_evaluation,
    criteria=AcceptanceCriteria(operating_fpr_budget=0.005),
)
(training_result.artifact_dir / "acceptance.json").write_text(
    json.dumps(decision.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
)
print(decision.summary)
```

Then:
- Add `accepted` / `acceptance` to the returned `HardenDefenderResult`.
- Decide the CLI contract: **recommend** exiting non-zero on rejection so a
  regression cannot silently ship, while still writing every artifact so the
  rejection is inspectable.
- Add tests: accept when metrics improve; reject when PR-AUC drops past
  tolerance; reject when `recall_at_fixed_fpr` lacks the budget key (a missing
  metric fails rather than passes — that is intentional, assert it).

Same wiring belongs in `scripts/harden_defender_crossfamily.py`.

</details>

### 3b. Re-run the pipeline and regenerate the numbers  ⏱ ~2–4 h  🔴 blocking

**None of the committed improvements have been run against real PaySim.** The
repo has no `data/` (gitignored) and no `models/`. Every number in the tables
above is from the *old* artifacts. Until this runs, the submission still shows
the regression.

```bash
python scripts/prepare_paysim.py <paysim.csv> --split-mode temporal
python scripts/train_baseline_detector.py data/processed/paysim/<run> --low-memory
python scripts/harden_defender.py ...          # see scripts/README.md
python scripts/build_final_benchmark_summary.py
```

Expect: recall to jump from ~0.78 toward ~0.93 at the 0.5% budget, and the
v1/v2/v3 table to stop showing a regression. **Verify, do not assume** — if the
numbers disagree with this prediction, report the real ones.

⚠️ The low-memory path was restructured: validation is now materialized
*before* training so it can serve as the `eval_set`. Added resident cost is the
validation DMatrix, ~80 MB for a 955k-row float32 split — fine against the
multi-GB peaks that mode exists to avoid, but worth watching on the 8 GB
machine. `--no-early-stopping` skips building it entirely.

### 3c. Graph features for mule networks  ⏱ ~4 h  🟠 fixes the one "weak" verdict

LOAFO mule recall is **0.0**; even v3, trained on the family, catches 5/12.
This is a *feature* problem. `src/aegis/generate/mule_network.py` builds
explicit `fan_out → layering → fan_in` topology with named graph stages, but
`src/aegis/features/temporal.py` exposes only two **cumulative**
distinct-counterparty scalars. The structure that defines the attack is
invisible to the model.

Add to `_CausalHistoryState` (all computable within the existing
`compute()`-then-`observe()` contract — strictly-prior-only, no leakage):

- **Windowed** in/out degree — the existing ones are cumulative, so a fan-out
  burst looks identical to a year of steady payments
- Amount-in vs amount-out ratio per account (pass-through detection)
- Time between credit and debit — velocity of money, the core mule signal
- Fan-in concentration (Herfindahl/Gini over counterparty amounts)
- 2-hop reachable-account count
- Round-number and reporting-threshold-proximity flags (structuring)

Bump `TemporalBaselineFeatureExtractor.version` and extend `FEATURE_SUFFIXES`.
`tests/test_features_streaming.py` proves the in-memory and streaming paths
agree — keep that green, it is structural, not incidental.

### 3d. Probability calibration  ⏱ ~3 h  🟠 real-world feasibility

`src/aegis/shared/contracts/detector.py:50` documents `risk_score` as
"Calibrated probability of fraud"; `base.py:78` says the same. **Nothing
calibrates.** `scale_pos_weight` (n_neg/n_pos — hundreds, likely >1000 on the
train split) systematically inflates outputs, which is exactly why the
F1-optimal threshold landed at 0.989 instead of near the base rate.

Consequence: `_policy_for_threshold` derives the approve/step-up/review/decline
bands by interpolating 40%/70% into the leftover `[threshold, 1.0]` range.
Monotonic and reproducible, but an arbitrary geometric split — not tied to
expected loss or review capacity, and not readable as probabilities.

Fit isotonic regression on validation scores (PAVA is ~25 lines of numpy — the
project deliberately avoids sklearn, see `AGENTS.md` §5). Then a band means
something a risk team recognises: "decline when P(fraud) > 0.9".

### 3e. Unsupervised second channel  ⏱ ~5 h  🟡 novelty

One supervised model trained on three known families **structurally cannot**
catch a fourth — LOAFO is the proof, not an anomaly. A second unsupervised
channel (anomaly score blended with, or maxed against, the supervised score)
is the standard answer and reads as genuine novelty: a defense whose second
channel exists specifically to cover what the first has never seen.

### 3f. Hyperparameter search  ⏱ background job  🟡

`DEFAULT_HYPERPARAMETERS` is one hand-picked config (`max_depth 5`, `eta 0.05`).
No sweep exists anywhere in the repo. A 20-config random search on validation
PR-AUC would likely beat it and can run unattended.

---

## 4. Two things to fix in the write-up regardless of code

**Statistical power.** The `limitations` block already admits it, but "LOAFO
recall 0.75" is *3 of 4 events*. A judge will discount it. The generators
scale — run the folds over hundreds of fraud events per family and the numbers
become defensible. Add bootstrap CIs on the test metrics while you are there.

**Base-rate shift.** Test fraud rate is 4010/955,744 = **0.42%**, well above
PaySim's corpus rate (~0.13%) — the temporal split concentrates fraud late. So
`scale_pos_weight` (fit on train) and the threshold (tuned on validation) are
both set on distributions that differ from test. Pull the per-split fraud rates
from the prep manifest and state this explicitly rather than letting a judge
find it.

---

## 5. Environment notes

Python 3.14, venv at `.venv/` (gitignored).

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev,api]"
./.venv/Scripts/python.exe -m pip install httpx2
```

⚠️ **Install with `-e`.** A non-editable `pip install ".[api]"` silently
shadows the editable install with a copy in `site-packages`, and your source
edits stop taking effect for anything except pytest (which uses
`pythonpath = ["src", "."]` from `pyproject.toml`). This cost real time — the
symptom is an `AttributeError` for a method you just wrote.

`httpx2` is needed by `starlette.testclient` for the four API test modules; it
is not in `pyproject.toml`. Worth adding to the `dev` extra.

```bash
./.venv/Scripts/python.exe -m pytest tests/ -q      # 589 passed, 14 skipped
./.venv/Scripts/python.exe -m ruff check src/ scripts/ tests/
```

⚠️ The pinned ruff is newer than the one the repo was formatted with, so
`ruff format` on untouched files produces unrelated cosmetic churn. Format only
files you actually edited, or the diff fills with noise. (I reverted eight such
files during this work.)

---

## 6. Suggested order for the remaining time

1. ~~**3a** wire the acceptance gate~~ ✅ done
2. **3b** re-run the pipeline (~2–4 h) — *blocking*; nothing above is real until this runs.
   ⚠️ Requires the PaySim CSV, which is **not in the repo** (`data/` is
   gitignored and empty on a fresh clone). Source: the Kaggle dataset
   "Synthetic Financial Datasets For Fraud Detection", file
   `PS_20174392719_1491204439457_log.csv`, ~470 MB / 6.36M rows. Without it,
   3b cannot start — budget download time before committing to this path.
3. **3c** graph features (~4 h) — only if 3b finishes with room to spare
4. **3d–3f** — write-up material if the code time runs out; they are honest,
   specific "future work" that shows you know where the model's limits are

If time collapses to almost nothing: **do 3a and 3b.** Together they turn "our
loop shipped two regressions" into "our loop has a gate, and here is the
stronger model it accepted" — which is precisely what the judging criteria
reward.
