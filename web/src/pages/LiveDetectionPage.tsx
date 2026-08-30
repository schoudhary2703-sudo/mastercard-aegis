import { useCallback } from "react";
import { Link } from "react-router-dom";
import { fetchRecentDetections } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { PageHeader } from "../components/ui/PageHeader";
import { Card, CardHeader } from "../components/ui/Card";
import { Callout } from "../components/ui/Panel";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { RealDataBadge } from "../components/real/RealBadge";
import { RealDetectionFeed } from "../components/real/RealDetectionFeed";

/**
 * Defend (step 3): what the detector actually did, per transaction.
 *
 * This page used to carry a browser-side "mock detection pass" underneath the
 * real feed. Two detection tables on one screen -- one measured, one invented
 * -- is exactly the ambiguity that costs a reader their trust in the measured
 * one, so the mock moved to /sandbox and this screen is real artifacts only.
 */
export function LiveDetectionPage() {
  const detectionsFetch = useCallback(
    (signal: AbortSignal) => fetchRecentDetections(50, signal),
    [],
  );
  const detectionsState = useApiResource(
    detectionsFetch,
    [],
    (data) => data.detections.length === 0,
  );

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Step 3 · Defend"
        title="Every transaction the detector scored, with the signal that drove the decision."
      >
        Per-transaction detector outputs joined with transaction context, read straight from
        persisted confrontation artifacts. Nothing on this screen is scored in the browser.
      </PageHeader>

      <Card>
        <CardHeader
          title="Detector output, per transaction"
          subtitle="Risk score, recommended action and ground truth for every transaction in the persisted confrontations."
          action={<RealDataBadge />}
        />
        <ApiStateSection
          state={detectionsState}
          emptyTitle="No real detections yet"
          emptyBody="Run scripts/run_bustout_confrontation.py to produce detector_outputs.jsonl artifacts."
          render={(data) => (
            <RealDetectionFeed detections={data.detections} totalAvailable={data.total_available} />
          )}
        />
      </Card>

      <Callout eyebrow="How the defender is scored">
        <p>
          These are decisions on individual attack transactions. The aggregate metrics the model is
          judged on — precision, recall, F1, false-positive rate on the untouched PaySim test split —
          are on{" "}
          <Link
            to="/final-benchmark"
            className="font-semibold text-[var(--color-accent-500)] hover:underline"
          >
            Results
          </Link>
          , and the full per-model metric set is on{" "}
          <Link
            to="/evaluation"
            className="font-semibold text-[var(--color-accent-500)] hover:underline"
          >
            per-model detail
          </Link>
          . A browser-side toy detector, kept only as a demo fallback, lives in the{" "}
          <Link to="/sandbox" className="font-semibold text-[var(--color-accent-500)] hover:underline">
            sandbox
          </Link>{" "}
          and shares nothing with the real model.
        </p>
      </Callout>
    </div>
  );
}
