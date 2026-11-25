import { useCallback, useRef } from "react";

export const CLIENT_UUID_CONFLICT_MESSAGE =
  "Cette saisie a déjà été enregistrée avec des informations différentes. Rechargez la page.";

/**
 * Clé d'idempotence d'une tentative d'enregistrement (`client_uuid`).
 *
 * Le même UUID est conservé tant que la saisie (`signature`) ne change pas et
 * qu'aucun succès n'a eu lieu : un nouvel essai après erreur réseau ou 5xx
 * rejoue donc la même requête. `reset()` (après succès) force un nouvel UUID.
 */
export function useClientUuid() {
  const state = useRef<{ uuid: string; signature: string } | null>(null);

  const get = useCallback((signature: string): string => {
    if (!state.current || state.current.signature !== signature) {
      state.current = { uuid: crypto.randomUUID(), signature };
    }
    return state.current.uuid;
  }, []);

  const reset = useCallback(() => {
    state.current = null;
  }, []);

  return { get, reset };
}
