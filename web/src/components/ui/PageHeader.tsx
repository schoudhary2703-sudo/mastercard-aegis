import type { ReactNode } from "react";

/**
 * Every screen opens with a claim, not a category label: a tracked-out
 * eyebrow, one thesis headline, one plain sentence of what follows.
 */
export function PageHeader({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow: string;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-5">
      <div className="max-w-[62ch]">
        <p className="t-eyebrow text-[var(--color-accent-500)]">{eyebrow}</p>
        <h1 className="t-display mt-3 text-[var(--color-ink)]">{title}</h1>
        {children && (
          <p className="t-body mt-3.5 text-[var(--color-ink-muted)]">{children}</p>
        )}
      </div>
      {actions && <div className="shrink-0 pt-1">{actions}</div>}
    </header>
  );
}

/**
 * Section lead inside a page. The takeaway goes in `title` -- a judge should
 * be able to read only the section headings and still get the argument.
 */
export function SectionHeader({
  eyebrow,
  title,
  actions,
  children,
}: {
  eyebrow?: string;
  title: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="max-w-[58ch]">
        {eyebrow && <p className="t-eyebrow mb-2 text-[var(--color-ink-faint)]">{eyebrow}</p>}
        <h2 className="t-h1 text-[var(--color-ink)]">{title}</h2>
        {children && (
          <p className="t-body-sm mt-2 text-[var(--color-ink-muted)]">{children}</p>
        )}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}
