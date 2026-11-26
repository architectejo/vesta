"""Corrections A2 après le contrôle de conformité : prêts de match non rendus,
dépenses libérées seulement (10.2 n° 167) et leur recherche, filtres et
pagination des mouvements, détenteur-joueur parti, archivage avec déclassement
en attente, recherche d'article sans dépendance au moteur, refus par rôle."""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import MembershipRoleFactory
from apps.core.tenant import active_club
from apps.logistics import services
from apps.logistics.models import Article, Holder, StockMovement
from apps.logistics.tests.conftest import LogisticsClubContext, client_for, make_member
from apps.sport.tests.factories import MatchFactory
from apps.treasury.tests import expense_helpers

pytestmark = pytest.mark.django_db

IN_PURCHASE = StockMovement.MovementType.IN_PURCHASE


def today() -> datetime.date:
    return timezone.now().date()


def make_article(ctx, name="Ballons de match") -> Article:
    with active_club(ctx.club):
        return services.create_article(club=ctx.club, actor=ctx.steward.user, name=name, category=Article.Category.BALLS)


def add_stock(ctx, article, quantity, holder=None, movement_type=IN_PURCHASE):
    with active_club(ctx.club):
        return services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=movement_type,
            article=article,
            quantity=quantity,
            movement_date=today(),
            holder=holder,
        )


def make_place(ctx, label="Local du club") -> Holder:
    with active_club(ctx.club):
        return services.create_holder(club=ctx.club, actor=ctx.steward.user, kind=Holder.Kind.PLACE, label=label)


def make_member_holder(ctx, membership) -> Holder:
    with active_club(ctx.club):
        return services.create_holder(club=ctx.club, actor=ctx.steward.user, kind=Holder.Kind.MEMBER, membership=membership)


def depart(ctx, membership) -> None:
    membership.status = Membership.Status.DEPARTED
    membership.left_by = ctx.president.user
    membership.save()


def make_expense(ctx, *, released: bool, category_name="Équipements"):
    with active_club(ctx.club):
        category = expense_helpers.make_category(ctx, name=category_name)
        expense = expense_helpers.make_expense(ctx, category, amount="40", reason="Ballons achetés au marché")
        if released:
            expense = expense_helpers.release(ctx, expense)
    return expense


# ---------------------------------------------------------------------------
# 1. Prêts de match non rendus
# ---------------------------------------------------------------------------


