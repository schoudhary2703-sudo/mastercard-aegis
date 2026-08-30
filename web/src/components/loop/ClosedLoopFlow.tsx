import type { ReactNode } from "react";

/**
 * The one central visual: how a GenAI-reasoned attack becomes a scored
 * transaction and then the next generation's bounded mutation.
 *
 * Two orthogonal distinctions are carried visually on purpose, because both
 * are architectural claims this project makes and neither survives being
 * demoted to a caption:
 *
 * * **Team** -- Red Team owns everything that proposes or produces an attack;
 *   Blue Team owns scoring and the caught/escaped outcome. Uses the existing
 *   `--color-attack-*` / `--color-defend-*` tokens, which
 *   `docs/UI_DESIGN_SYSTEM.md` reserves for exactly this attribution.
 * * **Reasoning vs. deterministic** -- GenAI reasons at two points and never
 *   emits a transaction row; deterministic code produces every number.
 *
 * `compact` keeps the original single-row chip strip used by Attack Lab (where
 * the surrounding replay already supplies the narrative). The full form adds
 * per-stage notes, the closing arrow, and the LOAFO sidecar.
 *
 * Everything here is static copy -- no API call, no artifact read -- so it
 * renders immediately on a cold backend.
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

type Team = "red" | "blue";

interface Stage {
  id: LoopStageId;
  label: string;
  /** Short label for the compact chip strip. */
  shortLabel: string;
  team: Team;
  /** True when a language model reasons at this stage. */
  genai: boolean;
  note: string;
}

const STAGES: Stage[] = [
  {
    id: "genai_attack",
    label: "GenAI Attack Analyst",
    shortLabel: "GenAI Attack Analyst",
    team: "red",
    genai: true,
    note: "Turns researched fraud taxonomy into a structured attack hypothesis.",
  },
  {
    id: "blueprint",
    label: "Structured Blueprint",
    shortLabel: "Structured Blueprint",
    team: "red",
    genai: false,
    note: "Bounded simulator parameters, validated against a frozen contract.",
  },
  {
    id: "simulator",
    label: "Deterministic Simulator",
    shortLabel: "Deterministic Simulator",
    team: "red",
    genai: false,
    note: "Writes every transaction row. Seeded, reproducible, never GenAI.",
  },
  {
    id: "defender",
    label: "XGBoost Defender",
    shortLabel: "XGBoost Defender",
    team: "blue",
    genai: false,
    note: "Scores each transaction with decision-time-safe features only.",
  },
  {
    id: "outcome",
    label: "Caught / Escaped",
    shortLabel: "Caught / Escaped",
    team: "blue",
    genai: false,
    note: "Fraud that escaped is the blind-spot signal the next round reads.",
  },
  {
    id: "genai_blindspot",
    label: "GenAI Blind-Spot Analyst",
    shortLabel: "GenAI Blind-Spot Analyst",
    team: "red",
    genai: true,
    note: "Reads the real misses and the risk scores actually assigned.",
  },
  {
    id: "mutation",
    label: "Bounded Mutation Proposal",
    shortLabel: "Bounded Mutation",
    team: "red",
    // Not a third GenAI call: this is the Blind-Spot Analyst's already-returned
    // output being bounds-checked and applied by deterministic code. Marking it
    // as a reasoning stage would contradict "a language model reasons at exactly
    // two points", which is the architectural claim the diagram exists to carry.
    genai: false,
    note: "The Blind-Spot Analyst's proposal, bounds-checked and applied by deterministic code. Out-of-bounds proposals are rejected, never clamped.",
  },
  {
    id: "next_gen",
    label: "Deterministic Next Generation",
    shortLabel: "Next Generation",
    team: "red",
    genai: false,
    note: "The simulator -- not the model -- generates the next scenario.",
  },
];

const TEAM_IDLE: Record<Team, string> = {
  red: "border-[var(--color-attack-100)] bg-[var(--color-attack-100)]/50 text-[var(--color-attack-600)]",
  blue: "border-[var(--color-defend-100)] bg-[var(--color-defend-100)]/60 text-[var(--color-defend-600)]",
};

const TEAM_ACTIVE: Record<Team, string> = {
  red: "border-[var(--color-attack-500)] bg-[var(--color-attack-100)] text-[var(--color-attack-600)] shadow-[var(--shadow-elevated)]",
  blue: "border-[var(--color-defend-500)] bg-[var(--color-defend-100)] text-[var(--color-defend-600)] shadow-[var(--shadow-elevated)]",
};

const TEAM_LABEL: Record<Team, string> = { red: "Red Team", blue: "Blue Team" };

