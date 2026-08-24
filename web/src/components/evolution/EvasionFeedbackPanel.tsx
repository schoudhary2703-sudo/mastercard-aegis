import { Badge } from "../ui/Badge";
import type { EvasionFeedback } from "../../types/aegis";

const DIRECTION_ARROW: Record<string, string> = {
  increase: "↑",
  decrease: "↓",
  set: "=",
  jitter: "~",
  resample: "↻",
};

export function EvasionFeedbackPanel({ feedback }: { feedback: EvasionFeedback }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={feedback.evaded ? "attack" : "defend"}>
          {feedback.evaded ? "Evasion detected" : "No credible evasion"}
        </Badge>
        <Badge variant="neutral">avg detector score {(feedback.detector_score * 100).toFixed(0)}%</Badge>
        <Badge variant="neutral">realism {(feedback.realism_score * 100).toFixed(0)}%</Badge>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Signals the detector keyed on
        </p>
        <div className="flex flex-wrap gap-1.5">
          {feedback.important_signals.map((s) => (
            <span
              key={s}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-sunken)] px-2 py-1 font-mono text-[11px] text-[var(--color-ink-muted)]"
            >
              {s}
            </span>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-faint)]">
          Proposed mutations for next generation
        </p>
        <div className="space-y-1.5">
          {feedback.suggested_mutations.map((m) => (
            <div
              key={m.parameter}
              className="flex items-center justify-between rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm"
            >
              <div>
                <span className="font-medium text-[var(--color-ink)]">{m.parameter}</span>
                <span className="ml-2 text-xs text-[var(--color-ink-muted)]">{m.rationale}</span>
              </div>
              <div className="flex shrink-0 items-center gap-2 text-xs">
                <span className="font-mono text-[var(--color-ink-faint)]">{String(m.current_value)}</span>
                <span className="text-[var(--color-attack-600)]">{DIRECTION_ARROW[m.direction]}</span>
                <span className="font-mono font-semibold text-[var(--color-ink)]">{String(m.proposed_value)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
