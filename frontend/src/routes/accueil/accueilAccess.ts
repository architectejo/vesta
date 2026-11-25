/**
 * Rôles habilités par carte de l'accueil (docs/ecrans/club-accueil.md §2,
 * §4), repris de la matrice CDC 2.4 — même principe que
 * `routes/sport/sportAccess.ts` : affichage seulement, le contrôle réel
 * reste toujours fait par l'API (CLAUDE.md règle n° 5, §2.5).
 */

export type ProfileRole = { role: string };

function hasAnyRole(roles: ProfileRole[] | undefined, required: readonly string[]): boolean {
  if (!roles) return false;
  return roles.some((r) => required.includes(r.role));
}

const ANNOUNCEMENT_PUBLISHER = ["president", "vice_president", "secretary"] as const;

export interface AccueilAccess {
  canPublishAnnouncement: boolean;
  isPresident: boolean;
  isCoach: boolean;
}

/**
 * La bannière « Dépense non justifiée » (§4) n'est pas gérée ici : elle
 * dépend de `getTreasuryCapabilities().capabilities.can_read_expenses`
 * (même source que `DepensesPage`), pas d'une liste de rôles recopiée.
 */
export function getAccueilAccess(roles: ProfileRole[] | undefined): AccueilAccess {
  return {
    canPublishAnnouncement: hasAnyRole(roles, ANNOUNCEMENT_PUBLISHER),
    isPresident: hasAnyRole(roles, ["president"]),
    isCoach: hasAnyRole(roles, ["coach", "assistant_coach"]),
  };
}
