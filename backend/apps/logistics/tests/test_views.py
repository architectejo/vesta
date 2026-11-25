"""Tests HTTP de l'API logistics (CDC 4.13 ; tâche 4.3)."""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.core.tenant import active_club
from apps.logistics import services
from apps.logistics.models import Article, StockMovement
from apps.logistics.tests.conftest import LogisticsClubContext, client_for
from apps.sport.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def test_steward_creates_article_and_records_movement(ctx: LogisticsClubContext):
    client = client_for(ctx.steward.user)
    created = client.post(
        reverse("logistics:article-list"),
        {"name": "Maillot domicile", "category": Article.Category.JERSEY, "unit": "pièce"},
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED
    article_id = created.data["id"]

    movement = client.post(
        reverse("logistics:movement-list"),
        {
            "movement_type": StockMovement.MovementType.IN_PURCHASE,
            "article_id": article_id,
            "quantity": 10,
            "movement_date": timezone.now().date().isoformat(),
        },
        format="json",
    )
    assert movement.status_code == status.HTTP_201_CREATED
    assert movement.data["in_stock"] == 10


@pytest.mark.parametrize("role_name", ["president", "vice_president", "treasurer", "coach"])
def test_other_roles_read_but_cannot_write(ctx: LogisticsClubContext, role_name: str):
    client = client_for(getattr(ctx, role_name).user)
    assert client.get(reverse("logistics:overview")).status_code == status.HTTP_200_OK
    assert client.get(reverse("logistics:article-list")).status_code == status.HTTP_200_OK
    denied = client.post(reverse("logistics:article-list"), {"name": "X", "category": Article.Category.MISC}, format="json")
    assert denied.status_code == status.HTTP_403_FORBIDDEN


def test_player_without_material_role_has_no_access_at_all(ctx: LogisticsClubContext):
    """Fiche d'écran logistique.md §2 : contrairement à la plupart des pages
    de club, un simple Joueur (et le DS, l'Adjoint, le Capitaine, le
    Médecin) n'a AUCUNE lecture sur la page Matériel -- « Vous n'avez pas
    accès à cette page. »"""

    client = client_for(ctx.player.user)
    assert client.get(reverse("logistics:overview")).status_code == status.HTTP_403_FORBIDDEN
    assert client.get(reverse("logistics:article-list")).status_code == status.HTTP_403_FORBIDDEN


def test_articles_and_movements_are_scoped_to_active_club(ctx: LogisticsClubContext, other_ctx: LogisticsClubContext):
    with active_club(ctx.club):
        own = services.create_article(club=ctx.club, actor=ctx.steward.user, name="Ballon", category=Article.Category.BALLS)
    with active_club(other_ctx.club):
        foreign = services.create_article(
            club=other_ctx.club, actor=other_ctx.steward.user, name="Ballon adverse", category=Article.Category.BALLS
        )

    client = client_for(ctx.steward.user)
    listed_ids = {row["id"] for row in client.get(reverse("logistics:article-list")).data["results"]}
    assert own.pk in listed_ids
    assert foreign.pk not in listed_ids

    assert client.get(reverse("logistics:article-detail", args=[foreign.pk])).status_code == status.HTTP_404_NOT_FOUND


def test_coach_records_match_equipment_out_and_steward_records_return(ctx: LogisticsClubContext):
    with active_club(ctx.club):
        article = services.create_article(club=ctx.club, actor=ctx.steward.user, name="Maillot", category=Article.Category.JERSEY)
        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=article,
            quantity=10,
            movement_date=timezone.now().date(),
        )
    match = MatchFactory(club=ctx.club, event__club=ctx.club)

    coach_client = client_for(ctx.coach.user)
    out_response = coach_client.post(
        reverse("logistics:match-equipment-out", args=[match.event_id]),
        {"lines": [{"article_id": article.pk, "quantity": 4}]},
        format="json",
    )
    assert out_response.status_code == status.HTTP_201_CREATED

    # Un simple joueur ne peut pas sortir d'équipements.
    player_client = client_for(ctx.player.user)
    denied = player_client.post(
        reverse("logistics:match-equipment-out", args=[match.event_id]),
        {"lines": [{"article_id": article.pk, "quantity": 1}]},
        format="json",
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    steward_client = client_for(ctx.steward.user)
    return_response = steward_client.post(
        reverse("logistics:match-equipment-return", args=[match.event_id]),
        {"lines": [{"article_id": article.pk, "quantity_returned": 4}]},
        format="json",
    )
    assert return_response.status_code == status.HTTP_200_OK
    assert return_response.data["lines"][0]["status"] == "returned"


def test_inventory_endpoints_full_cycle(ctx: LogisticsClubContext):
    with active_club(ctx.club):
        article = services.create_article(club=ctx.club, actor=ctx.steward.user, name="Ballon", category=Article.Category.BALLS)
        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=article,
            quantity=5,
            movement_date=timezone.now().date(),
        )

    client = client_for(ctx.steward.user)
    opened = client.post(reverse("logistics:inventory-open"))
    assert opened.status_code == status.HTTP_201_CREATED
    inventory_id = opened.data["id"]

    second_open = client.post(reverse("logistics:inventory-open"))
    assert second_open.status_code == status.HTTP_400_BAD_REQUEST

    counted = client.post(
        reverse("logistics:inventory-counts", args=[inventory_id]),
        {"counts": [{"article_id": article.pk, "physical_quantity": 4}]},
        format="json",
    )
    assert counted.status_code == status.HTTP_200_OK
    assert counted.data["to_justify"] == 1

    line_id = counted.data["inventory"]["lines"][0]["id"]
    justified = client.post(
        reverse("logistics:inventory-line-justify", args=[line_id]), {"discrepancy_reason": "loss"}, format="json"
    )
    assert justified.status_code == status.HTTP_200_OK
    assert justified.data["status"] == "justified"

    closed = client.post(reverse("logistics:inventory-close", args=[inventory_id]))
    assert closed.status_code == status.HTTP_200_OK
    assert closed.data["status"] == "closed"

    overview = client.get(reverse("logistics:overview"))
    assert overview.status_code == status.HTTP_200_OK
    assert overview.data["can_open"] is False  # trimestre déjà clôturé (D6d)


