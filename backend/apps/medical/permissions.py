"""Classes de permission DRF de l'app medical (matrice CDC 2.4 ; medical.md §2, §3).

Reprend le mecanisme d'``apps.core.roles`` (cumul de roles, CDC 2.2),
meme convention que ``apps.sport.permissions``/``apps.clubs.permissions``.
"""

from __future__ import annotations

from apps.clubs.models import MembershipRole
from apps.core.roles import HasClubRole

# Page « Medical » (medical.md §3) : Medecin, Coach, President (barre
# laterale, design-system §3.9).
MEDICAL_PAGE_ROLES = frozenset(
    {MembershipRole.Role.DOCTOR, MembershipRole.Role.COACH, MembershipRole.Role.PRESIDENT}
)

# Declaration d'une blessure (CDC 4.12 etape 1) : Coach, Capitaine, Medecin.
INJURY_REPORTER_ROLES = frozenset(
    {MembershipRole.Role.COACH, MembershipRole.Role.CAPTAIN, MembershipRole.Role.DOCTOR}
)

# Ecriture clinique (fiche, bilan, suivi, aptitude) : Medecin uniquement
# (matrice 2.4, ligne « Fiches de sante et blessures » : « É » Med seul).
DOCTOR_ONLY_ROLES = frozenset({MembershipRole.Role.DOCTOR})


class CanAccessMedicalPage(HasClubRole):
    required_roles = MEDICAL_PAGE_ROLES
    message = "Reserve au Medecin, au Coach et au President (CDC 2.4, 4.12)."


class CanReportInjury(HasClubRole):
    required_roles = INJURY_REPORTER_ROLES
    message = "Reserve au Coach, au Capitaine et au Medecin (CDC 2.4, 4.12)."


class IsClubDoctor(HasClubRole):
    required_roles = DOCTOR_ONLY_ROLES
    message = "Reserve au Medecin / referent sante (CDC 2.4, 4.12)."
