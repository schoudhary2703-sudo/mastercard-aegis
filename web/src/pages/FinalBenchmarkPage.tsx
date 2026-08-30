import { useCallback } from "react";
import { fetchBenchmark } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import type {
  FinalBenchmarkSummaryDTO,
  HardestEvasionDTO,
  ModelComparisonDTO,
  ModelComparisonEntryDTO,
} from "../api/types";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { BenchmarkInterpretation } from "../components/real/BenchmarkInterpretation";
import { HardestEvasionsTable } from "../components/real/HardestEvasionsTable";
import { LoafoResultsTable } from "../components/real/LoafoResultsTable";
import { ModelComparisonCards } from "../components/real/ModelComparisonCards";
import { RecallByFamilyChart } from "../components/real/RecallByFamilyChart";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../types/aegis";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { Details } from "../components/ui/Details";

/**
 * Results answers one question: *did the hardening generalize?*
 *
 * Order is verdict -> LOAFO -> model comparison -> family results -> hardest
 * survivors -> limitations. LOAFO leads because it is the actual contribution;
 * the native PaySim table is supporting context, not the headline.
 *
 * Two scenario-identity facts drive the wording and must not be blurred:
 *
 *  * **LOAFO fold vs Defender v3 is same-scenario.** Each fold report holds
 *    exactly one fresh scenario and both models were scored on it
 *    (`loafo_summary.json` methodology). Saying so is supported.
 *  * **The v1/v2/v3 comparison is same-split, not same-scenario.** All three
 *    were evaluated on the identical untouched PaySim test split (one
 *    `dataset_id`). That is a different guarantee from the per-family
 *    confrontation snapshots on Evolution, which each have their own scenario.
 */

function pct(value: number | null | undefined, digits = 1): string {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function familyLabel(family: string): string {
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family.replace(/_/g, " ");
}

/**
 * Which generation actually leads each native-test metric.
 *
 * Computed from the DTO rather than asserted, because the honest answer is
 * mixed -- baseline v1 still leads several metrics -- and a hand-written
 * sentence would rot the moment the artifacts change.
 */
function metricLeaders(comparison: ModelComparisonDTO): { label: string; leader: string }[] {
  const entries: [string, ModelComparisonEntryDTO | null][] = [
    ["Baseline v1", comparison.baseline_v1],
    ["Defender v2", comparison.defender_v2],
    ["Defender v3", comparison.defender_v3],
  ];
  const present = entries.filter((e): e is [string, ModelComparisonEntryDTO] => e[1] != null);
  if (present.length === 0) return [];

  const metrics: { label: string; get: (e: ModelComparisonEntryDTO) => number | null; lowerIsBetter?: boolean }[] = [
    { label: "PR-AUC", get: (e) => e.pr_auc },
    { label: "Recall", get: (e) => e.recall },
    { label: "F1", get: (e) => e.f1 },
    { label: "Precision", get: (e) => e.precision },
    { label: "FPR", get: (e) => e.false_positive_rate, lowerIsBetter: true },
    { label: "Recall @ 0.1% FPR", get: (e) => e.recall_at_fixed_fpr?.["0.001"] ?? null },
  ];

  const out: { label: string; leader: string }[] = [];
  for (const m of metrics) {
    let best: { name: string; value: number } | null = null;
    for (const [name, entry] of present) {
      const v = m.get(entry);
      if (v == null) continue;
      if (best == null || (m.lowerIsBetter ? v < best.value : v > best.value)) {
        best = { name, value: v };
      }
    }
    if (best) out.push({ label: m.label, leader: best.name });
  }
  return out;
}

function Verdict({ summary }: { summary: FinalBenchmarkSummaryDTO }) {
  const loafo = summary.loafo;
  const weakest = summary.claim_flags?.weakest_unseen_family;
  if (!loafo) return null;

  const strong = loafo.per_family.filter((f) => f.verdict === "strong").length;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold text-[var(--color-ink)]">
          Did the hardening generalize to attack families held out of training?
        </h2>
        <Badge variant="risk-medium">
          {loafo.overall_verdict === "partial"
            ? "Partial generalization"
            : `${loafo.overall_verdict} generalization`}
        </Badge>
      </div>

      <p className="mt-2 text-sm leading-relaxed text-[var(--color-ink)]">
        <strong>{strong} of {loafo.per_family.length} families transferred.</strong>{" "}
        {typeof weakest === "string" && (
          <>
            <span className="capitalize">{familyLabel(weakest)}</span> did not. Mean LOAFO recall
            across the three folds is {pct(loafo.mean_loafo_recall, 1)}.
          </>
        )}
      </p>

      <p className="mt-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-3 py-2 text-[11px] leading-snug text-[var(--color-ink-muted)]">
        <strong className="text-[var(--color-ink)]">
          The result is not &ldquo;AEGIS solved fraud detection.&rdquo;
        </strong>{" "}
        The result is that AEGIS can measure where hardening transfers and where it does not.
      </p>

      <p className="mt-2 text-[11px] leading-snug text-[var(--color-ink-faint)]">
        Mean LOAFO recall is <strong>not</strong> Defender v3&rsquo;s recall and not a production
        fraud-detection rate. It is the recall of three separate fold models, each trained with
        one attack family contributing zero rows, each scored on one fresh scenario of that
        held-out family (3&ndash;12 fraud events each &mdash; directional, not statistically
        powered).
      </p>
    </Card>
  );
}

