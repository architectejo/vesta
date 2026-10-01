import { ApiError } from "../../api/client";

/**
 * Traduit une erreur de vérification du code PIN (CDC 7.2) dans les
 * libellés standards de `PinPrompt` (docs/lot0/design-system.md §3.1).
 * L'interface ne fait que mettre en forme ce que le serveur a déjà décidé
 * (nombre d'essais restants, heure de déblocage) : aucune règle métier n'est
 * évaluée ici.
 */
export function formatPinError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Une erreur est survenue de notre côté. Réessayez dans un instant.";
  }
  if (error.status === 423) {
    const raw = error.raw as { locked_until?: string } | null;
    const until = raw?.locked_until ? formatClockTime(raw.locked_until) : null;
    return until
      ? `Trop de codes erronés. Les actions sensibles sont bloquées jusqu'à ${until}.`
      : error.detail;
  }
  if (error.status === 400) {
    const raw = error.raw as { attempts_remaining?: number } | null;
    if (typeof raw?.attempts_remaining === "number") {
      const n = raw.attempts_remaining;
      return `Code PIN incorrect. Il vous reste ${n} essai${n > 1 ? "s" : ""}.`;
    }
  }
  return error.detail;
}

function formatClockTime(isoDateTime: string): string | null {
  const date = new Date(isoDateTime);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(date);
}
