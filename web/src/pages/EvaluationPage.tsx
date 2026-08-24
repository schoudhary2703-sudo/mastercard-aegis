import { Link } from "react-router-dom";
import { Badge } from "../components/ui/Badge";
import { Card, CardHeader } from "../components/ui/Card";
import { EmptyState } from "../components/ui/States";
import { StatTile } from "../components/ui/StatTile";
import { ConfusionMatrix } from "../components/evaluation/ConfusionMatrix";
import { useLoop } from "../state/LoopContext";
import { ATTACK_FAMILIES, ATTACK_FAMILY_LABEL } from "../types/aegis";

export function EvaluationPage() {
  const { latest } = useLoop();

  if (!latest) {
    return (
      <EmptyState
        title="No evaluation available yet"
        body="Every number here is traceable to a round run in Co-Evolution. Run at least one round to populate this screen."
        action={
          <Link
            to="/co-evolution"
            className="rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-medium text-white transition-standard hover:bg-[var(--color-accent-500)]"
          >
            Go to Co-Evolution
          </Link>
        }
      />
    );
  }

  const { evaluation } = latest;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title={evaluation.evaluation_id}
          subtitle="Every metric below is scoped to this evaluation and this protocol."
          action={
            <div className="flex gap-2">
              <Badge variant="neutral">{evaluation.protocol}</Badge>
              <Badge variant="neutral">round {evaluation.round_index}</Badge>
              <Badge variant="defend">{evaluation.model_version}</Badge>
            </div>
          }
        />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <StatTile label="Precision" value={`${(evaluation.overall.precision * 100).toFixed(1)}%`} />
          <StatTile label="Recall" value={`${(evaluation.overall.recall * 100).toFixed(1)}%`} />
          <StatTile label="F1" value={`${(evaluation.overall.f1 * 100).toFixed(1)}%`} />
          <StatTile label="ROC-AUC" value={evaluation.overall.roc_auc.toFixed(2)} />
          <StatTile label="False positive rate" value={`${(evaluation.overall.fpr * 100).toFixed(1)}%`} />
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Confusion matrix" subtitle="Overall, this round." />
          <ConfusionMatrix counts={evaluation.overall.confusion} />
        </Card>

        <Card>
          <CardHeader title="Latency" subtitle="Per-transaction scoring latency, milliseconds." />
          <div className="grid grid-cols-3 gap-2">
            {(["p50", "p95", "p99"] as const).map((k) => (
              <div key={k} className="rounded-lg border border-[var(--color-border)] px-3 py-3 text-center">
                <p className="text-xl font-semibold tabular-nums text-[var(--color-ink)]">
                  {evaluation.latency[k].toFixed(1)}
                </p>
                <p className="mt-0.5 text-[11px] uppercase text-[var(--color-ink-faint)]">{k}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-[var(--color-ink-muted)]">
            Mean {evaluation.latency.mean.toFixed(1)}ms · Max {evaluation.latency.max.toFixed(1)}ms
          </p>
        </Card>
      </div>

      <Card>
        <CardHeader title="Per attack family" subtitle="Same metrics, scoped to each family plus all legitimate traffic." />
        <div className="overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
                <th className="py-2 pr-3">Family</th>
                <th className="px-3 py-2 text-right">Precision</th>
                <th className="px-3 py-2 text-right">Recall</th>
                <th className="px-3 py-2 text-right">F1</th>
                <th className="px-3 py-2 text-right">Alert rate</th>
              </tr>
            </thead>
            <tbody>
              {ATTACK_FAMILIES.map(({ id: family }) => {
                const m = evaluation.per_attack_family[family];
                return (
                  <tr key={family} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="py-2 pr-3 font-medium text-[var(--color-ink)]">{ATTACK_FAMILY_LABEL[family]}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{(m.precision * 100).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-right tabular-nums">{(m.recall * 100).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-right tabular-nums">{(m.f1 * 100).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-right tabular-nums">{(m.alert_rate * 100).toFixed(0)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
