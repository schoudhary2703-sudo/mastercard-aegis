import { useCallback, useMemo, useState } from "react";
import { fetchExperiments, fetchGenAI } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import type { ExperimentDTO } from "../api/types";
import { GenAIAnalystPanel } from "../components/genai/GenAIAnalystPanel";
import { OutcomeBadge, ReplayStream } from "../components/lab/ReplayStream";
import { ScoreBoard } from "../components/lab/ScoreBoard";
import { useReplay } from "../components/lab/useReplay";
import { ClosedLoopFlow, type LoopStageId } from "../components/loop/ClosedLoopFlow";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { Card } from "../components/ui/Card";
import { Details } from "../components/ui/Details";

/**
 * Attack Lab: pick a family, replay what really happened to it.
 *
 * The replay is explicitly a RECORDED EXPERIMENT REPLAY and is labeled as
 * such everywhere it appears. Nothing here generates transactions or scores
 * them -- the app has no detector and no simulator. Live generation would
 * mean shipping XGBoost to the browser, which this project deliberately does
 * not do.
 */

const EMPTY: ExperimentDTO[] = [];

function ReplayBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-attack-100)] px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--color-attack-600)]">
      Recorded experiment replay
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
          ? `v3 catches ${experiment.current_defender.caught_count}/${experiment.current_defender.fraud_count}`
          : `${experiment.caught_count}/${experiment.fraud_count} caught`}
      </p>
    </button>
  );
}

export function AttackLabPage() {
  const experimentsFetch = useCallback((s: AbortSignal) => fetchExperiments(s), []);
  const genaiFetch = useCallback((s: AbortSignal) => fetchGenAI(s), []);
  const experiments = useApiResource(experimentsFetch, [], (d) => d.experiments.length === 0);
  const genai = useApiResource(genaiFetch, []);

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

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-[var(--color-ink)] sm:text-2xl">Attack Lab</h1>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Pick an attack family and replay the real experiment against the defender.
        </p>
      </header>

      <ApiStateSection
        state={experiments}
        emptyTitle="No experiments to replay"
        emptyBody="No persisted confrontation or LOAFO artifacts were found under the configured artifacts root."
        render={() =>
          selected && (
            <div className="space-y-4">
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
                  <ReplayBadge />
                </div>

                {selected.parameters.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1">
                    {selected.parameters.slice(0, 8).map((p) => (
                      <span
                        key={p.name}
                        className="rounded bg-[var(--color-surface-sunken)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-ink-muted)]"
                      >
                        {p.name}
                        {p.value != null && `=${String(p.value)}`}
                      </span>
                    ))}
                  </div>
                )}

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
              </Card>

              <div className="-mx-1 overflow-x-auto px-1 pb-1">
                <div className="min-w-[560px]">
                  <ClosedLoopFlow active={activeStage} compact />
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
                <Card>
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

                <div className="space-y-4">
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
                    <h3 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">
                      Defender progression
                    </h3>
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

              <div>
                <h2 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">
                  GenAI reasoning
                </h2>
                <ApiStateSection
                  state={genai}
                  render={(data) => <GenAIAnalystPanel genai={data} />}
                />
              </div>

              <Details summary="Why this is a replay and not a live simulation">
                Generating and scoring a transaction requires the seeded Python simulators and the
                trained XGBoost model — neither runs in a browser, and shipping model weights to
                the client would let the page compute numbers that could drift from the persisted
                artifacts. So every event here was scored by a real detector in a run that already
                happened; the UI only paces the playback. Source:{" "}
                <code>{selected.source_artifacts.join(", ")}</code>.
              </Details>
            </div>
          )
        }
      />
    </div>
  );
}
