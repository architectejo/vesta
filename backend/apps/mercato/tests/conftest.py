"""Fixtures communes aux tests du mercato (tâche 4.4)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.treasury.models import ContributionType, Due
from apps.treasury.tests.factories import ContributionTypeFactory


def client_for(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def make_member(club, *, roles=(), status=Membership.Status.ACTIVE, **kwargs):
    user = UserFactory()
    membership = MembershipFactory(club=club, user=user, status=status, **kwargs)
    for role in roles:
        MembershipRoleFactory(membership=membership, club=club, role=role, appointed_at=timezone.now())
    return membership


def make_debtor(club, membership) -> Membership:
    """Rend ``membership`` en dette (même convention que
    ``apps.sport.tests.conftest.make_debtor``) : un type obligatoire échu,
    sans paiement."""

    ctype = ContributionTypeFactory(club=club, nature=ContributionType.Nature.MANDATORY, scope=ContributionType.Scope.ALL)
    Due.all_objects.create(
        club=club,
        membership=membership,
        contribution_type=ctype,
        period=datetime.date.today().replace(day=1),
        amount="10.00",
        due_date=datetime.date.today() - datetime.timedelta(days=60),
        source=Due.Source.SCHEDULER,
        created_at=timezone.now(),
    )
    return ctype


@dataclass
class MercatoClubContext:
    club: object
    president: Membership
    vice_president: Membership
    sports_director: Membership
    treasurer: Membership
    coach: Membership
    player: Membership


def build_mercato_club_context(*, timezone_name: str = "Africa/Kinshasa") -> MercatoClubContext:
    club = ClubSettingsFactory(timezone=timezone_name).club
    return MercatoClubContext(
        club=club,
        president=make_member(club, roles=[MembershipRole.Role.PRESIDENT]),
        vice_president=make_member(club, roles=[MembershipRole.Role.VICE_PRESIDENT]),
        sports_director=make_member(club, roles=[MembershipRole.Role.SPORTS_DIRECTOR]),
        treasurer=make_member(club, roles=[MembershipRole.Role.TREASURER]),
        coach=make_member(club, roles=[MembershipRole.Role.COACH]),
        player=make_member(club),
    )


@pytest.fixture
def ctx() -> MercatoClubContext:
    return build_mercato_club_context()


@pytest.fixture
def other_ctx() -> MercatoClubContext:
    return build_mercato_club_context()
