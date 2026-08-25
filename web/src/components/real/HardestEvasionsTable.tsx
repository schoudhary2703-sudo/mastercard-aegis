import type { HardestEvasionDTO } from "../../api/types";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../../types/aegis";
import { Badge } from "../ui/Badge";
import { DataTable, type Column } from "../ui/DataTable";

const ACTION_VARIANT: Record<string, "risk-low" | "risk-medium" | "risk-high" | "neutral"> = {
  approve: "risk-low",
  step_up: "risk-medium",
  review: "risk-medium",
  decline: "risk-high",
};

function familyLabel(family: string): string {
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family;
}

const COLUMNS: Column<HardestEvasionDTO>[] = [
  { key: "rank", header: "#", render: (e) => e.rank ?? "—", width: "3rem" },
  {
    key: "stage",
    header: "Stage",
    render: (e) => <Badge variant="neutral">{e.source_round}</Badge>,
  },
  {
    key: "transaction",
    header: "Transaction",
    render: (e) => <span className="font-mono text-xs">{e.transaction_id}</span>,
  },
  {
    key: "family",
    header: "Attack family",
    render: (e) => <Badge variant="attack">{familyLabel(e.attack_family)}</Badge>,
  },
  {
    key: "risk",
    header: "Risk score",
    align: "right",
    render: (e) => `${(e.detector_risk_score * 100).toFixed(1)}%`,
  },
  {
    key: "fidelity",
    header: "Fidelity",
    align: "right",
    render: (e) => (e.fidelity_score != null ? `${(e.fidelity_score * 100).toFixed(0)}%` : "—"),
  },
  {
    key: "hardness",
    header: "Hardness",
    align: "right",
    render: (e) => (e.hardness_score != null ? e.hardness_score.toFixed(3) : "—"),
  },
  {
    key: "model",
    header: "Model version",
    render: (e) => <span className="font-mono text-xs">{e.detector_model_version}</span>,
  },
  {
    key: "action",
    header: "Detector action",
    render: (e) => <Badge variant={ACTION_VARIANT[e.action] ?? "neutral"}>{e.action}</Badge>,
  },
];

/**
 * Fraudulent transactions that evaded the detector, ranked by hardness.
 * Only shows fields the backend already computed -- no generated
 * explanation of *why* a transaction survived.
 */
export function HardestEvasionsTable({
  evasions,
  totalAvailable,
}: {
  evasions: HardestEvasionDTO[];
  totalAvailable?: number;
}) {
  const credibleCount = evasions.filter((e) => e.credible_evasion).length;

  return (
    <div className="space-y-2">
      {totalAvailable != null && (
        <p className="text-xs text-[var(--color-ink-muted)]">
          Showing {evasions.length} of {totalAvailable} real evasions · {credibleCount} marked
          credible (evaded and within realism bounds).
        </p>
      )}
      <DataTable
        columns={COLUMNS}
        rows={evasions}
        rowKey={(e) => `${e.source_artifact}:${e.transaction_id}`}
        emptyLabel="No surviving evasions recorded yet."
      />
    </div>
  );
}
