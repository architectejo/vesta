import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./client";

const MAX_RETRIES = 3;

/** Pas de nouvelle tentative sur un refus de permission (403) : il ne
 * disparaîtra pas et retarderait l'écran « accès refusé ». */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status === 403) return false;
  return failureCount < MAX_RETRIES;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: shouldRetryQuery } } });
}