def test_loaned_for_match_counts_unreturned_loans_per_match(ctx: LogisticsClubContext):
    article = make_article(ctx)
    other = make_article(ctx, "Chasubles")
    add_stock(ctx, article, 20)
    add_stock(ctx, other, 5)
    match_a = MatchFactory(club=ctx.club, event__club=ctx.club)
    match_b = MatchFactory(club=ctx.club, event__club=ctx.club)
    coach = client_for(ctx.coach.user)
    for match, quantity in ((match_a, 4), (match_b, 2)):
        response = coach.post(
            reverse("logistics:match-equipment-out", args=[match.event_id]),
            {"lines": [{"article_id": article.pk, "quantity": quantity}]},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
    back = client_for(ctx.steward.user).post(
        reverse("logistics:match-equipment-return", args=[match_a.event_id]),
        {"lines": [{"article_id": article.pk, "quantity_returned": 1}]},
        format="json",
    )
    assert back.status_code == status.HTTP_200_OK, back.data

    reader = client_for(ctx.president.user)
    catalogue = {a["id"]: a for a in reader.get(reverse("logistics:article-list")).data["results"]}
    assert catalogue[article.pk]["loaned_for_match"] == 5  # 3 (match A) + 2 (match B)
    assert catalogue[other.pk]["loaned_for_match"] == 0
    detail = reader.get(reverse("logistics:article-detail", args=[article.pk])).data
    assert detail["loaned_for_match"] == 5


def test_loaned_for_match_is_club_scoped(ctx: LogisticsClubContext, other_ctx: LogisticsClubContext):
    article = make_article(ctx)
    foreign = make_article(other_ctx)
    add_stock(ctx, article, 5)
    add_stock(other_ctx, foreign, 5)
    match = MatchFactory(club=other_ctx.club, event__club=other_ctx.club)
    client_for(other_ctx.coach.user).post(
        reverse("logistics:match-equipment-out", args=[match.event_id]),
        {"lines": [{"article_id": foreign.pk, "quantity": 3}]},
        format="json",
    )
    with active_club(ctx.club):
        assert services.loaned_for_match_by_article() == {}


# ---------------------------------------------------------------------------
# 2. Dépenses libérées seulement (10.2 n° 167)
# ---------------------------------------------------------------------------


def _purchase_body(article, **extra):
    return {
        "movement_type": "in_purchase",
        "article_id": article.pk,
        "quantity": 2,
        "movement_date": today().isoformat(),
        **extra,
    }


def test_purchase_refused_on_pending_expense(ctx: LogisticsClubContext):
    article = make_article(ctx)
    pending = make_expense(ctx, released=False)
    response = client_for(ctx.steward.user).post(
        reverse("logistics:movement-list"), _purchase_body(article, expense_id=pending.pk), format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == services.EXPENSE_NOT_RELEASED_MESSAGE


def test_purchase_linked_to_released_expense(ctx: LogisticsClubContext):
    article = make_article(ctx)
    released = make_expense(ctx, released=True)
    client = client_for(ctx.steward.user)
    response = client.post(
        reverse("logistics:movement-list"), _purchase_body(article, expense_id=released.pk), format="json"
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["movement"]["expense_id"] == released.pk
    # seul un achat se rattache à une dépense
    donation = client.post(
        reverse("logistics:movement-list"),
        _purchase_body(article, movement_type="in_return", expense_id=released.pk),
        format="json",
    )
    assert donation.status_code == status.HTTP_400_BAD_REQUEST
    assert donation.data["detail"] == "Seul un achat peut être rattaché à une dépense."


def test_linkable_expenses_search_exposes_no_beneficiary_nor_reason(
    ctx: LogisticsClubContext, other_ctx: LogisticsClubContext
):
    released = make_expense(ctx, released=True, category_name="Équipements")
    make_expense(ctx, released=False, category_name="Transport")
    make_expense(other_ctx, released=True, category_name="Équipements")
    client = client_for(ctx.steward.user)
    url = reverse("logistics:linkable-expenses")

    data = client.get(url).data
    assert [r["id"] for r in data["results"]] == [released.pk]  # libérée, du club seulement
    row = data["results"][0]
    assert set(row) == {
        "id", "reference", "expense_date", "amount", "currency", "category", "status", "status_display",
    }
    assert row["category"] == "Équipements" and row["reference"] == f"D-{released.pk}"
    assert client.get(url, {"q": "EQUIPEMENTS"}).data["count"] == 1  # casse et accents ignorés
    assert client.get(url, {"q": "40"}).data["count"] == 1
    assert client.get(url, {"q": "transport"}).data["count"] == 0
    for role in ("president", "treasurer", "coach", "player"):
        assert client_for(getattr(ctx, role).user).get(url).status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# 3. Filtres et pagination des mouvements
# ---------------------------------------------------------------------------


def test_movements_filter_by_holder_and_types(ctx: LogisticsClubContext):
    article = make_article(ctx)
    place = make_place(ctx)
    add_stock(ctx, article, 3, holder=place)
    add_stock(ctx, article, 2)
    add_stock(ctx, article, 1, movement_type=StockMovement.MovementType.IN_DONATION)
    client = client_for(ctx.steward.user)
    url = reverse("logistics:movement-list")

    by_holder = client.get(url, {"holder": place.pk}).data
    assert by_holder["count"] == 1 and by_holder["results"][0]["quantity"] == 3
    unlocated = client.get(url, {"holder": "none"}).data
    assert sorted(r["quantity"] for r in unlocated["results"]) == [1, 2]
    typed = client.get(url, {"types": "in_donation,out_loss"}).data
    assert [r["quantity"] for r in typed["results"]] == [1]
    for bad in ({"types": "purchase"}, {"holder": "abc"}, {"limit": "0"}, {"offset": "-1"}):
        response = client.get(url, bad)
        assert response.status_code == status.HTTP_400_BAD_REQUEST, bad
        assert response.data["detail"] == "Paramètre invalide."


def test_movements_pagination(ctx: LogisticsClubContext):
    article = make_article(ctx)
    for quantity in range(1, 6):
        add_stock(ctx, article, quantity)
    client = client_for(ctx.steward.user)
    url = reverse("logistics:movement-list")
    first = client.get(url, {"limit": 2}).data
    assert first["count"] == 5 and len(first["results"]) == 2 and first["next_offset"] == 2
    last = client.get(url, {"limit": 2, "offset": 4}).data
    assert len(last["results"]) == 1 and last["next_offset"] is None
    seen = [r["id"] for r in first["results"]] + [r["id"] for r in client.get(url, {"limit": 2, "offset": 2}).data["results"]]
    assert len(set(seen)) == 4
    assert client.get(url, {"limit": 10000}).data["limit"] == 200


# ---------------------------------------------------------------------------
# 4. Détenteur-joueur parti ; archivage avec déclassement en attente
# ---------------------------------------------------------------------------


def test_no_entry_nor_transfer_to_member_holder_who_left(ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 5)
    membership = make_member(ctx.club)
    holder = make_member_holder(ctx, membership)
    depart(ctx, membership)
    with active_club(ctx.club):
        with pytest.raises(services.LogisticsError, match="ne fait plus partie du club"):
            services.record_movement(
                club=ctx.club, actor=ctx.steward.user, movement_type=IN_PURCHASE, article=article,
                quantity=1, movement_date=today(), holder=holder,
            )
    response = client_for(ctx.steward.user).post(
        reverse("logistics:transfer-create"),
        {"article_id": article.pk, "from_holder_id": None, "to_holder_id": holder.pk, "quantity": 1,
         "movement_date": today().isoformat()},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == services.MEMBER_HOLDER_LEFT_MESSAGE


def test_archive_refused_while_decommission_pending(ctx: LogisticsClubContext):
    article = make_article(ctx)
    place = make_place(ctx)
    add_stock(ctx, article, 2, holder=place)
    client = client_for(ctx.steward.user)
    flagged = client.post(
        reverse("logistics:decommission-list"),
        {"article_id": article.pk, "holder_id": place.pk, "quantity": 1, "reason": "worn", "noted_on": today().isoformat()},
        format="json",
    )
    assert flagged.status_code == status.HTTP_201_CREATED, flagged.data
    refused = client.post(reverse("logistics:holder-archive", args=[place.pk]))
    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert "déclassement en attente" in refused.data["detail"]


# ---------------------------------------------------------------------------
# 5. Recherche d'article sans dépendance au moteur
# ---------------------------------------------------------------------------


def test_article_search_ignores_case_and_accents(ctx: LogisticsClubContext):
    make_article(ctx, "Ballons d'entraînement")
    make_article(ctx, "Chasubles")
    client = client_for(ctx.steward.user)
    for query in ("ENTRAINEMENT", "entraînement", "  ballons  "):
        names = [a["name"] for a in client.get(reverse("logistics:article-list"), {"search": query}).data["results"]]
        assert names == ["Ballons d'entraînement"], query


# ---------------------------------------------------------------------------
# 7. Refus par rôle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [
        MembershipRole.Role.SPORTS_DIRECTOR,
        MembershipRole.Role.ASSISTANT_TREASURER,
        MembershipRole.Role.SECRETARY,
        MembershipRole.Role.CAPTAIN,
        MembershipRole.Role.DOCTOR,
    ],
)
def test_roles_without_material_access_are_refused(ctx: LogisticsClubContext, role):
    article = make_article(ctx)
    place = make_place(ctx)
    add_stock(ctx, article, 3, holder=place)
    with active_club(ctx.club):
        decommission = services.flag_decommission(
            club=ctx.club, actor=ctx.steward.user, article=article, quantity=1, reason="worn",
            noted_on=today(), holder=place,
        )
    if role == MembershipRole.Role.DOCTOR:
        member = make_member(ctx.club)
        MembershipRoleFactory(
            membership=member, club=ctx.club, role=role, appointed_at=timezone.now(), is_qualified_professional=False
        )
    else:
        member = make_member(ctx.club, roles=[role])
    client = client_for(member.user)
    forbidden = status.HTTP_403_FORBIDDEN
    assert client.get(reverse("logistics:holder-list")).status_code == forbidden
    assert client.post(reverse("logistics:holder-list"), {"kind": "place", "label": "X"}, format="json").status_code == forbidden
    assert client.get(reverse("logistics:holder-detail", args=[place.pk])).status_code == forbidden
    assert client.patch(reverse("logistics:holder-detail", args=[place.pk]), {"label": "Y"}, format="json").status_code == forbidden
    assert client.post(reverse("logistics:holder-archive", args=[place.pk])).status_code == forbidden
    assert client.get(reverse("logistics:decommission-list")).status_code == forbidden
    assert client.post(reverse("logistics:decommission-list"), {}, format="json").status_code == forbidden
    assert client.get(reverse("logistics:decommission-detail", args=[decommission.pk])).status_code == forbidden
    assert client.post(reverse("logistics:decommission-execute", args=[decommission.pk]), {}, format="json").status_code == forbidden
    assert client.post(reverse("logistics:decommission-cancel", args=[decommission.pk]), {}, format="json").status_code == forbidden
    for name in ("register", "register-csv", "register-pdf"):
        assert client.get(reverse(f"logistics:{name}")).status_code == forbidden, name
    assert client.get(reverse("logistics:linkable-expenses")).status_code == forbidden
