import type { RoundRecord } from "../../mock/loopSimulator";

export function RoundStepper({ rounds, activeIndex }: { rounds: RoundRecord[]; activeIndex: number }) {
  const total = 6;
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }, (_, i) => {
        const done = i < rounds.length;
        const isActive = i === activeIndex;
        return (
          <div key={i} className="flex flex-1 items-center gap-2">
            <div
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-semibold transition-standard ${
                isActive
                  ? "border-[var(--color-accent-600)] bg-[var(--color-accent-600)] text-white"
                  : done
                    ? "border-[var(--color-defend-600)] bg-[var(--color-defend-100)] text-[var(--color-defend-600)]"
                    : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-ink-faint)]"
              }`}
            >
              {i}
            </div>
            {i < total - 1 && (
              <div className={`h-px flex-1 ${done ? "bg-[var(--color-defend-600)]" : "bg-[var(--color-border)]"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
