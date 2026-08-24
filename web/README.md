# web/

The AEGIS demo UI. **Mock-data phase:** every screen is driven by locally
generated fixtures in `src/mock/`. There is no backend, no `api/` call, and
no ML. See [`docs/UI_DESIGN_SYSTEM.md`](../docs/UI_DESIGN_SYSTEM.md) for the
full design-system writeup and the migration path to a real `api/` layer.

## Run it

```bash
cd web
npm install
npm run dev
```

Opens at `http://localhost:5173`. No environment variables, no backend, no
Python install required to view the UI.

Other commands:

| Command | Does |
| --- | --- |
| `npm run build` | Typecheck (`tsc -b`) + production build to `dist/`. |
| `npm run lint` | `oxlint`. |
| `npm run preview` | Serve the production build locally. |

## What this is

Six screens telling the closed-loop story end to end with mock data:
Overview, Attack Studio, Live Detection, **Co-Evolution** (the hero
interaction -- run the loop round over round and watch the defender
harden), Attack Taxonomy, and Evaluation. Nothing here computes a "real"
metric; `docs/UI_DESIGN_SYSTEM.md` documents exactly what is mocked and why.

## Rules that still apply

* `web/` must not import `aegis.*` Python packages. Types in
  `src/types/aegis.ts` are a hand-maintained mirror of
  [`docs/CONTRACTS.md`](../docs/CONTRACTS.md), not a codegen output.
* When a real `api/` layer exists, `web/` becomes a read-only consumer of
  it and computes nothing of its own -- at that point `src/mock/` is
  replaced by fetch calls, not extended.
