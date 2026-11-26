"""Tests du registre de l'intendance : détenteurs, déplacements, provenances,
déclassement, registre PDF/CSV (lots 1, 3, 4, 5 ; docs/ecrans/logistique-intendance-registre.md)."""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.audit.models import AuditLog
from apps.core.tenant import active_club
from apps.logistics import services
from apps.logistics.models import Article, Decommission, Holder, LogisticsImmutableError, StockMovement
from apps.logistics.tests.conftest import LogisticsClubContext, client_for, make_member
from apps.sport.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db

IN_PURCHASE = StockMovement.MovementType.IN_PURCHASE


def today() -> datetime.date:
    return timezone.now().date()


def make_article(ctx, name="Ballons de match", category=Article.Category.BALLS, unit="pièce") -> Article:
    with active_club(ctx.club):
        return services.create_article(club=ctx.club, actor=ctx.steward.user, name=name, category=category, unit=unit)


def add_stock(ctx, article, quantity, *, holder=None, movement_type=IN_PURCHASE, provenance=None, **kwargs):
    with active_club(ctx.club):
        return services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=movement_type,
            article=article,
            quantity=quantity,
            movement_date=today(),
            holder=holder,
            provenance=provenance,
            **kwargs,
        )


def make_place(ctx, label="Local du club") -> Holder:
    with active_club(ctx.club):
        return services.create_holder(club=ctx.club, actor=ctx.steward.user, kind=Holder.Kind.PLACE, label=label)


def make_member_holder(ctx, membership=None) -> Holder:
    membership = membership or make_member(ctx.club)
    with active_club(ctx.club):
        return services.create_holder(club=ctx.club, actor=ctx.steward.user, kind=Holder.Kind.MEMBER, membership=membership)


def stock_of(ctx, article, holder=None) -> int:
    with active_club(ctx.club):
        return services.holder_stock(article, holder)


def total_of(ctx, article) -> int:
    with active_club(ctx.club):
        return services.theoretical_quantity(article)


# ---------------------------------------------------------------------------
# Compatibilité des données existantes (§13)
# ---------------------------------------------------------------------------


def test_legacy_movements_form_the_unlocated_line(ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 20)  # sans détenteur ni provenance : comme avant
    client = client_for(ctx.steward.user)

    detail = client.get(reverse("logistics:article-detail", args=[article.pk])).data
    assert detail["in_stock"] == 20
    assert detail["stock_by_holder"] == [{"holder_id": None, "holder": None, "holder_name": "Non localisé", "quantity": 20}]
    assert detail["provenances"][0]["origin_kind_display"] == "Origine non renseignée"
    assert detail["provenances"][0]["acquisition_date"] == today()

    holders = client.get(reverse("logistics:holder-list")).data
    assert holders["results"] == []
    assert holders["unlocated"] == {"stock_total": 20, "articles_count": 1}


