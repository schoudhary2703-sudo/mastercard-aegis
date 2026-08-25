# web/

The AEGIS demo UI. **Real data throughout.** Overview, Attack Taxonomy,
Attack Studio, Live Detection, Co-Evolution, Evaluation, and Final Benchmark
each carry one or more "Real pipeline data" sections that read live from the
`aegis.api` FastAPI service (`src/api/`); the original interactive mock demo,
driven by `src/mock/`, is kept alongside it on the relevant pages and clearly
labeled "Simulated demo (not real data)". See
[`docs/UI_DESIGN_SYSTEM.md`](../docs/UI_DESIGN_SYSTEM.md) for the design
system, and `docs/ARCHITECTURE.md` ("API architecture") for how `src/api/`
is structured.

## Run it

```bash
# terminal 1, from the repo root -- the API (needs: pip install -e ".[api]")
uvicorn aegis.api.app:app --reload --port 8000

# terminal 2
cd web
npm install
npm run dev
```

Opens at `http://localhost:5173`. The dev server proxies `/api/*` to
`http://localhost:8000` (see `vite.config.ts`), so no CORS setup or
environment variables are needed. If the API isn't running, every real-data
section shows an explicit "Could not reach the AEGIS API" error instead of
silently falling back -- the rest of the app (mock demo, navigation) still
works.

Other commands:

| Command | Does |
| --- | --- |
| `npm run build` | Typecheck (`tsc -b`) + production build to `dist/`. |
| `npm run lint` | `oxlint`. |
| `npm run preview` | Serve the production build locally. |

## What this is

Seven screens: Overview, Attack Studio, Live Detection, **Co-Evolution**
(the hero interaction -- run the loop round over round and watch the
defender harden, in the mock demo), Attack Taxonomy, Evaluation, and
**Final Benchmark** (the judge-facing summary: baseline v1 vs Defender v2 vs
Defender v3, recall by attack family, LOAFO generalization results, and the
hardest surviving attacks). Every page except the pure mock-demo panels now
reads real data through `src/api/client.ts`: the real closed-loop lineage
(Baseline v1 -> Round-0 -> Adaptive Red -> Defender v2 hardening -> fresh
confrontation -> Generation-2), real attack blueprints and confrontation
results, real recent detections, and the final v1/v2/v3/LOAFO benchmark.
`docs/UI_DESIGN_SYSTEM.md` documents what remains mocked and why.

## Rules that still apply

* `web/` must not import `aegis.*` Python packages. It talks to `aegis.api`
  only over HTTP. Types in `src/types/aegis.ts` are a hand-maintained
  mirror of [`docs/CONTRACTS.md`](../docs/CONTRACTS.md) used only by the
  mock demo; `src/api/types.ts` mirrors `src/aegis/api/dto.py` instead and
  is what real-data components use -- keep the two in sync with their
  respective Python sources, never with each other.
* `src/mock/` is not extended with new "real-looking" behavior. The mock
  demo stays exactly what it is -- simulated -- and is labeled as such
  everywhere it appears.
