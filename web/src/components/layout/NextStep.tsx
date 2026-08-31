import { Link, useLocation } from "react-router-dom";
import { nextStepFor } from "../../nav/journey";

/**
 * The walkthrough, self-driving.
 *
 * A judge who reaches the bottom of a screen should not have to go back to
 * the sidebar and work out where they are in the sequence. This puts the one
 * correct next screen directly under the content they just finished reading.
 */
export function NextStep() {
  const { pathname } = useLocation();
  const next = nextStepFor(pathname);
  if (!next) return null;

  return (
    <Link
      to={next.to}
      className="group flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4 transition-standard hover:border-[var(--color-accent-500)]"
    >
      <div className="min-w-0">
        <p className="t-eyebrow text-[var(--color-ink-faint)]">
          {next.step != null ? `Next · step ${next.step}` : "Next"}
        </p>
        <p className="mt-1 text-sm font-semibold text-[var(--color-ink)]">
          {next.label} — {next.hint}
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--color-ink-faint)]">
          Evidence for: {next.rubric}
        </p>
      </div>
      <span className="shrink-0 rounded-lg bg-[var(--color-accent-600)] px-4 py-2 text-sm font-semibold text-white transition-standard group-hover:bg-[var(--color-accent-500)]">
        Continue →
      </span>
    </Link>
  );
}
