"""Vues API de la formation par équipe et du placement terrain/banc
(extension client du 30/09/2026, hors CDC écrit à ce jour -- voir
``apps.sport.services.set_team_formation``/``place_team_player`` et le
compte rendu de la tâche). Complète les tests de service déjà écrits
(``test_team_field_positions.py``) par la couche HTTP : permissions,
traduction des erreurs métier en réponses HTTP, forme de la réponse
(mêmes formats que ``serialize_session_detail``/``serialize_team_assignment``
pour que le frontend réaffiche l'état sans inventer de format)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from rest_framework import status

from apps.sport import services
from apps.sport.models import Formation, TeamAssignment
from apps.sport.tests.conftest import client_for, make_debtor, make_member
from apps.sport.tests.factories import SessionFactory

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("Africa/Kinshasa")


def _arrived(session, hour=7, minute=40):
    return datetime.datetime.combine(session.event.event_date, datetime.time(hour, minute), tzinfo=TZ)


def _assign(session, membership, team, *, actor):
    services.mark_arrival(session=session, membership=membership, arrived_at=_arrived(session), marked_by=actor)
    return services.assign_team(session=session, membership=membership, team=team, assigned_by=actor)


# ---------------------------------------------------------------------------
# Formation par équipe
# ---------------------------------------------------------------------------


def test_coach_sets_team_formation_and_response_reflects_it(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:session-team-formation", args=[session.pk])

    response = client_for(ctx.coach.user).post(url, {"team": "A", "formation": Formation.F_4_3_3})

    assert response.status_code == status.HTTP_200_OK, response.data
    assert response.data["team_a_formation"] == Formation.F_4_3_3
    assert response.data["team_b_formation"] == ""


def test_plain_player_cannot_set_team_formation(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:session-team-formation", args=[session.pk])

    response = client_for(ctx.player.user).post(url, {"team": "A", "formation": Formation.F_4_4_2})

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_set_team_formation_rejects_invalid_formation_value(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:session-team-formation", args=[session.pk])

    response = client_for(ctx.coach.user).post(url, {"team": "A", "formation": "9-0-1"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_set_team_formation_blocked_on_locked_session(ctx):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    session = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday
    )
    url = reverse("sport:session-team-formation", args=[session.pk])

    response = client_for(ctx.coach.user).post(url, {"team": "A", "formation": Formation.F_4_4_2})

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "event_locked"


def test_session_team_formation_of_another_club_is_not_found(ctx, other_ctx):
    other_session = SessionFactory(club=other_ctx.club, event__club=other_ctx.club, event__season=other_ctx.season)
    url = reverse("sport:session-team-formation", args=[other_session.pk])

    response = client_for(ctx.coach.user).post(url, {"team": "A", "formation": Formation.F_4_4_2})

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Placement terrain/banc
# ---------------------------------------------------------------------------


def test_coach_places_an_assigned_player_on_field(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)
    url = reverse("sport:session-team-placement", args=[session.pk])

    response = client_for(ctx.coach.user).post(
        url, {"team": "A", "membership_id": ctx.player.pk, "x_coord": "50.00", "y_coord": "80.00"}
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    entry = next(item for item in response.data["team_a"] if item["membership_id"] == ctx.player.pk)
    assert entry["is_on_field"] is True
    assert entry["x_coord"] == "50.00"
    assert entry["y_coord"] == "80.00"


def test_sending_player_back_to_bench_clears_coordinates(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)
    services.place_team_player(
        session=session, team=TeamAssignment.Team.A, membership=ctx.player,
        x_coord=Decimal("10"), y_coord=Decimal("20"), actor=ctx.coach.user,
    )
    url = reverse("sport:session-team-placement", args=[session.pk])

    response = client_for(ctx.coach.user).post(url, {"team": "A", "membership_id": ctx.player.pk})

    assert response.status_code == status.HTTP_200_OK, response.data
    entry = next(item for item in response.data["team_a"] if item["membership_id"] == ctx.player.pk)
    assert entry["is_on_field"] is False
    assert entry["x_coord"] is None
    assert entry["y_coord"] is None


def test_placement_requires_both_coordinates_or_none(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)
    url = reverse("sport:session-team-placement", args=[session.pk])

    response = client_for(ctx.coach.user).post(url, {"team": "A", "membership_id": ctx.player.pk, "x_coord": "50.00"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_placement_refuses_a_debtor_with_role_filtered_reason(ctx):
    """``assign_team`` bloque déjà un débiteur à la répartition elle-même
    (CLAUDE.md règle n° 5) : la dette apparaît donc ICI après la
    répartition, pour vérifier le contrôle propre de ``place_team_player``
    (défense en profondeur), même convention que
    ``test_team_field_positions.py::test_player_who_becomes_debtor_after_assignment_cannot_be_placed``."""

    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)
    make_debtor(ctx.club, ctx.player)
    url = reverse("sport:session-team-placement", args=[session.pk])

    response = client_for(ctx.coach.user).post(
        url, {"team": "A", "membership_id": ctx.player.pk, "x_coord": "50.00", "y_coord": "50.00"}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "player_not_eligible"
    # 10.3 n° 188 : le Coach ne lit ni la dette ni le montant.
    assert response.data["detail"] == "Non éligible."


def test_placement_refuses_an_unassigned_player(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:session-team-placement", args=[session.pk])

    response = client_for(ctx.coach.user).post(
        url, {"team": "A", "membership_id": ctx.player.pk, "x_coord": "50.00", "y_coord": "50.00"}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "code" not in response.data


def test_placement_enforces_the_eleven_player_cap(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:session-team-placement", args=[session.pk])

    memberships = [make_member(ctx.club) for _ in range(11)]
    for index, membership in enumerate(memberships):
        _assign(session, membership, TeamAssignment.Team.A, actor=ctx.coach.user)
        response = client_for(ctx.coach.user).post(
            url,
            {
                "team": "A",
                "membership_id": membership.pk,
                "x_coord": f"{index}.00",
                "y_coord": "10.00",
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.data

    extra = make_member(ctx.club)
    _assign(session, extra, TeamAssignment.Team.A, actor=ctx.coach.user)
    overflow = client_for(ctx.coach.user).post(
        url, {"team": "A", "membership_id": extra.pk, "x_coord": "99.00", "y_coord": "99.00"}
    )

    assert overflow.status_code == status.HTTP_400_BAD_REQUEST
    assert "11" in overflow.data["detail"]


def test_plain_player_cannot_place_a_player(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)
    url = reverse("sport:session-team-placement", args=[session.pk])

    response = client_for(ctx.player.user).post(
        url, {"team": "A", "membership_id": ctx.player.pk, "x_coord": "50.00", "y_coord": "50.00"}
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_session_team_placement_of_another_club_is_not_found(ctx, other_ctx):
    other_session = SessionFactory(club=other_ctx.club, event__club=other_ctx.club, event__season=other_ctx.season)
    url = reverse("sport:session-team-placement", args=[other_session.pk])

    response = client_for(ctx.coach.user).post(
        url, {"team": "A", "membership_id": ctx.player.pk, "x_coord": "50.00", "y_coord": "50.00"}
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
