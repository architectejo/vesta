"""Fixtures communes aux tests de l'app medical (Lot 4, tache 4.2).

Meme structure que ``apps.sport.tests.conftest`` : un club de test avec
son bureau (President, Vice-president, Coach, Capitaine, Medecin) et des
joueurs, pour couvrir la matrice 2.4 sans dupliquer la mise en place
dans chaque fichier de test.
"""

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


def make_member(club, *, roles=(), status=Membership.Status.ACTIVE, role_kwargs=None, **kwargs):
    user = UserFactory()
    membership = MembershipFactory(club=club, user=user, status=status, **kwargs)
    for role in roles:
        MembershipRoleFactory(
            membership=membership, club=club, role=role, appointed_at=timezone.now(), **(role_kwargs or {})
        )
    return membership


@dataclass
class MedicalClubContext:
    club: object
    president: Membership
    vice_president: Membership
    doctor: Membership
    coach: Membership
    captain: Membership
    player: Membership
    other_player: Membership


def build_medical_club_context() -> MedicalClubContext:
    club = ClubSettingsFactory(timezone="Africa/Kinshasa").club
    return MedicalClubContext(
        club=club,
        president=make_member(club, roles=[MembershipRole.Role.PRESIDENT]),
        vice_president=make_member(club, roles=[MembershipRole.Role.VICE_PRESIDENT]),
        doctor=make_member(
            club, roles=[MembershipRole.Role.DOCTOR], role_kwargs={"is_qualified_professional": False}
        ),
        coach=make_member(club, roles=[MembershipRole.Role.COACH]),
        captain=make_member(club, roles=[MembershipRole.Role.CAPTAIN]),
        player=make_member(club),
        other_player=make_member(club),
    )


@pytest.fixture
def ctx() -> MedicalClubContext:
    return build_medical_club_context()


@pytest.fixture
def other_ctx() -> MedicalClubContext:
    return build_medical_club_context()
