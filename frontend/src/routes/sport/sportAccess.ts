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

const ATTENDANCE_RECORDER = ["coach", "assistant_coach", "captain", "president"] as const;
const ATTENDANCE_TIME_CORRECTOR = ["coach", "assistant_coach"] as const;
const TEAM_ASSIGNER = ["coach", "assistant_coach", "captain", "president"] as const;
const MATCH_MANAGER = ["coach", "assistant_coach"] as const;
const INCIDENT_RECORDER = ["coach", "assistant_coach", "captain"] as const;
const EVALUATOR = ["coach", "assistant_coach", "president", "vice_president"] as const;
const TACTICAL_PLAN_EDITOR = ["coach", "assistant_coach"] as const;
const INCIDENT_FULL_VISIBILITY = [
  "coach",
  "assistant_coach",
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
const MEDICAL_FULL_VISIBILITY = ["coach", "assistant_coach", "president", "vice_president", "sports_director", "doctor"] as const;
// Déclaration d'une blessure (medical.md §4.1 ; apps.medical.permissions.INJURY_REPORTER_ROLES).
const INJURY_REPORTER = ["coach", "assistant_coach", "captain", "doctor"] as const;

// Page Médical (apps.medical.permissions.MEDICAL_PAGE_ROLES) : Médecin, Coach, Président.
const MEDICAL_PAGE_ACCESS = ["doctor", "coach", "assistant_coach", "president"] as const;

// Statistiques d'entraînement nominatives (assiduité par joueur, notes moyennes) :
// apps.sport.permissions.EVALUATION_STATS_ROLES. Simple indication d'affichage ;
// l'API reste seule juge (403 sur le classement d'assiduité).
const TRAINING_STATS_STAFF = ["coach", "assistant_coach", "president", "vice_president", "sports_director"] as const;
const SESSION_CREATOR = ["coach", "assistant_coach"] as const;

export function canViewTrainingStaffStats(roles: ProfileRole[] | undefined): boolean {
  return hasAnyRole(roles, TRAINING_STATS_STAFF);
}

// Tests de performance (apps.sport.permissions.CanManagePerformanceTests) :
// Coach et Assistant créent, mesurent et corrigent ; Président, VP et DS lisent.
// Simple indication d'affichage : l'API reste seule juge.
const PERFORMANCE_MANAGER = ["coach", "assistant_coach"] as const;

export function canManagePerformanceTests(roles: ProfileRole[] | undefined): boolean {
  return hasAnyRole(roles, PERFORMANCE_MANAGER);
}

export function canCreateSession(roles: ProfileRole[] | undefined): boolean {
  return hasAnyRole(roles, SESSION_CREATOR);
}

export function canAccessMedicalPage(roles: ProfileRole[] | undefined): boolean {
  return hasAnyRole(roles, MEDICAL_PAGE_ACCESS);
}

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
    isCoach: hasAnyRole(roles, ["coach", "assistant_coach"]),
    isCaptain: hasAnyRole(roles, ["captain"]),
    isPresident: hasAnyRole(roles, ["president"]),
    isDoctor: hasAnyRole(roles, ["doctor"]),
  };
}
