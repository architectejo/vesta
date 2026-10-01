"""Fixtures communes aux tests de la tresorerie (tache 1.4b).

Chaque club de test dispose de ses parametres (`ClubSettings` : devise,
fuseau), d'un President, d'un Tresorier, d'un Tresorier adjoint, d'un
Vice-president et d'un simple joueur, tous avec un code PIN connu
(`PIN`). Le nouveau joueur « En attente » (`pending_member`) a un parrain
inscrit (CDC 4.3, etape 1).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.treasury.tests.factories import MembershipFeeTypeFactory

PIN = "2468"
WRONG_PIN = "1357"


def past_day(days: int = 2) -> datetime.date:
    """Date de paiement passee, sans ambiguite de fuseau (marge de 2 jours)."""

    return timezone.now().date() - datetime.timedelta(days=days)


def make_member(club, *, roles=(), status=Membership.Status.ACTIVE, sponsor=None, pin=PIN):
    user = UserFactory(pin_hash=make_password(pin) if pin else "")
    membership = MembershipFactory(club=club, user=user, status=status, sponsor=sponsor)
    for role in roles:
        MembershipRoleFactory(membership=membership, club=club, role=role, appointed_at=timezone.now())
    return membership


@dataclass
class ClubContext:
    club: object
    president: Membership
    vice_president: Membership
    treasurer: Membership
    assistant_treasurer: Membership
    player: Membership
    pending_member: Membership


def build_club_context(currency="USD") -> ClubContext:
    club = ClubSettingsFactory(currency=currency, timezone="Africa/Kinshasa").club
    president = make_member(club, roles=[MembershipRole.Role.PRESIDENT])
    player = make_member(club)
    return ClubContext(
        club=club,
        president=president,
        vice_president=make_member(club, roles=[MembershipRole.Role.VICE_PRESIDENT]),
        treasurer=make_member(club, roles=[MembershipRole.Role.TREASURER]),
        assistant_treasurer=make_member(club, roles=[MembershipRole.Role.ASSISTANT_TREASURER]),
        player=player,
        pending_member=make_member(club, status=Membership.Status.PENDING, sponsor=player),
    )


@pytest.fixture
def ctx(db) -> ClubContext:
    return build_club_context()


@pytest.fixture
def other_ctx(db) -> ClubContext:
    return build_club_context(currency="CDF")


@pytest.fixture
def fee_type(ctx):
    return MembershipFeeTypeFactory(club=ctx.club, created_by=ctx.president.user)


@pytest.fixture
def other_fee_type(other_ctx):
    return MembershipFeeTypeFactory(club=other_ctx.club, created_by=other_ctx.president.user)
