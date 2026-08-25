import { useCallback, useState } from "react";
import { fetchRecentDetections } from "../api/client";
import { useApiResource } from "../api/useApiResource";
import { AttackFamilySelector } from "../components/attack/AttackFamilySelector";
import { ActionBadge, Badge } from "../components/ui/Badge";
import { Card, CardHeader } from "../components/ui/Card";
import { DataTable, type Column } from "../components/ui/DataTable";
import { RiskBar } from "../components/ui/RiskBar";
import { EmptyState, SkeletonRows } from "../components/ui/States";
import { StatTile } from "../components/ui/StatTile";
import { ApiStateSection } from "../components/real/ApiStateSection";
import { MockDataBadge, RealDataBadge } from "../components/real/RealBadge";
import { RealDetectionFeed } from "../components/real/RealDetectionFeed";
import { generateBatchForFamily } from "../mock/generateBatch";
import { scoreTransactions } from "../mock/mockDetector";
import type { AttackFamily, DetectorOutput, Transaction } from "../types/aegis";

interface Row {
  txn: Transaction;
  out: DetectorOutput;
  outcome: "caught" | "evaded" | "correct-reject" | "false-positive";
}

let seedCounter = 30260101;

function outcomeFor(txn: Transaction, out: DetectorOutput): Row["outcome"] {
  const flagged = out.recommended_action !== "approve";
  if (txn.label === 1) return flagged ? "caught" : "evaded";
  return flagged ? "false-positive" : "correct-reject";
}

const OUTCOME_BADGE: Record<Row["outcome"], { variant: "risk-low" | "risk-high" | "risk-medium" | "neutral"; label: string }> = {
  caught: { variant: "risk-low", label: "Caught" },
  evaded: { variant: "risk-high", label: "Evaded" },
  "correct-reject": { variant: "neutral", label: "Clean" },
  "false-positive": { variant: "risk-medium", label: "False alarm" },
};

export function LiveDetectionPage() {
  const [family, setFamily] = useState<AttackFamily>("mule_network_structuring");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const detectionsFetch = useCallback((signal: AbortSignal) => fetchRecentDetections(50, signal), []);
  const detectionsState = useApiResource(
    detectionsFetch,
    [],
    (data) => data.detections.length === 0,
  );

  function runDetection() {
    setIsRunning(true);
    setRows(null);
    seedCounter += 1;
    const seed = seedCounter;
    window.setTimeout(() => {
      const batch = generateBatchForFamily(family, { seed, count: 40 });
      const outputs = scoreTransactions(batch.transactions, {
        modelVersion: "detector-v1-preview",
        defenderStrength: 0.55,
        seed: seed + 1,
      });
      const outMap = new Map(outputs.map((o) => [o.transaction_id, o]));
      setRows(
        batch.transactions.map((txn) => {
          const out = outMap.get(txn.transaction_id)!;
          return { txn, out, outcome: outcomeFor(txn, out) };
        }),
      );
      setIsRunning(false);
    }, 380);
  }

  const caught = rows?.filter((r) => r.outcome === "caught").length ?? 0;
  const evaded = rows?.filter((r) => r.outcome === "evaded").length ?? 0;
  const flaggedRate = rows ? rows.filter((r) => r.out.recommended_action !== "approve").length / rows.length : 0;

  const columns: Column<Row>[] = [
    { key: "id", header: "Transaction", render: (r) => <span className="font-mono text-xs">{r.txn.transaction_id}</span> },
    { key: "amount", header: "Amount", align: "right", render: (r) => `$${r.txn.amount.toLocaleString()}` },
    { key: "risk", header: "Risk score", render: (r) => <RiskBar score={r.out.risk_score} /> },
    { key: "action", header: "Detector action", render: (r) => <ActionBadge action={r.out.recommended_action} /> },
    {
      key: "truth",
      header: "Ground truth",
      render: (r) => (r.txn.label === 1 ? <Badge variant="attack">Fraud</Badge> : <Badge variant="neutral">Legitimate</Badge>),
    },
    {
      key: "outcome",
      header: "Outcome",
      render: (r) => <Badge variant={OUTCOME_BADGE[r.outcome].variant}>{OUTCOME_BADGE[r.outcome].label}</Badge>,
    },
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Real recent detections"
          subtitle="Per-transaction detector outputs joined with transaction context, read from real confrontation artifacts."
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

      <Card>
        <CardHeader
          title="Run a mock detection pass"
          subtitle="Generates a batch for the selected family and scores it with a single detector snapshot. Simulated in the browser, not real data."
          action={
            <div className="flex items-center gap-2">
              <MockDataBadge />
              <button
                type="button"
                onClick={runDetection}
                disabled={isRunning}
                className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-medium text-white transition-standard hover:bg-[var(--color-accent-500)] disabled:opacity-60"
              >
                {isRunning ? "Scoring…" : "Run detection"}
              </button>
            </div>
          }
        />
        <AttackFamilySelector value={family} onChange={setFamily} />
      </Card>

      {isRunning && (
        <Card>
          <SkeletonRows rows={6} />
        </Card>
      )}

      {!isRunning && !rows && (
        <EmptyState title="No detection run yet" body="Choose a family above and run detection to see per-transaction risk scores." />
      )}

      {!isRunning && rows && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile label="Transactions scored" value={rows.length} />
            <StatTile label="Fraud caught" value={caught} tone="positive" />
            <StatTile label="Fraud evaded" value={evaded} tone={evaded > 0 ? "risk" : "neutral"} />
            <StatTile label="Alert rate" value={`${(flaggedRate * 100).toFixed(0)}%`} />
          </div>
          <Card padded={false}>
            <div className="p-5 pb-0">
              <CardHeader title="Transaction feed" subtitle="One row per scored transaction, most recent first." />
            </div>
            <div className="px-5 pb-5">
              <DataTable columns={columns} rows={[...rows].reverse()} rowKey={(r) => r.txn.transaction_id} maxHeight="520px" />
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
