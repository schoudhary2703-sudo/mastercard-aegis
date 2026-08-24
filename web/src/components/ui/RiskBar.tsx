export function RiskBar({ score }: { score: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, score)) * 100);
  const color =
    pct >= 65 ? "var(--color-risk-high-600)" : pct >= 40 ? "var(--color-risk-medium-600)" : "var(--color-risk-low-600)";

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--color-surface-sunken)]">
        <div
          className="h-full rounded-full transition-standard"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="w-9 text-right text-xs font-medium tabular-nums text-[var(--color-ink-muted)]">{pct}%</span>
    </div>
  );
}
