import { useCallback, useMemo, useState } from "react";
import { fetchExperiments, fetchGenAI, fetchLandscape } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import type { ExperimentDTO, GenAIGuidedGenerationDTO, GenAIResponseDTO } from "../api/types";
import { GenAIAnalystPanel } from "../components/genai/GenAIAnalystPanel";
import { AttackRecommendations } from "../components/genai/AttackRecommendations";
import { GenAIFamilyCoverage } from "../components/genai/GenAIFamilyCoverage";
import { LiveGenAIEvidence } from "../components/genai/LiveGenAIEvidence";
import { OutcomeBadge, ReplayStream } from "../components/lab/ReplayStream";
import { ScoreBoard } from "../components/lab/ScoreBoard";
import { useReplay } from "../components/lab/useReplay";
import { ClosedLoopFlow, type LoopStageId } from "../components/loop/ClosedLoopFlow";
import { FraudLandscape } from "../components/landscape/FraudLandscape";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { RealDataBadge } from "../components/real/RealBadge";
import { Card } from "../components/ui/Card";
import { Details } from "../components/ui/Details";

/**
 * Attack Lab: one Red-Team / Blue-Team confrontation, told in order.
 *
 * Story order is deliberate and judge-first:
 *   A. which family                  (selector)
 *   B. how AEGIS attacks             (static Red -> Blue narrative)
 *   C. GenAI evidence                (all three families, then this one)
 *   D. the recorded confrontation    (scenario identity, then replay)
 *   E. deeper technical evidence     (progressive disclosure)
 *
 * Scenario identity is labelled, never assumed. Guided-generation, replay and
 * LOAFO evidence *may* use different persisted scenarios, and sometimes use the
 * same one: bust-out's replay is a standalone confrontation artifact, while the
 * mule and adaptive replays are read straight out of their LOAFO fold reports.
 * So this screen states each scenario's own `scenario_id`, evidence type and
 * scoring model rather than claiming any blanket relationship between them --
 * bust-out legitimately reads 1/3, 2/3 and 3/3 across guided, replay and LOAFO,
 * and an unlabelled juxtaposition would look like a model progression that
 * never happened.
 *
 * This page fetches `/api/experiments` and `/api/genai` only. The LOAFO
 * comparison's own scenario id lives in `/api/benchmark`, which is not read
 * here -- so the copy below deliberately does not assert whether a given replay
 * is or is not the LOAFO scenario. Do not re-introduce that claim without both
 * ids in hand.
 *
 * The replay is a RECORDED EXPERIMENT REPLAY throughout. Nothing here
 * generates transactions or scores them -- the app ships no simulator and no
 * detector.
 */

const EMPTY: ExperimentDTO[] = [];

/** Roles that mean "this row is a core defender generation", not a fold model. */
const CORE_ROLES = new Set(["baseline_v1", "defender_v2", "defender_v3"]);

function pct(value: number | null | undefined): string {
  return typeof value === "number" ? `${(value * 100).toFixed(0)}%` : "—";
}

function num(value: number | null | undefined, digits = 2): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

function ReplayBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-attack-100)] px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--color-attack-600)]">
      Recorded confrontation
    </span>
  );
}

function FamilyTab({
  experiment,
  active,
  onSelect,
}: {
  experiment: ExperimentDTO;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={`flex-1 rounded-lg border px-3 py-2.5 text-left transition-standard ${
        active
          ? "border-[var(--color-accent-500)] bg-[var(--color-accent-100)] shadow-[var(--shadow-card)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-strong)]"
      }`}
    >
      <p
        className={`text-xs font-semibold leading-tight ${
          active ? "text-[var(--color-accent-600)]" : "text-[var(--color-ink)]"
        }`}
      >
        {experiment.label}
      </p>
      <p className="mt-1 text-[11px] tabular-nums text-[var(--color-ink-faint)]">
        {experiment.current_defender
          ? `Defender v3: ${experiment.current_defender.caught_count}/${experiment.current_defender.fraud_count} caught`
          : `${experiment.caught_count}/${experiment.fraud_count} caught`}
      </p>
    </button>
  );
}

/**
 * B. How AEGIS attacks the defender.
 *
 * Static, two-sided, and deliberately shorter than Overview's eight-stage
 * diagram -- this is orientation for the confrontation below it, not a second
 * copy of the architecture explanation.
 */
