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

Navigation shows four primary screens -- **Overview** (`/`), **Attack Lab**
(`/attack-lab`), **Evolution** (`/co-evolution`), **Results**
(`/final-benchmark`) -- with the remaining four in a quieter "More" group.
Routes are unchanged; only the nav labels are short.

| Route | Purpose | Real data |
| --- | --- | --- |
| `/` | Overview -- static judge-facing hero, closed-loop diagram, "Where AEGIS fits", then three endpoint-scoped evidence cards. | Yes (+ static explanation) |
| `/attack-lab` | Attack Lab -- one Red-Team / Blue-Team confrontation per family: selector, static attack narrative, GenAI evidence, then the recorded replay. | Yes (no mock) |
| `/attack-studio` | Real attacks for the selected family, plus pick-a-family / generate-a-batch mock demo. | Yes (+ mock demo) |
| `/live-detection` | Real recent detections, plus a standalone mock detection pass. | Yes (+ mock demo) |
| `/co-evolution` | Evolution -- what happened during the loop: verdict, closed-loop timeline, what escaped per family. Mock demo collapsed at the bottom. | Yes (+ mock demo) |
| `/attack-taxonomy` | Real attack blueprints and confrontation results, plus illustrative reference blueprints. | Yes (+ mock demo) |
| `/evaluation` | Real per-model `EvaluationResult`s (v1/v2/v3), plus the latest mock Co-Evolution round's. | Yes (+ mock demo) |
| `/final-benchmark` | Results -- did the hardening generalize: verdict, LOAFO, fresh-scenario family chart, native-test model comparison, hardest survivors, limitations. | Yes (no mock) |

### Attack Lab: one confrontation, in story order

Attack Lab is ordered for a judge reading it cold, not for the data's
convenience: **A** family selector and family context, **B** a static
Red-Team / Blue-Team narrative of how the attack reaches the defender, **C**
GenAI evidence (all three families' coverage first, then the selected
family's own bounded-mutation record), **D** the recorded confrontation
(scenario identity, then the replay), **E** deeper technical evidence behind
`Details`. Raw blueprint parameters, the analyst transcripts and the latest
live chain all live in **E** so they cannot outrank the story.

Scenario identity is the screen's central safety rule. Guided-generation,
replay, and LOAFO evidence are separate *evidence types*. Their persisted
scenario ids may be different or shared depending on the family, so the UI
must display scenario identity explicitly rather than assuming either
relationship. Bust-out's replay is a standalone confrontation artifact whose
scenario differs from both its guided generation and its LOAFO scenario --
they read 1/3, 2/3 and 3/3 respectively -- while the mule and adaptive
replays are read straight out of their LOAFO fold reports and therefore
share that scenario. Every figure is consequently rendered next to its own
`scenario_id`, its evidence type and the model that scored it, and the
guided block notes that guided results are separate persisted scenarios
rather than same-scenario model progression.

Because Attack Lab reads only `/api/experiments` and `/api/genai`, and the
LOAFO comparison's own scenario id lives in `/api/benchmark`, the screen
deliberately does **not** assert whether a given replay is or is not the
LOAFO scenario. Do not re-introduce that claim in either direction without
both ids in hand. The progression card's heading does follow the data: a
held-out fold renders as "Held-out fold vs Defender v3" and states the shared
scenario id, because that comparison really is same-scenario; core defender
generations render as "Recorded hardening snapshots" and say explicitly that
each generation has its own persisted scenario, so they are not automatically
same-scenario model comparisons.

Mutation evidence distinguishes **proposed / applied / rejected**, with each
rejection's reason printed verbatim from the artifact -- reasons differ per
record and must never be paraphrased into a stronger claim about bounds. A
family with no rejected mutation renders no rejection block.

### Evolution vs Results: two questions, no overlap

The two pages are split by question, and neither repeats the other.

**Evolution** answers *what happened during the loop?* Order: a one-line
verdict, the closed-loop timeline (with its "what actually happened"
narrative), then what escaped per family. It states plainly that it is a
record of what the loop did, **not** a claim that each cycle improved the
detector. The LOAFO table, the native-test model comparison and the full
hardest-survivor ranking are deliberately absent here -- Evolution links to
Results for them so each figure is stated once, in the place that interprets
it.

**Results** answers *did the hardening generalize?* Order: verdict ->
LOAFO -> fresh-scenario family chart -> native-test model comparison ->
hardest survivors -> what the benchmark found. LOAFO leads because it is the
actual contribution; the native PaySim table is supporting context, not the
headline. Mean LOAFO recall is never labelled as Defender v3's recall or as a
production fraud-detection rate.

Two scenario-identity facts drive the wording and must not be blurred:

* **LOAFO fold vs Defender v3 is same-scenario.** Each fold report holds
  exactly one fresh scenario and both models were scored on it, so the
  comparison is like-for-like and the UI says so.
* **Per-generation confrontation snapshots are not.** A core-only family
  (bust-out) has one confrontation artifact *per* defender generation, each
  with its own scenario id -- same blueprint, three different scenario
  instances. Those render as "Recorded hardening snapshots" with an explicit
  note that they are not automatically same-scenario model comparisons, and
  must never be drawn as a causal v1 -> v2 -> v3 chart. The native PaySim
  model comparison is a third, separate case: same *split* (one `dataset_id`),
  which is a real guarantee and is stated as such.

Model-comparison honesty is computed, not asserted: the page derives which
generation leads each native-test metric from the DTO and prints it, because
the honest answer is mixed (baseline v1 still leads PR-AUC, recall and F1;
Defender v3 leads precision, FPR and recall @ 0.1% FPR). Hardening changed the
operating trade-off; it did not uniformly improve every metric, and the page
says so before a judge has to ask.

Hardest survivors lead with the top three as cards (family, scenario id, risk,
detector action) with the full ranking behind `Details`. No explanation of
*why* a transaction survived is persisted, so none is shown.

### Overview: cold-start-safe by construction

Overview is the only screen with a hard rule about *when* it renders. Its
hero, its `ClosedLoopFlow` diagram and its "Where AEGIS fits" panel contain
no artifact-derived number, so a judge who opens a cold or unreachable
backend still gets the complete explanation of the system rather than a page
of skeletons. Below them, `/api/landscape`, `/api/genai` and `/api/benchmark`
are fetched as three independent resources with three independent
loading/error states -- a slow or failed landscape read must never hide the
benchmark evidence.

Two claim-safety rules are enforced by the page's structure, not by copy:

* **No cross-scenario aggregate.** Overview never sums caught/escaped counts
  across experiments into a headline recall. Guided generations, selected
  experiment replays and LOAFO folds are separate evidence types whose
  persisted scenario ids may be different or shared depending on the family,
  and they are not all scored by the same model; one number over them is
  confusable with PaySim test recall and with LOAFO mean recall, so every
  figure names the exact evaluation it came from.
* **LOAFO is never labelled as defender recall.** Mean LOAFO recall is
  rendered with a "partial generalization" badge and an explicit line saying
  it is the recall of three fold models on three held-out scenarios, not
  Defender v3's.

`ClosedLoopFlow` carries two orthogonal distinctions visually: **team**
(`--color-attack-*` for Red Team, `--color-defend-*` for Blue Team, per the
attribution rule above) and **reasoning vs. deterministic** (a filled dot on
the two stages where a language model reasons, hollow elsewhere). Its
`compact` variant is the original single-row chip strip, still used inline by
Attack Lab. LOAFO appears beside the loop as a dashed sidecar explicitly
labelled "not a loop stage", because it generates no attacks and proposes no
mutations.

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
