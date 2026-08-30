/**
 * One consistent "this is real, and here is where it came from" marker.
 *
 * Used everywhere a section is backed by a persisted pipeline artifact, so a
 * judge learns the shape once. `source` is an optional artifact path shown in
 * mono after the label.
 */
export function ProvenanceChip({
  source,
  label = "Real pipeline data",
  className = "",
}: {
  source?: string;
  label?: string;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1.5 rounded-full border border-[var(--color-defend-100)] bg-[var(--color-defend-100)]/50 px-2 py-0.5 text-[10px] font-medium text-[var(--color-defend-600)] ${className}`}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-defend-500)]" />
      <span className="shrink-0">{label}</span>
      {source && (
        <span className="truncate font-mono text-[var(--color-ink-faint)]" title={source}>
          · {source}
        </span>
      )}
    </span>
  );
}
