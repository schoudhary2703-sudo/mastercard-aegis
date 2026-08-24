# UI Design System

Scope: `web/` only. This document describes the mock-data demo frontend built
for judge presentation. It does not describe, and must not be read as
specifying, any backend, detector, generator, or API behaviour.

## Status

**Mock foundation.** Every number on screen is computed client-side from
locally generated fixtures (`web/src/mock/`). There is no network call to a
backend. See [Mock data policy](#mock-data-policy) below for why, and what
changes when a real `api/` layer exists.

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

| Route | Purpose |
| --- | --- |
| `/` | Overview -- loop diagram, session stats, links into every screen. |
| `/attack-studio` | Pick a family, inspect its blueprint, generate a batch. |
| `/live-detection` | Standalone detection pass: risk scores, caught vs. evaded. |
| `/co-evolution` | **Hero.** Runs the closed loop round by round with metrics trend and evasion feedback. |
| `/attack-taxonomy` | Reference catalog of the three fixed attack families. |
| `/evaluation` | `EvaluationResult` for the latest Co-Evolution round: overall, per-family, confusion matrix, latency. |

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

When a real `api/` service layer exists, the intended migration is: replace
the contents of `src/mock/` with fetch calls into `api/`, keep
`src/types/aegis.ts` as the wire contract, and delete `defenderStrength` /
the seeded RNG entirely. No page or component should need to change, since
they only consume the typed shapes, never the mock internals.

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
