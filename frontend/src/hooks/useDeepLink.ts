import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Lien profond par paramètre d'URL (ex. `?paiement=12`) : appelle `onId` avec
 * l'identifiant puis retire le paramètre de l'adresse, pour qu'un
 * rafraîchissement ou un retour arrière ne rouvre pas la modale. Réagit aussi
 * quand la page est déjà affichée (clic sur une notification depuis la même page).
 */
export function useDeepLink(param: string, onId: (id: number) => void): void {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get(param);

  useEffect(() => {
    if (raw === null) return;
    const id = Number(raw);
    if (Number.isInteger(id) && id > 0) onId(id);
    const next = new URLSearchParams(searchParams);
    next.delete(param);
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raw]);
}