function ConfrontationNarrative() {
  const red = [
    "GenAI Attack Analyst reasons about the family",
    "→ structured attack blueprint",
    "→ deterministic simulator",
    "→ synthetic attack scenario",
  ];
  const blue = [
    "Defender v3 scores every transaction",
    "→ risk scores",
    "→ caught / escaped",
    "→ escaped transactions become blind-spot evidence",
  ];
  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-[var(--color-ink)]">
          How AEGIS attacks the defender
        </h2>
        <span className="rounded-full bg-[var(--color-surface-sunken)] px-2.5 py-0.5 text-[10px] font-semibold text-[var(--color-ink-muted)]">
          Transaction rows written by GenAI: <strong className="text-[var(--color-ink)]">0</strong>
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <div className="rounded-lg border border-[var(--color-attack-100)] bg-[var(--color-attack-100)]/50 p-3">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--color-attack-600)]">
            Red Team
          </p>
          <ol className="mt-1.5 space-y-0.5">
            {red.map((line) => (
              <li key={line} className="text-[11px] leading-snug text-[var(--color-ink-muted)]">
                {line}
              </li>
            ))}
          </ol>
        </div>
        <div className="rounded-lg border border-[var(--color-defend-100)] bg-[var(--color-defend-100)]/60 p-3">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--color-defend-600)]">
            Blue Team
          </p>
          <ol className="mt-1.5 space-y-0.5">
            {blue.map((line) => (
              <li key={line} className="text-[11px] leading-snug text-[var(--color-ink-muted)]">
                {line}
              </li>
            ))}
          </ol>
        </div>
      </div>

      <p className="mt-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-3 py-2 text-[11px] leading-snug text-[var(--color-ink-muted)]">
        <strong className="text-[var(--color-ink)]">Then the loop closes.</strong> The GenAI
        Blind-Spot Analyst reads those escaped transactions and returns a{" "}
        <strong className="text-[var(--color-ink)]">bounded mutation proposal</strong>; deterministic
        code bounds-checks it, applies what is in range, and the simulator &mdash; not the model
        &mdash; generates the next seeded scenario.
      </p>
    </Card>
  );
}

/**
 * C (second half). The selected family's own guided generation.
 *
 * Looked up by the DTO's explicit `attack_family`, never inferred from an id
 * or from ordering. Rendered only when that family actually has one, and the
 * rejection reason is printed verbatim from the artifact -- the reasons differ
 * per record and none of them may be paraphrased into a stronger claim.
 */
