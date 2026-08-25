import { useCallback } from "react";
import { fetchBenchmark } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { Card, CardHeader } from "../components/ui/Card";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { BenchmarkInterpretation } from "../components/real/BenchmarkInterpretation";
import { HardestEvasionsTable } from "../components/real/HardestEvasionsTable";
import { LoafoResultsTable } from "../components/real/LoafoResultsTable";
import { ModelComparisonCards } from "../components/real/ModelComparisonCards";
import { RealDataBadge } from "../components/real/RealBadge";
import { RecallByFamilyChart } from "../components/real/RecallByFamilyChart";

export function FinalBenchmarkPage() {
  const benchmarkFetch = useCallback((signal: AbortSignal) => fetchBenchmark(signal), []);
  const benchmarkState = useApiResource(
    benchmarkFetch,
    [],
    (data) => !data.model_comparison && !data.loafo && data.fresh_family_performance.length === 0,
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Final benchmark"
          subtitle="Baseline v1, Defender v2, and Defender v3 compared on untouched PaySim test, plus the LOAFO generalization results -- the complete, judge-facing picture."
          action={<RealDataBadge />}
        />
        <ApiStateSection
          state={benchmarkState}
          emptyTitle="No benchmark data yet"
          emptyBody="Run scripts/build_final_benchmark_summary.py after training v1/v2/v3 and the LOAFO benchmark to populate this page."
          render={(summary) => (
            <div className="space-y-6">
              <BenchmarkInterpretation summary={summary} />

              {summary.model_comparison && (
                <div>
                  <h3 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">
                    Model comparison
                  </h3>
                  <ModelComparisonCards comparison={summary.model_comparison} />
                </div>
              )}

              {summary.fresh_family_performance.length > 0 && (
                <div>
                  <h3 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">
                    Defender v3 recall by attack family
                  </h3>
                  <RecallByFamilyChart families={summary.fresh_family_performance} />
                </div>
              )}

              {summary.loafo && (
                <div>
                  <h3 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">
                    LOAFO: held-out-family generalization
                  </h3>
                  <LoafoResultsTable loafo={summary.loafo} />
                </div>
              )}

              <div>
                <h3 className="mb-3 text-sm font-semibold text-[var(--color-ink)]">
                  Hardest surviving attacks
                </h3>
                <HardestEvasionsTable
                  evasions={summary.hardest_surviving_attacks}
                  totalAvailable={summary.hardest_surviving_attacks.length}
                />
              </div>

              {summary.limitations.length > 0 && (
                <div className="rounded-lg border border-dashed border-[var(--color-border-strong)] p-4">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
                    Limitations
                  </p>
                  <ul className="list-disc space-y-1 pl-4 text-xs text-[var(--color-ink-muted)]">
                    {summary.limitations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        />
      </Card>
    </div>
  );
}
