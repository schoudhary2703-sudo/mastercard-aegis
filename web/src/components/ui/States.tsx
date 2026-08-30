import type { ReactNode } from "react";

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-sunken)] px-6 py-14 text-center">
      <p className="text-sm font-semibold text-[var(--color-ink)]">{title}</p>
      <p className="mt-1.5 max-w-sm text-sm text-[var(--color-ink-muted)]">{body}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", body }: { title?: string; body: string }) {
  return (
    <div className="flex flex-col items-start rounded-xl border border-[var(--color-risk-high-100)] bg-[var(--color-risk-high-100)]/40 px-5 py-4">
      <p className="text-sm font-semibold text-[var(--color-risk-high-600)]">{title}</p>
      <p className="mt-1 text-sm text-[var(--color-ink-muted)]">{body}</p>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-[var(--color-surface-sunken)] ${className}`} />;
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-[var(--color-border-strong)] border-t-transparent ${className}`}
    />
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}
