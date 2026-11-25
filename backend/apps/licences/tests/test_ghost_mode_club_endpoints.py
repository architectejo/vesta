"""Session de support (Ghost Mode, CDC 4.18, 5.4) utilisable en HTTP sur les données du club.

Position prudente (CDC 5.4 ne précise pas lecture/écriture par endpoint) :
lecture seule sur les données du club ; aucune écriture ; jamais de contenu
médical (10.2 n° 137) ; strictement limité au club de la session.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.core.ghost_context import clear_ghost_context
from apps.core.tenant import set_active_club

pytestmark = pytest.mark.django_db

READ_PATHS = [
    "/api/v1/assemblies/",
    "/api/v1/assemblies/documents/",
    "/api/v1/social/posts/",
    "/api/v1/social/announcements/",
    "/api/v1/clubs/players/",
    "/api/v1/social/chat/channels/",
    "/api/v1/treasury/contribution-types/",
]


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    set_active_club(None)
    clear_ghost_context()
    cache.clear()


@pytest.fixture
def ghost():
    club = ClubSettingsFactory().club
    other = ClubSettingsFactory().club
    president = MembershipFactory(club=club, status="active")
    MembershipRoleFactory(membership=president, club=club, role=MembershipRole.Role.PRESIDENT)
    superuser = SuperuserFactory()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(superuser).access_token}")
    start = client.post(
        reverse("licences:support-session-start"), {"club_id": club.pk, "reason": "Vérification."}, format="json"
    )
    assert start.status_code == status.HTTP_201_CREATED
    return client, str(start.data["id"]), club, other


@pytest.mark.parametrize("path", READ_PATHS)
def test_superuser_reads_club_data_during_support_session(ghost, path):
    client, session_id, _club, _other = ghost
    response = client.get(path, HTTP_X_SUPPORT_SESSION=session_id)
    assert response.status_code == status.HTTP_200_OK, (path, response.status_code, getattr(response, "data", None))


@pytest.mark.parametrize("path", READ_PATHS)
def test_superuser_without_support_session_stays_refused(ghost, path):
    client, _session_id, _club, _other = ghost
    response = client.get(path)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_support_session_is_read_only_and_never_medical(ghost):
    client, session_id, _club, _other = ghost
    denied = client.post("/api/v1/social/posts/", {"content": "x"}, format="json", HTTP_X_SUPPORT_SESSION=session_id)
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    for path in ("/api/v1/medical/page/unfit/", "/api/v1/medical/page/recent-injuries/", "/api/v1/medical/injuries/"):
        assert client.get(path, HTTP_X_SUPPORT_SESSION=session_id).status_code in (403, 404)
