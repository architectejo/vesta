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
    assert wrong_response.status_code == status.HTTP_403_FORBIDDEN


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


def _completed_offer(ctx, other_ctx):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    return services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)


def test_transferred_player_pending_in_new_club_still_sees_offer_and_quitus(ctx, other_ctx):
    """D8 : adhésion « en attente » dans le nouveau club, l'offre et le quitus restent accessibles au joueur visé seulement."""
    offer = _completed_offer(ctx, other_ctx)
    assert offer.status == "completed"
    player = client_for(other_ctx.player.user)
    mine = player.get(reverse("mercato:offer-mine"))
    assert mine.status_code == status.HTTP_200_OK and [o["id"] for o in mine.data["results"]] == [offer.pk]
    assert player.get(reverse("mercato:offer-detail", args=[offer.pk])).status_code == status.HTTP_200_OK
    assert player.get(reverse("mercato:offer-quitus", args=[offer.pk])).status_code == status.HTTP_200_OK

    # Un autre joueur (même club, ou autre club) ne voit rien : étanchéité.
    stranger = client_for(ctx.player.user)
    assert stranger.get(reverse("mercato:offer-mine")).data["results"] == []
    assert stranger.get(reverse("mercato:offer-detail", args=[offer.pk])).status_code == status.HTTP_404_NOT_FOUND
    assert stranger.get(reverse("mercato:offer-quitus", args=[offer.pk])).status_code == status.HTTP_403_FORBIDDEN


def test_respond_by_non_recipient_is_403(ctx, other_ctx):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    response = client_for(ctx.player.user).post(
        reverse("mercato:offer-respond", args=[offer.pk]), {"accept": True}, format="json"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_thread_with_unknown_offer_is_404(ctx, other_ctx):
    response = client_for(ctx.president.user).post(
        reverse("mercato:thread-list"),
        {"club_id": other_ctx.club.pk, "message": "Bonjour", "transfer_offer_id": 999999},
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_market_filters_and_pagination(ctx, other_ctx):
    import datetime


    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    other_ctx.player.user.birth_date = datetime.date.today().replace(year=datetime.date.today().year - 30, day=1)
    other_ctx.player.user.save()
    client = client_for(ctx.president.user)
    url = reverse("mercato:market-list")

    ids = lambda params: [r["membership_id"] for r in client.get(url, params).data["results"]]  # noqa: E731
    assert ids({}) == [other_ctx.player.pk]
    assert ids({"min_age": 25}) == [other_ctx.player.pk]
    assert ids({"min_age": 40}) == []
    assert ids({"max_age": 20}) == []
    assert ids({"city": other_ctx.club.city}) == [other_ctx.player.pk]
    assert ids({"city": "zzz-introuvable"}) == []
    assert ids({"min_rating": 5}) == []  # aucune évaluation
    data = client.get(url, {"page_size": 1}).data
    assert data["count"] == 1 and data["page_size"] == 1 and data["next_page"] is None
    assert client.get(url, {"min_age": "abc"}).status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.parametrize(
    "params",
    [
        {"club": "abc"},
        {"club": "0"},
        {"club": "99999999999999999999"},
        {"min_rating": "NaN"},
        {"min_rating": "Infinity"},
        {"min_rating": "-Infinity"},
        {"min_rating": "11"},
        {"min_rating": "-1"},
        {"min_age": "99999"},
        {"min_age": "-3"},
        {"max_age": "99999"},
        {"page": "0"},
        {"page": "-2"},
        {"page": "abc"},
        {"page": "99999999999999999999"},
        {"page_size": "0"},
        {"page_size": "-5"},
    ],
)
def test_market_rejects_invalid_parameters_in_french(ctx, other_ctx, params):
    response = client_for(ctx.president.user).get(reverse("mercato:market-list"), params)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"][0].isupper()
    assert "paramètre" in response.data["detail"] or "note" in response.data["detail"]


def test_market_still_accepts_valid_boundaries(ctx, other_ctx):
    client = client_for(ctx.president.user)
    url = reverse("mercato:market-list")

    assert client.get(url, {"min_rating": "0", "page": "1", "page_size": "100", "min_age": "0"}).status_code == 200
    assert client.get(url, {"min_rating": "10", "max_age": "120"}).status_code == 200
    assert client.get(url, {"club": str(other_ctx.club.pk)}).status_code == 200
