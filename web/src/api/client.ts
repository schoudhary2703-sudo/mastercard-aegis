/**
 * Typed fetch client for the AEGIS API.
 *
 * Every function here does exactly one `fetch` against one endpoint and
 * returns the parsed DTO. No caching, no retries, no client-side
 * recomputation of anything the backend already computed -- if a number is
 * wrong it is wrong in `aegis.api.service`, not here.
 */

import { API_BASE_URL } from "./config";
import type {
  AttackDetailDTO,
  AttacksResponseDTO,
  EvaluationResponseDTO,
  EvolutionResponseDTO,
  ExperimentsResponseDTO,
  FinalBenchmarkSummaryDTO,
  GenAIResponseDTO,
  LandscapeResponseDTO,
  HardestEvasionsResponseDTO,
  OverviewResponseDTO,
  RecentDetectionsResponseDTO,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly path: string;

  constructor(message: string, status: number, path: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }
}

// One attempt at one request. Network failure -> ApiError(status 0);
// HTTP error -> ApiError(status). A timeout arrives here as an AbortError
// whose signal is NOT the caller's, which the retry wrapper distinguishes.
async function getJsonOnce<T>(path: string, signal: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { signal });
  } catch (cause) {
    if (cause instanceof DOMException && (cause.name === "AbortError" || cause.name === "TimeoutError")) {
      throw cause;
    }
    throw new ApiError(
      cause instanceof Error ? cause.message : "network request failed",
      0,
      path,
    );
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // response body was not JSON; fall back to statusText
    }
    throw new ApiError(detail, response.status, path);
  }
  return (await response.json()) as T;
}

// Per-attempt hard cap, then give up on that attempt and retry.
const ATTEMPT_TIMEOUT_MS = 20_000;
// Backoff before each retry. Length = number of retries after the first try.
// Worst case ≈ 5 attempts × 20s + (1+3+8+15)s ≈ 127s, which comfortably
// rides out a cold Render free-tier container (~30-60s) — the call resolves
// as soon as the backend answers.
const RETRY_BACKOFF_MS = [1_000, 3_000, 8_000, 15_000];

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function linkSignals(outer: AbortSignal | undefined, inner: AbortSignal): AbortSignal {
  if (!outer) return inner;
  if (typeof AbortSignal.any === "function") return AbortSignal.any([outer, inner]);
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  outer.addEventListener("abort", onAbort, { once: true });
  inner.addEventListener("abort", onAbort, { once: true });
  return controller.signal;
}

/**
 * Fetch one endpoint, retrying transient failures (network drop, 5xx, or a
 * per-attempt timeout) with capped exponential backoff. Does NOT retry a
 * caller abort or a 4xx — those will not change on a second try. This is
 * what lets a screen recover on its own while a spun-down backend cold-starts
 * instead of hanging on a skeleton forever.
 */
async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt <= RETRY_BACKOFF_MS.length; attempt += 1) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    try {
      return await getJsonOnce<T>(path, linkSignals(signal, AbortSignal.timeout(ATTEMPT_TIMEOUT_MS)));
    } catch (error) {
      // Caller cancelled (unmount / new deps) — stop immediately.
      if (error instanceof DOMException && error.name === "AbortError" && signal?.aborted) {
        throw error;
      }
      // Definite client error — retrying is pointless.
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
        throw error;
      }
      lastError = error;
      if (attempt === RETRY_BACKOFF_MS.length) break;
      await sleep(RETRY_BACKOFF_MS[attempt], signal);
    }
  }
  if (lastError instanceof ApiError) throw lastError;
  throw new ApiError(
    lastError instanceof Error ? lastError.message : "request failed after retries",
    0,
    path,
  );
}

export function fetchOverview(signal?: AbortSignal): Promise<OverviewResponseDTO> {
  return getJson<OverviewResponseDTO>("/api/overview", signal);
}

export function fetchAttacks(signal?: AbortSignal): Promise<AttacksResponseDTO> {
  return getJson<AttacksResponseDTO>("/api/attacks", signal);
}

export function fetchAttack(attackId: string, signal?: AbortSignal): Promise<AttackDetailDTO> {
  return getJson<AttackDetailDTO>(`/api/attacks/${encodeURIComponent(attackId)}`, signal);
}

export function fetchRecentDetections(
  limit = 50,
  signal?: AbortSignal,
): Promise<RecentDetectionsResponseDTO> {
  return getJson<RecentDetectionsResponseDTO>(`/api/detections/recent?limit=${limit}`, signal);
}

export function fetchEvolution(signal?: AbortSignal): Promise<EvolutionResponseDTO> {
  return getJson<EvolutionResponseDTO>("/api/evolution", signal);
}

export function fetchEvaluation(signal?: AbortSignal): Promise<EvaluationResponseDTO> {
  return getJson<EvaluationResponseDTO>("/api/evaluation", signal);
}

export function fetchHardestEvasions(
  limit = 25,
  signal?: AbortSignal,
): Promise<HardestEvasionsResponseDTO> {
  return getJson<HardestEvasionsResponseDTO>(`/api/hardest-evasions?limit=${limit}`, signal);
}

export function fetchBenchmark(signal?: AbortSignal): Promise<FinalBenchmarkSummaryDTO> {
  return getJson<FinalBenchmarkSummaryDTO>("/api/benchmark", signal);
}

export function fetchExperiments(signal?: AbortSignal): Promise<ExperimentsResponseDTO> {
  return getJson<ExperimentsResponseDTO>("/api/experiments", signal);
}

export function fetchGenAI(signal?: AbortSignal): Promise<GenAIResponseDTO> {
  return getJson<GenAIResponseDTO>("/api/genai", signal);
}

export function fetchLandscape(signal?: AbortSignal): Promise<LandscapeResponseDTO> {
  return getJson<LandscapeResponseDTO>("/api/landscape", signal);
}
