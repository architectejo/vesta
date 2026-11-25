"""Classes de permission DRF de l'app assemblies (CDC 2.4, ligne « Assemblees
generales » ; assemblees-page-ag.md §2).

- Lecture (page, AG, decisions, PV signe) : tout joueur actif du club
  (``apps.clubs.permissions.IsActiveClubMember``, reutilisee telle quelle,
  aucune nouvelle classe necessaire).
- Convoquer (ordre du jour, invitation) : President, VP et Secretaire
  (decision client du 11/10/2026, 10.3 n 170) ; le Secretaire n'a NI la
  signature du PV, NI le vote, NI la cloture, NI le pointage.
- Pointer les presences, saisir les votes, rediger le PV,
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
ASSEMBLY_CONVENER_ROLES = ASSEMBLY_MANAGER_ROLES | {MembershipRole.Role.SECRETARY}

# Archive des documents (CDC 4.15.1, 10.3 n 171) : ecriture = Secretaire,
# President, VP ; lecture = Bureau (position prudente par defaut).
ARCHIVE_WRITER_ROLES = frozenset(
    {MembershipRole.Role.SECRETARY, MembershipRole.Role.PRESIDENT, MembershipRole.Role.VICE_PRESIDENT}
)
ARCHIVE_READER_ROLES = frozenset(
    {
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.SPORTS_DIRECTOR,
        MembershipRole.Role.TREASURER,
        MembershipRole.Role.ASSISTANT_TREASURER,
        MembershipRole.Role.STEWARD,
        MembershipRole.Role.SECRETARY,
    }
)


class CanManageAssembly(HasClubRole):
    required_roles = ASSEMBLY_MANAGER_ROLES
    message = "Réservé au Président et au Vice-président."


class CanConveneAssembly(HasClubRole):
    required_roles = ASSEMBLY_CONVENER_ROLES
    message = "Réservé au Président, au Vice-président et au Secrétaire."


class CanWriteArchive(HasClubRole):
    required_roles = ARCHIVE_WRITER_ROLES
    message = "Réservé au Secrétaire, au Président et au Vice-président."


class CanReadArchive(HasClubRole):
    required_roles = ARCHIVE_READER_ROLES
    message = "Réservé aux membres du Bureau."
