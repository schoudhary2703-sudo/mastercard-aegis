import { useState } from "react";
import type { EvaluationResponseDTO } from "../../api/types";
import { Card, CardHeader } from "../ui/Card";
import { StatTile } from "../ui/StatTile";

const METRIC_LABEL: Record<string, string> = {
  precision: "Precision",
  recall: "Recall",
  f1: "F1",
  pr_auc: "PR-AUC",
  roc_auc: "ROC-AUC",
  false_positive_rate: "False positive rate",
  false_negative_rate: "False negative rate",
  alert_rate: "Alert rate",
  threshold: "Threshold",
};

/**
 * Real, protocol-scoped evaluation results for every model the pipeline has
 * produced (baseline v1, Defender v2, ...), plus the regression comparison
 * between them. Every number is read from `/api/evaluation`.
 */
export function RealEvaluationPanel({ evaluation }: { evaluation: EvaluationResponseDTO }) {
  const [selectedId, setSelectedId] = useState(evaluation.evaluations[0]?.evaluation_id ?? "");
  const selected =
    evaluation.evaluations.find((e) => e.evaluation_id === selectedId) ?? evaluation.evaluations[0];

  if (!selected) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {evaluation.evaluations.map((e) => (
          <button
            key={e.evaluation_id}
            type="button"
            onClick={() => setSelectedId(e.evaluation_id)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-standard ${
              e.evaluation_id === selected.evaluation_id
                ? "border-[var(--color-accent-600)] bg-[var(--color-accent-600)]/10 text-[var(--color-accent-600)]"
                : "border-[var(--color-border)] text-[var(--color-ink-muted)] hover:border-[var(--color-border-strong)]"
            }`}
          >
            {e.model_version} · {e.split}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatTile label="Precision" value={`${(selected.overall.precision * 100).toFixed(1)}%`} />
        <StatTile label="Recall" value={`${(selected.overall.recall * 100).toFixed(1)}%`} />
        <StatTile label="F1" value={`${(selected.overall.f1 * 100).toFixed(1)}%`} />
        <StatTile label="ROC-AUC" value={selected.overall.roc_auc?.toFixed(3) ?? "—"} />
        <StatTile
          label="False positive rate"
          value={`${(selected.overall.false_positive_rate * 100).toFixed(3)}%`}
        />
      </div>
      <p className="text-xs text-[var(--color-ink-muted)]">
        {selected.protocol} · {selected.split} split · {selected.overall.support.toLocaleString()}{" "}
        scored transactions · source:{" "}
        <span className="font-mono">{selected.source_artifact}</span>
      </p>

      {evaluation.regression && (
        <Card>
          <CardHeader
            title="Baseline v1 → Defender v2 · initial hardening round"
            subtitle={`Per-metric regression for the first hardening step, computed on the ${evaluation.regression.split ?? "test"} split only -- never on the hard positives used to retrain Defender v2. Defender v3 (cross-family) and the full v1/v2/v3 table are on Final Results.`}
          />
          <div className="overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
                  <th className="py-2 pr-3">Metric</th>
                  <th className="px-3 py-2 text-right">Baseline v1</th>
                  <th className="px-3 py-2 text-right">Defender v2</th>
                  <th className="px-3 py-2 text-right">Delta</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(evaluation.regression.metrics).map(([name, m]) => (
                  <tr key={name} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="py-2 pr-3 font-medium text-[var(--color-ink)]">
                      {METRIC_LABEL[name] ?? name}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{m.baseline_v1.toFixed(4)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{m.defender_v2.toFixed(4)}</td>
                    <td
                      className={`px-3 py-2 text-right tabular-nums ${
                        m.delta >= 0 ? "text-[var(--color-risk-low-600)]" : "text-[var(--color-risk-high-600)]"
                      }`}
                    >
                      {m.delta >= 0 ? "+" : ""}
                      {m.delta.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {evaluation.regression.notes && (
            <p className="mt-3 text-xs text-[var(--color-ink-muted)]">{evaluation.regression.notes}</p>
          )}
        </Card>
      )}
    </div>
  );
}
