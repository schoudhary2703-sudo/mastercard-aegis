# web/

The AEGIS demo UI. **Now integrating real data.** Overview, Co-Evolution and
Evaluation each carry a "Real pipeline data" section that reads live from
the `aegis.api` FastAPI service (`src/api/`); the original interactive
mock demo, driven by `src/mock/`, is kept alongside it and clearly labeled
"Simulated demo (not real data)". See
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

Six screens telling the closed-loop story end to end: Overview, Attack
Studio, Live Detection, **Co-Evolution** (the hero interaction -- run the
loop round over round and watch the defender harden), Attack Taxonomy, and
Evaluation. Overview, Co-Evolution, and Evaluation now also show real
metrics and the real closed-loop lineage (Baseline v1 -> Round-0 -> Adaptive
Red -> Defender v2 hardening -> fresh confrontation -> Generation-2), read
through `src/api/client.ts`. Everything else remains the mock demo;
`docs/UI_DESIGN_SYSTEM.md` documents what is mocked and why.

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
