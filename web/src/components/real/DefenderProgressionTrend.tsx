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
import type { ModelComparisonDTO } from "../../api/types";

const toPct = (value: number | null | undefined): number | null =>
  value == null ? null : Math.round(value * 1000) / 10;

const LINES = [
  { key: "Precision", stroke: "var(--color-defend-600)" },
  { key: "Recall", stroke: "var(--color-attack-600)" },
  { key: "F1", stroke: "var(--color-ink-muted)" },
] as const;

/**
 * v1 -> v2 -> v3 for the three rate metrics on one zoomed axis, so "what
 * moved" reads in a glance: cross-family hardening nudged precision and F1
 * up, recall dipped at v2 and only partly recovered. FPR is on its own
 * scale (~0.02%) and stays in the per-version cards below.
 */
export function DefenderProgressionTrend({ comparison }: { comparison: ModelComparisonDTO }) {
  const { baseline_v1: v1, defender_v2: v2, defender_v3: v3 } = comparison;
  if (!v1 || !v2 || !v3) return null;

  const data = [
    { v: "v1", Precision: toPct(v1.precision), Recall: toPct(v1.recall), F1: toPct(v1.f1) },
    { v: "v2", Precision: toPct(v2.precision), Recall: toPct(v2.recall), F1: toPct(v2.f1) },
    { v: "v3", Precision: toPct(v3.precision), Recall: toPct(v3.recall), F1: toPct(v3.f1) },
  ];

  const values = data
    .flatMap((row) => [row.Precision, row.Recall, row.F1])
    .filter((x): x is number => x != null);
  const low = Math.max(0, Math.floor(Math.min(...values) / 5) * 5 - 2);
  const high = Math.min(100, Math.ceil(Math.max(...values) / 5) * 5 + 2);

  const ariaLabel =
    "Defender progression v1 to v3, percent. " +
    LINES.map(
      ({ key }) => `${key}: ${data.map((row) => row[key as "Precision"]).join(", ")}`,
    ).join("; ") +
    ".";

  return (
    <div role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 18, right: 20, left: 4, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="v"
            tick={{ fontSize: 12, fill: "var(--color-ink-muted)" }}
            axisLine={{ stroke: "var(--color-border)" }}
            tickLine={false}
          />
          <YAxis
            domain={[low, high]}
            unit="%"
            width={48}
            tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={CHART_TOOLTIP_STYLE}
            itemStyle={CHART_TOOLTIP_ITEM_STYLE}
            labelStyle={CHART_TOOLTIP_LABEL_STYLE}
            formatter={(value) => `${value}%`}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {LINES.map(({ key, stroke }) => (
            <Line isAnimationActive={false} key={key} type="monotone" dataKey={key} stroke={stroke} strokeWidth={2} dot={{ r: 3 }}>
              <LabelList
                dataKey={key}
                position="top"
                style={{ fontSize: 10, fill: "var(--color-ink-faint)" }}
              />
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
