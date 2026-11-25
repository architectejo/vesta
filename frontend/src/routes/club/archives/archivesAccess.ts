/**
 * Droits d'affichage de l'Archive des documents (docs/ecrans/club-archives.md
 * §2 ; CDC 4.15.1, 10.3 n° 171). L'API ne renvoie pas (encore) de drapeaux
 * `can_read_archives` / `can_upload` : les rôles du profil servent donc
 * uniquement à afficher ou masquer l'entrée de navigation et les boutons.
 * Le contrôle réel reste fait par l'API (403 sinon), jamais ici.
 */

export type ProfileRole = { role: string };

/** Lecture : Bureau (Président, VP, Secrétaire, DS, Trésorier, adjoint, Intendant). */
export const ARCHIVE_READER_ROLES = [
  "president",
  "vice_president",
  "secretary",
  "sports_director",
  "treasurer",
  "assistant_treasurer",
  "steward",
] as const;

/** Dépôt, remplacement, retrait, documents retirés : Secrétaire, Président, VP. */
export const ARCHIVE_WRITER_ROLES = ["secretary", "president", "vice_president"] as const;

function hasAnyRole(roles: ProfileRole[] | undefined, required: readonly string[]): boolean {
  return roles?.some((r) => required.includes(r.role)) ?? false;
}

export interface ArchivesAccess {
  canRead: boolean;
  canWrite: boolean;
}

export function getArchivesAccess(roles: ProfileRole[] | undefined): ArchivesAccess {
  return {
    canRead: hasAnyRole(roles, ARCHIVE_READER_ROLES),
    canWrite: hasAnyRole(roles, ARCHIVE_WRITER_ROLES),
  };
}
