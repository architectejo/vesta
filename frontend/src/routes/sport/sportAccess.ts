/**
 * Rôles habilités par écran du Lot 3 (matrice CDC 2.4), repris tels quels
 * de `backend/apps/sport/permissions.py` pour que l'interface montre ou
 * masque une action de manière cohérente avec ce que l'API accepte —
 * **sans jamais être la source de vérité** : le contrôle réel reste
 * toujours fait par le service (CLAUDE.md règle n° 5, §2.5). Un rôle
 * autorisé ici mais refusé côté API affichera simplement l'erreur
 * renvoyée par l'API (message standard « Vous n'avez pas accès à cette
 * action. »).
 */

export type ProfileRole = { role: string };

function hasAnyRole(roles: ProfileRole[] | undefined, required: readonly string[]): boolean {
  if (!roles) return false;
  return roles.some((r) => required.includes(r.role));
}

const ATTENDANCE_RECORDER = ["coach", "captain", "president"] as const;
const ATTENDANCE_TIME_CORRECTOR = ["coach"] as const;
const TEAM_ASSIGNER = ["coach", "captain", "president"] as const;
const MATCH_MANAGER = ["coach"] as const;
const INCIDENT_RECORDER = ["coach", "captain"] as const;
const EVALUATOR = ["coach", "president", "vice_president"] as const;
const TACTICAL_PLAN_EDITOR = ["coach"] as const;
const INCIDENT_FULL_VISIBILITY = [
  "coach",
  "captain",
  "president",
  "vice_president",
  "sports_director",
  "doctor",
] as const;
// Blessures (medical.md §10, écart 1 — correction appliquée) : liste
// complète (joueur, moment, aptitude en texte N1) visible du Médecin, du
// Coach, du Président, du VP et du DS ; **pas** du Capitaine (qui ne garde
// que le bouton « Déclarer une blessure », medical.md §10 écart 1).
const MEDICAL_FULL_VISIBILITY = ["coach", "president", "vice_president", "sports_director", "doctor"] as const;
// Déclaration d'une blessure (medical.md §4.1 ; apps.medical.permissions.INJURY_REPORTER_ROLES).
const INJURY_REPORTER = ["coach", "captain", "doctor"] as const;

export interface SportAccess {
  canRecordAttendance: boolean;
  canCorrectAttendanceTime: boolean;
  canAssignTeams: boolean;
  canManageMatch: boolean;
  canRecordIncident: boolean;
  canEvaluate: boolean;
  canEditTacticalPlan: boolean;
  canSeeIncidentFull: boolean;
  canSeeMedicalFull: boolean;
  canReportInjury: boolean;
  isCoach: boolean;
  isCaptain: boolean;
  isPresident: boolean;
  isDoctor: boolean;
}

export function getSportAccess(roles: ProfileRole[] | undefined): SportAccess {
  return {
    canRecordAttendance: hasAnyRole(roles, ATTENDANCE_RECORDER),
    canCorrectAttendanceTime: hasAnyRole(roles, ATTENDANCE_TIME_CORRECTOR),
    canAssignTeams: hasAnyRole(roles, TEAM_ASSIGNER),
    canManageMatch: hasAnyRole(roles, MATCH_MANAGER),
    canRecordIncident: hasAnyRole(roles, INCIDENT_RECORDER),
    canEvaluate: hasAnyRole(roles, EVALUATOR),
    canEditTacticalPlan: hasAnyRole(roles, TACTICAL_PLAN_EDITOR),
    canSeeIncidentFull: hasAnyRole(roles, INCIDENT_FULL_VISIBILITY),
    canSeeMedicalFull: hasAnyRole(roles, MEDICAL_FULL_VISIBILITY),
    canReportInjury: hasAnyRole(roles, INJURY_REPORTER),
    isCoach: hasAnyRole(roles, ["coach"]),
    isCaptain: hasAnyRole(roles, ["captain"]),
    isPresident: hasAnyRole(roles, ["president"]),
    isDoctor: hasAnyRole(roles, ["doctor"]),
  };
}
