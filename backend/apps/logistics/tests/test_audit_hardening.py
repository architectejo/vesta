"""Corrections après l'audit sécurité de la tâche A2 : Coach adjoint, transfert
vers un détenteur archivé, paramètres de requête invalides, tailles maximales,
joueur parti sur une sortie de stock, atomicité écriture + journal."""

from __future__ import annotations

import datetime
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.audit.models import AuditLog
from apps.clubs.models import Membership, MembershipRole
from apps.core.tenant import active_club
from apps.logistics import services
from apps.logistics.models import Article, Holder, StockMovement
from apps.logistics.tests.conftest import LogisticsClubContext, client_for, make_member
from apps.sport.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def today() -> datetime.date:
    return timezone.now().date()


def make_article(ctx, name="Ballons de match") -> Article:
    with active_club(ctx.club):
        return services.create_article(club=ctx.club, actor=ctx.steward.user, name=name, category=Article.Category.BALLS)


def add_stock(ctx, article, quantity, holder=None):
    with active_club(ctx.club):
        return services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=article,
            quantity=quantity,
            movement_date=today(),
            holder=holder,
        )


def make_place(ctx, label) -> Holder:
    with active_club(ctx.club):
        return services.create_holder(club=ctx.club, actor=ctx.steward.user, kind=Holder.Kind.PLACE, label=label)


@pytest.fixture
def assistant(ctx: LogisticsClubContext) -> Membership:
    return make_member(ctx.club, roles=[MembershipRole.Role.ASSISTANT_COACH])


# ---------------------------------------------------------------------------
# Coach adjoint
# ---------------------------------------------------------------------------


def test_assistant_coach_reads_material_and_downloads_register(ctx: LogisticsClubContext, assistant):
    article = make_article(ctx)
    add_stock(ctx, article, 3)
    client = client_for(assistant.user)
    assert client.get(reverse("logistics:overview")).status_code == status.HTTP_200_OK
    assert client.get(reverse("logistics:article-list")).status_code == status.HTTP_200_OK
    assert client.get(reverse("logistics:holder-list")).status_code == status.HTTP_200_OK
    assert client.get(reverse("logistics:register")).status_code == status.HTTP_200_OK
    csv_response = client.get(reverse("logistics:register-csv"))
    assert csv_response.status_code == status.HTTP_200_OK
    pdf_response = client.get(reverse("logistics:register-pdf"))
    assert pdf_response.status_code == status.HTTP_200_OK
    assert pdf_response.content.startswith(b"%PDF")
    # lecture seulement : aucune écriture du catalogue
    denied = client.post(reverse("logistics:article-list"), {"name": "X", "category": "balls"}, format="json")
    assert denied.status_code == status.HTTP_403_FORBIDDEN