def test_new_categories_and_unknown_condition_are_accepted(ctx: LogisticsClubContext):
    client = client_for(ctx.steward.user)
    for index, category in enumerate(["shorts", "bibs", "referee", "accessories", "furniture"]):
        response = client.post(
            reverse("logistics:article-list"),
            {"name": f"Article {index}", "category": category, "reference_condition": "unknown"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["reference_condition_display"] == "Non renseigné"
    assert Article.Category.BIBS.label == "Chasubles"


def test_transfer_and_decommission_types_cannot_be_posted_as_plain_movements(ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 5)
    client = client_for(ctx.steward.user)
    for forbidden in ("out_transfer", "in_transfer", "out_decommission"):
        response = client.post(
            reverse("logistics:movement-list"),
            {"movement_type": forbidden, "article_id": article.pk, "quantity": 1, "movement_date": today().isoformat()},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Détenteurs
# ---------------------------------------------------------------------------


def test_steward_creates_member_and_place_holders_via_api(ctx: LogisticsClubContext):
    client = client_for(ctx.steward.user)
    player = make_member(ctx.club)
    member = client.post(reverse("logistics:holder-list"), {"kind": "member", "membership_id": player.pk}, format="json")
    assert member.status_code == status.HTTP_201_CREATED
    assert member.data["kind"] == "member"
    assert member.data["name"] == f"{player.user.first_name} {player.user.last_name}".strip()
    place = client.post(reverse("logistics:holder-list"), {"kind": "place", "label": "  Local   du club "}, format="json")
    assert place.status_code == status.HTTP_201_CREATED
    assert place.data["name"] == "Local du club"

    duplicate_place = client.post(reverse("logistics:holder-list"), {"kind": "place", "label": "LOCAL DU CLUB"}, format="json")
    assert duplicate_place.status_code == status.HTTP_400_BAD_REQUEST
    assert duplicate_place.data["detail"] == "Ce lieu existe déjà."
    duplicate_member = client.post(reverse("logistics:holder-list"), {"kind": "member", "membership_id": player.pk}, format="json")
    assert duplicate_member.data["detail"] == "Ce joueur est déjà détenteur."
    assert AuditLog.objects.filter(club=ctx.club, action_type="logistics.holder.created").count() == 2


def test_holder_write_is_steward_only_and_read_follows_matrix(ctx: LogisticsClubContext):
    place = make_place(ctx)
    for role in ("president", "vice_president", "treasurer", "coach"):
        client = client_for(getattr(ctx, role).user)
        assert client.get(reverse("logistics:holder-list")).status_code == status.HTTP_200_OK
        assert client.get(reverse("logistics:holder-detail", args=[place.pk])).status_code == status.HTTP_200_OK
        assert (
            client.post(reverse("logistics:holder-list"), {"kind": "place", "label": "X"}, format="json").status_code
            == status.HTTP_403_FORBIDDEN
        )
        assert client.post(reverse("logistics:holder-archive", args=[place.pk])).status_code == status.HTTP_403_FORBIDDEN
        assert (
            client.patch(reverse("logistics:holder-detail", args=[place.pk]), {"label": "Y"}, format="json").status_code
            == status.HTTP_403_FORBIDDEN
        )


def test_player_holder_without_material_role_has_no_access(ctx: LogisticsClubContext):
    holder = make_member_holder(ctx, ctx.player)
    client = client_for(ctx.player.user)
    assert client.get(reverse("logistics:holder-list")).status_code == status.HTTP_403_FORBIDDEN
    assert client.get(reverse("logistics:holder-detail", args=[holder.pk])).status_code == status.HTTP_403_FORBIDDEN
    assert client.get(reverse("logistics:register")).status_code == status.HTTP_403_FORBIDDEN


def test_holders_are_isolated_between_clubs(ctx: LogisticsClubContext, other_ctx: LogisticsClubContext):
    foreign = make_place(other_ctx, "Stade adverse")
    client = client_for(ctx.steward.user)
    assert client.get(reverse("logistics:holder-list")).data["count"] == 0
    assert client.get(reverse("logistics:holder-detail", args=[foreign.pk])).status_code == status.HTTP_404_NOT_FOUND
    assert client.post(reverse("logistics:holder-archive", args=[foreign.pk])).status_code == status.HTTP_404_NOT_FOUND
    # un joueur d'un autre club ne devient pas détenteur
    outsider = make_member(other_ctx.club)
    response = client.post(reverse("logistics:holder-list"), {"kind": "member", "membership_id": outsider.pk}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    # ni source / destination d'un transfert, ni détenteur d'un mouvement
    article = make_article(ctx)
    add_stock(ctx, article, 5)
    transfer = client.post(
        reverse("logistics:transfer-create"),
        {
            "article_id": article.pk,
            "from_holder_id": None,
            "to_holder_id": foreign.pk,
            "quantity": 1,
            "movement_date": today().isoformat(),
        },
        format="json",
    )
    assert transfer.status_code == status.HTTP_400_BAD_REQUEST
    movement = client.post(
        reverse("logistics:movement-list"),
        {
            "movement_type": IN_PURCHASE,
            "article_id": article.pk,
            "quantity": 1,
            "movement_date": today().isoformat(),
            "holder_id": foreign.pk,
        },
        format="json",
    )
    assert movement.status_code == status.HTTP_400_BAD_REQUEST


def test_archive_holder_refused_while_stock_remains(ctx: LogisticsClubContext):
    holder = make_place(ctx)
    article = make_article(ctx)
    add_stock(ctx, article, 4, holder=holder)
    client = client_for(ctx.steward.user)
    refused = client.post(reverse("logistics:holder-archive", args=[holder.pk]))
    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert refused.data["detail"] == "Local du club détient encore 4 pièce(s) : déplacez-les avant d'archiver."

    other = make_place(ctx, "Stade")
    with active_club(ctx.club):
        services.record_transfer(
            club=ctx.club, actor=ctx.steward.user, article=article, source=holder, destination=other,
            quantity=4, movement_date=today(),
        )
    assert client.post(reverse("logistics:holder-archive", args=[holder.pk])).data["status"] == "archived"
    # un détenteur archivé ne peut plus recevoir de matériel
    with active_club(ctx.club):
        with pytest.raises(services.LogisticsError, match="archivé"):
            services.record_movement(
                club=ctx.club, actor=ctx.steward.user, movement_type=IN_PURCHASE, article=article,
                quantity=1, movement_date=today(), holder=holder,
            )


def test_holder_flagged_when_member_left_club(ctx: LogisticsClubContext):
    membership = make_member(ctx.club)
    holder = make_member_holder(ctx, membership)
    membership.status = "departed"
    membership.left_by = ctx.president.user  # le départ exige un acteur réel (clubs, CDC 5.1)
    membership.save()
    data = client_for(ctx.steward.user).get(reverse("logistics:holder-list")).data
    assert data["results"][0]["has_left_club"] is True
    assert holder.pk == data["results"][0]["id"]


def test_rename_place_only(ctx: LogisticsClubContext):
    place = make_place(ctx)
    member_holder = make_member_holder(ctx)
    client = client_for(ctx.steward.user)
    ok = client.patch(reverse("logistics:holder-detail", args=[place.pk]), {"label": "Stade municipal"}, format="json")
    assert ok.status_code == status.HTTP_200_OK and ok.data["name"] == "Stade municipal"
    refused = client.patch(reverse("logistics:holder-detail", args=[member_holder.pk]), {"label": "X"}, format="json")
    assert refused.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Stock par détenteur et déplacements
# ---------------------------------------------------------------------------


def test_stock_by_holder_is_exact_and_transfer_keeps_total(ctx: LogisticsClubContext):
    article = make_article(ctx)
    landry = make_member_holder(ctx)
    adolphe = make_place(ctx, "Chez Adolphe")
    add_stock(ctx, article, 14, holder=landry)
    add_stock(ctx, article, 10)  # non localisé
    client = client_for(ctx.steward.user)

    response = client.post(
        reverse("logistics:transfer-create"),
        {
            "article_id": article.pk,
            "from_holder_id": None,
            "to_holder_id": adolphe.pk,
            "quantity": 8,
            "movement_date": today().isoformat(),
            "reason": "Rangement",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["in_stock"] == 24
    assert response.data["out_movement"]["movement_type"] == "out_transfer"
    assert response.data["in_movement"]["movement_type"] == "in_transfer"
    assert response.data["out_movement"]["transfer_group"] == response.data["in_movement"]["transfer_group"]
    assert response.data["out_movement"]["recorded_by"]["name"]
    assert response.data["in_movement"]["recorded_by"]["name"]
    assert stock_of(ctx, article, landry) == 14
    assert stock_of(ctx, article, adolphe) == 8
    assert stock_of(ctx, article, None) == 2
    assert total_of(ctx, article) == 24
    rows = {(r["holder_id"], r["quantity"]) for r in response.data["stock_by_holder"]}
    assert rows == {(landry.pk, 14), (adolphe.pk, 8), (None, 2)}

    # un seul enregistrement de journal pour les deux mouvements
    assert AuditLog.objects.filter(club=ctx.club, action_type="logistics.transfer.created").count() == 1

    detail = client.get(reverse("logistics:holder-detail", args=[adolphe.pk])).data
    assert detail["stock_total"] == 8
    assert detail["articles"][0]["quantity"] == 8
    assert len(detail["recent_movements"]) == 1
    listing = client.get(reverse("logistics:holder-list")).data
    assert [r["stock_total"] for r in listing["results"]] == [14, 8]
    assert listing["unlocated"]["stock_total"] == 2


def test_transfer_refused_beyond_source_stock_or_same_holder(ctx: LogisticsClubContext):
    article = make_article(ctx)
    a = make_place(ctx, "A")
    b = make_place(ctx, "B")
    add_stock(ctx, article, 5, holder=a)
    add_stock(ctx, article, 50, holder=b)
    client = client_for(ctx.steward.user)
    body = {"article_id": article.pk, "from_holder_id": a.pk, "to_holder_id": b.pk, "quantity": 6, "movement_date": today().isoformat()}
    refused = client.post(reverse("logistics:transfer-create"), body, format="json")
    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert refused.data["detail"] == "Quantité supérieure au stock de A (5)."
    same = client.post(reverse("logistics:transfer-create"), {**body, "quantity": 1, "to_holder_id": a.pk}, format="json")
    assert same.data["detail"] == "Le détenteur d'arrivée doit être différent du détenteur de départ."
    none_dest = client.post(reverse("logistics:transfer-create"), {**body, "quantity": 1, "to_holder_id": None}, format="json")
    assert none_dest.data["detail"] == "Choisissez le nouveau détenteur."
    future = client.post(
        reverse("logistics:transfer-create"),
        {**body, "quantity": 1, "movement_date": (today() + datetime.timedelta(days=3)).isoformat()},
        format="json",
    )
    assert future.status_code == status.HTTP_400_BAD_REQUEST
    assert stock_of(ctx, article, a) == 5 and total_of(ctx, article) == 55
    assert StockMovement.objects.none  # aucun mouvement de transfert créé
    with active_club(ctx.club):
        assert not StockMovement.objects.filter(movement_type__in=StockMovement.TRANSFER_TYPES).exists()


def test_transfer_is_steward_only(ctx: LogisticsClubContext):
    article = make_article(ctx)
    dest = make_place(ctx)
    add_stock(ctx, article, 3)
    body = {"article_id": article.pk, "from_holder_id": None, "to_holder_id": dest.pk, "quantity": 1, "movement_date": today().isoformat()}
    for role in ("president", "vice_president", "treasurer", "coach", "player"):
        response = client_for(getattr(ctx, role).user).post(reverse("logistics:transfer-create"), body, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN


def test_out_movement_refused_beyond_holder_stock_even_if_total_suffices(ctx: LogisticsClubContext):
    article = make_article(ctx)
    holder = make_place(ctx)
    add_stock(ctx, article, 3, holder=holder)
    add_stock(ctx, article, 10)
    client = client_for(ctx.steward.user)
    body = {
        "movement_type": "out_distribution",
        "article_id": article.pk,
        "quantity": 5,
        "movement_date": today().isoformat(),
        "holder_id": holder.pk,
    }
    refused = client.post(reverse("logistics:movement-list"), body, format="json")
    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert refused.data["detail"] == "Quantité supérieure au stock de Local du club (3)."
    ok = client.post(reverse("logistics:movement-list"), {**body, "holder_id": None}, format="json")
    assert ok.status_code == status.HTTP_201_CREATED
    assert stock_of(ctx, article, None) == 5 and stock_of(ctx, article, holder) == 3
    assert ok.data["movement"]["holder"] is None


def test_match_out_defaults_to_suggested_holder_and_return_goes_back(ctx: LogisticsClubContext):
    article = make_article(ctx)
    holder = make_place(ctx)
    add_stock(ctx, article, 6, holder=holder)
    add_stock(ctx, article, 2)
    match = MatchFactory(club=ctx.club, event__club=ctx.club)
    coach = client_for(ctx.coach.user)
    out = coach.post(
        reverse("logistics:match-equipment-out", args=[match.event_id]),
        {"lines": [{"article_id": article.pk, "quantity": 4}]},
        format="json",
    )
    assert out.status_code == status.HTTP_201_CREATED, out.data
    assert out.data["lines"][0]["holder"]["id"] == holder.pk
    assert stock_of(ctx, article, holder) == 2
    back = coach.post(
        reverse("logistics:match-equipment-return", args=[match.event_id]),
        {"lines": [{"article_id": article.pk, "quantity_returned": 4}]},
        format="json",
    )
    assert back.status_code == status.HTTP_200_OK, back.data
    assert stock_of(ctx, article, holder) == 6
    detail = client_for(ctx.steward.user).get(reverse("logistics:article-detail", args=[article.pk])).data
    assert detail["suggested_holder"]["id"] == holder.pk


# ---------------------------------------------------------------------------
# Provenances (lot 3)
# ---------------------------------------------------------------------------


def test_opening_entry_with_donation_provenance_and_unknown_date(ctx: LogisticsClubContext):
    article = make_article(ctx)
    donor = make_member(ctx.club)
    client = client_for(ctx.steward.user)
    payload = {
        "movement_type": "in_opening",
        "article_id": article.pk,
        "quantity": 5,
        "movement_date": today().isoformat(),
        "provenance": {
            "origin_kind": "donation",
            "donor_membership_id": donor.pk,
            "acquisition_date_unknown": True,
            "acquisition_date_note": "Voir le comité précédent",
            "condition_at_entry": "good",
        },
    }
    response = client.post(reverse("logistics:movement-list"), payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED, response.data
    prov = response.data["movement"]["provenance"]
    assert prov["origin_kind"] == "donation"
    assert prov["donor"]["membership_id"] == donor.pk
    assert prov["acquisition_date"] is None and prov["acquisition_date_unknown"] is True
    assert prov["acquisition_date_note"] == "Voir le comité précédent"
    assert prov["condition_at_entry_display"] == "Bon état"
    assert response.data["movement"]["movement_type_display"] == "Reprise du registre"

    free = client.post(
        reverse("logistics:movement-list"),
        {
            **payload,
            "provenance": {
                "origin_kind": "donation",
                "donor_name": "Dr Luc Fumu",
                "acquisition_date": (today() - datetime.timedelta(days=30)).isoformat(),
            },
        },
        format="json",
    )
    assert free.status_code == status.HTTP_201_CREATED
    assert free.data["movement"]["provenance"]["donor"] == {"membership_id": None, "name": "Dr Luc Fumu"}
    assert free.data["movement"]["provenance"]["condition_at_entry"] == "unknown"
    # la date d'enregistrement reste distincte de la date d'acquisition
    assert free.data["movement"]["movement_date"] == today()

    detail = client.get(reverse("logistics:article-detail", args=[article.pk])).data
    assert len(detail["provenances"]) == 2
    entry = AuditLog.objects.filter(club=ctx.club, action_type="logistics.stock_movement.created").latest("created_at")
    assert entry.actor_id == ctx.steward.user.pk
    assert entry.after["origin_kind"] == "donation"


@pytest.mark.parametrize(
    "provenance, message",
    [
        ({"origin_kind": "donation"}, "Indiquez le donateur."),
        ({"origin_kind": "club_funds", "donor_name": "X"}, "Le donateur ne s'applique qu'à un don."),
        (
            {"origin_kind": "unknown", "acquisition_date": "2999-01-01"},
            "La date ne peut pas être dans le futur.",
        ),
        (
            {"origin_kind": "unknown", "acquisition_date_unknown": True, "acquisition_date": "2020-01-01"},
            "Une date inconnue ne peut pas être accompagnée d'une date d'acquisition.",
        ),
        (
            {"origin_kind": "unknown", "acquisition_date_note": "x"},
            "La précision ne s'applique qu'à une date d'acquisition inconnue.",
        ),
    ],
)
def test_invalid_provenance_is_refused(ctx: LogisticsClubContext, provenance, message):
    article = make_article(ctx)
    response = client_for(ctx.steward.user).post(
        reverse("logistics:movement-list"),
        {
            "movement_type": "in_donation",
            "article_id": article.pk,
            "quantity": 1,
            "movement_date": today().isoformat(),
            "provenance": provenance,
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == message
    assert total_of(ctx, article) == 0


def test_provenance_refused_on_outgoing_movement_and_foreign_donor(ctx: LogisticsClubContext, other_ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 5)
    client = client_for(ctx.steward.user)
    out = client.post(
        reverse("logistics:movement-list"),
        {
            "movement_type": "out_loss",
            "article_id": article.pk,
            "quantity": 1,
            "movement_date": today().isoformat(),
            "provenance": {"origin_kind": "club_funds"},
        },
        format="json",
    )
    assert out.status_code == status.HTTP_400_BAD_REQUEST
    foreign = make_member(other_ctx.club)
    donation = client.post(
        reverse("logistics:movement-list"),
        {
            "movement_type": "in_donation",
            "article_id": article.pk,
            "quantity": 1,
            "movement_date": today().isoformat(),
            "provenance": {"origin_kind": "donation", "donor_membership_id": foreign.pk},
        },
        format="json",
    )
    assert donation.status_code == status.HTTP_400_BAD_REQUEST


def test_movements_are_append_only(ctx: LogisticsClubContext):
    article = make_article(ctx)
    movement = add_stock(ctx, article, 5, provenance={"origin_kind": "unknown"})
    with active_club(ctx.club):
        movement.donor_name = "Autre"
        with pytest.raises(LogisticsImmutableError):
            movement.save()
        with pytest.raises(LogisticsImmutableError):
            movement.delete()
        with pytest.raises(LogisticsImmutableError):
            StockMovement.objects.filter(pk=movement.pk).update(quantity=1)
        with pytest.raises(LogisticsImmutableError):
            StockMovement.objects.filter(pk=movement.pk).delete()
    api = client_for(ctx.steward.user)
    assert api.patch(reverse("logistics:movement-detail", args=[movement.pk]), {}, format="json").status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert api.delete(reverse("logistics:movement-detail", args=[movement.pk])).status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ---------------------------------------------------------------------------
# Déclassement (lot 4)
# ---------------------------------------------------------------------------


def flag(client, article, quantity, holder=None, **extra):
    body = {
        "article_id": article.pk,
        "holder_id": holder.pk if holder else None,
        "quantity": quantity,
        "reason": "worn",
        "noted_on": today().isoformat(),
        **extra,
    }
    return client.post(reverse("logistics:decommission-list"), body, format="json")


def test_decommission_in_two_steps_keeps_stock_until_exit(ctx: LogisticsClubContext):
    article = make_article(ctx)
    holder = make_member_holder(ctx)
    add_stock(ctx, article, 10, holder=holder)
    client = client_for(ctx.steward.user)

    flagged = flag(client, article, 4, holder)
    assert flagged.status_code == status.HTTP_201_CREATED, flagged.data
    assert flagged.data["status"] == "pending"
    assert flagged.data["noted_by"]["name"]
    assert total_of(ctx, article) == 10  # le stock ne change pas
    detail = client.get(reverse("logistics:article-detail", args=[article.pk])).data
    assert detail["in_stock"] == 10 and detail["pending_decommission"] == 4
    assert client.get(reverse("logistics:holder-detail", args=[holder.pk])).data["articles"][0]["pending_decommission"] == 4

    dec_id = flagged.data["id"]
    unconfirmed = client.post(
        reverse("logistics:decommission-execute", args=[dec_id]), {"exit_date": today().isoformat()}, format="json"
    )
    assert unconfirmed.status_code == status.HTTP_400_BAD_REQUEST
    assert unconfirmed.data["detail"] == "Confirmez la sortie du stock."
    assert total_of(ctx, article) == 10

    executed = client.post(
        reverse("logistics:decommission-execute", args=[dec_id]),
        {"exit_date": today().isoformat(), "destination": "Donné à l'école du quartier", "confirm": True},
        format="json",
    )
    assert executed.status_code == status.HTTP_200_OK, executed.data
    assert executed.data["in_stock"] == 6
    assert executed.data["decommission"]["status"] == "done"
    assert executed.data["decommission"]["executed_by"]["name"]
    assert stock_of(ctx, article, holder) == 6
    with active_club(ctx.club):
        movement = StockMovement.objects.get(decommission_id=dec_id)
        assert movement.movement_type == "out_decommission" and movement.quantity == 4
        assert movement.holder_id == holder.pk
        assert "Donné à l'école du quartier" in movement.reason
    assert executed.data["decommission"]["exit_movement_id"] == movement.pk
    assert client.get(reverse("logistics:article-detail", args=[article.pk])).data["pending_decommission"] == 0

    again = client.post(
        reverse("logistics:decommission-execute", args=[dec_id]), {"exit_date": today().isoformat(), "confirm": True}, format="json"
    )
    assert again.data["detail"] == "Ce signalement n'est plus en attente."
    with active_club(ctx.club):
        with pytest.raises(LogisticsImmutableError):
            Decommission.objects.get(pk=dec_id).delete()
    actions = set(AuditLog.objects.filter(club=ctx.club, action_type__startswith="logistics.decommission.").values_list("action_type", flat=True))
    assert actions == {"logistics.decommission.flagged", "logistics.decommission.executed"}


def test_decommission_quantity_limited_by_holder_stock_and_pending(ctx: LogisticsClubContext):
    article = make_article(ctx, unit="paire")
    holder = make_place(ctx)
    add_stock(ctx, article, 5, holder=holder)
    add_stock(ctx, article, 20)
    client = client_for(ctx.steward.user)
    refused = flag(client, article, 6, holder)
    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert refused.data["detail"] == "Il ne reste que 5 paire chez Local du club."
    assert flag(client, article, 3, holder).status_code == status.HTTP_201_CREATED
    cumulative = flag(client, article, 3, holder)
    assert cumulative.data["detail"] == "Il ne reste que 2 paire chez Local du club."
    unlocated = flag(client, article, 21)
    assert unlocated.data["detail"] == "Il ne reste que 20 paire chez Non localisé."
    other_reason = flag(client, article, 1, holder, reason="other")
    assert other_reason.data["detail"] == "Précisez le motif."


def test_decommission_cancel_requires_reason_and_is_final(ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 5)
    client = client_for(ctx.steward.user)
    dec_id = flag(client, article, 2).data["id"]
    blank = client.post(reverse("logistics:decommission-cancel", args=[dec_id]), {"reason": "  "}, format="json")
    assert blank.status_code == status.HTTP_400_BAD_REQUEST
    cancelled = client.post(reverse("logistics:decommission-cancel", args=[dec_id]), {"reason": "Finalement gardés"}, format="json")
    assert cancelled.status_code == status.HTTP_200_OK
    assert cancelled.data["status"] == "cancelled" and cancelled.data["cancel_reason"] == "Finalement gardés"
    assert cancelled.data["cancelled_by"]["name"]
    assert total_of(ctx, article) == 5
    executed = client.post(
        reverse("logistics:decommission-execute", args=[dec_id]), {"exit_date": today().isoformat(), "confirm": True}, format="json"
    )
    assert executed.status_code == status.HTTP_400_BAD_REQUEST
    assert client.get(reverse("logistics:article-detail", args=[article.pk])).data["pending_decommission"] == 0
    still_listed = client.get(reverse("logistics:decommission-list") + "?status=cancelled").data
    assert still_listed["count"] == 1
    assert AuditLog.objects.filter(club=ctx.club, action_type="logistics.decommission.cancelled").count() == 1


def test_decommission_exit_date_rules(ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 5)
    client = client_for(ctx.steward.user)
    dec_id = flag(client, article, 2).data["id"]
    url = reverse("logistics:decommission-execute", args=[dec_id])
    future = client.post(url, {"exit_date": (today() + datetime.timedelta(days=5)).isoformat(), "confirm": True}, format="json")
    assert future.data["detail"] == "La date ne peut pas être dans le futur."
    before = client.post(url, {"exit_date": (today() - datetime.timedelta(days=2)).isoformat(), "confirm": True}, format="json")
    assert before.data["detail"] == "La date de sortie ne peut pas être antérieure au constat."
    assert total_of(ctx, article) == 5


def test_decommission_roles_and_isolation(ctx: LogisticsClubContext, other_ctx: LogisticsClubContext):
    article = make_article(ctx)
    add_stock(ctx, article, 5)
    steward = client_for(ctx.steward.user)
    dec_id = flag(steward, article, 1).data["id"]
    for role in ("president", "vice_president", "treasurer", "coach"):
        client = client_for(getattr(ctx, role).user)
        assert client.get(reverse("logistics:decommission-list")).status_code == status.HTTP_200_OK
        assert client.get(reverse("logistics:decommission-detail", args=[dec_id])).status_code == status.HTTP_200_OK
        assert flag(client, article, 1).status_code == status.HTTP_403_FORBIDDEN
        assert client.post(reverse("logistics:decommission-execute", args=[dec_id]), {"exit_date": today().isoformat(), "confirm": True}, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert client.post(reverse("logistics:decommission-cancel", args=[dec_id]), {"reason": "x"}, format="json").status_code == status.HTTP_403_FORBIDDEN
    assert client_for(ctx.player.user).get(reverse("logistics:decommission-list")).status_code == status.HTTP_403_FORBIDDEN

    foreign = client_for(other_ctx.steward.user)
    assert foreign.get(reverse("logistics:decommission-list")).data["count"] == 0
    assert foreign.get(reverse("logistics:decommission-detail", args=[dec_id])).status_code == status.HTTP_404_NOT_FOUND
    assert foreign.post(reverse("logistics:decommission-execute", args=[dec_id]), {"exit_date": today().isoformat(), "confirm": True}, format="json").status_code == status.HTTP_404_NOT_FOUND
    assert foreign.post(reverse("logistics:decommission-cancel", args=[dec_id]), {"reason": "x"}, format="json").status_code == status.HTTP_404_NOT_FOUND
    # article d'un autre club refusé au signalement
    assert flag(foreign, article, 1).status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Registre de l'intendance (lot 5)
# ---------------------------------------------------------------------------


def seed_register(ctx):
    balls = make_article(ctx, "Ballons de match", Article.Category.BALLS)
    jerseys = make_article(ctx, "Vareuse bleu-blanc", Article.Category.JERSEY)
    landry = make_member_holder(ctx)
    donor = make_member(ctx.club)
    add_stock(ctx, balls, 14, holder=landry, movement_type="in_donation",
              provenance={"origin_kind": "donation", "donor_membership_id": None, "donor_name": "Lusamba",
                          "acquisition_date": "2025-06-22", "condition_at_entry": "good"})
    add_stock(ctx, balls, 8, provenance={"origin_kind": "club_funds", "acquisition_date_unknown": True,
                                         "acquisition_date_note": "Voir le comité précédent"})
    add_stock(ctx, jerseys, 20, movement_type="in_opening", provenance={"origin_kind": "donation", "donor_membership_id": donor.pk})
    return balls, jerseys, landry, donor


def test_register_json_groups_by_nature_with_totals_and_distribution(ctx: LogisticsClubContext):
    balls, jerseys, landry, donor = seed_register(ctx)
    response = client_for(ctx.president.user).get(reverse("logistics:register"))
    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["club"]["name"] == ctx.club.name
    assert [s["category"] for s in data["sections"]] == ["jersey", "balls"]
    ball_section = data["sections"][1]
    assert ball_section["stock_total_by_unit"] == [{"unit": "pièce", "quantity": 22}]
    assert [(r["holder_name"], r["quantity"]) for r in ball_section["current_distribution"]] == [
        (landry.display_name, 14),
        ("Non localisé", 8),
    ]
    lines = {line["quantity"]: line for line in ball_section["lines"]}
    assert lines[14]["origin"] == "Don de Lusamba" and lines[14]["location"] == landry.display_name
    assert lines[14]["condition_display"] == "Bon état"
    assert lines[8]["origin"] == "Frais de l'équipe"
    assert lines[8]["acquisition_label"] == "Date inconnue — Voir le comité précédent"
    jersey_line = data["sections"][0]["lines"][0]
    assert jersey_line["origin"] == f"Don de {donor.user.first_name} {donor.user.last_name}".strip()
    assert jersey_line["condition_display"] == "Neuf"  # état de l'article en repli


def test_register_filters_and_exits(ctx: LogisticsClubContext):
    balls, jerseys, landry, _ = seed_register(ctx)
    client = client_for(ctx.treasurer.user)
    url = reverse("logistics:register")
    assert [s["category"] for s in client.get(url + "?category=balls").data["sections"]] == ["balls"]
    by_holder = client.get(url + f"?holder={landry.pk}").data
    assert len(by_holder["sections"]) == 1 and by_holder["sections"][0]["lines"][0]["quantity"] == 14
    assert by_holder["sections"][0]["stock_total_by_unit"][0]["quantity"] == 14
    unlocated = client.get(url + "?holder=none").data
    assert {s["category"] for s in unlocated["sections"]} == {"jersey", "balls"}
    assert client.get(url + "?search=lusamba").data["sections"][0]["lines"][0]["quantity"] == 14
    assert client.get(url + "?category=nope").status_code == status.HTTP_400_BAD_REQUEST
    assert client.get(url + "?holder=999999").status_code == status.HTTP_404_NOT_FOUND

    # un article entièrement sorti disparaît, sauf « Afficher les sorties »
    add_stock(ctx, jerseys, 20, movement_type="out_loss")
    assert [s["category"] for s in client.get(url).data["sections"]] == ["balls"]
    with_exits = client.get(url + "?include_exits=true").data
    assert {s["category"] for s in with_exits["sections"]} == {"jersey", "balls"}
    assert with_exits["exits"][0]["movement_type"] == "out_loss"


def test_register_lists_pending_decommissions(ctx: LogisticsClubContext):
    balls, *_ = seed_register(ctx)
    steward = client_for(ctx.steward.user)
    assert flag(steward, balls, 3, reason="damaged").status_code == status.HTTP_201_CREATED
    data = steward.get(reverse("logistics:register")).data
    assert data["decommissions"][0]["quantity"] == 3
    assert data["decommissions"][0]["reason_display"] == "Abîmé"
    assert data["sections"][-1]["stock_total_by_unit"][0]["quantity"] == 22  # le stock reste compté


def test_register_pdf_contains_club_name_not_imara_and_is_logged(ctx: LogisticsClubContext):
    balls, *_ = seed_register(ctx)
    flag(client_for(ctx.steward.user), balls, 2)
    response = client_for(ctx.coach.user).get(reverse("logistics:register-pdf"))
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/pdf"
    assert "attachment" in response["Content-Disposition"]
    content = response.content
    assert content.startswith(b"%PDF")
    assert ctx.club.name.encode() in content
    assert b"INTENDANCE" in content
    for forbidden in (b"IMARA", b"imara", b"Imara"):
        assert forbidden not in content
    assert b"MediaBox" in content and b"841.88" in content  # A4 paysage
    entry = AuditLog.objects.get(club=ctx.club, action_type="logistics.register.exported")
    assert entry.actor_id == ctx.coach.user.pk and entry.after["format"] == "pdf"


def test_register_pdf_header_uses_other_club_name_without_leak(ctx: LogisticsClubContext, other_ctx: LogisticsClubContext):
    seed_register(other_ctx)
    seed_register(ctx)
    foreign_article = Article.all_objects.get(club=other_ctx.club, name="Vareuse bleu-blanc")
    foreign_article.name = "Article secret etranger"
    foreign_article.save()
    content = client_for(ctx.steward.user).get(reverse("logistics:register-pdf")).content
    assert ctx.club.name.encode() in content
    assert other_ctx.club.name.encode() not in content
    assert b"Article secret etranger" not in content
    other_content = client_for(other_ctx.steward.user).get(reverse("logistics:register-pdf")).content
    assert other_ctx.club.name.encode() in other_content and ctx.club.name.encode() not in other_content


def test_register_empty_pdf_is_generated(ctx: LogisticsClubContext):
    response = client_for(ctx.steward.user).get(reverse("logistics:register-pdf") + "?category=balls")
    assert response.status_code == status.HTTP_200_OK and response.content.startswith(b"%PDF")


def test_register_csv_columns_bom_and_round_trip_values(ctx: LogisticsClubContext):
    balls, *_ = seed_register(ctx)
    add_stock(ctx, balls, 1, provenance={"origin_kind": "donation", "donor_name": "=CMD()"})
    response = client_for(ctx.steward.user).get(reverse("logistics:register-csv"))
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"].startswith("text/csv")
    raw = response.content
    assert raw.startswith("﻿".encode("utf-8"))
    rows = raw.decode("utf-8-sig").splitlines()
    assert rows[0] == "nature;designation;quantite;unite;origine;date_acquisition;localisation;etat"
    assert any(r.startswith("Ballons;Ballons de match;14;pièce;Lusamba;22/06/2025;") and r.endswith(";Bon état") for r in rows)
    assert any(";Frais de l'équipe;Voir le comité précédent;;" in r for r in rows)
    assert any("'=CMD()" in r for r in rows) and not any(";=CMD()" in r for r in rows)
    assert AuditLog.objects.filter(club=ctx.club, action_type="logistics.register.exported").count() == 1


def test_register_roles_and_isolation(ctx: LogisticsClubContext, other_ctx: LogisticsClubContext):
    seed_register(other_ctx)
    for role in ("president", "vice_president", "treasurer", "coach", "steward"):
        client = client_for(getattr(ctx, role).user)
        for name in ("register", "register-pdf", "register-csv"):
            assert client.get(reverse(f"logistics:{name}")).status_code == status.HTTP_200_OK
    assert client_for(ctx.steward.user).get(reverse("logistics:register")).data["is_empty"] is True
    player = client_for(ctx.player.user)
    for name in ("register", "register-pdf", "register-csv"):
        assert player.get(reverse(f"logistics:{name}")).status_code == status.HTTP_403_FORBIDDEN
    assert b"Ballons" not in client_for(ctx.steward.user).get(reverse("logistics:register-csv")).content
    assert client_for(ctx.steward.user).get(reverse("logistics:register-pdf") + f"?holder={Holder.all_objects.filter(club=other_ctx.club).first().pk}").status_code == status.HTTP_404_NOT_FOUND


def test_unauthenticated_requests_are_refused():
    from rest_framework.test import APIClient

    client = APIClient()
    for name in ("holder-list", "decommission-list", "register", "register-pdf", "register-csv"):
        assert client.get(reverse(f"logistics:{name}")).status_code in (401, 403)
