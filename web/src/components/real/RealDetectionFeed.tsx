import type { DetectionRecordDTO } from "../../api/types";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../../types/aegis";
import { Badge } from "../ui/Badge";
import { DataTable, type Column } from "../ui/DataTable";
import { RiskBar } from "../ui/RiskBar";

const ACTION_VARIANT: Record<string, "risk-low" | "risk-medium" | "risk-high" | "neutral"> = {
  approve: "risk-low",
  step_up: "risk-medium",
  review: "risk-medium",
  decline: "risk-high",
};

function familyLabel(family: string | null): string {
  if (!family) return "—";
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family;
}

const COLUMNS: Column<DetectionRecordDTO>[] = [
  {
    key: "id",
    header: "Transaction",
    render: (d) => <span className="font-mono text-xs">{d.transaction_id}</span>,
  },
  {
    key: "scenario",
    header: "Scenario",
    render: (d) => (d.scenario_id ? <span className="font-mono text-xs">{d.scenario_id}</span> : "—"),
  },
  { key: "risk", header: "Risk score", render: (d) => <RiskBar score={d.risk_score} /> },
  {
    key: "action",
    header: "Detector action",
    render: (d) => <Badge variant={ACTION_VARIANT[d.recommended_action] ?? "neutral"}>{d.recommended_action}</Badge>,
  },
  {
    key: "truth",
    header: "Ground truth",
    render: (d) =>
      d.ground_truth_label == null ? (
        <Badge variant="neutral">Unknown</Badge>
      ) : d.ground_truth_label === 1 ? (
        <Badge variant="attack">Fraud</Badge>
      ) : (
        <Badge variant="neutral">Legitimate</Badge>
      ),
  },
  { key: "family", header: "Attack family", render: (d) => familyLabel(d.attack_family) },
  {
    key: "model",
    header: "Model version",
    render: (d) => <span className="font-mono text-xs">{d.model_version}</span>,
  },
];

/**
 * Real detector outputs joined with their transaction context, read from
 * `/api/detections/recent`. One row per scored transaction from an actual
 * confrontation artifact -- no client-side scoring, nothing simulated.
 */
export function RealDetectionFeed({
  detections,
  totalAvailable,
}: {
  detections: DetectionRecordDTO[];
  totalAvailable: number;
}) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-[var(--color-ink-muted)]">
        Showing {detections.length} of {totalAvailable} scored transactions from real confrontation
        artifacts.
      </p>
      <DataTable
        columns={COLUMNS}
        rows={detections}
        rowKey={(d) => `${d.source_artifact}:${d.transaction_id}`}
        maxHeight="520px"
        emptyLabel="No detector outputs recorded yet."
      />
    </div>
  );
}
