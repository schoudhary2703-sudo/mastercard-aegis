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
- [ ] Confirm the default branch judges will see is the one you intend, and
  that it is up to date with whatever branch you've been working on. This
  repository does not have a documented requirement from the challenge brief
  pinning the branch name to `main` -- work has been happening on `master`
  (`git branch --show-current`). Either rename/push to whatever branch name
  your actual submission process expects, or record the branch name
  explicitly in item 9 below; do not assume `main` is required without
  checking the submission instructions you were given.

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

Items 4-6 below are external packaging steps -- a hosted URL, a `.docx`
writeup, and screenshot files -- not code in this repository. All three are
now produced; what remains in each is a final re-check immediately before
submitting. The API and UI they depend on are verified working (item 8).

## 4. Deployed demo URL -- **done, re-verify before submitting**

- [x] Deployed per `docs/DEPLOYMENT.md`. URLs:
  - Frontend: <https://mastercard-aegis.vercel.app>
  - API: <https://mastercard-aegis.onrender.com>
  - Repository: <https://github.com/tensorforgee/mastercard-aegis>
- [x] `GET https://mastercard-aegis.onrender.com/api/health` returns
  `{"status": "ok"}` from outside the dev machine.
- [x] The deployed frontend serves the current judge-facing UI -- verified by
  string-matching the served production bundle for markers from each UI pass
  ("Stress-test fraud models", "Where AEGIS fits", "Leave One Attack Family
  Out", "Recorded hardening snapshots", "LOAFO evaluation evidence").
- [x] Re-verified from a clean production browser session (Milestone 5A):
  Overview, Attack Lab, Evolution and Results all load real data, no error
  state, no console errors, at 1440px and 375px. Production is serving the
  Results y-axis fix (ticks render `0% / 25% / 50% / 75% / 100%`).
  **Re-run once more after any further push.**
- [ ] Note for the demo: the API is on a free tier and cold-starts in roughly
  25 seconds. The Overview hero, closed-loop diagram and "Where AEGIS fits"
  render immediately regardless, but warm the API by loading the site once
  before judges do.

## 5. Walkthrough .docx -- **done**

- [x] Written: [`submission/AEGIS_Judge_Walkthrough.docx`](../submission/AEGIS_Judge_Walkthrough.docx)
  -- 6 pages, US Letter, Calibri, with headers/footers and page numbers.
  Structure: title + headline evidence / how AEGIS works + Overview /
  Red Team + Attack Lab / closed loop in practice + Evolution / Results +
  generalization / real-world fit + limitations. All four final screenshots
  are embedded at full resolution. `docs/JUDGE_DEMO_60S.md` is the condensed
  version if the format wants a short summary alongside it.
- [x] Every number quoted in the document was cross-checked against
  `submission/artifacts/data/reports/final_benchmark_summary.json`,
  `attack_taxonomy.json`, `generation_scale_benchmark.json`,
  `genai_family_summary.json` and `models/loafo_summary.json`, and against
  `docs/CLAIMS_AUDIT.md`'s "Supported claims" / "Claims we must NOT make".
- [x] Exported as `.docx`, then rendered to PDF and every page visually
  inspected: no clipping, no overlapping objects, no broken tables, no
  orphan headings, no unexpected blank pages, hyperlinks render correctly.
- [ ] Confirm `.docx` is the format the submission form actually requires,
  and re-export if it wants PDF instead.

## 6. Screenshots -- **done**

- [x] Four final screenshots captured from the **production** frontend at
  1440px wide, saved under [`submission/screenshots/`](../submission/screenshots):
  `01_overview.png`, `02_attack_lab.png`, `03_evolution.png`,
  `04_results.png`. They self-order in a folder and are embedded in the
  walkthrough `.docx`.
- [x] Captured with the API warm and reachable -- every screenshot shows
  real data, with no loader, error state, empty state, hover overlay or open
  mobile drawer.
- [x] Reviewed individually: no clipped headings, no horizontal overflow,
  no misleading metric context. Mule-network structuring's 0% held-out
  result is visible in `04_results.png` and was deliberately not cropped out.
- [x] Verified against production (Milestone 5A): fresh 1440px captures of
  all four screens are **byte-identical** (SHA-256) to the committed files,
  and all four are embedded unchanged in the walkthrough `.docx`.
  Re-capture only if the UI changes again.

## 7. Demo smoke test

Run this immediately before presenting, on the actual machine/URL you will
present from:

All of the following were performed against **production** during Milestone
5A. Re-run them on the machine/URL you actually present from.

- [x] `GET /api/health` returns `{"status": "ok"}` (plus `benchmark`,
  `genai`, `landscape`, `experiments`, `evolution`, `attacks`, `evaluation`,
  `hardest-evasions`, `detections/recent` -- all HTTP 200).
- [x] `/` (Overview) renders its static hero, closed-loop diagram and
  "Where AEGIS fits" panel **before** any API response arrives -- proven by
  stubbing `/api/*` to never resolve and confirming all static content still
  rendered while the evidence numbers were absent.
- [x] `/` (Overview) then populates all three evidence cards -- 14 / 3 /
  55,000, GenAI 3/3, and Defender v3 (PR-AUC 0.904, recall @ 0.1% FPR 85.2%,
  FPR 0.0216%, LOAFO 58.3% "partial generalization") -- no error or empty
  state, and no generic 58% "Defender recall" anywhere.
- [x] `/co-evolution` shows all six real closed-loop stages as "Real".
- [x] `/attack-lab` shows all three family tabs, the bounded-mutation panel
  (6 proposed / 5 applied / 1 rejected with its verbatim reason), and the
  recorded confrontation's scenario-identity block; "Run replay" streamed
  0/15 -> 15/15 with the loop stage advancing.
- [x] `/final-benchmark` shows the "Partial generalization" verdict, the
  LOAFO table, the family chart with all bars drawn and a full `100%`
  y-axis label, the model comparison, and non-empty hardest-survivor cards.
- [x] `/attack-taxonomy` renders 14 identified / 3 deeply simulated with
  three working "Open in Attack Lab" links into the deep-simulated families.
- [x] Browser console shows no errors on any of the above pages.
- [x] Mock-demo panels still work independently of the API (Co-Evolution's
  "Run round 0" advanced to "Run round 1" and is labelled simulated).

## 8. Final verification summary

Re-run on your final commit before submitting -- this item is not satisfied
by a verification pass on an earlier commit.

Results on the current HEAD (Milestone 5A):

- [x] `pytest` -- full suite passes, exit 0, zero failures.
- [x] `ruff check .` -- "All checks passed!".
- [x] Frontend `tsc -b`, `oxlint`, `npm run build` -- all clean (7 oxlint
  warnings, the long-standing pre-existing set).
- [x] Browser smoke test against **production** (not a dev server) -- see
  item 7.
- [ ] `mypy` -- **does not currently run to completion in this environment**,
  and this is not an AEGIS code defect. `pyproject.toml` pins
  `python_version = "3.10"`, but this `.venv` is Python 3.14.7 with numpy
  2.5.2, whose bundled stubs use PEP 695 `type` statements (3.12+). mypy
  errors inside `numpy/__init__.pyi` and stops before checking any project
  file. Pre-existing and unrelated to the submission materials; it affects
  no deployed behaviour, no evidence artifact and no claim. Resolve by
  running mypy on a Python matching the pinned target, or by bumping
  `python_version` -- **after** submission, since the product is frozen.

## 9. Submission assets / links

Collect in one place before submitting:

- [ ] Repository URL and the exact branch/tag/commit judges should check
  out (this repo has no fixed branch-name requirement -- state whichever one
  you are actually submitting).
- [ ] Deployed demo URL (item 4).
- [ ] Walkthrough `.docx` (item 5).
- [ ] Screenshots (item 6), or the slide deck/folder containing them.
- [ ] This repo's own
  `submission/artifacts/data/reports/final_benchmark_summary.json` (tracked,
  so judges can open it straight from the repository), if the submission
  format accepts a raw-data attachment alongside the narrative documents --
  it is the single source every number in this submission was drawn from.
