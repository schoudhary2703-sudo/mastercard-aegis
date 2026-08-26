import type { ReplayCounters } from "./useReplay";

/**
 * The four numbers a judge should be able to read at a glance during a
 * replay. Values are the running counts of what is actually on screen, so
 * they always reconcile with the stream beside them.
 */
export function ScoreBoard({ counters }: { counters: ReplayCounters }) {
  const cells = [
    { label: "Fraud", value: counters.fraudSeen, tone: "neutral" as const },
    { label: "Caught", value: counters.caught, tone: "good" as const },
    { label: "Escaped", value: counters.escaped, tone: "bad" as const },
    {
      label: "Recall",
      value: counters.recall === null ? "—" : `${(counters.recall * 100).toFixed(0)}%`,
      tone: "neutral" as const,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {cells.map((c) => (
        <div
          key={c.label}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5 text-center"
        >
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
            {c.label}
          </p>
          <p
            className={`mt-0.5 text-xl font-bold tabular-nums sm:text-2xl ${
              c.tone === "good"
                ? "text-[var(--color-risk-low-600)]"
                : c.tone === "bad"
                  ? "text-[var(--color-risk-high-600)]"
                  : "text-[var(--color-ink)]"
            }`}
          >
            {c.value}
          </p>
        </div>
      ))}
    </div>
  );
}
