import { useCallback } from "react";
import { fetchEvolution, fetchExperiments, fetchHardestEvasions } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import type { ExperimentDTO } from "../api/types";
import { AttackFamilySelector } from "../components/attack/AttackFamilySelector";
import { OutcomeBadge } from "../components/lab/ReplayStream";
import { LoopDiagram } from "../components/loop/LoopDiagram";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { HardestEvasionsTable } from "../components/real/HardestEvasionsTable";
import { MockDataBadge } from "../components/real/RealBadge";
import { RealEvolutionTimeline } from "../components/real/RealEvolutionTimeline";
import { Card } from "../components/ui/Card";
import { Details } from "../components/ui/Details";
import { useLoop } from "../state/LoopContext";

/**
 * Evolution: the escape story, told with real numbers.
 *
 * The lead is what got through and whether hardening closed it -- that is the
 * finding. The browser-side mock demo is still here (it is the fallback if
 * the API dies mid-demo) but is collapsed so it cannot be mistaken for, or
 * visually compete with, the real result.
 */

function EscapeSummary({ experiments }: { experiments: ExperimentDTO[] }) {
  // Current-defender counters, not the per-experiment headline: a LOAFO
  // family's headline describes the handicapped fold model, so summing those
  // would report an escape count no deployed defender actually produces.
  const totalEscaped = experiments.reduce(
    (n, e) => n + (e.current_defender?.escaped_count ?? 0),
    0,
  );
  const totalFraud = experiments.reduce((n, e) => n + (e.current_defender?.fraud_count ?? 0), 0);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2.5">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            Fraud attempts
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--color-ink)]">
            {totalFraud}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--color-risk-high-100)] bg-[var(--color-risk-high-100)]/40 p-3 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            Escaped
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--color-risk-high-600)]">
            {totalEscaped}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--color-risk-low-100)] bg-[var(--color-risk-low-100)]/40 p-3 text-center">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            Caught
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--color-risk-low-600)]">
            {totalFraud - totalEscaped}
          </p>
        </div>
      </div>

      <div className="space-y-2.5">
        {experiments.map((e) => (
          <div
            key={e.attack_family}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-semibold text-[var(--color-ink)]">{e.label}</p>
              <div className="flex items-center gap-2 text-[11px] tabular-nums">
                <span className="text-[var(--color-risk-low-600)]">
                  {e.current_defender?.caught_count ?? e.caught_count} caught
                </span>
                <span className="text-[var(--color-ink-faint)]">·</span>
                <span className="text-[var(--color-risk-high-600)]">
                  {e.current_defender?.escaped_count ?? e.escaped_count} escaped
                </span>
                <span className="text-[var(--color-ink-faint)]">by v3</span>
              </div>
            </div>

            <div className="mt-2 space-y-1.5">
              {e.progression.map((p) => (
                <div key={p.label + p.model_version} className="flex items-center gap-2">
                  <span className="w-32 shrink-0 truncate text-[11px] text-[var(--color-ink-muted)] sm:w-44">
                    {p.label}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--color-border)]">
                    <div
                      className="h-full rounded-full bg-[var(--color-risk-low-600)]"
                      style={{ width: `${Math.max(1, p.recall * 100)}%` }}
                    />
                  </div>
                  <span className="w-16 shrink-0 text-right text-[11px] font-semibold tabular-nums text-[var(--color-ink)]">
                    {(p.recall * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>

            {e.hardest_survivor && (
              <div className="mt-2.5 flex flex-wrap items-center gap-2 border-t border-[var(--color-border)] pt-2">
                <OutcomeBadge caught={false} />
                <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-[var(--color-ink-muted)]">
                  {e.hardest_survivor.transaction_id}
                </span>
                <span className="text-[11px] font-semibold tabular-nums text-[var(--color-ink)]">
                  {(e.hardest_survivor.detector_risk_score * 100).toFixed(1)}% risk
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function CoEvolutionPage() {
  const { family, setFamily, rounds, runNextRound, latest } = useLoop();

  const evolutionFetch = useCallback((s: AbortSignal) => fetchEvolution(s), []);
  const experimentsFetch = useCallback((s: AbortSignal) => fetchExperiments(s), []);
  const hardestFetch = useCallback((s: AbortSignal) => fetchHardestEvasions(25, s), []);

  const evolution = useApiResource(evolutionFetch, []);
  const experiments = useApiResource(experimentsFetch, [], (d) => d.experiments.length === 0);
  const hardest = useApiResource(hardestFetch, [], (d) => d.evasions.length === 0);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-[var(--color-ink)] sm:text-2xl">Evolution</h1>
        <p className="text-xs text-[var(--color-ink-muted)]">
          What escaped, and whether hardening closed it.
        </p>
      </header>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">Escape story</h2>
        <ApiStateSection
          state={experiments}
          emptyTitle="No experiments yet"
          emptyBody="No persisted confrontation or LOAFO artifacts found."
          render={(data) => <EscapeSummary experiments={data.experiments} />}
        />
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">Closed-loop timeline</h2>
        <ApiStateSection
          state={evolution}
          emptyTitle="No closed-loop artifacts yet"
          emptyBody="Run the pipeline scripts to populate this timeline."
          render={(data) => <RealEvolutionTimeline evolution={data} />}
        />
      </Card>

      <Card padded={false}>
        <h2 className="px-5 pt-5 text-sm font-semibold text-[var(--color-ink)]">
          Hardest surviving attacks
        </h2>
        <div className="overflow-x-auto px-5 pb-5 pt-3">
          <ApiStateSection
            state={hardest}
            emptyTitle="No surviving evasions"
            emptyBody="Fills in once a confrontation produces a credible evasion."
            render={(data) => (
              <HardestEvasionsTable
                evasions={data.evasions}
                totalAvailable={data.total_available}
              />
            )}
          />
        </div>
      </Card>

      <Details summary="Interactive browser demo (simulated, not real data)">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <MockDataBadge />
            <button
              type="button"
              onClick={runNextRound}
              disabled={rounds.length >= 6}
              className="rounded-lg bg-[var(--color-accent-600)] px-3 py-1.5 text-xs font-semibold text-white transition-standard hover:bg-[var(--color-accent-500)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {rounds.length === 0
                ? "Run round 0"
                : rounds.length >= 6
                  ? "Demo complete"
                  : `Run round ${rounds.length}`}
            </button>
            {latest && (
              <span className="text-[11px] tabular-nums text-[var(--color-ink-muted)]">
                R{latest.roundIndex} · recall{" "}
                {(latest.evaluation.overall.recall * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <LoopDiagram active={latest ? "retrain" : "identify"} compact />
          <AttackFamilySelector value={family} onChange={setFamily} />
          <p>
            A deterministic client-side toy, kept as a fallback if the API becomes unreachable
            mid-demo. It shares no code and no numbers with the real pipeline above.
          </p>
        </div>
      </Details>
    </div>
  );
}
