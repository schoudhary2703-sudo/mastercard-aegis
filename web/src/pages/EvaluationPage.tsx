import { useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchEvaluation } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { Card, CardHeader } from "../components/ui/Card";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { RealDataBadge } from "../components/real/RealBadge";
import { PageHeader } from "../components/ui/PageHeader";
import { Callout } from "../components/ui/Panel";
import { RealEvaluationPanel } from "../components/real/RealEvaluationPanel";

/**
 * Per-model metric detail: the appendix to Results, not a step in the
 * walkthrough.
 *
 * This page used to open with the same three-model comparison that is
 * Evidence 1 on Results, and close with a mock round's confusion matrix and
 * latency table. Both are gone: the comparison has one owner (Results), the
 * mock has one home (/sandbox), and what is left here is the thing Results
 * genuinely does not show -- the complete persisted metric set for every
 * model on both the test and validation splits.
 *
 * It stays out of the nav and is reached from Results and from Defend.
 */
export function EvaluationPage() {
  const evaluationFetch = useCallback((signal: AbortSignal) => fetchEvaluation(signal), []);
  const evaluationState = useApiResource(
    evaluationFetch,
    [],
    (data) => data.evaluations.length === 0,
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Appendix · per-model detail"
        title="The complete persisted metric set, model by model and split by split."
      >
        Every EvaluationResult on disk, on the untouched test and validation splits.
      </PageHeader>

      <Callout eyebrow="Looking for the headline?">
        <p>
          The three-model comparison, the operating point and the leave-one-family-out benchmark are
          on{" "}
          <Link
            to="/final-benchmark"
            className="font-semibold text-[var(--color-accent-500)] hover:underline"
          >
            Results
          </Link>
          . This page is the full metric dump behind them.
        </p>
      </Callout>

      <Card>
        <CardHeader
          title="Per-model metric detail"
          subtitle="Pick a model and split for its full metric set."
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
