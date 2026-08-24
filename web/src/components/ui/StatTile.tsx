import type { ReactNode } from "react";

interface StatTileProps {
  label: string;
  value: ReactNode;
  delta?: { direction: "up" | "down" | "flat"; label: string };
  tone?: "neutral" | "positive" | "risk";
  hint?: string;
}

const DELTA_COLOR: Record<NonNullable<StatTileProps["delta"]>["direction"], string> = {
  up: "text-[var(--color-risk-low-600)]",
  down: "text-[var(--color-risk-high-600)]",
  flat: "text-[var(--color-ink-faint)]",
};

const DELTA_ARROW: Record<NonNullable<StatTileProps["delta"]>["direction"], string> = {
  up: "↑",
  down: "↓",
  flat: "→",
};

export function StatTile({ label, value, delta, tone = "neutral", hint }: StatTileProps) {
  const valueColor =
    tone === "positive"
      ? "text-[var(--color-risk-low-600)]"
      : tone === "risk"
        ? "text-[var(--color-risk-high-600)]"
        : "text-[var(--color-ink)]";

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-[var(--shadow-card)]">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-ink-faint)]">{label}</p>
      <p className={`mt-1.5 text-2xl font-semibold tabular-nums ${valueColor}`}>{value}</p>
      {delta && (
        <p className={`mt-1 text-xs font-medium ${DELTA_COLOR[delta.direction]}`}>
          {DELTA_ARROW[delta.direction]} {delta.label}
        </p>
      )}
      {hint && <p className="mt-1 text-xs text-[var(--color-ink-faint)]">{hint}</p>}
    </div>
  );
}
