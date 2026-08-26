import type { ReplayEventDTO } from "../../api/types";

/**
 * The transaction stream: one row per scored transaction, with the verdict
 * read straight off the artifact.
 *
 * Only fraud rows get a CAUGHT/ESCAPED badge -- a legitimate warm-up
 * transaction that was approved is neither, and badging it would inflate the
 * apparent size of the result.
 */

function riskTone(score: number): string {
  if (score >= 0.65) return "text-[var(--color-risk-high-600)]";
  if (score >= 0.4) return "text-[var(--color-risk-medium-600)]";
  return "text-[var(--color-risk-low-600)]";
}

function riskBarColor(score: number): string {
  if (score >= 0.65) return "bg-[var(--color-risk-high-600)]";
  if (score >= 0.4) return "bg-[var(--color-risk-medium-600)]";
  return "bg-[var(--color-risk-low-600)]";
}

export function OutcomeBadge({ caught }: { caught: boolean }) {
  return caught ? (
    <span className="inline-flex shrink-0 items-center rounded-md bg-[var(--color-risk-low-100)] px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-[var(--color-risk-low-600)]">
      Caught
    </span>
  ) : (
    <span className="inline-flex shrink-0 items-center rounded-md bg-[var(--color-risk-high-100)] px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-[var(--color-risk-high-600)]">
      Escaped
    </span>
  );
}

function shortId(id: string): string {
  const parts = id.split("-");
  return parts.length > 3 ? `…${parts.slice(-3).join("-")}` : id;
}

export function ReplayStream({
  events,
  emptyLabel = "Press Run to replay this experiment.",
}: {
  events: ReplayEventDTO[];
  emptyLabel?: string;
}) {
  if (events.length === 0) {
    return (
      <div className="flex min-h-[140px] items-center justify-center rounded-lg border border-dashed border-[var(--color-border-strong)] p-6 text-center text-xs text-[var(--color-ink-faint)]">
        {emptyLabel}
      </div>
    );
  }

  return (
    <ul className="max-h-[380px] space-y-1.5 overflow-y-auto pr-1">
      {events.map((e) => (
        <li
          key={e.transaction_id}
          className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${
            e.is_fraud
              ? e.caught
                ? "border-[var(--color-risk-low-100)] bg-[var(--color-risk-low-100)]/35"
                : "border-[var(--color-risk-high-100)] bg-[var(--color-risk-high-100)]/35"
              : "border-[var(--color-border)] bg-[var(--color-surface)]"
          }`}
        >
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-[11px] text-[var(--color-ink-muted)]">
              {shortId(e.transaction_id)}
            </p>
            <div className="mt-1 flex items-center gap-2">
              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--color-border)] sm:w-24">
                <div
                  className={`h-full rounded-full ${riskBarColor(e.risk_score)}`}
                  style={{ width: `${Math.max(2, Math.min(100, e.risk_score * 100))}%` }}
                />
              </div>
              <span className={`text-xs font-semibold tabular-nums ${riskTone(e.risk_score)}`}>
                {(e.risk_score * 100).toFixed(1)}%
              </span>
              <span className="hidden text-[11px] capitalize text-[var(--color-ink-faint)] sm:inline">
                {e.action.replace(/_/g, " ")}
              </span>
            </div>
          </div>
          {e.is_fraud ? (
            <OutcomeBadge caught={e.caught} />
          ) : (
            <span className="shrink-0 text-[11px] text-[var(--color-ink-faint)]">legit</span>
          )}
        </li>
      ))}
    </ul>
  );
}
