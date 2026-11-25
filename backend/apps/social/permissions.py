"""Classes de permission DRF de l'app social (CDC 2.4 ; matrice « Communiques
officiels », « Fil public : publier », « Chat d'equipe » ;
fil-public-communication.md).

- Fil : lecture ouverte a tout membre actif (``IsActiveClubMember``,
  reutilisee) ; publier/commenter/aimer/signaler : tous les joueurs (meme
  classe suffit, aucune restriction de role) ; suppression : gerée au
  niveau service (auteur ou President du club d'origine -- pas une simple
  question de role, CDC 4.16).
- Communiques : lecture/« J'ai lu »/partage : tout joueur ; publier,
  epingler/desepingler, voir les accuses de lecture : President, VP,
  Secretaire (decision client du 11/10/2026, 10.3 n 169).
- Chat : le canal General est ouvert a tout membre actif ; le canal
  Bureau est restreint aux roles du bureau (10.3 n 165 : President, VP, DS,
  Tresorier, adjoint, Intendant, Secretaire depuis le 11/10/2026 -- SANS le
  Medecin, malgre l'incoherence relevee avec club-comite-bureau.md).
"""

from __future__ import annotations

from apps.clubs.models import MembershipRole
from apps.core.roles import HasClubRole, has_any_role

ANNOUNCEMENT_MANAGER_ROLES = frozenset(
    {MembershipRole.Role.PRESIDENT, MembershipRole.Role.VICE_PRESIDENT, MembershipRole.Role.SECRETARY}
)

# Position provisoire la plus restrictive (point ouvert F.10) : le CDC ne
# definit pas la composition du canal Bureau. `club-comite-bureau.md`
# range le Medecin dans la section « Bureau », mais 2.3 distingue « les
# membres du bureau et le Medecin » -- le Medecin est donc EXCLU ici,
# a lever par le client.
BOARD_CHANNEL_ROLES = frozenset(
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


class CanManageAnnouncements(HasClubRole):
    required_roles = ANNOUNCEMENT_MANAGER_ROLES
    message = "Réservé au Président, au Vice-président et au Secrétaire."


def can_access_board_channel(user, *, club=None) -> bool:
    return has_any_role(user, BOARD_CHANNEL_ROLES, club=club)
