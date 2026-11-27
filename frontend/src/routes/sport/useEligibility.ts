import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import type { MyProfile } from "../../api/clubs";
import { listEligibility, type EligibilityItem } from "../../api/sport";

/** Préfixe de la clé : complété par l'identifiant du club actif (étanchéité du cache). */
export const ELIGIBILITY_QUERY_KEY = ["sport", "eligibility"] as const;

/** Rafraîchissement de l'éligibilité dans « Composer l'équipe » (§4.1, 4.8 : 15 s, polling). */
export const ELIGIBILITY_POLL_MS = 15_000;

/**
 * Intervalle de rafraîchissement suspendu quand l'onglet est caché (même
 * règle que le fil et le chat, 6.5) : aucune requête inutile en arrière-plan.
 */
export function visiblePollInterval(ms: number): () => number | false {
  return () => (typeof document !== "undefined" && document.visibilityState === "hidden" ? false : ms);
}

const EMPTY: ReadonlyMap<number, EligibilityItem> = new Map();

function indexByMembership(data: { results: EligibilityItem[] }): ReadonlyMap<number, EligibilityItem> {
  return new Map(data.results.map((item) => [item.membership_id, item] as const));
}

function isAccessDenied(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

function shouldRetry(failureCount: number, error: Error): boolean {
  if (isAccessDenied(error)) return false;
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
 *
 * Sécurité : la clé du cache porte le club actif (un changement de club ne
 * réutilise jamais les motifs de l'ancien), et un refus d'accès (401/403, par
 * exemple après révocation du rôle de Coach) efface aussitôt les motifs déjà
 * reçus au lieu de continuer à les afficher.
 *
 * `pollMs` (facultatif) : rafraîchissement périodique tant que `enabled`
 * reste vrai (modale ouverte), suspendu onglet caché. Pas de WebSocket
 * (contrainte d'hébergement, CLAUDE.md §4).
 */
export function useEligibility(
  enabled: boolean,
  options: { pollMs?: number } = {},
): ReadonlyMap<number, EligibilityItem> {
  const queryClient = useQueryClient();
  const clubId = queryClient.getQueryData<MyProfile>(["profile", "me"])?.club?.id ?? null;
  const query = useQuery({
    queryKey: [...ELIGIBILITY_QUERY_KEY, clubId],
    queryFn: listEligibility,
    enabled,
    staleTime: 15_000,
    refetchInterval: options.pollMs ? visiblePollInterval(options.pollMs) : false,
    retry: shouldRetry,
    select: indexByMembership,
  });
  if (isAccessDenied(query.error)) return EMPTY;
  return query.data ?? EMPTY;
}
