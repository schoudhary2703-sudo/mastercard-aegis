import type { LoafoBenchmarkDTO, LoafoFamilyResultDTO } from "../../api/types";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../../types/aegis";
import { Badge } from "../ui/Badge";
import { DataTable, type Column } from "../ui/DataTable";
import { StatTile } from "../ui/StatTile";

function familyLabel(family: string): string {
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family;
}

const VERDICT_VARIANT: Record<string, "risk-low" | "risk-medium" | "risk-high" | "neutral"> = {
  strong: "risk-low",
  partial: "risk-medium",
  weak: "risk-high",
};

const COLUMNS: Column<LoafoFamilyResultDTO>[] = [
  { key: "family", header: "Held-out family", render: (r) => familyLabel(r.attack_family) },
  {
    key: "trained_on",
    header: "Trained on",
    render: (r) => r.training_families.map(familyLabel).join(" + "),
  },
  {
    key: "loafo_recall",
    header: "LOAFO recall",
    align: "right",
    render: (r) => `${(r.loafo_recall * 100).toFixed(0)}%`,
  },
  {
    key: "v3_recall",
    header: "Defender v3 recall (same scenario)",
    align: "right",
    render: (r) => `${(r.defender_v3_recall_same_scenario * 100).toFixed(0)}%`,
  },
  {
    key: "verdict",
    header: "Generalization",
    render: (r) => <Badge variant={VERDICT_VARIANT[r.verdict] ?? "neutral"}>{r.verdict}</Badge>,
  },
];

/**
 * Leave-One-Attack-Family-Out results: for each family, a model trained
 * without any hard positives from that family, scored on one fresh scenario
 * of it. Defender v3's recall on the identical scenario is shown alongside
 * as the memorization reference. All real `EvaluationResult`s, all read
 * from `models/loafo_summary.json` / each fold's `loafo_fold_report.json`.
 */
export function LoafoResultsTable({ loafo }: { loafo: LoafoBenchmarkDTO }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatTile
          label="Mean LOAFO recall"
          value={`${(loafo.mean_loafo_recall * 100).toFixed(0)}%`}
          tone={loafo.mean_loafo_recall > 0 ? "positive" : "risk"}
        />
        <StatTile
          label="Overall generalization"
          value={loafo.overall_verdict}
          tone={
            loafo.overall_verdict === "strong"
              ? "positive"
              : loafo.overall_verdict === "weak"
                ? "risk"
                : "neutral"
          }
        />
      </div>
      <DataTable
        columns={COLUMNS}
        rows={loafo.per_family}
        rowKey={(r) => r.attack_family}
        emptyLabel="No LOAFO results yet."
      />
      <p className="text-xs text-[var(--color-ink-muted)]">{loafo.verdict_rubric}</p>
    </div>
  );
}
