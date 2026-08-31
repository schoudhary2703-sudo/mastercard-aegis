import { useEffect } from "react";
import { API_BASE_URL } from "./config";

/**
 * Fire-and-forget ping at app mount so a spun-down backend (Render free tier
 * sleeps after ~15 min idle) starts waking immediately — before the user
 * navigates and before route code-splits finish loading. The result is
 * ignored; the real screens do their own fetches with retry.
 */
export function useWarmup(): void {
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60_000);
    fetch(`${API_BASE_URL}/api/health`, { signal: controller.signal, cache: "no-store" })
      .catch(() => {
        /* cold start / offline — the screens surface their own state */
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, []);
}
