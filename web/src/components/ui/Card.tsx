import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  padded?: boolean;
  /** `hero` = the one lead card on a screen: stronger border, real elevation. */
  variant?: "default" | "hero";
}

/**
 * Legacy surface, kept so the feature components that predate `Panel` keep
 * working. New screens should use `Panel` -- this delegates to the same
 * tokens so both stay visually identical.
 */
export function Card({
  children,
  padded = true,
  variant = "default",
  className = "",
  ...rest
}: CardProps) {
  const surface =
    variant === "hero"
      ? "rounded-2xl border-[var(--color-border-strong)] shadow-[var(--shadow-elevated)]"
      : "rounded-xl border-[var(--color-border)] shadow-[var(--shadow-card)]";
  return (
    <div
      className={`border bg-[var(--color-surface)] ${surface} ${padded ? "p-5 sm:p-6" : ""} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div className="max-w-[58ch]">
        <h3 className="t-h2 text-[var(--color-ink)]">{title}</h3>
        {subtitle && <p className="t-body-sm mt-1.5 text-[var(--color-ink-muted)]">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
