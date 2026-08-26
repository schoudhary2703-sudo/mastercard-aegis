import type { ReactNode } from "react";

/**
 * The one central visual: how a GenAI-reasoned attack becomes a scored
 * transaction and then the next generation's mutation.
 *
 * Stage ids are stable so callers can highlight whichever stage a replay is
 * currently at. Reasoning stages (GenAI) and deterministic stages are given
 * different treatments on purpose -- that distinction is the architectural
 * claim this project makes, so the diagram has to carry it visually rather
 * than in a caption.
 */

export type LoopStageId =
  | "genai_attack"
  | "blueprint"
  | "simulator"
  | "defender"
  | "outcome"
  | "genai_blindspot"
  | "mutation"
  | "next_gen";

type Kind = "genai" | "deterministic" | "outcome";

interface Stage {
  id: LoopStageId;
  label: string;
  kind: Kind;
}

const STAGES: Stage[] = [
  { id: "genai_attack", label: "GenAI Attack Analyst", kind: "genai" },
  { id: "blueprint", label: "Structured Blueprint", kind: "deterministic" },
  { id: "simulator", label: "Deterministic Simulator", kind: "deterministic" },
  { id: "defender", label: "XGBoost Defender", kind: "deterministic" },
  { id: "outcome", label: "Caught / Escaped", kind: "outcome" },
  { id: "genai_blindspot", label: "GenAI Blind-Spot Analyst", kind: "genai" },
  { id: "mutation", label: "Bounded Mutation", kind: "genai" },
  { id: "next_gen", label: "Next Generation", kind: "deterministic" },
];

const KIND_IDLE: Record<Kind, string> = {
  genai: "border-[var(--color-attack-100)] bg-[var(--color-attack-100)]/40 text-[var(--color-attack-600)]",
  deterministic: "border-[var(--color-border)] bg-[var(--color-surface-sunken)] text-[var(--color-ink-muted)]",
  outcome: "border-[var(--color-border)] bg-[var(--color-surface-sunken)] text-[var(--color-ink-muted)]",
};

const KIND_ACTIVE: Record<Kind, string> = {
  genai: "border-[var(--color-attack-500)] bg-[var(--color-attack-100)] text-[var(--color-attack-600)] shadow-[var(--shadow-elevated)]",
  deterministic:
    "border-[var(--color-accent-500)] bg-[var(--color-accent-100)] text-[var(--color-accent-600)] shadow-[var(--shadow-elevated)]",
  outcome:
    "border-[var(--color-accent-500)] bg-[var(--color-accent-100)] text-[var(--color-accent-600)] shadow-[var(--shadow-elevated)]",
};

export function ClosedLoopFlow({
  active,
  compact = false,
}: {
  active?: LoopStageId;
  compact?: boolean;
}) {
  return (
    <div>
      <ol
        className={`flex flex-wrap items-stretch gap-1.5 ${compact ? "" : "gap-2"}`}
        aria-label="AEGIS closed loop"
      >
        {STAGES.map((stage, i) => {
          const isActive = stage.id === active;
          return (
            <li key={stage.id} className="flex items-center gap-1.5">
              <div
                aria-current={isActive ? "step" : undefined}
                className={`rounded-lg border px-2.5 py-1.5 text-center text-[11px] font-medium leading-tight transition-standard sm:text-xs ${
                  isActive ? KIND_ACTIVE[stage.kind] : KIND_IDLE[stage.kind]
                }`}
              >
                {stage.label}
              </div>
              {i < STAGES.length - 1 && (
                <span aria-hidden="true" className="text-xs text-[var(--color-ink-faint)]">
                  →
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {!compact && (
        <p className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[var(--color-ink-faint)]">
          <LegendSwatch className="bg-[var(--color-attack-100)] border-[var(--color-attack-500)]">
            GenAI reasons
          </LegendSwatch>
          <LegendSwatch className="bg-[var(--color-surface-sunken)] border-[var(--color-border-strong)]">
            Deterministic code produces every number
          </LegendSwatch>
        </p>
      )}
    </div>
  );
}

function LegendSwatch({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2.5 w-2.5 rounded-sm border ${className}`} />
      {children}
    </span>
  );
}
