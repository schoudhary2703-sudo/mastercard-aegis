import type { ReactNode } from "react";

/**
 * Progressive disclosure for methodology.
 *
 * The judge-facing surface stays short by default; everything that used to
 * be a paragraph of standing body text lives behind one of these instead.
 * Native <details> so it works without JS state and stays keyboard- and
 * screen-reader-accessible.
 */
export function Details({
  summary,
  children,
  className = "",
}: {
  summary: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details
      className={`group rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-sunken)] ${className}`}
    >
      <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-[var(--color-ink-muted)] transition-standard hover:text-[var(--color-ink)]">
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block text-[10px] transition-standard group-open:rotate-90"
          >
            ▶
          </span>
          {summary}
        </span>
      </summary>
      <div className="border-t border-[var(--color-border)] px-3 py-2.5 text-xs leading-relaxed text-[var(--color-ink-muted)]">
        {children}
      </div>
    </details>
  );
}

/**
 * A short label with a hover/focus explanation. Used to keep a metric name
 * to one or two words while its definition stays one interaction away.
 */
export function InfoTip({ label, tip }: { label: ReactNode; tip: string }) {
  return (
    <span
      title={tip}
      tabIndex={0}
      className="cursor-help border-b border-dotted border-[var(--color-ink-faint)] focus-visible:outline-2"
    >
      {label}
    </span>
  );
}
