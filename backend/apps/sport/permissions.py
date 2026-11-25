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

from apps.clubs.models import COACHING_STAFF_ROLES, MembershipRole
from apps.core.roles import HasClubRole

# Pointage (CDC 4.7, 4.8) : Coach, Capitaine, Président (matrice 2.4,
# ligne « Séances et matchs » — colonne « É »).
ATTENDANCE_RECORDER_ROLES = frozenset(
    {*COACHING_STAFF_ROLES, MembershipRole.Role.CAPTAIN, MembershipRole.Role.PRESIDENT}
)

# Correction de l'heure d'arrivée : réservée au Coach (CDC 4.7).
ATTENDANCE_TIME_CORRECTOR_ROLES = COACHING_STAFF_ROLES

# Répartition A/B : Coach, Capitaine, Président (CDC 4.7 ; 10.2 n° 38 :
# le placement manuel d'un retardataire est en outre réservé au Coach et
# au Capitaine, contrôle fait par le service, pas par cette classe).
TEAM_ASSIGNER_ROLES = frozenset(
    {*COACHING_STAFF_ROLES, MembershipRole.Role.CAPTAIN, MembershipRole.Role.PRESIDENT}
)

# Composition, publication, score, buts, équipements (CDC 4.8) : Coach
# uniquement (matrice 2.4, « Feuille de match et composition » : « É »
# pour le Coach seul).
MATCH_MANAGER_ROLES = COACHING_STAFF_ROLES

# Incidents/cartons (CDC 4.9) : Coach et Capitaine.
INCIDENT_RECORDER_ROLES = frozenset({*COACHING_STAFF_ROLES, MembershipRole.Role.CAPTAIN})

# Évaluations (CDC 4.10) : Coach, Président, Vice-président.
EVALUATOR_ROLES = frozenset(
    {*COACHING_STAFF_ROLES, MembershipRole.Role.PRESIDENT, MembershipRole.Role.VICE_PRESIDENT}
)

# Édition du plan tactique (CDC 4.11 ; 10.2 n° 32) : Coach uniquement.
TACTICAL_PLAN_EDITOR_ROLES = COACHING_STAFF_ROLES

# Visibilité complète des incidents et suspensions (matrice 2.4, ligne
# « Discipline ») : Coach, Capitaine, Président, Vice-président, Directeur
# sportif, Médecin. Un simple joueur ne voit que les siens (« les siens
# pour J », sport-seance.md §2) -- filtre applique par la vue, pas par une
# classe de permission (lecture ouverte à tout membre actif, périmètre
# restreint au queryset).
INCIDENT_FULL_VISIBILITY_ROLES = frozenset(
    {
        *COACHING_STAFF_ROLES,
        MembershipRole.Role.CAPTAIN,
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.SPORTS_DIRECTOR,
        MembershipRole.Role.DOCTOR,
    }
)


class CanRecordAttendance(HasClubRole):
    required_roles = ATTENDANCE_RECORDER_ROLES
    message = "Réservé au Coach (ou son assistant), au Capitaine et au Président."


class CanCorrectAttendanceTime(HasClubRole):
    required_roles = ATTENDANCE_TIME_CORRECTOR_ROLES
    message = "Seul le Coach (ou son assistant) corrige une heure d'arrivée."


class CanAssignTeams(HasClubRole):
    required_roles = TEAM_ASSIGNER_ROLES
    message = "Réservé au Coach (ou son assistant), au Capitaine et au Président."


class CanManageMatch(HasClubRole):
    required_roles = MATCH_MANAGER_ROLES
    message = "Réservé au Coach du club ou à son assistant."


class CanRecordIncident(HasClubRole):
    required_roles = INCIDENT_RECORDER_ROLES
    message = "Réservé au Coach (ou son assistant) et au Capitaine."


class CanEvaluate(HasClubRole):
    required_roles = EVALUATOR_ROLES
    message = "Réservé au Coach (ou son assistant), au Président et au Vice-président."


class CanEditTacticalPlan(HasClubRole):
    required_roles = TACTICAL_PLAN_EDITOR_ROLES
    message = "Réservé au Coach du club ou à son assistant."


# Statistiques de séance (sport-statistiques-seance.md A3, B) : présence
# ouverte à tout membre actif ; « Notes du Coach » et assiduité nominative
# réservées au staff technique, au bureau (Président, Vice-président) et au
# Directeur sportif (lecture seule). Un simple joueur ne voit que sa note.
EVALUATION_STATS_ROLES = frozenset({*EVALUATOR_ROLES, MembershipRole.Role.SPORTS_DIRECTOR})
ATTENDANCE_RANKING_ROLES = EVALUATION_STATS_ROLES

# Tests de performance (partie C, C3) : Coach et Assistant créent et mesurent
# (C-Q3, position provisoire : ni Capitaine, ni Président, ni Vice-président) ;
# Coach, Assistant, Président, Vice-président et Directeur sportif lisent tout
# (le Président et le Vice-président en lecture seule) ; tout autre joueur ne
# lit que ses propres résultats.
PERFORMANCE_MANAGER_ROLES = COACHING_STAFF_ROLES
PERFORMANCE_VIEW_ALL_ROLES = EVALUATION_STATS_ROLES


class CanViewAttendanceRanking(HasClubRole):
    required_roles = ATTENDANCE_RANKING_ROLES
    message = "Réservé au staff technique, au bureau sportif et au Directeur sportif."


class CanManagePerformanceTests(HasClubRole):
    required_roles = PERFORMANCE_MANAGER_ROLES
    message = "Réservé au Coach du club ou à son assistant."
    ghost_readable = False


class CanViewAllPerformance(HasClubRole):
    required_roles = PERFORMANCE_VIEW_ALL_ROLES
    message = "Vous ne pouvez consulter que vos propres mesures."
