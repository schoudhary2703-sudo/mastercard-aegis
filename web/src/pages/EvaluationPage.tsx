import { useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchEvaluation } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { Card, CardHeader } from "../components/ui/Card";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { RealDataBadge } from "../components/real/RealBadge";
import { RealEvaluationPanel } from "../components/real/RealEvaluationPanel";

/**
 * Per-model metric detail: the appendix to Results, not a step in the
 * walkthrough.
 *
 * This page used to close with a mock round's confusion matrix, latency table
 * and per-family metrics, gated on whether a browser-side demo round had been
 * run -- which meant an untouched page opened on an empty state telling the
 * reader to go run a simulation. All of that moved to /sandbox. What is left
 * is the thing Results genuinely does not show: the complete persisted metric
 * set for every model on both splits.
 *
 * It stays out of the nav and is reached from Results.
 */
export function EvaluationPage() {
  const evaluationFetch = useCallback((signal: AbortSignal) => fetchEvaluation(signal), []);
  const evaluationState = useApiResource(
    evaluationFetch,
    [],
    (data) => data.evaluations.length === 0,
  );

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-[var(--color-ink)] sm:text-2xl">
          Per-model metric detail
        </h1>
        <p className="text-xs text-[var(--color-ink-muted)]">
          Every EvaluationResult on disk, on the untouched test and validation splits.
        </p>
      </header>

      <p className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-3 py-2.5 text-[11px] leading-snug text-[var(--color-ink-muted)]">
        The three-model comparison, the operating point and the leave-one-family-out benchmark are
        on{" "}
        <Link
          to="/final-benchmark"
          className="font-semibold text-[var(--color-accent-600)] hover:underline"
        >
          Results
        </Link>
        . This page is the full metric dump behind them.
      </p>

      <Card>
        <CardHeader
          title="Real evaluation results"
          subtitle="Protocol-scoped metrics read from persisted model artifacts. Pick a model and split for its full metric set."
          action={<RealDataBadge />}
        />
        <ApiStateSection
          state={evaluationState}
          emptyTitle="No real evaluations yet"
          emptyBody="Run scripts/train_baseline_detector.py to produce evaluation_test.json / evaluation_validation.json."
          render={(evaluation) => <RealEvaluationPanel evaluation={evaluation} />}
        />
      </Card>
    </div>
  );
}
