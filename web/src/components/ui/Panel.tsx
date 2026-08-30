import type { HTMLAttributes, ReactNode } from "react";

type Variant = "default" | "hero" | "callout" | "warn";

const SURFACE: Record<Variant, string> = {
  default:
    "rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-card)]",
  hero: "rounded-2xl border border-[var(--color-border-strong)] bg-[var(--color-surface)] shadow-[var(--shadow-elevated)]",
  callout:
    "rounded-r-xl border border-l-2 border-[var(--color-border)] border-l-[var(--color-accent-500)] bg-[var(--color-surface-sunken)]",
  warn: "rounded-r-xl border border-l-2 border-[var(--color-border)] border-l-[var(--color-risk-medium-600)] bg-[var(--color-surface-sunken)]",
};

const PADDING: Record<Variant, string> = {
  default: "p-5 sm:p-6",
  hero: "p-6 sm:p-7",
  callout: "px-4 py-3.5 sm:px-5",
  warn: "px-4 py-3.5 sm:px-5",
};

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  variant?: Variant;
  padded?: boolean;
}

/**
 * Every bounded surface in the app. `hero` is the one lead panel per screen;
 * `callout` / `warn` carry a caveat as a first-class element rather than a
 * footnote or a disclosure.
 */
export function Panel({
  children,
  variant = "default",
  padded = true,
  className = "",
  ...rest
}: PanelProps) {
  return (
    <div className={`${SURFACE[variant]} ${padded ? PADDING[variant] : ""} ${className}`} {...rest}>
      {children}
    </div>
  );
}

/** Eyebrow + body, for a caveat panel. */
export function Callout({
  eyebrow,
  tone = "note",
  children,
}: {
  eyebrow: string;
  tone?: "note" | "warn";
  children: ReactNode;
}) {
  return (
    <Panel variant={tone === "warn" ? "warn" : "callout"}>
      <p
        className={`t-eyebrow ${
          tone === "warn"
            ? "text-[var(--color-risk-medium-600)]"
            : "text-[var(--color-accent-500)]"
        }`}
      >
        {eyebrow}
      </p>
      <div className="t-body-sm mt-2 text-[var(--color-ink-muted)]">{children}</div>
    </Panel>
  );
}