def test_open_inventory_refused_when_quarter_already_closed(ctx: LogisticsClubContext):
    """D6d : un trimestre déjà clôturé ne peut pas être ré-ouvert (400, pas 500)."""
    client = client_for(ctx.steward.user)
    first = client.post(reverse("logistics:inventory-open"))
    assert first.status_code == status.HTTP_201_CREATED
    closed = client.post(reverse("logistics:inventory-close", args=[first.data["id"]]))
    assert closed.status_code == status.HTTP_200_OK, closed.data

    overview = client.get(reverse("logistics:overview")).data
    assert overview["can_open"] is False
    assert overview["openable_quarter_label"] is None

    again = client.post(reverse("logistics:inventory-open"))
    assert again.status_code == status.HTTP_400_BAD_REQUEST
    assert "déjà" in again.data["detail"]


def test_movement_rejects_unknown_references(ctx: LogisticsClubContext, other_ctx: LogisticsClubContext):
    """D11 : membership d'un autre club, match/dépense inexistants -> 400."""
    client = client_for(ctx.steward.user)
    article = client.post(
        reverse("logistics:article-list"), {"name": "Ballon", "category": Article.Category.MISC}, format="json"
    ).data["id"]
    base = {
        "movement_type": StockMovement.MovementType.IN_PURCHASE,
        "article_id": article,
        "quantity": 2,
        "movement_date": timezone.now().date().isoformat(),
    }
    for extra in (
        {"membership_id": other_ctx.player.id},
        {"match_id": 999999},
        {"expense_id": 999999},
    ):
        resp = client.post(reverse("logistics:movement-list"), {**base, **extra}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST, extra
        assert resp.data["detail"]


def test_duplicate_article_name_answers_400_case_insensitively(ctx: LogisticsClubContext):
    client = client_for(ctx.steward.user)
    first = client.post(
        reverse("logistics:article-list"), {"name": "Maillot B2", "category": Article.Category.JERSEY}, format="json"
    )
    assert first.status_code == status.HTTP_201_CREATED

    duplicate = client.post(
        reverse("logistics:article-list"), {"name": "maillot b2", "category": Article.Category.JERSEY}, format="json"
    )
    assert duplicate.status_code == status.HTTP_400_BAD_REQUEST
    assert duplicate.data["detail"] == "Un article porte déjà ce nom dans votre club."

    other = client.post(
        reverse("logistics:article-list"), {"name": "Ballon", "category": Article.Category.MISC}, format="json"
    )
    rename = client.patch(reverse("logistics:article-detail", args=[other.data["id"]]), {"name": "MAILLOT B2"}, format="json")
    assert rename.status_code == status.HTTP_400_BAD_REQUEST
    assert rename.data["detail"] == "Un article porte déjà ce nom dans votre club."

    same_name_on_itself = client.patch(
        reverse("logistics:article-detail", args=[other.data["id"]]), {"name": "BALLON"}, format="json"
    )
    assert same_name_on_itself.status_code == status.HTTP_200_OK
    assert Article.all_objects.filter(club=ctx.club).count() == 2


def test_same_article_name_is_allowed_in_another_club(ctx: LogisticsClubContext, other_ctx: LogisticsClubContext):
    payload = {"name": "Maillot B2", "category": Article.Category.JERSEY}
    assert client_for(ctx.steward.user).post(reverse("logistics:article-list"), payload, format="json").status_code == 201
    assert client_for(other_ctx.steward.user).post(reverse("logistics:article-list"), payload, format="json").status_code == 201
