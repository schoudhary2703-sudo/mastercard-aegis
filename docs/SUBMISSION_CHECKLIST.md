# Submission checklist

Run through this once, in order, before submitting. Items marked **done**
were verified as part of this hardening pass and should still be true
unless something changed since; re-check anything you touched.

## 1. GitHub repo cleanup

- [x] `.gitignore` excludes `data/` (except `.gitkeep`/`README.md`),
  `models/`, caches, and `.env` -- verified: `git ls-files` shows no file
  under `data/` or `models/` beyond `.gitkeep` placeholders and
  `data/README.md`. Found and fixed during this pass: `data/hardening/`
  and `data/reports/` (added after the original `data/*` ignore patterns
  were written) were untracked but **not yet ignored** -- a real risk that
  a broad `git add -A`/`git add data/` would have committed generated
  hardening/benchmark data. Both are now excluded the same way as
  `data/raw/`, `data/synthetic/`, etc.
- [x] No stray build artifacts tracked (`__pycache__/`, `*.pyc`,
  `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `web/dist/`,
  `web/node_modules/`) -- verified via `git status --short` and
  `git ls-files | grep -iE "__pycache__|\.pyc$"` (empty).
- [ ] Run `git status --short` one final time immediately before
  committing -- confirm nothing unexpected is staged (a stray local
  `.env`, a personal scratch file, an editor swap file).
- [ ] Confirm the default branch judges will see is the one you intend
  (`main` per this repo's convention) and that it is up to date with
  whatever branch you've been working on.

## 2. Secrets scan

- [x] No API keys, tokens, passwords, or private-key material found in
  `src/`, `scripts/`, `web/src/`, or any tracked `.env*` file (checked for
  `api_key`, `secret_key`, `password =`, AWS-style key patterns, PEM
  private-key headers).
- [x] `.env.example` contains only variable *names* and commented-out
  example values, no real credentials -- correct, since none of this
  repo's code requires a credential (no external API keys are read
  anywhere).
- [ ] If you created a real `.env` locally, confirm it is untracked
  (`git check-ignore .env` should print `.env`) before your final commit.
- [ ] If you deploy (`docs/DEPLOYMENT.md`), confirm no deployment
  platform's dashboard-entered secret ever gets committed to this repo
  (it shouldn't need to be -- this repo has no secrets to deploy).

## 3. Final commit / push

- [ ] `make check` (lint + typecheck + test) passes clean on the exact
  commit you intend to submit -- see [Final verification](#7-final-verification-summary) below for the run performed during this pass.
- [ ] `cd web && npm run build` succeeds on the exact commit.
- [ ] Commit message(s) describe what changed, per this repo's normal
  style (see `git log`); avoid a single unreviewed "final" mega-commit if
  you can split it meaningfully.
- [ ] Push to the remote and confirm the pushed commit is what CI (if
  configured) or a fresh `git clone` actually builds and tests clean --
  a local-only pass that never made it to the remote does not count.

## 4. Deployed demo URL -- **pending**

- [ ] Deploy per `docs/DEPLOYMENT.md` (frontend + API, or the local-only
  fallback if no hosting is available) and record the URL here or in your
  submission form.
- [ ] Confirm `GET <api-url>/api/health` returns `{"status": "ok"}` from
  outside your own machine before sharing the URL.
- [ ] Confirm the deployed frontend's `/final-benchmark` page loads real
  data (not an error state) from a clean browser session (no dev-only
  cookies/cache).

## 5. Walkthrough .docx -- **pending**

- [ ] Write the walkthrough document following `docs/DEMO_FLOW.md`'s
  section order (opening, Overview, Attack Taxonomy, Round-0, hardening,
  cross-family results, LOAFO, hardest survivors, Final Benchmark,
  closing).
- [ ] Every number quoted in the document matches
  `data/reports/final_benchmark_summary.json` exactly -- cross-check
  against `docs/CLAIMS_AUDIT.md`'s "Supported claims" section before
  finalizing, and do not restate anything from "Claims we must NOT make."
- [ ] Export/save as `.docx` per the submission's required format.

## 6. Screenshots -- **pending**

- [ ] Capture, at minimum: Overview (real pipeline status card),
  Co-Evolution (real closed-loop timeline including Round-0 and the
  narrative panel), Final Benchmark (model comparison cards, recall-by-family
  chart, LOAFO table, hardest-survivors table).
- [ ] Capture with the API reachable (real data visible, not an error
  state) and at a resolution that keeps text legible.
- [ ] Name files descriptively (e.g. `01-overview.png`,
  `02-coevolution-round0.png`, `03-final-benchmark.png`) so they self-order
  in a folder or slide deck.

## 7. Demo smoke test

Run this immediately before presenting, on the actual machine/URL you will
present from:

- [ ] `GET /api/health` returns `{"status": "ok"}`.
- [ ] `/` (Overview) loads with a populated "Real pipeline status" card,
  not an error or empty state.
- [ ] `/co-evolution` shows all six real closed-loop stages as "Real", not
  "Not run".
- [ ] `/final-benchmark` shows the model comparison table, the
  recall-by-family chart, the LOAFO table, and a non-empty hardest-survivors
  table.
- [ ] Click through to one real attack blueprint on `/attack-taxonomy` and
  confirm its confrontation results render.
- [ ] Open the browser console and confirm no errors on any of the above
  pages.
- [ ] Confirm the mock-demo panels (Co-Evolution's "Run round" button,
  Attack Studio's "Generate batch") still work independently of the API,
  as a fallback if the live API becomes unreachable mid-demo.

## 8. Final verification summary

Verification performed as part of this hardening pass (see the report
below for exact commands and results): full `pytest`, `ruff check .`,
strict `mypy`, frontend `tsc -b`, `oxlint`, `npm run build`, and a browser
smoke test against a live API + dev server. Re-run all of these on your
final commit before submitting -- this checklist item is not satisfied by
a verification pass on an earlier commit.

## 9. Submission assets / links

Collect in one place before submitting:

- [ ] Repository URL (and branch/tag, if not `main`).
- [ ] Deployed demo URL (item 4).
- [ ] Walkthrough `.docx` (item 5).
- [ ] Screenshots (item 6), or the slide deck/folder containing them.
- [ ] This repo's own `data/reports/final_benchmark_summary.json`, if the
  submission format accepts a raw-data attachment alongside the narrative
  documents -- it is the single source every number in this submission was
  drawn from.
