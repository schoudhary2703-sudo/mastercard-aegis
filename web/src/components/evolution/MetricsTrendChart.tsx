import {
  CartesianGrid,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_TOOLTIP_STYLE, CHART_TOOLTIP_ITEM_STYLE, CHART_TOOLTIP_LABEL_STYLE } from "../ui/chartTheme";
import type { RoundRecord } from "../../mock/loopSimulator";

export function MetricsTrendChart({ rounds }: { rounds: RoundRecord[] }) {
  const data = rounds.map((r) => ({
    round: `R${r.roundIndex}`,
    recall: Math.round(r.evaluation.overall.recall * 1000) / 10,
    evasionRate:
      r.evaluation.overall.confusion.false_negative > 0 ||
      r.evaluation.overall.confusion.true_positive > 0
        ? Math.round(
            (r.evaluation.overall.confusion.false_negative /
              Math.max(
                1,
                r.evaluation.overall.confusion.false_negative +
                  r.evaluation.overall.confusion.true_positive,
              )) *
              1000,
          ) / 10
        : 0,
  }));

  const ariaLabel =
    "Detector recall and fraud evasion rate by round, percent. " +
    data.map((d) => `${d.round}: recall ${d.recall}, evasion ${d.evasionRate}`).join("; ") +
    ".";

  return (
    <div role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 16, right: 16, left: 4, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="round"
            tick={{ fontSize: 12, fill: "var(--color-ink-muted)" }}
            axisLine={{ stroke: "var(--color-border)" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 12, fill: "var(--color-ink-muted)" }}
            axisLine={false}
            tickLine={false}
            domain={[0, 100]}
            unit="%"
            width={48}
          />
          <Tooltip
            contentStyle={CHART_TOOLTIP_STYLE}
            itemStyle={CHART_TOOLTIP_ITEM_STYLE}
            labelStyle={CHART_TOOLTIP_LABEL_STYLE}
            formatter={(value) => `${value}%`}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
isAnimationActive={false}             type="monotone"
            dataKey="recall"
            name="Detector recall"
            stroke="var(--color-defend-600)"
            strokeWidth={2}
            dot={{ r: 3 }}
          >
            <LabelList dataKey="recall" position="top" style={{ fontSize: 10, fill: "var(--color-ink-faint)" }} />
          </Line>
          <Line
isAnimationActive={false}             type="monotone"
            dataKey="evasionRate"
            name="Fraud evasion rate"
            stroke="var(--color-attack-600)"
            strokeWidth={2}
            dot={{ r: 3 }}
          >
            <LabelList dataKey="evasionRate" position="bottom" style={{ fontSize: 10, fill: "var(--color-ink-faint)" }} />
          </Line>
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
