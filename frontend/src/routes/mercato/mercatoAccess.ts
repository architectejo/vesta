import type { ProfileRole } from "../sport/sportAccess";

/** Rôles habilités par la fiche `mercato.md` §2 (matrice CDC 2.4), repris
 * tels quels de `backend/apps/mercato/permissions.py`. L'interface ne fait
 * jamais autorité : un rôle autorisé ici mais refusé côté API affichera le
 * message renvoyé par l'API (CLAUDE.md règle n° 5). */

const MARKET_READER_ROLES = ["president", "vice_president", "sports_director", "treasurer", "coach"] as const;
const OFFER_AND_MESSAGING_ROLES = ["president", "sports_director"] as const;

function hasAnyRole(roles: ProfileRole[] | undefined, required: readonly string[]): boolean {
  if (!roles) return false;
  return roles.some((r) => required.includes(r.role));
}

export interface MercatoAccess {
  canReadMarket: boolean;
  canMakeOfferOrMessage: boolean;
}

export function getMercatoAccess(roles: ProfileRole[] | undefined): MercatoAccess {
  return {
    canReadMarket: hasAnyRole(roles, MARKET_READER_ROLES),
    canMakeOfferOrMessage: hasAnyRole(roles, OFFER_AND_MESSAGING_ROLES),
  };
}
