"""Tests unitaires des règles métier de la logistique (CDC 4.13 ; tâche 4.3)."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.core.tenant import active_club
from apps.logistics import services
from apps.logistics.models import Article, Inventory, InventoryLine, LogisticsImmutableError, StockMovement
from apps.logistics.tests.conftest import LogisticsClubContext
from apps.sport.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


def make_article(ctx: LogisticsClubContext, **kwargs) -> Article:
    with active_club(ctx.club):
        return services.create_article(
            club=ctx.club,
            actor=ctx.steward.user,
            name=kwargs.pop("name", "Maillot domicile"),
            category=kwargs.pop("category", Article.Category.JERSEY),
            **kwargs,
        )


def test_movement_updates_theoretical_stock(ctx: LogisticsClubContext):
    article = make_article(ctx)
    with active_club(ctx.club):
        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=article,
            quantity=20,
            movement_date=timezone.now().date(),
        )
        assert services.theoretical_quantity(article) == 20

        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.OUT_DISTRIBUTION,
            article=article,
            quantity=5,
            movement_date=timezone.now().date(),
        )
        assert services.theoretical_quantity(article) == 15


def test_out_movement_refused_beyond_stock(ctx: LogisticsClubContext):
    article = make_article(ctx)
    with active_club(ctx.club):
        with pytest.raises(services.LogisticsError, match="Quantité supérieure au stock disponible"):
            services.record_movement(
                club=ctx.club,
                actor=ctx.steward.user,
                movement_type=StockMovement.MovementType.OUT_DISTRIBUTION,
                article=article,
                quantity=1,
                movement_date=timezone.now().date(),
            )


def test_movement_date_cannot_be_in_the_future(ctx: LogisticsClubContext):
    article = make_article(ctx)
    with active_club(ctx.club):
        with pytest.raises(services.LogisticsError, match="ne peut pas être dans le futur"):
            services.record_movement(
                club=ctx.club,
                actor=ctx.steward.user,
                movement_type=StockMovement.MovementType.IN_DONATION,
                article=article,
                quantity=1,
                movement_date=timezone.now().date() + datetime.timedelta(days=1),
            )


def test_stock_movement_is_immutable(ctx: LogisticsClubContext):
    article = make_article(ctx)
    with active_club(ctx.club):
        movement = services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_DONATION,
            article=article,
            quantity=3,
            movement_date=timezone.now().date(),
        )
        movement.reason = "modifié"
        with pytest.raises(LogisticsImmutableError):
            movement.save()
        with pytest.raises(LogisticsImmutableError):
            movement.delete()


def test_archive_refused_if_stock_not_zero(ctx: LogisticsClubContext):
    article = make_article(ctx)
    with active_club(ctx.club):
        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=article,
            quantity=4,
            movement_date=timezone.now().date(),
        )
        with pytest.raises(services.LogisticsError, match="stock"):
            services.archive_article(article=article, actor=ctx.steward.user)

        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.OUT_WEAR,
            article=article,
            quantity=4,
            movement_date=timezone.now().date(),
        )
        archived = services.archive_article(article=article, actor=ctx.steward.user)
        assert archived.status == Article.Status.ARCHIVED


def test_match_equipment_out_is_all_or_nothing(ctx: LogisticsClubContext):
    jersey = make_article(ctx, name="Maillot")
    socks = make_article(ctx, name="Bas", category=Article.Category.SOCKS)
    match = MatchFactory(club=ctx.club, event__club=ctx.club)
    with active_club(ctx.club):
        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=jersey,
            quantity=5,
            movement_date=timezone.now().date(),
        )
        # Pas de stock pour "socks" -> la ligne échoue, rien n'est créé (point ouvert n° 10).
        with pytest.raises(services.LogisticsError):
            services.record_match_equipment_out(
                club=ctx.club,
                actor=ctx.coach.user,
                match=match,
                lines=[{"article": jersey, "quantity": 2}, {"article": socks, "quantity": 2}],
            )
        assert services.theoretical_quantity(jersey) == 5  # rien n'a été décompté

        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=socks,
            quantity=5,
            movement_date=timezone.now().date(),
        )
        services.record_match_equipment_out(
            club=ctx.club,
            actor=ctx.coach.user,
            match=match,
            lines=[{"article": jersey, "quantity": 2}, {"article": socks, "quantity": 2}],
        )
        summary = {row["article_id"]: row for row in services.match_equipment_summary(match)}
        assert summary[jersey.pk]["status"] == "out"
        assert summary[jersey.pk]["out_quantity"] == 2


def test_match_equipment_return_partial_then_full(ctx: LogisticsClubContext):
    jersey = make_article(ctx, name="Maillot")
    match = MatchFactory(club=ctx.club, event__club=ctx.club)
    with active_club(ctx.club):
        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=jersey,
            quantity=10,
            movement_date=timezone.now().date(),
        )
        services.record_match_equipment_out(club=ctx.club, actor=ctx.coach.user, match=match, lines=[{"article": jersey, "quantity": 5}])

        with pytest.raises(services.LogisticsError, match="ne peut pas dépasser"):
            services.record_match_equipment_return(
                club=ctx.club, actor=ctx.steward.user, match=match, lines=[{"article": jersey, "quantity_returned": 6}]
            )

        services.record_match_equipment_return(
            club=ctx.club, actor=ctx.coach.user, match=match, lines=[{"article": jersey, "quantity_returned": 3}]
        )
        summary = {row["article_id"]: row for row in services.match_equipment_summary(match)}
        assert summary[jersey.pk]["status"] == "partially_returned"
        assert summary[jersey.pk]["remaining_quantity"] == 2

        services.record_match_equipment_return(
            club=ctx.club, actor=ctx.steward.user, match=match, lines=[{"article": jersey, "quantity_returned": 2}]
        )
        summary = {row["article_id"]: row for row in services.match_equipment_summary(match)}
        assert summary[jersey.pk]["status"] == "returned"


def test_inventory_lifecycle_blocks_second_opening_and_requires_justification(ctx: LogisticsClubContext):
    article = make_article(ctx)
    with active_club(ctx.club):
        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=article,
            quantity=10,
            movement_date=timezone.now().date(),
        )
        inventory = services.open_inventory(club=ctx.club, actor=ctx.steward.user)

        ok, _reason = services.can_open_inventory(ctx.club)
        assert ok is False

        with pytest.raises(services.LogisticsError):
            services.open_inventory(club=ctx.club, actor=ctx.steward.user)

        ok, reason = services.can_close_inventory(inventory)
        assert ok is False
        assert "à compter" in reason

        lines = services.record_counts(
            inventory=inventory, actor=ctx.steward.user, counts=[{"article": article, "physical_quantity": 8}]
        )
        assert lines[0].discrepancy == -2

        ok, reason = services.can_close_inventory(inventory)
        assert ok is False
        assert "à justifier" in reason

        services.justify_discrepancy(line=lines[0], actor=ctx.steward.user, reason=InventoryLine.DiscrepancyReason.LOSS)

        ok, _reason = services.can_close_inventory(inventory)
        assert ok is True

        closed = services.close_inventory(inventory=inventory, actor=ctx.steward.user)
        assert closed.status == Inventory.Status.CLOSED

        ok, _reason = services.can_open_inventory(ctx.club)
        assert ok is True


def test_recount_changing_discrepancy_clears_justification(ctx: LogisticsClubContext):
    article = make_article(ctx)
    with active_club(ctx.club):
        services.record_movement(
            club=ctx.club,
            actor=ctx.steward.user,
            movement_type=StockMovement.MovementType.IN_PURCHASE,
            article=article,
            quantity=10,
            movement_date=timezone.now().date(),
        )
        inventory = services.open_inventory(club=ctx.club, actor=ctx.steward.user)
        [line] = services.record_counts(inventory=inventory, actor=ctx.steward.user, counts=[{"article": article, "physical_quantity": 8}])
        services.justify_discrepancy(line=line, actor=ctx.steward.user, reason=InventoryLine.DiscrepancyReason.LOSS)
        assert line.justified_at is not None

        [line] = services.record_counts(inventory=inventory, actor=ctx.steward.user, counts=[{"article": article, "physical_quantity": 7}])
        assert line.discrepancy == -3
        assert line.justified_at is None
        assert line.discrepancy_reason == ""


def test_blocking_only_once_own_quarter_has_ended(ctx: LogisticsClubContext):
    make_article(ctx)
    with active_club(ctx.club):
        q1 = datetime.datetime(2026, 2, 15, 12, 0, tzinfo=datetime.timezone.utc)
        inventory = services.open_inventory(club=ctx.club, actor=ctx.steward.user, now=q1)
        assert inventory.quarter_label == "2026-Q1"

        overview_same_quarter = services.get_material_overview(ctx.club, now=q1)
        assert overview_same_quarter["blocking"] is False

        q2 = datetime.datetime(2026, 5, 1, 12, 0, tzinfo=datetime.timezone.utc)
        overview_next_quarter = services.get_material_overview(ctx.club, now=q2)
        assert overview_next_quarter["blocking"] is True


def test_weekly_alert_deduplicated(ctx: LogisticsClubContext):
    from apps.notifications.models import Notification

    make_article(ctx)
    with active_club(ctx.club):
        q1 = datetime.datetime(2026, 2, 15, 12, 0, tzinfo=datetime.timezone.utc)
        services.open_inventory(club=ctx.club, actor=ctx.steward.user, now=q1)

        q2 = datetime.datetime(2026, 5, 1, 12, 0, tzinfo=datetime.timezone.utc)
        sent = services.send_inventory_open_alerts(club=ctx.club, now=q2)
        assert sent == 1
        assert Notification.objects.filter(
            recipient=ctx.president.user, event_type=Notification.EventType.INVENTORY_OPEN_ALERT
        ).count() == 1

        # Même semaine : pas de doublon.
        sent_again = services.send_inventory_open_alerts(club=ctx.club, now=q2 + datetime.timedelta(days=2))
        assert sent_again == 0

        # 8 jours plus tard : nouvelle alerte.
        sent_next_week = services.send_inventory_open_alerts(club=ctx.club, now=q2 + datetime.timedelta(days=8))
        assert sent_next_week == 1
