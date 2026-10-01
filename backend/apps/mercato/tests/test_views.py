"""Tests HTTP de l'API mercato (CDC 4.14 ; tâche 4.4)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from apps.mercato import services
from apps.mercato.tests.conftest import MercatoClubContext, client_for

pytestmark = pytest.mark.django_db


def test_player_toggles_own_availability(ctx: MercatoClubContext):
    client = client_for(ctx.player.user)
    response = client.patch(reverse("mercato:availability"), {"is_on_transfer_market": True}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_on_transfer_market"] is True


@pytest.mark.parametrize("role_name", ["treasurer", "coach", "vice_president"])
def test_market_read_allowed_but_offer_and_messaging_denied(ctx: MercatoClubContext, other_ctx: MercatoClubContext, role_name: str):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    client = client_for(getattr(ctx, role_name).user)
    assert client.get(reverse("mercato:market-list")).status_code == status.HTTP_200_OK

    denied = client.post(
        reverse("mercato:offer-create"),
        {"target_membership_id": other_ctx.player.pk, "message": "Bonjour"},
        format="json",
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN


def test_president_creates_offer_and_player_accepts(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)

    client_president = client_for(ctx.president.user)
    created = client_president.post(
        reverse("mercato:offer-create"),
        {"target_membership_id": other_ctx.player.pk, "message": "Rejoignez-nous", "conditions": ""},
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED
    offer_id = created.data["id"]

    # Un autre joueur ne peut pas répondre à la place du joueur visé.
    client_wrong_player = client_for(ctx.player.user)
    wrong_response = client_wrong_player.post(
        reverse("mercato:offer-respond", args=[offer_id]), {"accept": True}, format="json"
    )
    assert wrong_response.status_code == status.HTTP_400_BAD_REQUEST


def test_player_sees_and_responds_to_his_own_offer(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )

    client_player = client_for(other_ctx.player.user)
    detail = client_player.get(reverse("mercato:offer-detail", args=[offer.pk]))
    assert detail.status_code == status.HTTP_200_OK

    responded = client_player.post(reverse("mercato:offer-respond", args=[offer.pk]), {"accept": True}, format="json")
    assert responded.status_code == status.HTTP_200_OK
    assert responded.data["status"] == "completed"


def test_my_offers_lists_offers_for_the_authenticated_player(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    client = client_for(other_ctx.player.user)
    response = client.get(reverse("mercato:offer-mine"))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
