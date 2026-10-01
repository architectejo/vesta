"""Tests d'étanchéité inter-clubs du mercato (CDC 2.1 de mercato.md ; point
de vigilance n° 1 de la tâche 4.4).

Le marché est le seul écran qui affiche des données d'un AUTRE club :
ces tests vérifient qu'un club ne voit de l'autre QUE ce que le marché
public expose explicitement -- jamais une donnée financière, médicale, ni
un champ privé (poids, taille, téléphone, email)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from apps.mercato import services
from apps.mercato.models import TransferOffer
from apps.mercato.tests.conftest import MercatoClubContext, client_for, make_debtor

pytestmark = pytest.mark.django_db


def test_market_listing_never_exposes_private_fields(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    other_ctx.player.user.weight_kg = Decimal("70.0")
    other_ctx.player.user.height_cm = Decimal("180.0")
    other_ctx.player.user.phone = "+243900000000"
    other_ctx.player.user.save()
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)

    client = client_for(ctx.president.user)
    response = client.get(reverse("mercato:market-list"))
    assert response.status_code == status.HTTP_200_OK
    row = next(r for r in response.data["results"] if r["membership_id"] == other_ctx.player.pk)

    forbidden_keys = {"weight_kg", "height_cm", "phone", "email", "balance", "is_in_good_standing", "birth_date", "fitness_status"}
    assert forbidden_keys.isdisjoint(row.keys())
    assert row["club"]["id"] == other_ctx.club.id


def test_public_player_detail_never_exposes_private_fields(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    client = client_for(ctx.president.user)
    response = client.get(reverse("mercato:player-public-detail", args=[other_ctx.player.pk]))
    assert response.status_code == status.HTTP_200_OK
    forbidden_keys = {"weight_kg", "height_cm", "phone", "email", "balance", "is_in_good_standing", "birth_date", "fitness_status"}
    assert forbidden_keys.isdisjoint(response.data.keys())


def test_market_hides_players_not_on_market(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    # other_ctx.player n'est jamais mis sur le marché ici.
    client = client_for(ctx.president.user)
    response = client.get(reverse("mercato:market-list"))
    ids = {r["membership_id"] for r in response.data["results"]}
    assert other_ctx.player.pk not in ids


def test_target_club_never_sees_debt_amount_or_word_dette(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    make_debtor(other_ctx.club, other_ctx.player)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)
    assert offer.status == TransferOffer.Status.BLOCKED_DEBT

    # Club B (destinataire, target_club = ctx.club) : jamais de montant, jamais
    # le statut brut "blocked_debt", jamais le mot "dette".
    client_b = client_for(ctx.president.user)
    response = client_b.get(reverse("mercato:offer-detail", args=[offer.pk]))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "awaiting_quitus"
    assert response.data["debt_amount"] is None
    assert "dette" not in str(response.data).lower()

    # Club A (origine) : le Président voit le montant.
    client_a = client_for(other_ctx.president.user)
    response_a = client_a.get(reverse("mercato:offer-detail", args=[offer.pk]))
    assert response_a.data["status"] == TransferOffer.Status.BLOCKED_DEBT
    assert response_a.data["debt_amount"] == "10.00"


def test_target_club_sports_director_never_sees_amount_in_origin_side(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    """Le DS/Coach du club d'origine ne voit pas le montant (§5.3 point
    ouvert n° 3, position la plus prudente appliquée par défaut)."""

    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    make_debtor(other_ctx.club, other_ctx.player)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )
    offer = services.respond_to_offer(offer=offer, actor=other_ctx.player.user, accept=True)

    client = client_for(other_ctx.coach.user)
    response = client.get(reverse("mercato:offer-detail", args=[offer.pk]))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["debt_amount"] is None


def test_offers_from_a_third_club_are_not_visible(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    from apps.mercato.tests.conftest import build_mercato_club_context

    third_ctx = build_mercato_club_context()
    services.set_market_availability(membership=other_ctx.player, actor=other_ctx.player.user, is_on_market=True)
    offer = services.create_transfer_offer(
        initiated_by=ctx.president.user, target_club=ctx.club, target_membership=other_ctx.player, message="Bonjour"
    )

    client = client_for(third_ctx.president.user)
    response = client.get(reverse("mercato:offer-detail", args=[offer.pk]))
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_messaging_restricted_to_president_and_sports_director(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    """Position provisoire, la plus prudente, appliquée à la contradiction
    schéma §8.2 / CDC 4.14 (voir docstring apps.mercato.models) : la
    messagerie n'est lisible/utilisable que par le Président et le DS,
    jamais par « tout membre » des deux clubs."""

    thread_url = reverse("mercato:thread-list")

    # Président : autorisé à écrire.
    client_president = client_for(ctx.president.user)
    created = client_president.post(
        thread_url, {"club_id": other_ctx.club.id, "message": "Bonjour, avez-vous un joueur disponible ?"}, format="json"
    )
    assert created.status_code == status.HTTP_201_CREATED
    thread_id = created.data["id"]

    # Trésorier et Coach : aucun accès à la messagerie (même club).
    for member in (ctx.treasurer, ctx.coach, ctx.vice_president, ctx.player):
        client = client_for(member.user)
        assert client.get(thread_url).status_code == status.HTTP_403_FORBIDDEN
        assert (
            client.get(reverse("mercato:thread-messages", args=[thread_id])).status_code == status.HTTP_403_FORBIDDEN
        )

    # Directeur sportif du club destinataire : autorisé à lire le fil.
    client_ds_other = client_for(other_ctx.sports_director.user)
    read = client_ds_other.get(thread_url)
    assert read.status_code == status.HTTP_200_OK
    assert any(t["id"] == thread_id for t in read.data["results"])


def test_third_club_officer_cannot_read_a_thread_between_two_other_clubs(ctx: MercatoClubContext, other_ctx: MercatoClubContext):
    from apps.mercato.tests.conftest import build_mercato_club_context

    third_ctx = build_mercato_club_context()
    client_president = client_for(ctx.president.user)
    created = client_president.post(
        reverse("mercato:thread-list"), {"club_id": other_ctx.club.id, "message": "Bonjour"}, format="json"
    )
    thread_id = created.data["id"]

    client_third = client_for(third_ctx.president.user)
    response = client_third.get(reverse("mercato:thread-messages", args=[thread_id]))
    assert response.status_code == status.HTTP_404_NOT_FOUND
