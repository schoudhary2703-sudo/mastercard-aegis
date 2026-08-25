# Deployment

The safest deployment for a judge demo is the one that cannot retrain a
model, cannot touch a real payment system, and cannot fail because a
multi-GB dataset didn't upload. This document describes that deployment
using only what already exists in this repository (`aegis.api`'s
environment variables, `web/vite.config.ts`'s proxy, `npm run build`,
`uvicorn`) -- no Docker file, no provider-specific config, and no cloud
account are assumed, because none exist in this repo today.

## Why this is safe

`src/aegis/api/` and `web/` are **read-only consumers** of persisted
artifacts (`docs/ARCHITECTURE.md`): the API never imports `XGBoostDetector`,
never calls `.fit()` or `.predict()`, and never writes to `models/` or
`data/`. Confirmed by inspection: no `src/aegis/api/*.py` file imports
`XGBoostDetector` or references `model.json`. This means:

* Deploying the API **cannot** retrain, fine-tune, or mutate a model, on
  purpose -- there is no code path that does.
* The API does not need the actual trained model weights (`model.json`,
  ~970KB each) or their feature caches (`features/`, ~700MB **per model** --
  by far the largest thing in `models/`) at all. It only reads small JSON
  reports: `metadata.json`, `evaluation_test.json`,
  `evaluation_validation.json`, `regression_vs_*.json`,
  `codex_handoff.json`/`generation2_handoff.json`, `loafo_fold_report.json`,
  `loafo_summary.json`.
* The API does not need the raw PaySim CSV or the prepared
  `train.jsonl`/`validation.jsonl`/`test.jsonl` splits (`data/processed/`,
  `data/raw/` -- multi-GB) at all.

## Artifact expectations

The API reads everything under one directory, `AEGIS_ARTIFACTS_ROOT`
(`src/aegis/api/settings.py`), defaulting to the repository root. For a
deployment, point it at a **curated bundle** instead of the full working
tree:

```
<artifacts-root>/
  models/
    <model-version>/
      metadata.json
      evaluation_test.json
      evaluation_validation.json
      regression_vs_baseline.json        # Defender v2 only
      regression_vs_v1_v2.json           # Defender v3 only
      generation2_handoff.json           # Defender v2 only
      codex_handoff.json                 # Defender v3 only
      loafo_fold_report.json             # LOAFO fold models only
    loafo_summary.json
  data/
    reports/final_benchmark_summary.json
    synthetic/                           # confrontations, adaptive_rounds,
                                          # mule_confrontations,
                                          # adaptive_evasion_confrontations,
                                          # loafo_evaluations
    hardening/                           # hard_positives.jsonl + provenance.json
```