function BoundedMutationPanel({
  guided,
  familyLabel,
}: {
  guided: GenAIGuidedGenerationDTO;
  familyLabel: string;
}) {
  const applied = guided.applied_mutations;
  const rejected = guided.rejected_mutations;
  const proposed = applied.length + rejected.length;

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="flex flex-wrap items-center justify-between gap-2 bg-[var(--color-surface-sunken)] px-3 py-2">
        <span className="text-[10px] font-bold uppercase tracking-wide text-[var(--color-attack-600)]">
          Bounded mutation &mdash; {familyLabel}
        </span>
        <span className="text-[10px] tabular-nums text-[var(--color-ink-muted)]">
          <strong className="text-[var(--color-ink)]">{proposed}</strong> proposed ·{" "}
          <strong className="text-[var(--color-risk-low-600)]">{applied.length}</strong> applied ·{" "}
          <strong
            className={
              rejected.length > 0
                ? "text-[var(--color-risk-high-600)]"
                : "text-[var(--color-ink-faint)]"
            }
          >
            {rejected.length}
          </strong>{" "}
          rejected
        </span>
      </div>

      <p className="border-t border-[var(--color-border)] px-3 py-1.5 text-[10px] leading-snug text-[var(--color-ink-faint)]">
        Proposed by the Blind-Spot Analyst from this family&rsquo;s real detector failures.
        Deterministic validation decides what is applied &mdash; out-of-range proposals are
        rejected, never clamped.
      </p>

      {applied.length > 0 && (
        <div className="border-t border-[var(--color-border)] px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-risk-low-600)]">
            Applied
          </p>
          <ul className="mt-1 space-y-0.5">
            {applied.map((m) => (
              <li key={m.parameter} className="font-mono text-[11px] text-[var(--color-ink)]">
                {m.parameter} {num(m.from_value)} &rarr; {num(m.to_value)}
                <span className="ml-1.5 font-sans text-[10px] text-[var(--color-ink-faint)]">
                  {m.direction}
                  {typeof m.magnitude === "number" && ` · magnitude ${m.magnitude}`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {rejected.length > 0 && (
        <div className="border-t border-[var(--color-border)] bg-[var(--color-risk-high-100)]/40 px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-risk-high-600)]">
            Rejected by the deterministic bounds check
          </p>
          <ul className="mt-1 space-y-0.5">
            {rejected.map((m) => (
              <li key={m.parameter} className="text-[11px] leading-snug text-[var(--color-ink)]">
                <span className="font-mono">{m.parameter}</span>
                <span className="text-[var(--color-ink-faint)]">
                  {" "}
                  ({m.direction}
                  {typeof m.magnitude === "number" && `, magnitude ${m.magnitude}`})
                </span>{" "}
                &mdash;{" "}
                <span className="text-[var(--color-risk-high-600)]">
                  rejected: {m.reason}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-t border-[var(--color-border)] px-3 py-2 text-[11px] tabular-nums text-[var(--color-ink-muted)]">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Resulting scenario
        </span>
        <span className="break-all font-mono text-[var(--color-ink)]">
          {guided.scenario_id ?? "—"}
        </span>
        <span>
          <span className="font-semibold text-[var(--color-risk-low-600)]">
            {guided.caught_count} caught
          </span>
          {" · "}
          <span className="font-semibold text-[var(--color-risk-high-600)]">
            {guided.escaped_count} escaped
          </span>
          {" · recall "}
          {pct(guided.recall)}
          {" · fidelity "}
          {num(guided.fidelity_score)}
        </span>
        {guided.detector_model_version && (
          <span className="font-mono text-[10px] text-[var(--color-ink-faint)]">
            scored by {guided.detector_model_version}
          </span>
        )}
      </div>
    </div>
  );
}

/** C. GenAI evidence: all three families first, then this family's own run. */
function GenAIEvidenceSection({
  data,
  selected,
}: {
  data: GenAIResponseDTO;
  selected: ExperimentDTO;
}) {
  // Explicit field on the DTO -- not inferred from scenario-id shape or order.
  const guidedForFamily =
    data.guided_generations.find((g) => g.attack_family === selected.attack_family) ?? null;

  return (
    <Card>
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-[var(--color-ink)]">
          GenAI evidence across all three families
        </h2>
        <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
          All 3 deeply simulated families have persisted live GenAI evidence.
        </p>
      </div>

      <div className="space-y-2.5">
        {data.family_coverage && <GenAIFamilyCoverage coverage={data.family_coverage} />}

        <p className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-3 py-2 text-[11px] leading-snug text-[var(--color-ink-muted)]">
          Guided-generation results are separate persisted scenarios. They are evidence of the
          GenAI loop, not same-scenario model progression. Guided-generation, replay, and LOAFO
          evidence may use different persisted scenarios &mdash; AEGIS labels scenario identity
          explicitly rather than assuming they are the same.
        </p>

        {guidedForFamily ? (
          <BoundedMutationPanel guided={guidedForFamily} familyLabel={selected.label} />
        ) : (
          <p className="text-[11px] text-[var(--color-ink-faint)]">
            No guided generation persisted for {selected.label}.
          </p>
        )}
      </div>
    </Card>
  );
}

export function AttackLabPage() {
  const experimentsFetch = useCallback((s: AbortSignal) => fetchExperiments(s), []);
  const genaiFetch = useCallback((s: AbortSignal) => fetchGenAI(s), []);
  const experiments = useApiResource(experimentsFetch, [], (d) => d.experiments.length === 0);
  const genai = useApiResource(genaiFetch, []);
  const landscapeFetch = useCallback((s: AbortSignal) => fetchLandscape(s), []);
  const landscape = useApiResource(landscapeFetch, []);

  const [selectedFamily, setSelectedFamily] = useState<string | null>(null);

  // Memoized so the array identity is stable across renders -- `selected`
  // feeds useReplay, which resets the stream whenever the experiment changes.
  const list = useMemo(
    () => (experiments.status === "ready" ? experiments.data.experiments : EMPTY),
    [experiments],
  );
  const selected = useMemo(
    () => list.find((e) => e.attack_family === selectedFamily) ?? list[0] ?? null,
    [list, selectedFamily],
  );

  const replay = useReplay(selected);

  const activeStage: LoopStageId | undefined = replay.running
    ? "defender"
    : replay.finished
      ? "outcome"
      : undefined;

  // These two cases are NOT the same kind of comparison, and conflating them
  // would manufacture a causal chart that the artifacts do not support:
  //
  //  * A LOAFO family (mule, adaptive) has one fold report holding exactly one
  //    fresh scenario, and both the fold model and Defender v3 were scored on
  //    it. Same-scenario, and `loafo_summary.json`'s methodology says so.
  //  * A core-only family (bust-out) has one confrontation artifact *per
  //    defender generation*, each with its own scenario id
  //    (bustout-...-20260101 / -20260825 / -20260901). Same blueprint, three
  //    different scenario instances -- a recorded history, not a same-scenario
  //    progression.
  const progressionIsCoreOnly =
    selected?.progression.every((p) => CORE_ROLES.has(p.role)) ?? true;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-[var(--color-ink)] sm:text-2xl">Attack Lab</h1>
        <p className="text-xs text-[var(--color-ink-muted)]">
          One Red-Team / Blue-Team confrontation per attack family, replayed from persisted
          evidence.
        </p>
      </header>

      <ApiStateSection
        state={experiments}
        emptyTitle="No experiments to replay"
        emptyBody="No persisted confrontation or LOAFO artifacts were found under the configured artifacts root."
        render={() =>
          selected && (
            <div className="space-y-4">
              {/* ---- A. family selector ---- */}
              <div className="flex flex-col gap-2 sm:flex-row">
                {list.map((e) => (
                  <FamilyTab
                    key={e.attack_family}
                    experiment={e}
                    active={e.attack_family === selected.attack_family}
                    onSelect={() => setSelectedFamily(e.attack_family)}
                  />
                ))}
              </div>

              <Card>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-[var(--color-ink)]">
                      {selected.attack_name}
                    </h2>
                    <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                      {selected.headline}
                    </p>
                    <p className="mt-1 text-xs text-[var(--color-attack-600)]">
                      {selected.genai_angle}
                    </p>
                  </div>
                </div>
              </Card>

              {/* ---- B. how AEGIS attacks ---- */}
              <ConfrontationNarrative />

              {/* ---- C. GenAI evidence ---- */}
              <ApiStateSection
                state={genai}
                emptyTitle="No GenAI runs yet"
                emptyBody="Run scripts/run_genai_analysis.py to produce a reasoning artifact."
                render={(data) => <GenAIEvidenceSection data={data} selected={selected} />}
              />

              {/* ---- D. the recorded confrontation ---- */}
              <Card>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-[var(--color-ink)]">
                      The recorded confrontation
                    </h2>
                    <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                      What was tried, what {selected.replayed_model_label} did, and what survived.
                    </p>
                  </div>
                  <ReplayBadge />
                </div>

                <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-3 py-2.5 sm:grid-cols-2">
                  {[
                    { k: "Scenario id", v: selected.scenario_id, mono: true },
                    { k: "Evidence type", v: "Recorded experiment replay", mono: false },
                    { k: "Scored by", v: selected.model_version, mono: true },
                    {
                      k: "Outcome",
                      v: `${selected.caught_count} caught · ${selected.escaped_count} escaped of ${selected.fraud_count} fraud events`,
                      mono: false,
                    },
                  ].map((row) => (
                    <div key={row.k} className="min-w-0">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
                        {row.k}
                      </dt>
                      <dd
                        className={`break-all text-[11px] text-[var(--color-ink)] ${
                          row.mono ? "font-mono" : "tabular-nums"
                        }`}
                      >
                        {row.v}
                      </dd>
                    </div>
                  ))}
                </dl>

                <p className="mt-2 text-[11px] leading-snug text-[var(--color-ink-faint)]">
                  Guided-generation, replay, and LOAFO evidence may use different persisted
                  scenarios. AEGIS labels scenario identity explicitly rather than assuming they
                  are the same. With {selected.fraud_count} fraud event
                  {selected.fraud_count === 1 ? "" : "s"}, this result is directional, not a
                  statistically powered estimate.
                </p>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={replay.running ? replay.stop : replay.start}
                    disabled={selected.events.length === 0}
                    className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-semibold text-white transition-standard hover:bg-[var(--color-accent-500)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {replay.running ? "Pause" : replay.started ? "Replay again" : "Run replay"}
                  </button>
                  <button
                    type="button"
                    onClick={replay.showAll}
                    disabled={selected.events.length === 0}
                    className="rounded-lg border border-[var(--color-border-strong)] px-3 py-2 text-sm font-medium text-[var(--color-ink-muted)] transition-standard hover:text-[var(--color-ink)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Show all
                  </button>
                  <span className="text-[11px] tabular-nums text-[var(--color-ink-faint)]">
                    {replay.counters.revealed}/{replay.counters.totalEvents} events
                  </span>
                  {selected.replayed_model_label && (
                    <span className="text-[11px] text-[var(--color-ink-muted)]">
                      vs <strong>{selected.replayed_model_label}</strong>
                    </span>
                  )}
                </div>

                <div className="-mx-1 mt-3 overflow-x-auto px-1 pb-1">
                  <div className="min-w-[560px]">
                    <ClosedLoopFlow active={activeStage} compact />
                  </div>
                </div>
              </Card>

              {/* `min-w-0` on both tracks: a grid item defaults to
                  `min-width: auto`, so a long unbreakable transaction id inside
                  either card widens the whole track and pushes the page into
                  horizontal scroll at 375px. */}
              <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
                <Card className="min-w-0">
                  <div className="mb-3">
                    <ScoreBoard counters={replay.counters} />
                  </div>
                  <ReplayStream events={replay.revealed} />
                  {!selected.events_complete && selected.events_note && (
                    <p className="mt-2 rounded-lg bg-[var(--color-surface-sunken)] px-2.5 py-1.5 text-[11px] text-[var(--color-ink-muted)]">
                      Partial stream — {selected.events_note}
                    </p>
                  )}
                </Card>

                <div className="min-w-0 space-y-4">
                  <Card>
                    <h3 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">
                      Hardest survivor
                    </h3>
                    {selected.hardest_survivor ? (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <p className="min-w-0 truncate font-mono text-[11px] text-[var(--color-ink-muted)]">
                            {selected.hardest_survivor.transaction_id}
                          </p>
                          <OutcomeBadge caught={false} />
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            {
                              l: "Risk",
                              v: `${(selected.hardest_survivor.detector_risk_score * 100).toFixed(1)}%`,
                            },
                            {
                              l: "Fidelity",
                              v:
                                selected.hardest_survivor.fidelity_score != null
                                  ? `${(selected.hardest_survivor.fidelity_score * 100).toFixed(0)}%`
                                  : "—",
                            },
                            {
                              l: "Hardness",
                              v: selected.hardest_survivor.hardness_score?.toFixed(3) ?? "—",
                            },
                          ].map((m) => (
                            <div
                              key={m.l}
                              className="rounded-lg bg-[var(--color-surface-sunken)] px-2 py-1.5 text-center"
                            >
                              <p className="text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)]">
                                {m.l}
                              </p>
                              <p className="text-sm font-bold tabular-nums text-[var(--color-ink)]">
                                {m.v}
                              </p>
                            </div>
                          ))}
                        </div>
                        <p className="font-mono text-[10px] text-[var(--color-ink-faint)]">
                          {selected.hardest_survivor.detector_model_version}
                        </p>
                      </div>
                    ) : (
                      <p className="text-xs text-[var(--color-ink-muted)]">
                        Nothing survived this experiment.
                      </p>
                    )}
                  </Card>

                  <Card>
                    <h3 className="text-sm font-semibold text-[var(--color-ink)]">
                      {progressionIsCoreOnly
                        ? "Recorded hardening snapshots"
                        : "Held-out fold vs Defender v3"}
                    </h3>
                    <p className="mb-2 mt-0.5 text-[11px] leading-snug text-[var(--color-ink-faint)]">
                      {progressionIsCoreOnly ? (
                        <>
                          One confrontation was recorded per defender generation against the same
                          blueprint, each with its own persisted scenario. These document the
                          system&rsquo;s evolution &mdash; they are not automatically
                          same-scenario model comparisons.
                        </>
                      ) : (
                        <>
                          Both rows were scored on this same fresh scenario (
                          <span className="break-all font-mono">{selected.scenario_id}</span>).
                        </>
                      )}
                    </p>
                    <div className="space-y-2">
                      {selected.progression.map((p) => (
                        <div key={p.label + p.model_version}>
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="truncate text-xs text-[var(--color-ink)]">
                              {p.label}
                            </span>
                            <span className="shrink-0 text-xs font-bold tabular-nums text-[var(--color-ink)]">
                              {p.caught_count}/{p.fraud_count}
                            </span>
                          </div>
                          <div className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--color-border)]">
                            <div
                              className="h-full rounded-full bg-[var(--color-risk-low-600)]"
                              style={{ width: `${Math.max(1, p.recall * 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                </div>
              </div>

              {/* ---- E. deeper technical evidence ---- */}
              <div className="space-y-2">
                <h2 className="text-sm font-semibold text-[var(--color-ink)]">
                  Deeper technical evidence
                </h2>

                {selected.parameters.length > 0 && (
                  <Details summary={`Blueprint parameters (${selected.parameters.length})`}>
                    <div className="flex flex-wrap gap-1">
                      {selected.parameters.map((p) => (
                        <span
                          key={p.name}
                          className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-ink-muted)]"
                        >
                          {p.name}
                          {p.value != null && `=${String(p.value)}`}
                        </span>
                      ))}
                    </div>
                  </Details>
                )}

                <ApiStateSection
                  state={genai}
                  render={(data) => (
                    <div className="space-y-2">
                      <Details summary="Latest live GenAI chain (most recent run on disk, any family)">
                        <div className="space-y-2">
                          <p className="text-[11px] leading-snug text-[var(--color-ink-faint)]">
                            <strong className="text-[var(--color-ink)]">
                              LATEST LIVE GENAI CHAIN
                            </strong>{" "}
                            &mdash; the most recent persisted live reasoning chain across all
                            families
                            {data.latest_guided_generation?.attack_family
                              ? `, currently ${data.latest_guided_generation.attack_family}`
                              : ""}
                            . It is not filtered to the family selected above and is not the
                            replayed scenario.
                          </p>
                          <LiveGenAIEvidence genai={data} />
                        </div>
                      </Details>

                      {data.attack_recommendations && (
                        <Details summary="Attack Analyst recommendations vs the blueprint's declared bounds">
                          <AttackRecommendations preview={data.attack_recommendations} />
                        </Details>
                      )}

                      <Details summary="Full analyst reasoning (Attack Analyst + Blind-Spot Analyst)">
                        <GenAIAnalystPanel genai={data} />
                      </Details>
                    </div>
                  )}
                />

                <Details summary="Why this is a replay and not a live simulation">
                  Generating and scoring a transaction requires the seeded Python simulators and
                  the trained XGBoost model — neither runs in a browser, and shipping model weights
                  to the client would let the page compute numbers that could drift from the
                  persisted artifacts. So every event here was scored by a real detector in a run
                  that already happened; the UI only paces the playback. Source:{" "}
                  <code>{selected.source_artifacts.join(", ")}</code>.
                </Details>
              </div>
            </div>
          )
        }
      />

      {/* --- Fidelity: the criterion this step exists to argue -------------
          Moved here from Identify, which was arguing attack *diversity* and
          had grown to nearly four screens carrying evidence for a criterion
          it does not own. */}
      <section className="border-t border-[var(--color-border)] pt-8">
        <h2 className="t-h1 text-[var(--color-ink)]">Is the generated traffic realistic?</h2>
        <p className="t-body-sm mb-4 mt-1 max-w-2xl text-[var(--color-ink-muted)]">
          One generation-only benchmark run &mdash; no scoring, no fitting, no retraining &mdash;
          and the fidelity decomposition behind it.
        </p>

        <div className="space-y-4">
          <div>
            <div className="mb-2.5 flex items-center justify-between gap-3">
              <h3 className="t-eyebrow text-[var(--color-ink-faint)]">Generation at scale</h3>
              <RealDataBadge />
            </div>
            <Card>
              <ApiStateSection
                state={landscape}
                emptyTitle="No scale benchmark yet"
                emptyBody="Run scripts/run_generation_scale_benchmark.py."
                render={(data) => <FraudLandscape landscape={data} section="scale" />}
              />
            </Card>
          </div>

          {/* The scale panel above already carries each family's headline
              fidelity score. This is the component decomposition behind it --
              real evidence, but a deep dive, so it opens on demand rather
              than adding a screen of tables to the default view. */}
          <Details summary="Fidelity breakdown — distributional, behavioural and structural components">
            <ApiStateSection
              state={landscape}
              emptyTitle="No fidelity breakdown yet"
              emptyBody="Run scripts/run_generation_scale_benchmark.py."
              render={(data) => <FraudLandscape landscape={data} section="fidelity" />}
            />
          </Details>
        </div>
      </section>
    </div>
  );
}
