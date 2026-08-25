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
  FinalBenchmarkSummaryDTO,
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

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { signal });
  } catch (cause) {
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
