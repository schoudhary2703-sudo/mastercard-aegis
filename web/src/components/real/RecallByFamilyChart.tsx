import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FreshFamilyPerformanceDTO } from "../../api/types";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../../types/aegis";

function familyLabel(family: string): string {
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family;
}

/**
 * Defender v3's recall on each family's fresh scenario, next to that same
 * scenario's LOAFO fold recall (trained without that family at all) --
 * memorization vs. genuine generalization, side by side. Both series come
 * straight from `fresh_family_performance`; nothing is computed here beyond
 * unit conversion (fraction -> percent) for the axis.
 */
export function RecallByFamilyChart({ families }: { families: FreshFamilyPerformanceDTO[] }) {
  // Short, path-safe `dataKey`s with the human label supplied via `name`.
  // Recharts resolves `dataKey` as an object path, so long keys full of spaces
  // and parentheses are fragile; the displayed legend/tooltip text is
  // unchanged. (This was not what broke the bars -- see `isAnimationActive`
  // below.)
  const data = families.map((f) => ({
    family: familyLabel(f.attack_family),
    defenderV3: Math.round((f.defender_v3.recall ?? 0) * 1000) / 10,
    loafoFold: Math.round((f.fold_model.recall ?? 0) * 1000) / 10,
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
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
          width={40}
        />
        <Tooltip
          contentStyle={{ borderRadius: 8, border: "1px solid var(--color-border)", fontSize: 12 }}
          formatter={(value) => `${value}%`}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {/* `isAnimationActive={false}` is load-bearing, not cosmetic: with
            recharts 3.10 + React 19 the entry animation never commits inside a
            ResponsiveContainer here, so `recharts-bar-rectangles` mounted empty
            and the chart rendered grid, axes and legend but no bars at all.
            Verified against the pre-existing code -- this was already broken
            before this page was restructured. */}
        <Bar
          dataKey="defenderV3"
          isAnimationActive={false}
          name="Defender v3 (trained on this family)"
          fill="var(--color-defend-600)"
          radius={[4, 4, 0, 0]}
        />
        <Bar
          dataKey="loafoFold"
          isAnimationActive={false}
          name="LOAFO (family held out)"
          fill="var(--color-attack-600)"
          radius={[4, 4, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
