import type { ModelComparisonDTO, ModelComparisonEntryDTO } from "../../api/types";
import { Badge } from "../ui/Badge";

function pct(value: number | null, digits = 1): string {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function num(value: number | null, digits = 3): string {
  return value == null ? "—" : value.toFixed(digits);
}

const CARD_LABEL: Record<"baseline_v1" | "defender_v2" | "defender_v3", string> = {
  baseline_v1: "Baseline v1",
  defender_v2: "Defender v2",
  defender_v3: "Defender v3",
};

function ModelCard({
  slot,
  entry,
}: {
  slot: "baseline_v1" | "defender_v2" | "defender_v3";
  entry: ModelComparisonEntryDTO;
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-[var(--shadow-card)]">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          {CARD_LABEL[slot]}
        </p>
        {slot === "defender_v3" && <Badge variant="defend">Latest</Badge>}
      </div>
      <p className="mt-1 truncate font-mono text-[11px] text-[var(--color-ink-faint)]">
        {entry.model_version}
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div>
          <p className="text-lg font-semibold tabular-nums text-[var(--color-ink)]">
            {pct(entry.recall)}
          </p>
          <p className="text-[11px] text-[var(--color-ink-faint)]">Recall</p>
        </div>
        <div>
          <p className="text-lg font-semibold tabular-nums text-[var(--color-ink)]">
            {pct(entry.precision)}
          </p>
          <p className="text-[11px] text-[var(--color-ink-faint)]">Precision</p>
        </div>
        <div>
          <p className="text-sm font-medium tabular-nums text-[var(--color-ink-muted)]">
            {pct(entry.f1)}
          </p>
          <p className="text-[11px] text-[var(--color-ink-faint)]">F1</p>
        </div>
        <div>
          <p className="text-sm font-medium tabular-nums text-[var(--color-ink-muted)]">
            {pct(entry.false_positive_rate, 3)}
          </p>
          <p className="text-[11px] text-[var(--color-ink-faint)]">FPR</p>
        </div>
      </div>
    </div>
  );
}

const METRIC_ROWS: {
  key: keyof ModelComparisonEntryDTO;
  label: string;
  format: (v: ModelComparisonEntryDTO) => string;
}[] = [
  { key: "precision", label: "Precision", format: (e) => pct(e.precision) },
  { key: "recall", label: "Recall", format: (e) => pct(e.recall) },
  { key: "f1", label: "F1", format: (e) => pct(e.f1) },
  { key: "pr_auc", label: "PR-AUC", format: (e) => num(e.pr_auc) },
  { key: "roc_auc", label: "ROC-AUC", format: (e) => num(e.roc_auc) },
  { key: "false_positive_rate", label: "FPR", format: (e) => pct(e.false_positive_rate, 3) },
  {
    key: "recall_at_fixed_fpr",
    label: "Recall @ 0.1% FPR",
    format: (e) => pct(e.recall_at_fixed_fpr["0.001"] ?? null),
  },
  { key: "threshold", label: "Threshold", format: (e) => num(e.threshold, 4) },
  {
    key: "latency_ms",
    label: "Mean latency",
    format: (e) => {
      const mean = e.latency_ms?.mean_ms;
      return typeof mean === "number" ? `${mean.toFixed(2)}ms` : "—";
    },
  },
];

/**
 * v1 vs v2 vs v3 on the identical, untouched PaySim test split. Every value
 * is read from `ModelComparisonDTO`, itself a straight read of
 * `regression_vs_v1_v2.json` -- nothing here is computed in the browser.
 */
export function ModelComparisonCards({ comparison }: { comparison: ModelComparisonDTO }) {
  const { baseline_v1, defender_v2, defender_v3 } = comparison;
  if (!baseline_v1 || !defender_v2 || !defender_v3) return null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <ModelCard slot="baseline_v1" entry={baseline_v1} />
        <ModelCard slot="defender_v2" entry={defender_v2} />
        <ModelCard slot="defender_v3" entry={defender_v3} />
      </div>

      <div className="overflow-auto rounded-lg border border-[var(--color-border)]">
        <table className="w-full border-collapse text-sm">
          <thead className="bg-[var(--color-surface-sunken)]">
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
              <th className="px-3 py-2">Metric</th>
              <th className="px-3 py-2 text-right">Baseline v1</th>
              <th className="px-3 py-2 text-right">Defender v2</th>
              <th className="px-3 py-2 text-right">Defender v3</th>
            </tr>
          </thead>
          <tbody>
            {METRIC_ROWS.map((row) => (
              <tr key={row.key} className="border-b border-[var(--color-border)] last:border-0">
                <td className="px-3 py-2 text-xs font-medium text-[var(--color-ink)]">{row.label}</td>
                <td className="px-3 py-2 text-right text-xs tabular-nums text-[var(--color-ink-muted)]">
                  {row.format(baseline_v1)}
                </td>
                <td className="px-3 py-2 text-right text-xs tabular-nums text-[var(--color-ink-muted)]">
                  {row.format(defender_v2)}
                </td>
                <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-[var(--color-ink)]">
                  {row.format(defender_v3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-[var(--color-ink-muted)]">
        Split: {comparison.split} · source: <span className="font-mono">{comparison.source_artifact}</span>
      </p>
    </div>
  );
}
