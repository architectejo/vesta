"""Fixtures communes aux tests de la logistique (tâche 4.3)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory, MembershipRoleFactory


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


@dataclass
class LogisticsClubContext:
    club: object
    president: Membership
    vice_president: Membership
    treasurer: Membership
    steward: Membership
    coach: Membership
    player: Membership


def build_logistics_club_context(*, timezone_name: str = "Africa/Kinshasa") -> LogisticsClubContext:
    club = ClubSettingsFactory(timezone=timezone_name).club
    return LogisticsClubContext(
        club=club,
        president=make_member(club, roles=[MembershipRole.Role.PRESIDENT]),
        vice_president=make_member(club, roles=[MembershipRole.Role.VICE_PRESIDENT]),
        treasurer=make_member(club, roles=[MembershipRole.Role.TREASURER]),
        steward=make_member(club, roles=[MembershipRole.Role.STEWARD]),
        coach=make_member(club, roles=[MembershipRole.Role.COACH]),
        player=make_member(club),
    )


@pytest.fixture
def ctx() -> LogisticsClubContext:
    return build_logistics_club_context()


@pytest.fixture
def other_ctx() -> LogisticsClubContext:
    return build_logistics_club_context()
