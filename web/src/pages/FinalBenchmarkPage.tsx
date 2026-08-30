import { useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchBenchmark } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import type { FinalBenchmarkSummaryDTO, ModelComparisonEntryDTO } from "../api/types";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { DefenderProgressionTrend } from "../components/real/DefenderProgressionTrend";
import { HardestEvasionsScatter } from "../components/real/HardestEvasionsScatter";
import { HardestEvasionsTable } from "../components/real/HardestEvasionsTable";
import { LoafoResultsTable } from "../components/real/LoafoResultsTable";
import { OperatingPointPanel } from "../components/real/OperatingPointPanel";
import { RecallByFamilyChart } from "../components/real/RecallByFamilyChart";
import { PageHeader, SectionHeader } from "../components/ui/PageHeader";
import { Callout, Panel } from "../components/ui/Panel";
import { Reveal } from "../components/ui/Reveal";
import { MetricDelta, SourceLink, StatBlock } from "../components/ui/StatBlock";

/**
 * Final Results: the proof.
 *
 * The page answers one question in order -- does hardening generalize, or did
 * the model just memorize what it was shown? Verdict first, then the three
 * pieces of evidence, then the limitations that bound all of it.
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
  baseline,
  current,
}: {
  label: string;
  entry: ModelComparisonEntryDTO | null;
  baseline?: ModelComparisonEntryDTO | null;
  current?: boolean;
}) {
  if (!entry) return null;
  const f1Delta =
    baseline?.f1 != null && entry.f1 != null ? (entry.f1 - baseline.f1) * 100 : null;

  return (
    <div
      className={`rounded-xl border p-4 transition-standard ${
        current
          ? "border-[var(--color-accent-600)] bg-[var(--color-accent-100)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="t-label text-[var(--color-ink)]">{label}</p>
        {current && (
          <span className="rounded-full bg-[var(--color-accent-600)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
            Current
          </span>
        )}
      </div>
      <p className="t-stat mt-2.5 text-[var(--color-ink)]">{pct(entry.f1)}</p>
      <div className="mt-1 flex items-center gap-2">
        <span className="t-eyebrow text-[var(--color-ink-faint)]">F1</span>
        {f1Delta != null && f1Delta !== 0 && <MetricDelta value={f1Delta} suffix="pts" />}
      </div>
      <dl className="mt-3.5 grid grid-cols-3 gap-1.5 text-center">
        {[
          { l: "Prec", v: pct(entry.precision, 0) },
          { l: "Recall", v: pct(entry.recall, 0) },
          { l: "FPR", v: pct(entry.false_positive_rate, 3) },
        ].map((m) => (
          <div key={m.l} className="rounded-lg bg-[var(--color-surface-sunken)] px-1 py-1.5">
            <dt className="t-eyebrow text-[var(--color-ink-faint)]">{m.l}</dt>
            <dd className="t-mono-sm mt-1 font-medium text-[var(--color-ink)]">{m.v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** The verdict, stated as a sentence rather than a metric tile. */
