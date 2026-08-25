import type { ReactNode } from "react";
import type { ApiResourceState } from "../../api/useApiResource";
import { EmptyState, ErrorState, SkeletonRows } from "../ui/States";

/**
 * Renders the loading / error / empty / ready states of `useApiResource`
 * explicitly, so every real-data section has all four instead of only
 * ever showing the happy path.
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
      return <SkeletonRows rows={4} />;
    case "error":
      return <ErrorState title="Could not reach the AEGIS API" body={state.error.message} />;
    case "empty":
      return <EmptyState title={emptyTitle} body={emptyBody} />;
    case "ready":
      return <>{render(state.data)}</>;
    default:
      return null;
  }
}
