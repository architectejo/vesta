import { ApiError } from "../../api/client";

/** Texte de repli quand l'API d'éligibilité n'a pas fourni de motif (403, réseau). */
export const GENERIC_REASON = "Non sélectionnable pour l'instant";
export const GENERIC_REASON_INLINE = "motif non disponible pour l'instant";

/** Retire le point final du motif de l'API pour l'insérer dans une phrase. */
export function inlineReason(reason: string): string {
  return reason.trim().replace(/[.\s]+$/, "");
}

/**
 * Message d'un refus de l'API à l'enregistrement d'une ligne de composition
 * (sport-feuille-de-match.md §4.1) : un joueur devenu non sélectionnable
 * entre-temps (`code: "player_not_eligible"`) est nommé, avec le motif de
 * l'API sans double point final ; les autres refus (numéro déjà attribué…)
 * gardent le texte de l'API tel quel.
 */
export function compositionErrorMessage(error: unknown, playerName: string): string {
  if (!(error instanceof ApiError)) return "Enregistrement impossible.";
  if (error.code === "player_not_eligible") {
    const reason = inlineReason(error.detail) || GENERIC_REASON_INLINE;
    return `${playerName} n'est plus sélectionnable : ${reason}.`;
  }
  return error.detail;
}
