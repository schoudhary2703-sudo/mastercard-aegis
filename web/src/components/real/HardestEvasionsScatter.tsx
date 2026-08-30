import {
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { CHART_TOOLTIP_STYLE, CHART_TOOLTIP_ITEM_STYLE, CHART_TOOLTIP_LABEL_STYLE } from "../ui/chartTheme";
import type { HardestEvasionDTO } from "../../api/types";
import { ATTACK_FAMILY_LABEL, type AttackFamily } from "../../types/aegis";

/** Category hues — team/attribution colours, not the risk traffic-light. */
const FAMILY_FILL: Record<string, string> = {
  synthetic_identity_bustout: "var(--color-attack-600)",
  mule_network_structuring: "var(--color-accent-500)",
  adaptive_detector_evasion: "var(--color-ink-muted)",
};

function familyLabel(family: string): string {
  return ATTACK_FAMILY_LABEL[family as AttackFamily] ?? family.replace(/_/g, " ");
}

interface Point {
  x: number;
  y: number;
  z: number;
  txn: string;
}

/**
 * Every surviving evasion as one point: risk score (x) vs fidelity (y),
 * sized by hardness, coloured by family. Makes the shape of the failure
 * legible -- where the points sit and which family they belong to -- in a
 * way a 13-row table does not.
 */
export function HardestEvasionsScatter({ evasions }: { evasions: HardestEvasionDTO[] }) {
  const usable = evasions.filter(
    (e) => e.fidelity_score != null && e.hardness_score != null,
  );
  if (usable.length < 2) return null;

  const families = Array.from(new Set(usable.map((e) => e.attack_family)));
  const seriesByFamily = families.map((family) => ({
    family,
    fill: FAMILY_FILL[family] ?? "var(--color-ink-muted)",
    points: usable
      .filter((e) => e.attack_family === family)
      .map<Point>((e) => ({
        x: Math.round(e.detector_risk_score * 1000) / 10,
        y: Math.round((e.fidelity_score ?? 0) * 1000) / 10,
        z: e.hardness_score ?? 0,
        txn: e.transaction_id,
      })),
  }));

  const counts = families
    .map((f) => ({ f, n: usable.filter((e) => e.attack_family === f).length }))
    .sort((a, b) => b.n - a.n);
  const dominant = counts[0];

  const ariaLabel =
    `Scatter of ${usable.length} surviving evasions: risk score versus fidelity, sized by hardness. ` +
    counts.map((c) => `${familyLabel(c.f)}: ${c.n}`).join("; ") +
    ".";

  return (
    <figure className="m-0" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{ top: 12, right: 20, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            type="number"
            dataKey="x"
            name="Risk score"
            unit="%"
            domain={[0, "dataMax"]}
            tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }}
            axisLine={{ stroke: "var(--color-border)" }}
            tickLine={false}
            label={{
              value: "Detector risk score",
              position: "insideBottom",
              offset: -2,
              fontSize: 11,
              fill: "var(--color-ink-faint)",
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Fidelity"
            unit="%"
            domain={[0, 100]}
            width={48}
            tick={{ fontSize: 11, fill: "var(--color-ink-muted)" }}
            axisLine={false}
            tickLine={false}
            label={{
              value: "Fidelity",
              angle: -90,
              position: "insideLeft",
              fontSize: 11,
              fill: "var(--color-ink-faint)",
            }}
          />
          <ZAxis type="number" dataKey="z" range={[40, 320]} name="Hardness" />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            contentStyle={CHART_TOOLTIP_STYLE}
            itemStyle={CHART_TOOLTIP_ITEM_STYLE}
            labelStyle={CHART_TOOLTIP_LABEL_STYLE}
            formatter={(value, name) => (name === "Hardness" ? `${value}` : `${value}%`)}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {seriesByFamily.map((series) => (
            <Scatter
isAnimationActive={false}               key={series.family}
              name={familyLabel(series.family)}
              data={series.points}
              fill={series.fill}
              fillOpacity={0.75}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
      <figcaption className="mt-2 text-xs text-[var(--color-ink-muted)]">
        Point size is hardness. Most survivors cluster at{" "}
        <strong>low risk score and high fidelity</strong> — realistic attacks the model scored as
        clearly safe — and {dominant.n} of {usable.length} are {familyLabel(dominant.f)}.
      </figcaption>
    </figure>
  );
}