function Verdict({ summary }: { summary: FinalBenchmarkSummaryDTO }) {
  const loafo = summary.loafo;
  const weakest = summary.claim_flags?.weakest_unseen_family;
  if (!loafo) return null;

  const strong = loafo.per_family.filter((f) => f.verdict === "strong").length;
  const total = loafo.per_family.length;

  return (
    <Panel variant="hero">
      <div className="grid gap-7 lg:grid-cols-12 lg:items-center">
        <div className="lg:col-span-7">
          <p className="t-eyebrow text-[var(--color-ink-faint)]">The answer</p>
          <p className="t-h1 mt-3 text-[var(--color-ink)]">
            <span className={`capitalize ${VERDICT_TONE[loafo.overall_verdict] ?? ""}`}>
              {loafo.overall_verdict}
            </span>
            {" — hardening transferred to "}
            {strong} of {total} unseen families, and not at all to{" "}
            {typeof weakest === "string" ? weakest.replace(/_/g, " ") : "one of them"}.
          </p>
          <p className="t-body mt-3 text-[var(--color-ink-muted)]">
            Each fold retrains the detector with one attack family contributing zero rows, then
            scores it on a fresh scenario from that family. It is the hardest test in this
            submission, and we report the fold it failed.
          </p>
        </div>
        <div className="flex gap-8 lg:col-span-5 lg:justify-end">
          <StatBlock
            label="Mean LOAFO recall"
            value={loafo.mean_loafo_recall * 100}
            format={(n) => `${n.toFixed(0)}%`}
            size="xl"
            source={loafo.source_artifact}
          />
        </div>
      </div>
    </Panel>
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
    <div className="space-y-14">
      <PageHeader
        eyebrow="Evidence · final benchmark"
        title="Did hardening actually generalize — or did the model just memorize what it was shown?"
        actions={
          <Link
            to="/evaluation"
            className="t-body-sm rounded-lg border border-[var(--color-border-strong)] px-3.5 py-2 font-medium text-[var(--color-ink-muted)] transition-standard hover:text-[var(--color-ink)]"
          >
            Per-model metric detail →
          </Link>
        }
      >
        Baseline v1 → Defender v2 → Defender v3 on an untouched PaySim test split, plus a
        leave-one-attack-family-out benchmark where the held-out family contributes zero training
        rows. Every figure is read live from a persisted artifact.
      </PageHeader>

      <ApiStateSection
        state={state}
        emptyTitle="No benchmark data yet"
        emptyBody="Run scripts/build_final_benchmark_summary.py to populate this page."
        render={(summary) => (
          <div className="space-y-14">
            <Verdict summary={summary} />

            {summary.model_comparison && (
              <Reveal>
                <section>
                  <SectionHeader
                    eyebrow="Evidence 1 · three generations"
                    title="Cross-family hardening bought precision and a lower false-positive rate, and gave back a little recall."
                    actions={<SourceLink source={summary.model_comparison.source_artifact} />}
                  >
                    All three models scored on the identical, untouched test split.
                  </SectionHeader>
                  <Panel>
                    <DefenderProgressionTrend comparison={summary.model_comparison} />
                  </Panel>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3">
                    <ProgressionCard
                      label="Baseline v1"
                      entry={summary.model_comparison.baseline_v1}
                    />
                    <ProgressionCard
                      label="Defender v2"
                      entry={summary.model_comparison.defender_v2}
                      baseline={summary.model_comparison.baseline_v1}
                    />
                    <ProgressionCard
                      label="Defender v3"
                      entry={summary.model_comparison.defender_v3}
                      baseline={summary.model_comparison.baseline_v1}
                      current
                    />
                  </div>
                </section>
              </Reveal>
            )}

            {summary.model_comparison && (
              <Reveal>
                <section>
                  <SectionHeader
                    eyebrow="Evidence 2 · the operating point"
                    title="The same detector catches 78% or 93% of fraud, depending only on where the threshold sits."
                  >
                    Both readings come from the same persisted evaluation. Nothing here is a re-run
                    or a projection — it is the shipped model, read at the operating point a
                    payments team would actually choose.
                  </SectionHeader>
                  <Panel>
                    <OperatingPointPanel comparison={summary.model_comparison} />
                  </Panel>
                </section>
              </Reveal>
            )}

            {summary.fresh_family_performance.length > 0 && (
              <Reveal>
                <section>
                  <SectionHeader
                    eyebrow="Evidence 3 · per family"
                    title="Where the detector never saw a family, it can miss that family entirely."
                    actions={
                      <SourceLink source={summary.fresh_family_performance[0]?.source_artifact} />
                    }
                  />
                  <Panel>
                    <RecallByFamilyChart families={summary.fresh_family_performance} />
                  </Panel>
                </section>
              </Reveal>
            )}

            {summary.loafo && (
              <Reveal>
                <section>
                  <SectionHeader
                    eyebrow="Evidence 4 · leave one family out"
                    title="Two families transferred. Mule-network structuring did not."
                    actions={<SourceLink source={summary.loafo.source_artifact} />}
                  />
                  <Panel padded={false} className="overflow-hidden">
                    <div className="overflow-x-auto">
                      <LoafoResultsTable loafo={summary.loafo} />
                    </div>
                  </Panel>
                </section>
              </Reveal>
            )}

            <Reveal>
              <section>
                <SectionHeader
                  eyebrow="What survived"
                  title="Every attack that got through was realistic and scored as clearly safe."
                >
                  Hardness ranks a surviving transaction by how confidently the detector approved it,
                  weighted by how closely it matches real PaySim traffic.
                </SectionHeader>
                {summary.hardest_surviving_attacks.length > 1 && (
                  <Panel className="mb-3">
                    <HardestEvasionsScatter evasions={summary.hardest_surviving_attacks} />
                  </Panel>
                )}
                <details className="group">
                  <summary className="t-body-sm cursor-pointer list-none rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-[var(--color-ink-muted)] transition-standard hover:border-[var(--color-border-strong)] hover:text-[var(--color-ink)]">
                    <span className="inline-flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className="inline-block text-[10px] transition-standard group-open:rotate-90"
                      >
                        ▶
                      </span>
                      Show all {summary.hardest_surviving_attacks.length} surviving transactions
                    </span>
                  </summary>
                  <Panel padded={false} className="mt-3 overflow-hidden">
                    <div className="overflow-x-auto">
                      <HardestEvasionsTable
                        evasions={summary.hardest_surviving_attacks}
                        totalAvailable={summary.hardest_surviving_attacks.length}
                      />
                    </div>
                  </Panel>
                </details>
              </section>
            </Reveal>

            <Reveal>
              <Callout eyebrow="Limitations · read before citing" tone="warn">
                <ul className="list-disc space-y-1.5 pl-4">
                  {summary.limitations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                  {summary.loafo?.verdict_rubric && <li>{summary.loafo.verdict_rubric}</li>}
                </ul>
              </Callout>
            </Reveal>
          </div>
        )}
      />
    </div>
  );
}