def test_assistant_coach_records_match_equipment_out(ctx: LogisticsClubContext, assistant):
    article = make_article(ctx)
    add_stock(ctx, article, 6)
    match = MatchFactory(club=ctx.club, event__club=ctx.club)
    response = client_for(assistant.user).post(
        reverse("logistics:match-equipment-out", args=[match.event_id]),
        {"lines": [{"article_id": article.pk, "quantity": 2}]},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data


# ---------------------------------------------------------------------------
# Transfert vers un détenteur archivé (API)
# ---------------------------------------------------------------------------


def test_transfer_to_archived_holder_refused_via_api(ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 4)
    archived = make_place(ctx, "Ancien local")
    client = client_for(ctx.steward.user)
    assert client.post(reverse("logistics:holder-archive", args=[archived.pk])).data["status"] == "archived"
    response = client.post(
        reverse("logistics:transfer-create"),
        {
            "article_id": article.pk,
            "from_holder_id": None,
            "to_holder_id": archived.pk,
            "quantity": 1,
            "movement_date": today().isoformat(),
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == "Ce détenteur est archivé : choisissez un détenteur actif."
    with active_club(ctx.club):
        assert services.holder_stock(article, archived) == 0


# ---------------------------------------------------------------------------
# Paramètres de requête invalides
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("param", ["article", "match", "expense"])
def test_movement_list_invalid_numeric_param_is_400(ctx: LogisticsClubContext, param):
    response = client_for(ctx.steward.user).get(reverse("logistics:movement-list"), {param: "abc"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == "Paramètre invalide."


def test_decommission_list_invalid_article_param_is_400(ctx: LogisticsClubContext):
    response = client_for(ctx.steward.user).get(reverse("logistics:decommission-list"), {"article": "1 OR 1=1"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == "Paramètre invalide."


def test_valid_numeric_param_still_filters(ctx: LogisticsClubContext):
    article = make_article(ctx)
    other = make_article(ctx, "Chasubles")
    add_stock(ctx, article, 2)
    add_stock(ctx, other, 3)
    data = client_for(ctx.steward.user).get(reverse("logistics:movement-list"), {"article": str(article.pk)}).data
    assert data["count"] == 1 and data["results"][0]["quantity"] == 2


# ---------------------------------------------------------------------------
# Tailles maximales
# ---------------------------------------------------------------------------


def test_movement_reason_max_length(ctx: LogisticsClubContext):
    article = make_article(ctx)
    body = {
        "movement_type": "in_purchase",
        "article_id": article.pk,
        "quantity": 1,
        "movement_date": today().isoformat(),
    }
    client = client_for(ctx.steward.user)
    refused = client.post(reverse("logistics:movement-list"), {**body, "reason": "x" * 501}, format="json")
    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert refused.data["reason"][0] == "Le motif ne peut pas dépasser 500 caractères."
    ok = client.post(reverse("logistics:movement-list"), {**body, "reason": "x" * 500}, format="json")
    assert ok.status_code == status.HTTP_201_CREATED


def test_match_equipment_lines_and_observation_limits(ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 100)
    match = MatchFactory(club=ctx.club, event__club=ctx.club)
    coach = client_for(ctx.coach.user)
    too_many = coach.post(
        reverse("logistics:match-equipment-out", args=[match.event_id]),
        {"lines": [{"article_id": article.pk, "quantity": 1}] * 51},
        format="json",
    )
    assert too_many.status_code == status.HTTP_400_BAD_REQUEST
    assert too_many.data["lines"][0] == "50 lignes au plus par enregistrement."

    steward = client_for(ctx.steward.user)
    return_url = reverse("logistics:match-equipment-return", args=[match.event_id])
    too_many_back = steward.post(
        return_url, {"lines": [{"article_id": article.pk, "quantity_returned": 0}] * 51}, format="json"
    )
    assert too_many_back.status_code == status.HTTP_400_BAD_REQUEST
    assert too_many_back.data["lines"][0] == "50 lignes au plus par enregistrement."
    long_observation = steward.post(
        return_url,
        {"lines": [{"article_id": article.pk, "quantity_returned": 0}], "observation": "x" * 501},
        format="json",
    )
    assert long_observation.status_code == status.HTTP_400_BAD_REQUEST
    assert long_observation.data["observation"][0] == "L'observation ne peut pas dépasser 500 caractères."


# ---------------------------------------------------------------------------
# Joueur parti sur une sortie de stock ; donateur ancien membre accepté
# ---------------------------------------------------------------------------


def _departed_member(ctx) -> Membership:
    membership = make_member(ctx.club)
    membership.status = Membership.Status.DEPARTED
    membership.left_by = ctx.president.user
    membership.save()
    return membership


def test_out_movement_refuses_departed_member(ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 5)
    departed = _departed_member(ctx)
    response = client_for(ctx.steward.user).post(
        reverse("logistics:movement-list"),
        {
            "movement_type": "out_distribution",
            "article_id": article.pk,
            "quantity": 1,
            "movement_date": today().isoformat(),
            "membership_id": departed.pk,
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == "Ce joueur ne fait plus partie du club : choisissez un membre actif."


def test_donor_may_be_a_former_member(ctx: LogisticsClubContext):
    article = make_article(ctx)
    departed = _departed_member(ctx)
    response = client_for(ctx.steward.user).post(
        reverse("logistics:movement-list"),
        {
            "movement_type": "in_donation",
            "article_id": article.pk,
            "quantity": 2,
            "movement_date": today().isoformat(),
            "provenance": {"origin_kind": "donation", "donor_membership_id": departed.pk},
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["movement"]["provenance"]["donor"]["membership_id"] == departed.pk


# ---------------------------------------------------------------------------
# Atomicité : un journal qui échoue annule l'écriture
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_holder_creation_rolled_back_when_audit_fails(ctx: LogisticsClubContext):
    with active_club(ctx.club):
        with mock.patch("apps.logistics.services.log_action", side_effect=RuntimeError("journal indisponible")):
            with pytest.raises(RuntimeError):
                services.create_holder(club=ctx.club, actor=ctx.steward.user, kind=Holder.Kind.PLACE, label="Stade")
        assert not Holder.objects.filter(label="Stade").exists()
    assert not AuditLog.objects.filter(club=ctx.club, action_type="logistics.holder.created").exists()


@pytest.mark.django_db(transaction=True)
def test_holder_archive_rolled_back_when_audit_fails(ctx: LogisticsClubContext):
    place = make_place(ctx, "Stade")
    with active_club(ctx.club):
        with mock.patch("apps.logistics.services.log_action", side_effect=RuntimeError("journal indisponible")):
            with pytest.raises(RuntimeError):
                services.archive_holder(holder=place, actor=ctx.steward.user)
        place.refresh_from_db()
    assert place.status == Holder.Status.ACTIVE