function HardestSurvivorCards({ evasions }: { evasions: HardestEvasionDTO[] }) {
  const top = evasions.slice(0, 3);
  if (top.length === 0) {
    return (
      <p className="text-xs text-[var(--color-ink-muted)]">No surviving evasions recorded yet.</p>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
      {top.map((e) => (
        <div
          key={`${e.source_artifact}:${e.transaction_id}`}
          className="min-w-0 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wide text-[var(--color-ink-faint)]">
              #{e.rank ?? "—"}
            </span>
            <Badge variant="attack">{familyLabel(e.attack_family)}</Badge>
          </div>
          <p className="mt-1.5 break-all font-mono text-[10px] text-[var(--color-ink-muted)]">
            {e.transaction_id}
          </p>
          <p className="mt-0.5 break-all font-mono text-[10px] text-[var(--color-ink-faint)]">
            scenario {e.scenario_id || "—"}
          </p>
          <div className="mt-2 grid grid-cols-2 gap-1.5">
            <div className="rounded bg-[var(--color-surface-sunken)] px-2 py-1 text-center">
              <p className="text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)]">
                Risk
              </p>
              <p className="text-sm font-bold tabular-nums text-[var(--color-ink)]">
                {pct(e.detector_risk_score, 1)}
              </p>
            </div>
            <div className="rounded bg-[var(--color-surface-sunken)] px-2 py-1 text-center">
              <p className="text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)]">
                Action
              </p>
              <p className="text-sm font-bold text-[var(--color-ink)]">{e.action || "—"}</p>
            </div>
          </div>
          <p className="mt-1.5 truncate font-mono text-[10px] text-[var(--color-ink-faint)]">
            {e.detector_model_version}
          </p>
        </div>
      ))}
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
        <h1 className="text-xl font-bold text-[var(--color-ink)] sm:text-2xl">Results</h1>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Did the hardening generalize? Every figure read live from persisted benchmark
          artifacts.
        </p>
      </header>

      <ApiStateSection
        state={state}
        emptyTitle="No benchmark data yet"
        emptyBody="Run scripts/build_final_benchmark_summary.py to populate this page."
        render={(summary) => (
          <div className="space-y-4">
            {/* 1. verdict */}
            <Verdict summary={summary} />

            {/* 2. LOAFO -- the hero */}
            {summary.loafo && (
              <Card>
                <div className="mb-1">
                  <h2 className="text-sm font-semibold text-[var(--color-ink)]">
                    LOAFO &mdash; Leave One Attack Family Out
                  </h2>
                  <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                    Hold one attack family out of hardening entirely, harden without it, then
                    evaluate on a fresh scenario of that family. This tests transfer, not
                    memorization.
                  </p>
                </div>
                <p className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-3 py-2 text-[11px] leading-snug text-[var(--color-ink-muted)]">
                  In each fold the held-out family contributes{" "}
                  <strong className="text-[var(--color-ink)]">zero training rows</strong>, and the
                  fold model and Defender v3 are scored on the{" "}
                  <strong className="text-[var(--color-ink)]">same fresh scenario</strong> &mdash;
                  each fold report holds exactly one scenario, so that comparison is
                  like-for-like. This is a different guarantee from the per-generation
                  confrontation snapshots on Evolution, which each have their own scenario.
                </p>
                <div className="-mx-1 overflow-x-auto px-1">
                  <LoafoResultsTable loafo={summary.loafo} />
                </div>
              </Card>
            )}

            {/* 3. family results on those same fresh scenarios */}
            {summary.fresh_family_performance.length > 0 && (
              <Card>
                <h2 className="text-sm font-semibold text-[var(--color-ink)]">
                  Fresh LOAFO scenarios: family-held-out fold vs Defender v3
                </h2>
                <p className="mb-3 mt-0.5 text-xs text-[var(--color-ink-muted)]">
                  Both bars in each pair come from the same fresh scenario for that family. Guided
                  generations and confrontation replays are separate evidence and are not mixed
                  into this chart.
                </p>
                {/* No scroll wrapper here: RecallByFamilyChart uses Recharts'
                    ResponsiveContainer, which measures its parent -- wrapping it
                    in an overflow/min-width track collapses the bars to zero
                    height. It is responsive on its own. */}
                <RecallByFamilyChart families={summary.fresh_family_performance} />
              </Card>
            )}

            {/* 4. native-test model comparison */}
            {summary.model_comparison && (
              <Card>
                <h2 className="text-sm font-semibold text-[var(--color-ink)]">
                  Native PaySim test split: v1 vs v2 vs v3
                </h2>
                <p className="mb-3 mt-0.5 text-xs text-[var(--color-ink-muted)]">
                  All three generations evaluated on the identical untouched PaySim test split
                  (one dataset id), so these are directly comparable.
                </p>

                <p className="mb-3 rounded-lg border border-[var(--color-risk-medium-100)] bg-[var(--color-risk-medium-100)]/40 px-3 py-2 text-[11px] leading-snug text-[var(--color-ink)]">
                  <strong>
                    Hardening changed the operating trade-off; it did not uniformly improve every
                    native-test metric.
                  </strong>{" "}
                  Where each generation leads:{" "}
                  {metricLeaders(summary.model_comparison)
                    .map((m) => `${m.label} → ${m.leader}`)
                    .join(" · ")}
                  .
                </p>

                <div className="-mx-1 overflow-x-auto px-1">
                  <div className="min-w-[320px]">
                    <ModelComparisonCards comparison={summary.model_comparison} />
                  </div>
                </div>
              </Card>
            )}

            {/* 5. hardest survivors */}
            <Card>
              <h2 className="text-sm font-semibold text-[var(--color-ink)]">
                Hardest surviving attacks
              </h2>
              <p className="mb-3 mt-0.5 text-xs text-[var(--color-ink-muted)]">
                Real fraudulent transactions that a real detector let through, ranked by hardness
                ((1 − risk) × fidelity) within their own confrontation. No explanation of{" "}
                <em>why</em> each survived is persisted, so none is shown.
              </p>
              <HardestSurvivorCards evasions={summary.hardest_surviving_attacks} />
              {summary.hardest_surviving_attacks.length > 3 && (
                <Details
                  className="mt-2.5"
                  summary={`Full ranking (${summary.hardest_surviving_attacks.length} evasions)`}
                >
                  <div className="-mx-1 overflow-x-auto px-1">
                    <HardestEvasionsTable
                      evasions={summary.hardest_surviving_attacks}
                      totalAvailable={summary.hardest_surviving_attacks.length}
                    />
                  </div>
                </Details>
              )}
            </Card>

            {/* 6. what the benchmark found + limitations */}
            <Card>
              <h2 className="text-sm font-semibold text-[var(--color-ink)]">
                What this benchmark found
              </h2>
              <p className="mb-3 mt-0.5 text-xs text-[var(--color-ink-muted)]">
                Read from the same artifacts as everything above &mdash; including the results
                that did not go our way.
              </p>
              <BenchmarkInterpretation summary={summary} />
              <Details className="mt-2.5" summary="Scope and limitations">
                <ul className="list-disc space-y-1 pl-4">
                  <li>
                    All data is synthetic: PaySim is a public synthetic mobile-money simulator,
                    and every attack is generated by AEGIS&rsquo;s own deterministic simulators.
                  </li>
                  <li>
                    Fresh scenarios hold 3&ndash;12 fraud events each, so per-family figures are
                    directional, not statistically powered estimates.
                  </li>
                  <li>
                    Generalization is partial, not universal; no claim of universal fraud
                    detection is made anywhere in this submission.
                  </li>
                  <li>
                    Defender v3 is frozen. Nothing on this site retrains, refits or rescores it,
                    and there is no Defender v4.
                  </li>
                  <li>
                    This is a read-only demo over persisted benchmark artifacts &mdash; not a
                    deployment, and not connected to live payment scoring.
                  </li>
                  {summary.limitations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                  {summary.loafo?.verdict_rubric && <li>{summary.loafo.verdict_rubric}</li>}
                </ul>
              </Details>
            </Card>
          </div>
        )}
      />
    </div>
  );
}
