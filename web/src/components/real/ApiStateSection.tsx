import type { ReactNode } from "react";
import type { ApiResourceState } from "../../api/useApiResource";
import { EmptyState, ErrorState, SkeletonRows, Spinner } from "../ui/States";

/**
 * Renders the loading / error / empty / ready states of `useApiResource`
 * explicitly, so every real-data section has all four instead of only
 * ever showing the happy path.
 *
 * A long `loading` (backend cold-starting) gets an explanatory line under
 * the skeleton; an `error` gets a Retry button wired to the hook's own
 * retry, so a judge never has to hard-reload the page.
 */
export function ApiStateSection<T>({
  state,
  emptyTitle = "No real data yet",
  emptyBody = "The pipeline has not produced this artifact yet. Run the relevant script under scripts/ to populate it.",
  render,
}: {
  state: ApiResourceState<T>;
  emptyTitle?: string;
  emptyBody?: string;
  render: (data: T) => ReactNode;
}) {
  switch (state.status) {
    case "loading":
      return (
        <div className="space-y-3">
          <SkeletonRows rows={4} />
          {state.slow && (
            <p className="flex items-center gap-2 text-xs text-[var(--color-ink-muted)]">
              <Spinner />
              Starting the analysis backend — the first request after a period of inactivity can
              take up to a minute.
            </p>
          )}
        </div>
      );
    case "error":
      return (
        <div className="space-y-3">
          <ErrorState title="Could not reach the AEGIS API" body={state.error.message} />
          <button
            type="button"
            onClick={state.retry}
            className="rounded-lg border border-[var(--color-border-strong)] px-3 py-1.5 text-xs font-semibold text-[var(--color-ink)] transition-standard hover:bg-[var(--color-surface-sunken)]"
          >
            Retry
          </button>
        </div>
      );
    case "empty":
      return <EmptyState title={emptyTitle} body={emptyBody} />;
    case "ready":
      return <>{render(state.data)}</>;
    default:
      return null;
  }
}
