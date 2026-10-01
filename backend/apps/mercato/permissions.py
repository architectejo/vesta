"""Classes de permission DRF de l'app mercato (matrice CDC 2.4 ; fiche
d'écran mercato.md §2)."""

from __future__ import annotations

from apps.clubs.models import MembershipRole
from apps.core.roles import HasClubRole

# Marché (consultation), Offres du club : Pdt, VP, DS, Trés, Coach (« É »/« L »).
MARKET_READER_ROLES = frozenset(
    {
        MembershipRole.Role.PRESIDENT,
        MembershipRole.Role.VICE_PRESIDENT,
        MembershipRole.Role.SPORTS_DIRECTOR,
        MembershipRole.Role.TREASURER,
        MembershipRole.Role.COACH,
    }
)

# Faire une offre, Messagerie entre clubs : Pdt, DS seulement (« É »).
OFFER_AND_MESSAGING_ROLES = frozenset({MembershipRole.Role.PRESIDENT, MembershipRole.Role.SPORTS_DIRECTOR})


class CanReadMarket(HasClubRole):
    required_roles = MARKET_READER_ROLES
    message = "Réservé au Président, au Vice-président, au Directeur sportif, au Trésorier et au Coach (CDC 2.4)."


class CanMakeOfferOrMessage(HasClubRole):
    required_roles = OFFER_AND_MESSAGING_ROLES
    message = "Réservé au Président et au Directeur sportif (CDC 2.4, 4.14)."
