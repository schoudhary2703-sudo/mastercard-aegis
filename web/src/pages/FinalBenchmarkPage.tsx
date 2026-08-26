import { useCallback } from "react";
import { fetchBenchmark } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import type { FinalBenchmarkSummaryDTO, ModelComparisonEntryDTO } from "../api/types";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { HardestEvasionsTable } from "../components/real/HardestEvasionsTable";
import { LoafoResultsTable } from "../components/real/LoafoResultsTable";
import { RecallByFamilyChart } from "../components/real/RecallByFamilyChart";
import { Card } from "../components/ui/Card";
import { Details } from "../components/ui/Details";

/**
 * Final Results, condensed to the four things a judge needs: the v1→v2→v3
 * progression, per-family recall, LOAFO, and the hardest survivor.
 *
 * The interpretation prose and limitations list that used to sit inline are
 * now behind <Details>. Nothing is removed -- it is one click away, and the
 * limitations still come from the API rather than the component.
 */

const VERDICT_TONE: Record<string, string> = {
  strong: "text-[var(--color-risk-low-600)]",
  partial: "text-[var(--color-risk-medium-600)]",
  weak: "text-[var(--color-risk-high-600)]",
};

function pct(value: number | null | undefined, digits = 1): string {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function ProgressionCard({
  label,
  entry,
  current,
}: {
  label: string;
  entry: ModelComparisonEntryDTO | null;
  current?: boolean;
}) {
  if (!entry) return null;
  return (
    <div
      className={`rounded-xl border p-3 sm:p-4 ${
        current
          ? "border-[var(--color-accent-500)] bg-[var(--color-accent-100)]/40"
          : "border-[var(--color-border)] bg-[var(--color-surface)]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-[var(--color-ink)]">{label}</p>
        {current && (
          <span className="rounded-full bg-[var(--color-accent-600)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
            Current
          </span>
        )}
      </div>
      <p className="mt-2 text-2xl font-bold tabular-nums text-[var(--color-ink)]">
        {pct(entry.f1)}
      </p>
      <p className="text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)]">F1</p>
      <dl className="mt-2 grid grid-cols-3 gap-1.5 text-center">
        {[
          { l: "Prec", v: pct(entry.precision, 0) },
          { l: "Recall", v: pct(entry.recall, 0) },
          { l: "FPR", v: pct(entry.false_positive_rate, 3) },
        ].map((m) => (
          <div key={m.l} className="rounded bg-[var(--color-surface-sunken)] px-1 py-1">
            <dt className="text-[10px] uppercase text-[var(--color-ink-faint)]">{m.l}</dt>
            <dd className="text-xs font-semibold tabular-nums text-[var(--color-ink)]">{m.v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Headline({ summary }: { summary: FinalBenchmarkSummaryDTO }) {
  const loafo = summary.loafo;
  const weakest = summary.claim_flags?.weakest_unseen_family;
  if (!loafo) return null;
  return (
    <div className="grid gap-2.5 sm:grid-cols-3">
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-center">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Mean LOAFO recall
        </p>
        <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--color-ink)]">
          {pct(loafo.mean_loafo_recall, 0)}
        </p>
      </div>
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-center">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Generalization
        </p>
        <p
          className={`mt-1 text-2xl font-bold capitalize ${
            VERDICT_TONE[loafo.overall_verdict] ?? "text-[var(--color-ink)]"
          }`}
        >
          {loafo.overall_verdict}
        </p>
      </div>
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-center">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Weakest unseen family
        </p>
        <p className="mt-1 text-xs font-semibold text-[var(--color-risk-high-600)]">
          {typeof weakest === "string" ? weakest.replace(/_/g, " ") : "—"}
        </p>
      </div>
    </div>
  );
}

export function FinalBenchmarkPage() {
  const benchmarkFetch = useCallback((s: AbortSignal) => fetchBenchmark(s), []);
  const state = useApiResource(
    benchmarkFetch,
    [],
    (d) => !d.model_comparison && !d.loafo && d.fresh_family_performance.length === 0,
  );

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-[var(--color-ink)] sm:text-2xl">Final Results</h1>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Every figure read live from persisted benchmark artifacts.
        </p>
      </header>

      <ApiStateSection
        state={state}
        emptyTitle="No benchmark data yet"
        emptyBody="Run scripts/build_final_benchmark_summary.py to populate this page."
        render={(summary) => (
          <div className="space-y-5">
            <Headline summary={summary} />

            {summary.model_comparison && (
              <section>
                <h2 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">
                  Defender progression
                </h2>
                <div className="grid gap-2.5 sm:grid-cols-3">
                  <ProgressionCard
                    label="Baseline v1"
                    entry={summary.model_comparison.baseline_v1}
                  />
                  <ProgressionCard
                    label="Defender v2"
                    entry={summary.model_comparison.defender_v2}
                  />
                  <ProgressionCard
                    label="Defender v3"
                    entry={summary.model_comparison.defender_v3}
                    current
                  />
                </div>
              </section>
            )}

            {summary.fresh_family_performance.length > 0 && (
              <section>
                <h2 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">
                  Recall by attack family
                </h2>
                <Card>
                  <RecallByFamilyChart families={summary.fresh_family_performance} />
                </Card>
              </section>
            )}

            {summary.loafo && (
              <section>
                <h2 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">
                  LOAFO — held-out family
                </h2>
                <Card padded={false} className="overflow-hidden">
                  <div className="overflow-x-auto">
                    <LoafoResultsTable loafo={summary.loafo} />
                  </div>
                </Card>
              </section>
            )}

            <section>
              <h2 className="mb-2 text-sm font-semibold text-[var(--color-ink)]">
                Hardest surviving attacks
              </h2>
              <Card padded={false} className="overflow-hidden">
                <div className="overflow-x-auto">
                  <HardestEvasionsTable
                    evasions={summary.hardest_surviving_attacks}
                    totalAvailable={summary.hardest_surviving_attacks.length}
                  />
                </div>
              </Card>
            </section>

            <Details summary="Interpretation and limitations">
              <ul className="list-disc space-y-1 pl-4">
                {summary.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
                {summary.loafo?.verdict_rubric && <li>{summary.loafo.verdict_rubric}</li>}
              </ul>
            </Details>
          </div>
        )}
      />
    </div>
  );
}
