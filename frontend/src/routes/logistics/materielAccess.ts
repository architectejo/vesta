import type { ProfileRole } from "../sport/sportAccess";

/** Rôles habilités par la fiche `logistique.md` §2 (matrice CDC 2.4), repris
 * tels quels de `backend/apps/logistics/permissions.py`. L'interface ne fait
 * jamais autorité : un rôle autorisé ici mais refusé côté API affichera le
 * message renvoyé par l'API (CLAUDE.md règle n° 5). */

const MATERIAL_READER_ROLES = ["steward", "president", "vice_president", "treasurer", "coach", "assistant_coach"] as const;
const EXPENSE_DETAIL_ROLES = ["president", "vice_president", "treasurer"] as const;

function hasAnyRole(roles: ProfileRole[] | undefined, required: readonly string[]): boolean {
  if (!roles) return false;
  return roles.some((r) => required.includes(r.role));
}

export interface MaterialAccess {
  canReadMaterial: boolean;
  canManageMaterial: boolean;
  canSeeExpenseDetail: boolean;
  isCoach: boolean;
}

export function getMaterialAccess(roles: ProfileRole[] | undefined): MaterialAccess {
  return {
    canReadMaterial: hasAnyRole(roles, MATERIAL_READER_ROLES),
    canManageMaterial: hasAnyRole(roles, ["steward"]),
    canSeeExpenseDetail: hasAnyRole(roles, EXPENSE_DETAIL_ROLES),
    isCoach: hasAnyRole(roles, ["coach", "assistant_coach"]),
  };
}
