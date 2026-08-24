import type { ConfusionCounts } from "../../types/aegis";

export function ConfusionMatrix({ counts }: { counts: ConfusionCounts }) {
  const cells = [
    { label: "True positive", value: counts.true_positive, tone: "risk-low-100", text: "risk-low-600" },
    { label: "False positive", value: counts.false_positive, tone: "risk-medium-100", text: "risk-medium-600" },
    { label: "False negative", value: counts.false_negative, tone: "risk-high-100", text: "risk-high-600" },
    { label: "True negative", value: counts.true_negative, tone: "surface-sunken", text: "ink-muted" },
  ];

  return (
    <div className="grid grid-cols-2 gap-2">
      {cells.map((c) => (
        <div
          key={c.label}
          className="rounded-lg border border-[var(--color-border)] px-3 py-3 text-center"
          style={{ background: `var(--color-${c.tone})` }}
        >
          <p className="text-xl font-semibold tabular-nums" style={{ color: `var(--color-${c.text})` }}>
            {c.value}
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--color-ink-muted)]">{c.label}</p>
        </div>
      ))}
    </div>
  );
}