**Excluded, deliberately:** every `models/*/model.json` (trained weights)
and every `models/*/features/` directory (materialized feature arrays --
in this repo's own run, ~700MB per model, ~4.3GB total across six models).
Neither is read by any API route. Building the curated bundle from this
repo's own real artifacts:

```bash
mkdir -p deploy-artifacts/models deploy-artifacts/data
rsync -a --exclude='model.json' --exclude='features/' models/ deploy-artifacts/models/
rsync -a data/reports data/synthetic data/hardening deploy-artifacts/data/
du -sh deploy-artifacts   # this repo's real bundle: well under 5 MB
```

(No `rsync` on Windows: robocopy or a small Python `shutil.copytree` with
the same exclusions works identically -- the exclusion list, not the tool,
is what matters.)

**Do not require the multi-GB PaySim files for the live demo.** The curated
bundle above never includes `data/raw/`, `data/processed/`, or any
`features/` directory.

**Do not retrain in production.** No deploy step should run
`train_baseline_detector.py`, `harden_defender.py`,
`harden_defender_crossfamily.py`, or `run_loafo_benchmark.py` -- those are
one-time, local, pre-submission steps that already produced the artifacts
in the curated bundle. The deployed API only ever reads.

## Recommended topology

**Frontend and API deployed separately**, exactly as they already run
locally (`web/README.md`):

```
Frontend (static host)  --https-->  API (any host that can run `uvicorn`)
   web/dist/                           aegis.api.app:app, read-only
```

* **Frontend:** `cd web && npm install && npm run build` produces a fully
  static `web/dist/` (`index.html` + hashed assets, `HashRouter` so no
  server-side rewrite rules are needed). Serve it from any static file
  host. Set `VITE_API_BASE_URL` to the deployed API's origin at build time
  (see `web/src/api/config.ts`) so the built bundle calls the right API --
  left unset, it calls relative `/api/...` paths, which only works if the
  same host reverse-proxies `/api` to the API process (that's what the Vite
  dev server's proxy does locally; a static host does not do this for you
  in production).
* **API:** `pip install -e ".[api]"` then
  `uvicorn aegis.api.app:app --host 0.0.0.0 --port <port>` on any host that
  can run a long-lived Python process (a small VM, a container platform, a
  managed Python app host -- whichever your team already has access to;
  this repo does not assume a specific one). Point `AEGIS_ARTIFACTS_ROOT`
  at the curated bundle described above.

## Environment variables

See [`.env.example`](../.env.example) for the complete, current list (the
only variables any code in this repo actually reads). For a deployment:

| Variable | Where | Set to |
| --- | --- | --- |
| `AEGIS_ARTIFACTS_ROOT` | API process | Absolute path to the curated bundle on the API host. |
| `AEGIS_API_CORS_ORIGINS` | API process | The frontend's deployed origin, e.g. `https://your-frontend.example.com`. Comma-separate multiple origins. Omit only for local dev (defaults to the Vite dev server's origin). |
| `VITE_API_BASE_URL` | Frontend build (`web/.env`, read at `npm run build` time, not at runtime) | The API's deployed origin, e.g. `https://your-api.example.com`. Leave unset only if the frontend host reverse-proxies `/api` to the API itself. |

## Start / build commands

```bash
# API host
python -m pip install -e ".[api]"
AEGIS_ARTIFACTS_ROOT=/path/to/deploy-artifacts \
AEGIS_API_CORS_ORIGINS=https://your-frontend.example.com \
  uvicorn aegis.api.app:app --host 0.0.0.0 --port 8000

# Frontend build (run once per deploy, or in CI)
cd web
echo "VITE_API_BASE_URL=https://your-api.example.com" > .env
npm install
npm run build
# upload web/dist/ to your static host
```

## Fallback: local-only demo

If no hosting is available before the judging window, run both processes
locally exactly as in development (`README.md` "How to run locally") and
present from that machine:

```bash
# terminal 1
uvicorn aegis.api.app:app --reload --port 8000
# terminal 2
cd web && npm run dev
```

No environment variables are required for this path -- the Vite dev
server's built-in proxy (`web/vite.config.ts`) forwards `/api/*` to
`http://localhost:8000` and the API's CORS default already allows
`http://localhost:5173`. This is the path used to verify every real number
in this submission (`docs/DEMO_FLOW.md`), so it is guaranteed to work
against this repo's own artifacts.

If even the API cannot run (e.g. `fastapi`/`uvicorn` cannot be installed on
the presentation machine), `web/` still functions: every page's mock demo
section (clearly labeled "Simulated demo") keeps working, and every real
section shows an explicit "Could not reach the AEGIS API" error rather than
a fabricated number -- degrade to walking through
`data/reports/final_benchmark_summary.json` directly, or a screenshot
captured beforehand, rather than presenting a broken real section as if it
were working.

## What is explicitly not covered

Authentication, a database, Docker, and any specific cloud provider's
config format are out of scope for this repo (`AGENTS.md` "Non-goals") and
are not part of this deployment plan. This is a read-only demo surface over
static benchmark artifacts, not a production service.
