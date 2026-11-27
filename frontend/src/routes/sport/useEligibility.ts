import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { listEligibility, type EligibilityItem } from "../../api/sport";

export const ELIGIBILITY_QUERY_KEY = ["sport", "eligibility"] as const;

const EMPTY: ReadonlyMap<number, EligibilityItem> = new Map();

function indexByMembership(data: { results: EligibilityItem[] }): ReadonlyMap<number, EligibilityItem> {
  return new Map(data.results.map((item) => [item.membership_id, item] as const));
}

function shouldRetry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return false;
  return failureCount < 1;
}

/**
 * Éligibilité groupée (`GET /sport/eligibility/`, §4.1 bis) indexée par
 * adhésion. Le motif vient tel quel de l'API (règles métier côté serveur).
 *
 * Tolérant par construction : un 403 (rôle sans droit) ou une erreur réseau
 * donnent simplement une table vide, sans message bloquant ; l'appelant garde
 * alors son comportement de repli (`is_unavailable` sans motif). Un 403 n'est
 * jamais rejoué.
 */
export function useEligibility(enabled: boolean): ReadonlyMap<number, EligibilityItem> {
  const query = useQuery({
    queryKey: ELIGIBILITY_QUERY_KEY,
    queryFn: listEligibility,
    enabled,
    staleTime: 15_000,
    retry: shouldRetry,
    select: indexByMembership,
  });
  return query.data ?? EMPTY;
}
