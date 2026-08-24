import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RoundRecord } from "../../mock/loopSimulator";

export function MetricsTrendChart({ rounds }: { rounds: RoundRecord[] }) {
  const data = rounds.map((r) => ({
    round: `R${r.roundIndex}`,
    recall: Math.round(r.evaluation.overall.recall * 1000) / 10,
    evasionRate: r.evaluation.overall.confusion.false_negative > 0 || r.evaluation.overall.confusion.true_positive > 0
      ? Math.round(
          (r.evaluation.overall.confusion.false_negative /
            Math.max(1, r.evaluation.overall.confusion.false_negative + r.evaluation.overall.confusion.true_positive)) *
            1000,
        ) / 10
      : 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis dataKey="round" tick={{ fontSize: 12, fill: "var(--color-ink-muted)" }} axisLine={{ stroke: "var(--color-border)" }} tickLine={false} />
        <YAxis
          tick={{ fontSize: 12, fill: "var(--color-ink-muted)" }}
          axisLine={false}
          tickLine={false}
          domain={[0, 100]}
          unit="%"
          width={40}
        />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)", fontSize: 12 }}
          formatter={(value) => `${value}%`}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="recall" name="Detector recall" stroke="var(--color-defend-600)" strokeWidth={2} dot={{ r: 3 }} />
        <Line type="monotone" dataKey="evasionRate" name="Fraud evasion rate" stroke="var(--color-attack-600)" strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
