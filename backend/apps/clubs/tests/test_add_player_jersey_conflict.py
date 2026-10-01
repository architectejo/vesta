"""Ajout manuel d'un joueur : numero de maillot deja porte (CDC 4.3 etape 1).

Regression : `add_player_with_sponsor` leve `PlayerImportError` quand le
numero de maillot est deja porte par un joueur actif du club. La vue
`POST clubs:players-add` ne l'attrapait pas (500). Elle doit renvoyer 400
avec `{"detail": <message du service>}`, sans rien ecrire en base.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from apps.clubs import services as clubs_services
from apps.clubs.models import Membership
from apps.clubs.tests.test_add_player_atomicity import _authenticated_client, _counts
from apps.clubs.tests.test_membership_application import add_player, build_context
from apps.treasury.tests.conftest import make_member

pytestmark = pytest.mark.django_db

TAKEN_NUMBER = 10
FREE_NUMBER = 11


def _give_jersey(membership, number):
    membership.jersey_number = number
    membership.save()
    return membership


def _payload(ctx, **overrides) -> dict:
    data = {
        "email": "maillot@example.com",
        "first_name": "Nouveau",
        "last_name": "Maillot",
        "position": Membership.Position.MIDFIELDER,
        "sponsor_membership_id": ctx.sponsor.id,
    }
    data.update(overrides)
    return data


class TestAddPlayerJerseyConflictService:
    def test_jersey_number_worn_by_an_active_member_raises_player_import_error(self):
        ctx = build_context()
        holder = _give_jersey(make_member(ctx.club), TAKEN_NUMBER)

        with pytest.raises(clubs_services.PlayerImportError) as exc_info:
            add_player(ctx, email="maillot@example.com", jersey_number=TAKEN_NUMBER)

        assert str(exc_info.value)
        assert holder.user.last_name in str(exc_info.value)


class TestAddPlayerJerseyConflictView:
    def test_president_adding_a_player_with_a_taken_jersey_number_gets_400_with_detail(self):
        ctx = build_context()
        _give_jersey(make_member(ctx.club), TAKEN_NUMBER)
        client = _authenticated_client(ctx.president.user)

        response = client.post(reverse("clubs:players-add"), _payload(ctx, jersey_number=TAKEN_NUMBER))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"]
        assert str(TAKEN_NUMBER) in response.data["detail"]

    def test_taken_jersey_number_creates_no_user_membership_or_application(self):
        ctx = build_context()
        _give_jersey(make_member(ctx.club), TAKEN_NUMBER)
        client = _authenticated_client(ctx.president.user)
        before = _counts()

        response = client.post(reverse("clubs:players-add"), _payload(ctx, jersey_number=TAKEN_NUMBER))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert _counts() == before

    def test_taken_jersey_number_by_the_sponsor_is_also_refused(self):
        ctx = build_context()
        _give_jersey(ctx.sponsor, TAKEN_NUMBER)
        client = _authenticated_client(ctx.president.user)
        before = _counts()

        response = client.post(reverse("clubs:players-add"), _payload(ctx, jersey_number=TAKEN_NUMBER))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert _counts() == before

    def test_free_jersey_number_still_returns_201_and_is_stored(self):
        ctx = build_context()
        _give_jersey(make_member(ctx.club), TAKEN_NUMBER)
        client = _authenticated_client(ctx.president.user)

        response = client.post(reverse("clubs:players-add"), _payload(ctx, jersey_number=FREE_NUMBER))

        assert response.status_code == status.HTTP_201_CREATED
        membership = Membership.all_objects.get(club=ctx.club, user__email="maillot@example.com")
        assert membership.jersey_number == FREE_NUMBER

    def test_jersey_number_worn_in_another_club_does_not_block_the_add(self):
        ctx = build_context()
        other = build_context()
        _give_jersey(make_member(other.club), TAKEN_NUMBER)
        client = _authenticated_client(ctx.president.user)

        response = client.post(reverse("clubs:players-add"), _payload(ctx, jersey_number=TAKEN_NUMBER))

        assert response.status_code == status.HTTP_201_CREATED

    def test_refused_jersey_conflict_does_not_block_a_later_add_with_a_free_number(self):
        ctx = build_context()
        _give_jersey(make_member(ctx.club), TAKEN_NUMBER)
        client = _authenticated_client(ctx.president.user)

        refused = client.post(reverse("clubs:players-add"), _payload(ctx, jersey_number=TAKEN_NUMBER))
        accepted = client.post(reverse("clubs:players-add"), _payload(ctx, jersey_number=FREE_NUMBER))

        assert refused.status_code == status.HTTP_400_BAD_REQUEST
        assert accepted.status_code == status.HTTP_201_CREATED

    def test_add_without_jersey_number_still_returns_201(self):
        ctx = build_context()
        _give_jersey(make_member(ctx.club), TAKEN_NUMBER)
        client = _authenticated_client(ctx.president.user)

        response = client.post(reverse("clubs:players-add"), _payload(ctx))

        assert response.status_code == status.HTTP_201_CREATED
