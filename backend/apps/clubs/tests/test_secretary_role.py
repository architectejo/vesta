"""Role Secretaire : nomination, revocation, un seul titulaire, cumul
(CDC 2.2, 2.3 ; decision client du 11/10/2026, 10.3 n 169)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.clubs import services
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubFactory, MembershipFactory, MembershipRoleFactory
from apps.core.roles import get_active_roles
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

SECRETARY = MembershipRole.Role.SECRETARY


def _client(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _president(club):
    membership = MembershipFactory(club=club)
    MembershipRoleFactory(membership=membership, role=MembershipRole.Role.PRESIDENT)
    return membership


def test_secretary_has_key_and_label():
    assert SECRETARY == "secretary"
    assert MembershipRole.Role(SECRETARY).label == "Secrétaire"


def test_president_appoints_the_secretary_through_the_api_and_the_player_is_notified():
    club = ClubFactory()
    president = _president(club)
    target = MembershipFactory(club=club)

    response = _client(president.user).post(
        reverse("clubs:role-appoint"), {"membership_id": target.id, "role": SECRETARY}, format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["role"] == "secretary"
    assert response.data["role_label"] == "Secrétaire"
    assert SECRETARY in get_active_roles(target.user, club=club)
    assert Notification.objects.filter(recipient=target.user, event_type="role_appointed_or_revoked").exists()


def test_only_the_president_can_appoint_the_secretary():
    club = ClubFactory()
    vp = MembershipFactory(club=club)
    MembershipRoleFactory(membership=vp, role=MembershipRole.Role.VICE_PRESIDENT)
    target = MembershipFactory(club=club)

    response = _client(vp.user).post(
        reverse("clubs:role-appoint"), {"membership_id": target.id, "role": SECRETARY}, format="json"
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_another_clubs_president_cannot_appoint_a_secretary_here():
    club_a, club_b = ClubFactory(), ClubFactory()
    president_a = _president(club_a)
    target_b = MembershipFactory(club=club_b)

    response = _client(president_a.user).post(
        reverse("clubs:role-appoint"), {"membership_id": target_b.id, "role": SECRETARY}, format="json"
    )

    assert response.status_code in (403, 404)
    assert not MembershipRole.all_objects.filter(club=club_b, role=SECRETARY).exists()


def test_a_second_active_secretary_is_refused_by_default():
    club = ClubFactory()
    president = _president(club)
    first, second = MembershipFactory(club=club), MembershipFactory(club=club)
    services.appoint_president_nominated_role(president_user=president.user, target_membership=first, role=SECRETARY)

    with pytest.raises(ValidationError):
        services.appoint_president_nominated_role(
            president_user=president.user, target_membership=second, role=SECRETARY
        )


def test_revoking_frees_the_seat_and_removes_the_rights():
    club = ClubFactory()
    president = _president(club)
    first, second = MembershipFactory(club=club), MembershipFactory(club=club)
    role = services.appoint_president_nominated_role(
        president_user=president.user, target_membership=first, role=SECRETARY
    )

    services.revoke_president_nominated_role(president_user=president.user, role=role, reason="Fin de mandat")

    assert SECRETARY not in get_active_roles(first.user, club=club)
    services.appoint_president_nominated_role(president_user=president.user, target_membership=second, role=SECRETARY)
    assert SECRETARY in get_active_roles(second.user, club=club)


def test_two_clubs_each_have_their_own_secretary():
    club_a, club_b = ClubFactory(), ClubFactory()
    for club in (club_a, club_b):
        services.appoint_president_nominated_role(
            president_user=_president(club).user, target_membership=MembershipFactory(club=club), role=SECRETARY
        )
    assert MembershipRole.all_objects.filter(role=SECRETARY, revoked_at__isnull=True).count() == 2


def test_the_secretary_can_cumulate_with_another_role_and_rights_are_the_union():
    club = ClubFactory()
    president = _president(club)
    target = MembershipFactory(club=club)
    services.appoint_president_nominated_role(president_user=president.user, target_membership=target, role=SECRETARY)
    services.appoint_president_nominated_role(
        president_user=president.user, target_membership=target, role=MembershipRole.Role.TREASURER
    )
    assert get_active_roles(target.user, club=club) >= {SECRETARY, MembershipRole.Role.TREASURER}


def test_a_plain_player_cannot_appoint_themselves_secretary():
    club = ClubFactory()
    _president(club)
    player = MembershipFactory(club=club)
    response = _client(player.user).post(
        reverse("clubs:role-appoint"), {"membership_id": player.id, "role": SECRETARY}, format="json"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
