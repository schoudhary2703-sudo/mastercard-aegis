import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./client";

export type ApiResourceState<T> =
  | { status: "loading"; slow: boolean }
  | { status: "error"; error: Error; retry: () => void }
  | { status: "empty" }
  | { status: "ready"; data: T };

/**
 * Fetches one API resource and exposes loading / error / empty / ready
 * states for a component to render explicitly. Aborts the in-flight request
 * on unmount or when `deps` change, so a slow response for a previous
 * attack id can never clobber the state for the current one.
 *
 * `loading` carries a `slow` flag that flips true after `slowAfterMs` so the
 * UI can explain a long wait (e.g. a spun-down backend cold-starting) instead
 * of showing a silent skeleton. `error` carries a `retry` that re-runs the
 * fetch without a full remount.
 */
export function useApiResource<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  isEmpty?: (data: T) => boolean,
  slowAfterMs = 4000,
): ApiResourceState<T> {
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const [state, setState] = useState<ApiResourceState<T>>({ status: "loading", slow: false });

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading", slow: false });

    const slowTimer = setTimeout(() => {
      setState((current) =>
        current.status === "loading" ? { status: "loading", slow: true } : current,
      );
    }, slowAfterMs);

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
          retry,
        });
      })
      .finally(() => clearTimeout(slowTimer));

    return () => {
      clearTimeout(slowTimer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  return state;
}
