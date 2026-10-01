"""Classes de permission DRF de l'app logistics (matrice CDC 2.4 ; fiche
d'écran logistique.md §2)."""

from __future__ import annotations

from apps.clubs.models import MembershipRole
from apps.core.roles import HasClubRole

# Matrice 2.4, ligne « Matériel et inventaires » : Intendant seul en
# écriture (catalogue, mouvements, inventaire).
MATERIAL_MANAGER_ROLES = frozenset({MembershipRole.Role.STEWARD})

# Lecture de la page Matériel (fiche d'écran logistique.md §2) : Intendant,
# Président, Vice-président, Trésorier, Coach seulement. Les autres rôles
# (DS, Trésorier adjoint, Capitaine, Médecin, Joueur) n'ont AUCUNE entrée
# de menu ni accès direct -- contrairement à la plupart des pages de club,
# ce n'est pas une simple lecture ouverte à tout membre actif.
MATERIAL_READER_ROLES = frozenset(
    {
        MembershipRole.Role.STEWARD,
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.TREASURER,
        MembershipRole.Role.COACH,
    }
)

# Retour d'équipements d'un match : Coach et Intendant (fiche §5.2, point
# ouvert n° 4 de sport-feuille-de-match.md, proposition reprise).
EQUIPMENT_RETURN_ROLES = frozenset({MembershipRole.Role.STEWARD, MembershipRole.Role.COACH})

# Sortie d'équipements pour un match depuis la feuille de match : Coach
# seul (matrice 2.4, « Feuille de match et composition »).
EQUIPMENT_OUT_ROLES = frozenset({MembershipRole.Role.COACH})


class CanManageMaterial(HasClubRole):
    required_roles = MATERIAL_MANAGER_ROLES
    message = "Réservé à l'Intendant (CDC 2.4, 4.13)."


class CanReadMaterial(HasClubRole):
    required_roles = MATERIAL_READER_ROLES
    message = "Vous n'avez pas accès à cette page (CDC 2.4, 4.13)."


class CanRecordEquipmentReturn(HasClubRole):
    required_roles = EQUIPMENT_RETURN_ROLES
    message = "Réservé au Coach et à l'Intendant (logistique.md §5.2)."


class CanRecordEquipmentOut(HasClubRole):
    required_roles = EQUIPMENT_OUT_ROLES
    message = "Réservé au Coach (CDC 2.4, 4.8)."
