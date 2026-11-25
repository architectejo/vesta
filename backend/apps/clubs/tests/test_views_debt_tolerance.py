"""Tolérance de dette configurable par le club (CDC 4.4.2, 10.2 n°4)."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubFactory, ClubSettingsFactory, MembershipFactory, MembershipRoleFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _client(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _club_with_president():
    club = ClubFactory()
    ClubSettingsFactory(club=club)
    president = MembershipFactory(club=club)
    MembershipRoleFactory(membership=president, club=club, role=MembershipRole.Role.PRESIDENT)
    return club, president


def test_tout_membre_lit_la_tolerance():
    club, _ = _club_with_president()
    club.settings.debt_tolerance_days = 12
    club.settings.save()
    member = MembershipFactory(club=club)

    response = _client(member.user).get(reverse("clubs:identity"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["debt_tolerance_days"] == 12


def test_le_president_modifie_la_tolerance_et_c_est_journalise():
    club, president = _club_with_president()

    response = _client(president.user).patch(
        reverse("clubs:identity"), {"debt_tolerance_days": 30}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["debt_tolerance_days"] == 30
    club.settings.refresh_from_db()
    assert club.settings.debt_tolerance_days == 30
    entry = AuditLog.objects.filter(action_type="clubs.identity.updated", club=club).latest("id")
    assert entry.before["debt_tolerance_days"] == 0
    assert entry.after["debt_tolerance_days"] == 30


def test_un_autre_role_ne_peut_pas_modifier_la_tolerance():
    club, _ = _club_with_president()
    treasurer = MembershipFactory(club=club)
    MembershipRoleFactory(membership=treasurer, club=club, role=MembershipRole.Role.TREASURER)

    response = _client(treasurer.user).patch(
        reverse("clubs:identity"), {"debt_tolerance_days": 30}, format="json"
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    club.settings.refresh_from_db()
    assert club.settings.debt_tolerance_days == 0


@pytest.mark.parametrize("value", [-1, 91, 1000, "abc"])
def test_valeur_hors_bornes_refusee(value):
    club, president = _club_with_president()

    response = _client(president.user).patch(
        reverse("clubs:identity"), {"debt_tolerance_days": value}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    club.settings.refresh_from_db()
    assert club.settings.debt_tolerance_days == 0


@pytest.mark.parametrize("value", [0, 90])
def test_bornes_acceptees(value):
    club, president = _club_with_president()

    response = _client(president.user).patch(
        reverse("clubs:identity"), {"debt_tolerance_days": value}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["debt_tolerance_days"] == value


def test_etancheite_entre_clubs():
    club_a, president_a = _club_with_president()
    club_b, _ = _club_with_president()

    _client(president_a.user).patch(reverse("clubs:identity"), {"debt_tolerance_days": 45}, format="json")

    club_b.settings.refresh_from_db()
    assert club_b.settings.debt_tolerance_days == 0
