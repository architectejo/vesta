"""Fixtures communes aux tests de l'app sport (taches 3.2-3.4).

Meme structure que ``apps.treasury.tests.conftest`` : un club de test
avec son bureau (Président, Vice-président, Directeur sportif, Coach,
Capitaine, Médecin) et des joueurs dans des situations différentes (en
ordre, en dette, en attente d'adhésion), pour couvrir CLAUDE.md règle n°
5 sans dupliquer la mise en place dans chaque fichier de test.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory, MembershipRoleFactory, SeasonFactory
from apps.treasury.models import ContributionType, Due
from apps.treasury.tests.factories import ContributionTypeFactory


def client_for(user) -> APIClient:
    """Client API authentifie par JWT (meme convention que
    ``apps.treasury.tests.test_views_contribution_types.client_for``)."""

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


def make_debtor(club, membership) -> Membership:
    """Rend ``membership`` en dette : un type obligatoire échu, sans paiement
    (voir apps.treasury.services._matured_mandatory_dues)."""

    ctype = ContributionTypeFactory(
        club=club, nature=ContributionType.Nature.MANDATORY, scope=ContributionType.Scope.ALL
    )
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
    return membership


@dataclass
class SportClubContext:
    club: object
    season: object
    president: Membership
    vice_president: Membership
    sports_director: Membership
    doctor: Membership
    coach: Membership
    captain: Membership
    player: Membership
    debtor: Membership
    pending_member: Membership


def build_sport_club_context(*, timezone_name: str = "Africa/Kinshasa") -> SportClubContext:
    club = ClubSettingsFactory(timezone=timezone_name).club
    today = timezone.now().date()
    season = SeasonFactory(
        club=club,
        start_date=today.replace(month=1, day=1),
        end_date=today.replace(month=12, day=31),
    )
    president = make_member(club, roles=[MembershipRole.Role.PRESIDENT])
    coach = make_member(club, roles=[MembershipRole.Role.COACH])
    captain = make_member(club, roles=[MembershipRole.Role.CAPTAIN])
    player = make_member(club)
    debtor = make_member(club)
    make_debtor(club, debtor)
    return SportClubContext(
        club=club,
        season=season,
        president=president,
        vice_president=make_member(club, roles=[MembershipRole.Role.VICE_PRESIDENT]),
        sports_director=make_member(club, roles=[MembershipRole.Role.SPORTS_DIRECTOR]),
        doctor=make_member(
            club, roles=[MembershipRole.Role.DOCTOR], role_kwargs={"is_qualified_professional": False}
        ),
        coach=coach,
        captain=captain,
        player=player,
        debtor=debtor,
        pending_member=make_member(club, status=Membership.Status.PENDING, sponsor=player),
    )


@pytest.fixture
def ctx() -> SportClubContext:
    return build_sport_club_context()


@pytest.fixture
def other_ctx() -> SportClubContext:
    return build_sport_club_context()
