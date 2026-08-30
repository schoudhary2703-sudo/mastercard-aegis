import { useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchEvolution, fetchExperiments } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { PageHeader } from "../components/ui/PageHeader";
import type { ExperimentDTO } from "../api/types";
import { OutcomeBadge } from "../components/lab/ReplayStream";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { RealEvolutionTimeline } from "../components/real/RealEvolutionTimeline";
import { Card } from "../components/ui/Card";
import { Callout } from "../components/ui/Panel";

/**
 * Evolve (step 4): the escape story, told with real numbers.
 *
 * The lead is what got through and whether hardening closed it -- that is the
 * finding, and it is the whole page now.
 *
 * Two things were removed. The browser-side mock demo moved to /sandbox: a
 * collapsed toy on an evidence page is still a toy on an evidence page. And
 * the "Hardest surviving attacks" table moved to Results, where it belongs --
 * it was rendering a *different* row set here (the recent-evasions endpoint)
 * under the same heading as the benchmark table on Results, so a reader
 * comparing the two screens found two tables with one name and no overlap.
 * One table, one owner, one source.
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
  const evolutionFetch = useCallback((s: AbortSignal) => fetchEvolution(s), []);
  const experimentsFetch = useCallback((s: AbortSignal) => fetchExperiments(s), []);

  const evolution = useApiResource(evolutionFetch, []);
  const experiments = useApiResource(experimentsFetch, [], (d) => d.experiments.length === 0);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Step 4 · Evolve"
        title="What escaped the detector, and whether the next generation closed the gap."
      >
        Each round promotes the transactions that evaded scoring into training data, retrains, and
        re-runs the confrontation on a fresh scenario.
      </PageHeader>

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

      <Callout eyebrow="What escaped, in full">
        <p>
          Every fraudulent transaction that survived a confrontation — ranked by hardness, with its
          risk score, fidelity and the model that approved it — is tabulated once, on{" "}
          <Link
            to="/final-benchmark"
            className="font-semibold text-[var(--color-accent-500)] hover:underline"
          >
            Results
          </Link>
          , alongside the benchmark it came from.
        </p>
      </Callout>
    </div>
  );
}
