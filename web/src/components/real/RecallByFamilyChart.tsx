import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_TOOLTIP_STYLE, CHART_TOOLTIP_ITEM_STYLE, CHART_TOOLTIP_LABEL_STYLE } from "../ui/chartTheme";
import type { FreshFamilyPerformanceDTO } from "../../api/types";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../../types/aegis";

const SERIES_V3 = "Defender v3 (trained on this family)";
const SERIES_LOAFO = "LOAFO (family held out)";

function familyLabel(family: string): string {
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family;
}

function toPct(value: number | null | undefined): number {
  return Math.round((value ?? 0) * 1000) / 10;
}

/**
 * Defender v3's recall on each family's fresh scenario, next to that same
 * scenario's LOAFO fold recall (trained without that family at all) --
 * memorization vs. genuine generalization, side by side. Both series come
 * straight from `fresh_family_performance`; nothing is computed here beyond
 * unit conversion (fraction -> percent).
 */
export function RecallByFamilyChart({ families }: { families: FreshFamilyPerformanceDTO[] }) {
  const data = families.map((f) => ({
    family: familyLabel(f.attack_family),
    [SERIES_V3]: toPct(f.defender_v3.recall),
    [SERIES_LOAFO]: toPct(f.fold_model.recall),
  }));

  const ariaLabel =
    "Recall by attack family, percent. " +
    data
      .map((d) => `${d.family}: Defender v3 ${d[SERIES_V3]}, LOAFO held-out ${d[SERIES_LOAFO]}`)
      .join("; ") +
    ".";

  return (
    <figure className="m-0" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart
          data={data}
          margin={{ top: 18, right: 16, left: 4, bottom: 0 }}
          barGap={2}
          barCategoryGap="26%"
        >
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="family"
            tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }}
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
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar isAnimationActive={false} dataKey={SERIES_V3} fill="var(--color-defend-600)" radius={[4, 4, 0, 0]}>
            <LabelList
              dataKey={SERIES_V3}
              position="top"
              formatter={(value) => `${Math.round(Number(value))}`}
              style={{ fontSize: 10, fontWeight: 600, fill: "var(--color-ink-muted)" }}
            />
          </Bar>
          <Bar isAnimationActive={false} dataKey={SERIES_LOAFO} fill="var(--color-attack-600)" radius={[4, 4, 0, 0]}>
            <LabelList
              dataKey={SERIES_LOAFO}
              position="top"
              formatter={(value) => `${Math.round(Number(value))}`}
              style={{ fontSize: 10, fontWeight: 600, fill: "var(--color-ink-muted)" }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <figcaption className="mt-2 text-xs text-[var(--color-ink-muted)]">
        Teal is Defender v3 scoring a family it was trained on; orange is a fold trained with that
        family fully held out. Where orange collapses toward zero (mule-network structuring),
        hardening did not transfer — the model needs that family's own examples.
      </figcaption>
    </figure>
  );
}
