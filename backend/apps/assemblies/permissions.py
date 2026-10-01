"""Classes de permission DRF de l'app assemblies (CDC 2.4, ligne « Assemblees
generales » ; assemblees-page-ag.md §2).

- Lecture (page, AG, decisions, PV signe) : tout joueur actif du club
  (``apps.clubs.permissions.IsActiveClubMember``, reutilisee telle quelle,
  aucune nouvelle classe necessaire).
- Convoquer, pointer les presences, saisir les votes, rediger le PV,
  definir le seuil de quorum : President, Vice-president.
- Signer le PV : verifie par le service (``sign_minutes``), pas par une
  classe de permission generique -- la signature du President et celle du
  Vice-president sont deux droits distincts, chacun pour sa propre ligne
  (assemblees-page-ag.md §2 : « chacun pour sa signature »).
"""

from __future__ import annotations

from apps.clubs.models import MembershipRole
from apps.core.roles import HasClubRole

ASSEMBLY_MANAGER_ROLES = frozenset({MembershipRole.Role.PRESIDENT, MembershipRole.Role.VICE_PRESIDENT})


class CanManageAssembly(HasClubRole):
    required_roles = ASSEMBLY_MANAGER_ROLES
    message = "Reserve au President et au Vice-president (CDC 2.4, 4.15)."
