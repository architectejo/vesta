"""Plan tactique (CDC 4.11 ; 10.2 n° 16, n° 31, n° 32 ; CLAUDE.md règle n° 5)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.clubs.models import Membership
from apps.sport import services
from apps.sport.models import TacticalPlan, TacticalPlanAnnotation

pytestmark = pytest.mark.django_db


def _create_plan(ctx):
    return services.create_tactical_plan(
        club=ctx.club, name="Plan du dimanche", formation=TacticalPlan.Formation.F_4_4_2, squad_size=11,
        created_by=ctx.coach.user,
    )


def test_place_eligible_player(ctx):
    plan = _create_plan(ctx)
    placement = services.place_on_plan(plan=plan, membership=ctx.player, x_coord=Decimal("50.00"), y_coord=Decimal("80.00"), placed_by=ctx.coach.user)
    assert placement.pk is not None


def test_cannot_place_debtor_even_manually(ctx):
    plan = _create_plan(ctx)
    with pytest.raises(services.PlayerNotEligibleError) as exc:
        services.place_on_plan(plan=plan, membership=ctx.debtor, x_coord=Decimal("50.00"), y_coord=Decimal("80.00"), placed_by=ctx.coach.user)
    assert "En dette" in str(exc.value)


def test_cannot_place_pending_membership(ctx):
    plan = _create_plan(ctx)
    with pytest.raises(services.PlayerNotEligibleError):
        services.place_on_plan(plan=plan, membership=ctx.pending_member, x_coord=Decimal("50"), y_coord=Decimal("80"), placed_by=ctx.coach.user)


def test_cannot_edit_published_plan(ctx):
    plan = _create_plan(ctx)
    services.place_on_plan(plan=plan, membership=ctx.player, x_coord=Decimal("50"), y_coord=Decimal("80"), placed_by=ctx.coach.user)
    services.publish_tactical_plan(plan=plan, published_by=ctx.coach.user)
    with pytest.raises(services.SportValidationError):
        services.place_on_plan(plan=plan, membership=ctx.captain, x_coord=Decimal("30"), y_coord=Decimal("40"), placed_by=ctx.coach.user)


def test_publish_blocked_while_placed_player_ineligible(ctx):
    plan = _create_plan(ctx)
    services.place_on_plan(plan=plan, membership=ctx.player, x_coord=Decimal("50"), y_coord=Decimal("80"), placed_by=ctx.coach.user)

    from apps.sport.tests.conftest import make_debtor

    make_debtor(ctx.club, ctx.player)

    with pytest.raises(services.SportValidationError):
        services.publish_tactical_plan(plan=plan, published_by=ctx.coach.user)


def test_duplicate_skips_ineligible_players(ctx):
    plan = _create_plan(ctx)
    services.place_on_plan(plan=plan, membership=ctx.player, x_coord=Decimal("50"), y_coord=Decimal("80"), placed_by=ctx.coach.user)

    # Un joueur devenu inéligible APRÈS avoir été placé (pas ctx.debtor,
    # déjà bloqué à la pose) : on le rend en dette une fois placé.
    services.place_on_plan(plan=plan, membership=ctx.captain, x_coord=Decimal("30"), y_coord=Decimal("40"), placed_by=ctx.coach.user)
    from apps.sport.tests.conftest import make_debtor

    make_debtor(ctx.club, ctx.captain)

    new_plan, skipped = services.duplicate_tactical_plan(plan=plan, name="Copie", created_by=ctx.coach.user)
    assert ctx.captain in skipped
    from apps.sport.models import TacticalPlanPlacement

    assert TacticalPlanPlacement.all_objects.filter(club=ctx.club, plan=new_plan, membership=ctx.player).exists()
    assert not TacticalPlanPlacement.all_objects.filter(club=ctx.club, plan=new_plan, membership=ctx.captain).exists()


def test_update_number_and_position_updates_membership_and_refuses_duplicate(ctx):
    plan = _create_plan(ctx)
    placement = services.place_on_plan(plan=plan, membership=ctx.player, x_coord=Decimal("50"), y_coord=Decimal("80"), placed_by=ctx.coach.user)

    ctx.captain.jersey_number = 7
    ctx.captain.save()

    with pytest.raises(services.SportValidationError, match="déjà porté"):
        services.update_plan_placement_number_and_position(
            placement=placement, jersey_number=7, position=Membership.Position.FORWARD, updated_by=ctx.coach.user
        )
    services.update_plan_placement_number_and_position(
        placement=placement, jersey_number=8, position=Membership.Position.FORWARD, updated_by=ctx.coach.user
    )
    ctx.player.refresh_from_db()
    assert ctx.player.jersey_number == 8
    assert ctx.player.position == Membership.Position.FORWARD

    # D4 : champ non transmis = inchangé.
    services.update_plan_placement_number_and_position(placement=placement, jersey_number=9, updated_by=ctx.coach.user)
    ctx.player.refresh_from_db()
    assert ctx.player.jersey_number == 9
    assert ctx.player.position == Membership.Position.FORWARD


def test_annotation_add_and_delete(ctx):
    plan = _create_plan(ctx)
    annotation = services.add_annotation(plan=plan, annotation_type=TacticalPlanAnnotation.AnnotationType.NOTE, created_by=ctx.coach.user, text="Restez compacts")
    assert annotation.pk is not None
    services.delete_annotation(annotation=annotation, deleted_by=ctx.coach.user)
    assert not TacticalPlanAnnotation.all_objects.filter(pk=annotation.pk).exists()


def test_delete_plan(ctx):
    plan = _create_plan(ctx)
    plan_id = plan.pk
    services.delete_tactical_plan(plan=plan, deleted_by=ctx.coach.user)
    assert not TacticalPlan.all_objects.filter(pk=plan_id).exists()


def test_reduced_squad_size_requires_custom_formation(ctx):
    with pytest.raises(Exception):
        services.create_tactical_plan(
            club=ctx.club, name="Plan à 7", formation=TacticalPlan.Formation.F_4_4_2, squad_size=7, created_by=ctx.coach.user
        )
    plan = services.create_tactical_plan(
        club=ctx.club, name="Plan à 7", formation=TacticalPlan.Formation.CUSTOM, squad_size=7, created_by=ctx.coach.user
    )
    assert plan.pk is not None
