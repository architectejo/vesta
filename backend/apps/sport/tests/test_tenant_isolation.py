"""Étanchéité multi-club (CLAUDE.md règle n° 8 ; CDC 9.2 Lot 1, repris ici
pour le domaine sport)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.tenant import TenantMismatchError, active_club
from apps.sport import services
from apps.sport.models import TacticalPlan, TeamAssignment
from apps.sport.tests.factories import SessionFactory

pytestmark = pytest.mark.django_db


def test_team_assignments_of_one_club_never_leak_to_another(ctx, other_ctx):
    session_a = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    session_b = SessionFactory(club=other_ctx.club, event__club=other_ctx.club, event__season=other_ctx.season)

    tz_a = services._club_tz(services._club_settings(ctx.club))
    arrived_a = datetime.datetime.combine(session_a.event.event_date, datetime.time(7, 40), tzinfo=tz_a)
    services.mark_arrival(session=session_a, membership=ctx.player, arrived_at=arrived_a, marked_by=ctx.coach.user)

    tz_b = services._club_tz(services._club_settings(other_ctx.club))
    arrived_b = datetime.datetime.combine(session_b.event.event_date, datetime.time(7, 40), tzinfo=tz_b)
    services.mark_arrival(session=session_b, membership=other_ctx.player, arrived_at=arrived_b, marked_by=other_ctx.coach.user)

    assignments_a = TeamAssignment.all_objects.filter(club=ctx.club)
    assignments_b = TeamAssignment.all_objects.filter(club=other_ctx.club)
    assert assignments_a.count() == 1
    assert assignments_b.count() == 1
    assert assignments_a.first().membership_id == ctx.player.pk
    assert assignments_b.first().membership_id == other_ctx.player.pk


def test_cannot_place_a_player_from_another_club_on_a_plan(ctx, other_ctx):
    plan = services.create_tactical_plan(
        club=ctx.club, name="Plan", formation=TacticalPlan.Formation.F_4_4_2, squad_size=11, created_by=ctx.coach.user
    )
    with pytest.raises(Exception):
        services.place_on_plan(
            plan=plan, membership=other_ctx.player, x_coord=Decimal("50"), y_coord=Decimal("80"), placed_by=ctx.coach.user
        )


def test_tenant_model_save_rejects_cross_club_write_under_active_context(ctx, other_ctx):
    """Défense en profondeur (CLAUDE.md règle n° 8) : même en écriture
    directe (pas via un service), un enregistrement d'un autre club que
    le club actif du contexte courant est refusé."""

    plan = TacticalPlan(
        club=other_ctx.club, name="Plan d'un autre club", formation=TacticalPlan.Formation.F_4_4_2, squad_size=11,
        created_by=ctx.coach.user,
    )
    with active_club(ctx.club):
        with pytest.raises(TenantMismatchError):
            plan.save()
