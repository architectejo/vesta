"""Vues API du plan tactique (tâche 3.6 : CDC 4.11, 10.2 n° 16/31/32,
matrice 2.4)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from apps.sport.models import TacticalPlan, TacticalPlanPlacement
from apps.sport.tests.conftest import client_for

pytestmark = pytest.mark.django_db


def _plan_payload(**overrides):
    data = {"name": "Plan de départ", "formation": TacticalPlan.Formation.F_4_4_2, "squad_size": 11}
    data.update(overrides)
    return data


def test_only_coach_creates_and_deletes_a_plan(ctx):
    denied = client_for(ctx.president.user).post(reverse("sport:tactical-plan-list"), _plan_payload())
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    created = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-list"), _plan_payload())
    assert created.status_code == status.HTTP_201_CREATED
    plan_id = created.data["id"]

    delete_denied = client_for(ctx.president.user).delete(reverse("sport:tactical-plan-detail", args=[plan_id]))
    assert delete_denied.status_code == status.HTTP_403_FORBIDDEN

    delete_ok = client_for(ctx.coach.user).delete(reverse("sport:tactical-plan-detail", args=[plan_id]))
    assert delete_ok.status_code == status.HTTP_204_NO_CONTENT


def test_draft_plan_is_hidden_from_non_coach_but_visible_once_published(ctx):
    created = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-list"), _plan_payload())
    plan_id = created.data["id"]
    detail_url = reverse("sport:tactical-plan-detail", args=[plan_id])

    listed_by_player = client_for(ctx.player.user).get(reverse("sport:tactical-plan-list"))
    assert all(item["id"] != plan_id for item in listed_by_player.data["results"])

    denied_detail = client_for(ctx.player.user).get(detail_url)
    assert denied_detail.status_code == status.HTTP_403_FORBIDDEN

    published = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-publish", args=[plan_id]))
    assert published.status_code == status.HTTP_200_OK

    now_visible = client_for(ctx.player.user).get(detail_url)
    assert now_visible.status_code == status.HTTP_200_OK


def test_placement_refuses_a_debtor_with_role_filtered_reason(ctx):
    created = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-list"), _plan_payload())
    plan_id = created.data["id"]
    url = reverse("sport:tactical-plan-placement-create", args=[plan_id])

    refused = client_for(ctx.coach.user).post(url, {"membership_id": ctx.debtor.pk, "x_coord": "50", "y_coord": "80"})
    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert refused.data["code"] == "player_not_eligible"
    assert refused.data["detail"] == "Non éligible."  # 10.3 n° 188
    assert TacticalPlanPlacement.all_objects.filter(club=ctx.club, plan_id=plan_id, membership=ctx.debtor).count() == 0

    placed = client_for(ctx.coach.user).post(url, {"membership_id": ctx.player.pk, "x_coord": "50", "y_coord": "80"})
    assert placed.status_code == status.HTTP_201_CREATED
    assert placed.data["no_longer_eligible"] is None


def test_publish_is_blocked_while_a_placed_player_is_no_longer_eligible(ctx):
    import datetime

    from django.utils import timezone as dj_timezone

    from apps.treasury.models import ContributionType, Due
    from apps.treasury.tests.factories import ContributionTypeFactory

    created = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-list"), _plan_payload())
    plan_id = created.data["id"]
    # On place un joueur en ordre, puis on simule sa mise en dette après
    # coup (le service refuserait déjà un placement direct d'un débiteur,
    # voir ``test_placement_refuses_a_debtor_with_role_filtered_reason``).
    client_for(ctx.coach.user).post(
        reverse("sport:tactical-plan-placement-create", args=[plan_id]),
        {"membership_id": ctx.player.pk, "x_coord": "40", "y_coord": "60"},
    )
    ctype = ContributionTypeFactory(
        club=ctx.club, nature=ContributionType.Nature.MANDATORY, scope=ContributionType.Scope.ALL
    )
    Due.all_objects.create(
        club=ctx.club,
        membership=ctx.player,
        contribution_type=ctype,
        period=datetime.date.today().replace(day=1),
        amount="10.00",
        due_date=datetime.date.today() - datetime.timedelta(days=60),
        source=Due.Source.SCHEDULER,
        created_at=dj_timezone.now(),
    )

    publish = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-publish", args=[plan_id]))
    assert publish.status_code == status.HTTP_400_BAD_REQUEST


def test_duplicate_skips_ineligible_players(ctx):
    created = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-list"), _plan_payload())
    plan_id = created.data["id"]
    client_for(ctx.coach.user).post(
        reverse("sport:tactical-plan-placement-create", args=[plan_id]),
        {"membership_id": ctx.player.pk, "x_coord": "40", "y_coord": "60"},
    )

    duplicated = client_for(ctx.coach.user).post(
        reverse("sport:tactical-plan-duplicate", args=[plan_id]), {"name": "Copie"}
    )
    assert duplicated.status_code == status.HTTP_201_CREATED
    assert duplicated.data["skipped_count"] == 0
    assert len(duplicated.data["placements"]) == 1


def test_only_coach_updates_plan_settings(ctx):
    created = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-list"), _plan_payload())
    plan_id = created.data["id"]
    url = reverse("sport:tactical-plan-detail", args=[plan_id])
    payload = {"name": "Plan modifié", "formation": TacticalPlan.Formation.F_4_3_3, "squad_size": 11}

    denied = client_for(ctx.president.user).patch(url, payload)
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    allowed = client_for(ctx.coach.user).patch(url, payload)
    assert allowed.status_code == status.HTTP_200_OK, allowed.data
    assert allowed.data["name"] == "Plan modifié"
    assert allowed.data["formation"] == TacticalPlan.Formation.F_4_3_3


def test_update_plan_settings_is_blocked_once_published(ctx):
    created = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-list"), _plan_payload())
    plan_id = created.data["id"]
    client_for(ctx.coach.user).post(reverse("sport:tactical-plan-publish", args=[plan_id]))

    response = client_for(ctx.coach.user).patch(
        reverse("sport:tactical-plan-detail", args=[plan_id]),
        {"name": "Plan modifié", "formation": TacticalPlan.Formation.F_4_3_3, "squad_size": 11},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_plan_of_another_club_is_not_found(ctx, other_ctx):
    from apps.sport import services as sport_services

    other_plan = sport_services.create_tactical_plan(
        club=other_ctx.club,
        name="Plan étanchéité",
        formation=TacticalPlan.Formation.F_4_4_2,
        squad_size=11,
        created_by=other_ctx.coach.user,
    )
    sport_services.publish_tactical_plan(plan=other_plan, published_by=other_ctx.coach.user)

    response = client_for(ctx.player.user).get(reverse("sport:tactical-plan-detail", args=[other_plan.pk]))

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_patch_placement_partial_keeps_position_and_refuses_duplicate_number(ctx):
    """D4 (champ absent = inchangé) et D5 (numéro unique dans le club -> 400 français)."""
    created = client_for(ctx.coach.user).post(reverse("sport:tactical-plan-list"), _plan_payload())
    plan_id = created.data["id"]
    placed = client_for(ctx.coach.user).post(
        reverse("sport:tactical-plan-placement-create", args=[plan_id]),
        {"membership_id": ctx.player.pk, "x_coord": "50", "y_coord": "80"},
    )
    url = reverse("sport:placement-detail", args=[placed.data["id"]])
    first = client_for(ctx.coach.user).patch(url, {"jersey_number": 10, "position": "midfielder"})
    assert first.status_code == status.HTTP_200_OK, first.data
    only_number = client_for(ctx.coach.user).patch(url, {"jersey_number": 11})
    assert only_number.status_code == status.HTTP_200_OK
    ctx.player.refresh_from_db()
    assert ctx.player.jersey_number == 11
    assert ctx.player.position == "midfielder"

    ctx.captain.jersey_number = 4
    ctx.captain.save()
    dup = client_for(ctx.coach.user).patch(url, {"jersey_number": 4})
    assert dup.status_code == status.HTTP_400_BAD_REQUEST
    assert "déjà porté" in dup.data["detail"]
