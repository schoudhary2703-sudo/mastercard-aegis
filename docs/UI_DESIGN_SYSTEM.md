# UI Design System

Scope: `web/` only. This document describes the mock-data demo frontend built
for judge presentation. It does not describe, and must not be read as
specifying, any backend, detector, generator, or API behaviour.

## Status

**Real data + mock demo, side by side.** A real `api/` layer now exists
(`src/aegis/api/`, FastAPI) and `web/src/api/` is a typed client for it.
Every page except the pure interactive demo now shows one or more sections
computed server-side from persisted pipeline artifacts, each labeled
"Real pipeline data"; the original client-side mock (`web/src/mock/`,
described in [Mock data policy](#mock-data-policy) below) is kept alongside
it where it still adds value (an interactive, no-backend-required walk
through one closed-loop round) and is always labeled "Simulated demo (not
real data)". A page never blends the two without a label.

## Stack

* Vite + React + TypeScript -- one dev command, no server-rendering
  complexity the demo does not need.
* Tailwind CSS v4 (via `@tailwindcss/vite`) -- design tokens as CSS
  variables in `src/index.css`, utility classes for layout.
* `react-router-dom` (`HashRouter`) -- hash-based routing so the built
  `dist/` works from a static file server or `vite preview` with no
  rewrite rules to configure. Demo reliability over URL purity.
* `recharts` -- the only charting dependency, used for the two real charts
  (round-over-round metrics trend).
* No global state library. A single `LoopProvider` (React context +
  reducer, `src/state/LoopContext.tsx`) holds the Co-Evolution round
  history; everything else is local component state.

## Visual language

* **Neutrals carry the page.** Slate/white surfaces, one border color, one
  muted-text color. Color is reserved for meaning, not decoration.
* **Navy shell.** The sidebar uses a dark navy scale (`--color-navy-*`) to
  read as security-platform chrome, distinct from body content.
* **One interactive accent** (`--color-accent-*`, blue) for buttons, links,
  focus rings.
* **Attack vs. defend** (`--color-attack-*` amber, `--color-defend-*` blue)
  -- used *only* to attribute something to the Red Team or Blue Team side
  of the loop (blueprint badges, loop-diagram stage fill). Never used for
  risk.
* **Risk traffic-light** (`--color-risk-low/medium/high-*` -- green / amber
  / red) -- used *only* for transaction- or detector-level risk state
  (`RiskBar`, `RiskBadge`, `ActionBadge`, confusion-matrix cells). Never
  used for team attribution.

Keeping those two color languages disjoint is deliberate: a judge should be
able to tell at a glance whether a color means "this is the attacker's"
or "this transaction is risky" without reading the label.

* **Type.** System sans stack (no web font fetch -- offline-safe for a
  demo room with no internet). One weight scale: semibold headings, medium
  body, tabular-nums on every metric so columns of numbers align.
* **Motion.** A single 160ms ease transition class (`.transition-standard`)
  used for hover/active state changes only. No looping or decorative
  animation, no skeleton shimmer beyond a plain pulse.

## Screens

| Route | Purpose | Real data |
| --- | --- | --- |
| `/` | Overview -- real pipeline status, loop diagram, session stats, links into every screen. | Yes (+ mock demo) |
| `/attack-studio` | Real attacks for the selected family, plus pick-a-family / generate-a-batch mock demo. | Yes (+ mock demo) |
| `/live-detection` | Real recent detections, plus a standalone mock detection pass. | Yes (+ mock demo) |
| `/co-evolution` | Real closed-loop lineage and hardest surviving attacks; **hero mock demo** below runs the loop round by round. | Yes (+ mock demo) |
| `/attack-taxonomy` | Real attack blueprints and confrontation results, plus illustrative reference blueprints. | Yes (+ mock demo) |
| `/evaluation` | Real per-model `EvaluationResult`s (v1/v2/v3), plus the latest mock Co-Evolution round's. | Yes (+ mock demo) |
| `/final-benchmark` | v1 vs v2 vs v3 comparison, recall by family, LOAFO results, hardest surviving attacks. | Yes (no mock) |

## Component conventions

* `components/ui/` -- presentation-only primitives (`Card`, `StatTile`,
  `Badge`, `DataTable`, `RiskBar`, `Tabs`, `EmptyState`, `ErrorState`,
  `Skeleton`). No fixture imports here.
* `components/loop/`, `components/attack/`, `components/detect/`,
  `components/evolution/`, `components/evaluation/` -- feature components,
  one concern per file, composed by pages.
* `pages/` -- one file per route. A page wires fixtures/state into
  components; it does not contain markup-heavy JSX of its own beyond
  layout.
* Every card that shows data has three states: loading (`Skeleton`),
  empty (`EmptyState`), and populated. Errors use `ErrorState` (currently
  unreachable since there is no network call to fail, but present for when
  `api/` is wired in).

## Mock data policy

`web/src/types/aegis.ts` hand-mirrors the shapes in
[`docs/CONTRACTS.md`](CONTRACTS.md) -- it is not generated from the Python
package, and `web/` does not import `aegis.*`. `web/src/mock/` contains:

* `blueprints.ts` -- one static `AttackBlueprint` per in-scope family.
* `generateBatch.ts` -- deterministic (seeded) fixture transactions.
* `mockDetector.ts` -- a scoring heuristic standing in for
  `defend/BaseDetector.predict()`, parameterized by a `defenderStrength`
  demo dial. **Not a model.**
* `metrics.ts` -- confusion-matrix and classification-metric arithmetic
  matching `EvaluationResult`'s shape, computed from the mock scores above.
* `loopSimulator.ts` -- advances one round: mutate blueprint from prior
  feedback, generate, score, evaluate, derive feedback.

Now that the real `api/` service layer exists, real data lives beside the
mock rather than replacing it: `src/api/types.ts` and `src/api/client.ts`
are the real wire contract (mirroring `src/aegis/api/dto.py`), consumed only
by components under `src/components/real/`. `src/mock/` and
`src/types/aegis.ts` are untouched and still power the interactive
Co-Evolution/Attack-Studio/Live-Detection demos, each clearly labeled
"Simulated demo (not real data)" wherever it appears. The two type systems
are deliberately not unified -- `src/types/aegis.ts` mirrors the frozen
`aegis.shared.contracts`, `src/api/types.ts` mirrors the API's own DTOs, and
neither should be edited to match the other.

## Known limitations

* Per-attack-family evaluation metrics show `0%` (not "N/A") when a family
  has no positive examples in the current round, since only one family is
  exercised per Co-Evolution run. A real evaluator would report this as
  undefined/absent rather than zero.
* The detector's `recommended_action` thresholds (`approve` / `step_up` /
  `review` / `decline`) and its `predicted_label` threshold are both fixed
  constants in `mockDetector.ts`, not calibrated against the mock scores.
* Charts are static per render; there is no chart interaction (zoom,
  brush) beyond the built-in Recharts tooltip.
