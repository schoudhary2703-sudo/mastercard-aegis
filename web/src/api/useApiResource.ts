import { useEffect, useState } from "react";
import { ApiError } from "./client";

export type ApiResourceState<T> =
  | { status: "loading" }
  | { status: "error"; error: Error }
  | { status: "empty" }
  | { status: "ready"; data: T };

/**
 * Fetches one API resource and exposes loading / error / empty / ready
 * states for a component to render explicitly. Aborts the in-flight request
 * on unmount or when `deps` change, so a slow response for a previous
 * attack id can never clobber the state for the current one.
 */
export function useApiResource<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  isEmpty?: (data: T) => boolean,
): ApiResourceState<T> {
  const [state, setState] = useState<ApiResourceState<T>>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });

    fetcher(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setState(isEmpty?.(data) ? { status: "empty" } : { status: "ready", data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState({
          status: "error",
          error:
            error instanceof ApiError || error instanceof Error
              ? error
              : new Error("unknown error"),
        });
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
