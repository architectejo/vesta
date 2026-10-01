"""Classes de permission DRF de l'app sport (matrice CDC 2.4).

Chaque classe couvre une ligne de la matrice 2.4 (« Séances et matchs »,
« Feuille de match et composition », « Plan tactique », « Discipline »,
« Évaluations »). La lecture simple (« L ») ne demande pas de classe
dédiée : ``apps.clubs.permissions.IsActiveClubMember`` suffit déjà --
tout membre actif du club (bureau, staff, joueur) y a droit, y compris
Trésorier/Adjoint/Intendant qui n'ont que « — » sur ces lignes mais
reçoivent la lecture du rôle Joueur (union des droits, CDC 2.2).

Réservé aux vues à construire (tâche 3.7 et suivantes) : ce module ne
suppose aucune vue déjà écrite, il ne fait que déclarer les ensembles de
rôles et les classes réutilisables, comme le reste de l'app à ce stade
(tâches 3.2-3.4 : modèles, services, verrouillage, suspensions).
"""

from __future__ import annotations

from apps.clubs.models import MembershipRole
from apps.core.roles import HasClubRole

# Pointage (CDC 4.7, 4.8) : Coach, Capitaine, Président (matrice 2.4,
# ligne « Séances et matchs » — colonne « É »).
ATTENDANCE_RECORDER_ROLES = frozenset(
    {MembershipRole.Role.COACH, MembershipRole.Role.CAPTAIN, MembershipRole.Role.PRESIDENT}
)

# Correction de l'heure d'arrivée : réservée au Coach (CDC 4.7).
ATTENDANCE_TIME_CORRECTOR_ROLES = frozenset({MembershipRole.Role.COACH})

# Répartition A/B : Coach, Capitaine, Président (CDC 4.7 ; 10.2 n° 38 :
# le placement manuel d'un retardataire est en outre réservé au Coach et
# au Capitaine, contrôle fait par le service, pas par cette classe).
TEAM_ASSIGNER_ROLES = frozenset(
    {MembershipRole.Role.COACH, MembershipRole.Role.CAPTAIN, MembershipRole.Role.PRESIDENT}
)

# Composition, publication, score, buts, équipements (CDC 4.8) : Coach
# uniquement (matrice 2.4, « Feuille de match et composition » : « É »
# pour le Coach seul).
MATCH_MANAGER_ROLES = frozenset({MembershipRole.Role.COACH})

# Incidents/cartons (CDC 4.9) : Coach et Capitaine.
INCIDENT_RECORDER_ROLES = frozenset({MembershipRole.Role.COACH, MembershipRole.Role.CAPTAIN})

# Évaluations (CDC 4.10) : Coach, Président, Vice-président.
EVALUATOR_ROLES = frozenset(
    {MembershipRole.Role.COACH, MembershipRole.Role.PRESIDENT, MembershipRole.Role.VICE_PRESIDENT}
)

# Édition du plan tactique (CDC 4.11 ; 10.2 n° 32) : Coach uniquement.
TACTICAL_PLAN_EDITOR_ROLES = frozenset({MembershipRole.Role.COACH})

# Visibilité complète des incidents et suspensions (matrice 2.4, ligne
# « Discipline ») : Coach, Capitaine, Président, Vice-président, Directeur
# sportif, Médecin. Un simple joueur ne voit que les siens (« les siens
# pour J », sport-seance.md §2) -- filtre applique par la vue, pas par une
# classe de permission (lecture ouverte à tout membre actif, périmètre
# restreint au queryset).
INCIDENT_FULL_VISIBILITY_ROLES = frozenset(
    {
        MembershipRole.Role.COACH,
        MembershipRole.Role.CAPTAIN,
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.SPORTS_DIRECTOR,
        MembershipRole.Role.DOCTOR,
    }
)


class CanRecordAttendance(HasClubRole):
    required_roles = ATTENDANCE_RECORDER_ROLES
    message = "Réservé au Coach, au Capitaine et au Président (CDC 2.4, 4.7)."


class CanCorrectAttendanceTime(HasClubRole):
    required_roles = ATTENDANCE_TIME_CORRECTOR_ROLES
    message = "Seul le Coach corrige une heure d'arrivée (CDC 4.7)."


class CanAssignTeams(HasClubRole):
    required_roles = TEAM_ASSIGNER_ROLES
    message = "Réservé au Coach, au Capitaine et au Président (CDC 2.4, 4.7)."


class CanManageMatch(HasClubRole):
    required_roles = MATCH_MANAGER_ROLES
    message = "Réservé au Coach (CDC 2.4, 4.8)."


class CanRecordIncident(HasClubRole):
    required_roles = INCIDENT_RECORDER_ROLES
    message = "Réservé au Coach et au Capitaine (CDC 2.4, 4.9)."


class CanEvaluate(HasClubRole):
    required_roles = EVALUATOR_ROLES
    message = "Réservé au Coach, au Président et au Vice-président (CDC 2.4, 4.10)."


class CanEditTacticalPlan(HasClubRole):
    required_roles = TACTICAL_PLAN_EDITOR_ROLES
    message = "Réservé au Coach (CDC 2.4, 4.11, 10.2 n° 32)."