export function ClosedLoopFlow({
  active,
  compact = false,
}: {
  active?: LoopStageId;
  compact?: boolean;
}) {
  if (compact) return <CompactStrip active={active} />;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px]">
        <TeamKey team="red" />
        <TeamKey team="blue" />
        <span className="inline-flex items-center gap-1.5 text-[var(--color-ink-faint)]">
          <span aria-hidden="true">&#9679;</span> GenAI reasons
        </span>
        <span className="inline-flex items-center gap-1.5 text-[var(--color-ink-faint)]">
          <span aria-hidden="true">&#9675;</span> Deterministic code produces every number
        </span>
      </div>

      <ol
        aria-label="AEGIS closed loop"
        className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4"
      >
        {STAGES.map((stage, i) => {
          const isActive = stage.id === active;
          return (
            <li
              key={stage.id}
              aria-current={isActive ? "step" : undefined}
              className={`rounded-lg border p-2.5 transition-standard ${
                isActive ? TEAM_ACTIVE[stage.team] : TEAM_IDLE[stage.team]
              }`}
            >
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-bold tabular-nums opacity-60">{i + 1}</span>
                <span aria-hidden="true" className="text-[9px]">
                  {stage.genai ? "●" : "○"}
                </span>
                <span className="text-[11px] font-semibold leading-tight sm:text-xs">
                  {stage.label}
                </span>
              </div>
              <p className="mt-1 text-[10px] leading-snug text-[var(--color-ink-muted)]">
                {stage.note}
              </p>
            </li>
          );
        })}
      </ol>

      <p className="mt-2 flex items-start gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-2.5 py-2 text-[11px] leading-snug text-[var(--color-ink-muted)]">
        <span aria-hidden="true" className="text-[var(--color-ink-faint)]">
          &#8634;
        </span>
        <span>
          <strong className="text-[var(--color-ink)]">The loop closes.</strong> Stage 8 feeds back
          into stage 4 &mdash; the next generation is scored by the same frozen defender, and
          whatever escapes becomes the next round&rsquo;s blind-spot evidence.
        </span>
      </p>

      <div className="mt-2 rounded-lg border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-sunken)] px-2.5 py-2">
        <p className="text-[11px] font-semibold text-[var(--color-ink)]">
          LOAFO &mdash; a separate generalization test, not a loop stage
        </p>
        <p className="mt-0.5 text-[11px] leading-snug text-[var(--color-ink-muted)]">
          Hold one attack family out of training entirely, then score the defender on a fresh
          scenario of that held-out family. It measures whether hardening{" "}
          <em>transfers to an attack the model has never seen</em>, rather than whether it
          memorized the attacks it was shown. LOAFO generates no attacks and proposes no
          mutations.
        </p>
      </div>
    </div>
  );
}

/** The original single-row chip strip. Kept for Attack Lab's inline use. */
function CompactStrip({ active }: { active?: LoopStageId }) {
  return (
    <ol className="flex flex-wrap items-stretch gap-1.5" aria-label="AEGIS closed loop">
      {STAGES.map((stage, i) => {
        const isActive = stage.id === active;
        return (
          <li key={stage.id} className="flex items-center gap-1.5">
            <div
              aria-current={isActive ? "step" : undefined}
              className={`rounded-lg border px-2.5 py-1.5 text-center text-[11px] font-medium leading-tight transition-standard sm:text-xs ${
                isActive ? TEAM_ACTIVE[stage.team] : TEAM_IDLE[stage.team]
              }`}
            >
              {stage.shortLabel}
            </div>
            {i < STAGES.length - 1 ? (
              <span aria-hidden="true" className="text-xs text-[var(--color-ink-faint)]">
                &rarr;
              </span>
            ) : (
              <span
                aria-hidden="true"
                title="The loop closes"
                className="text-xs text-[var(--color-ink-faint)]"
              >
                &#8634;
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function TeamKey({ team }: { team: Team }): ReactNode {
  return (
    <span className="inline-flex items-center gap-1.5 text-[var(--color-ink-muted)]">
      <span
        aria-hidden="true"
        className={`inline-block h-2.5 w-2.5 rounded-sm border ${
          team === "red"
            ? "border-[var(--color-attack-500)] bg-[var(--color-attack-100)]"
            : "border-[var(--color-defend-500)] bg-[var(--color-defend-100)]"
        }`}
      />
      <strong className="font-semibold text-[var(--color-ink)]">{TEAM_LABEL[team]}</strong>
      {team === "red" ? "proposes and produces attacks" : "scores and is measured"}
    </span>
  );
}
