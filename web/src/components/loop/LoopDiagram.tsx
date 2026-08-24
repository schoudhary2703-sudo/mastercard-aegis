export type LoopStage = "identify" | "generate" | "defend" | "evaluate" | "evolve" | "retrain";

const STAGES: { key: LoopStage; label: string; owner: "attack" | "defend" | "neutral" }[] = [
  { key: "identify", label: "Identify", owner: "attack" },
  { key: "generate", label: "Generate", owner: "attack" },
  { key: "defend", label: "Defend", owner: "defend" },
  { key: "evaluate", label: "Evaluate", owner: "neutral" },
  { key: "evolve", label: "Evolve", owner: "attack" },
  { key: "retrain", label: "Retrain", owner: "defend" },
];

const OWNER_ACTIVE: Record<(typeof STAGES)[number]["owner"], string> = {
  attack: "border-[var(--color-attack-600)] bg-[var(--color-attack-100)] text-[var(--color-attack-600)]",
  defend: "border-[var(--color-defend-600)] bg-[var(--color-defend-100)] text-[var(--color-defend-600)]",
  neutral: "border-[var(--color-ink-muted)] bg-[var(--color-surface-sunken)] text-[var(--color-ink)]",
};

export function LoopDiagram({ active, compact = false }: { active?: LoopStage; compact?: boolean }) {
  return (
    <div className="w-full">
      <div className="flex items-center">
        {STAGES.map((stage, i) => {
          const isActive = stage.key === active;
          return (
            <div key={stage.key} className="flex flex-1 items-center last:flex-none">
              <div
                className={`flex flex-1 flex-col items-center justify-center rounded-xl border px-2 text-center transition-standard ${
                  compact ? "py-2.5" : "py-4"
                } ${
                  isActive
                    ? OWNER_ACTIVE[stage.owner]
                    : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-ink-faint)]"
                }`}
              >
                <span className={`font-semibold ${compact ? "text-xs" : "text-sm"}`}>{stage.label}</span>
              </div>
              {i < STAGES.length - 1 && (
                <svg width="20" height="10" viewBox="0 0 20 10" className="mx-1 shrink-0 text-[var(--color-ink-faint)]">
                  <path d="M0 5 H14 M10 1 L14 5 L10 9" fill="none" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 text-xs text-[var(--color-ink-faint)]">
        <svg width="14" height="14" viewBox="0 0 14 14" className="shrink-0">
          <path
            d="M12 7 A5 5 0 1 1 9.5 2.8"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
          <path d="M9.5 0.5 L9.5 2.8 L11.9 3.1" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
        Retrain feeds back into Identify -- the loop closes every round.
      </div>
    </div>
  );
}
