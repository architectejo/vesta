"""Pointage et répartition A/B (CDC 4.7 ; 10.2 n° 6, 7, 25, 29, 38)."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.sport import services
from apps.sport.models import Attendance, TeamAssignment
from apps.sport.tests.factories import SessionFactory

pytestmark = pytest.mark.django_db


def _at(session, hour, minute):
    tz = services._club_tz(services._club_settings(session.club))
    return datetime.datetime.combine(session.event.event_date, datetime.time(hour, minute), tzinfo=tz)


def test_arrival_before_cutoff_is_present(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    attendance = services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 7, 45), marked_by=ctx.coach.user)
    assert attendance.status == Attendance.Status.PRESENT


def test_arrival_after_cutoff_is_late_absent(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    attendance = services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 8, 15), marked_by=ctx.coach.user)
    assert attendance.status == Attendance.Status.LATE_ABSENT


def test_present_players_auto_alternate_a_b(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    from apps.sport.tests.conftest import make_member

    second_player = make_member(ctx.club)
    third_player = make_member(ctx.club)

    services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 7, 40), marked_by=ctx.coach.user)
    services.mark_arrival(session=session, membership=second_player, arrived_at=_at(session, 7, 41), marked_by=ctx.coach.user)
    services.mark_arrival(session=session, membership=third_player, arrived_at=_at(session, 7, 42), marked_by=ctx.coach.user)

    a1 = TeamAssignment.all_objects.get(club=ctx.club, session=session, membership=ctx.player)
    a2 = TeamAssignment.all_objects.get(club=ctx.club, session=session, membership=second_player)
    a3 = TeamAssignment.all_objects.get(club=ctx.club, session=session, membership=third_player)
    assert (a1.team, a2.team, a3.team) == (TeamAssignment.Team.A, TeamAssignment.Team.B, TeamAssignment.Team.A)


def test_late_arrival_is_not_auto_assigned(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 8, 30), marked_by=ctx.coach.user)
    assert not TeamAssignment.all_objects.filter(club=ctx.club, session=session, membership=ctx.player).exists()


def test_late_arrival_placeable_manually_by_coach(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 8, 30), marked_by=ctx.coach.user)
    assignment = services.assign_team(session=session, membership=ctx.player, team=TeamAssignment.Team.A, assigned_by=ctx.coach.user)
    assert assignment.team == TeamAssignment.Team.A


def test_late_arrival_cannot_be_placed_by_president(ctx):
    """10.2 n° 38 : réservé au Coach et au Capitaine (position provisoire,
    sport-seance.md §2, point ouvert 1)."""

    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 8, 30), marked_by=ctx.coach.user)
    with pytest.raises(services.SportPermissionError):
        services.assign_team(session=session, membership=ctx.player, team=TeamAssignment.Team.A, assigned_by=ctx.president.user)


def test_president_can_move_an_already_assigned_player(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 7, 40), marked_by=ctx.coach.user)
    assignment = services.assign_team(session=session, membership=ctx.player, team=TeamAssignment.Team.B, assigned_by=ctx.president.user)
    assert assignment.team == TeamAssignment.Team.B


def test_debtor_cannot_be_assigned_even_manually(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.debtor, arrived_at=_at(session, 7, 40), marked_by=ctx.coach.user)
    # Le pointage présent n'a pas dû auto-répartir un joueur en dette.
    assert not TeamAssignment.all_objects.filter(club=ctx.club, session=session, membership=ctx.debtor).exists()
    with pytest.raises(services.PlayerNotEligibleError):
        services.assign_team(session=session, membership=ctx.debtor, team=TeamAssignment.Team.A, assigned_by=ctx.coach.user)


def test_pending_membership_cannot_be_assigned(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.pending_member, arrived_at=_at(session, 7, 40), marked_by=ctx.coach.user)
    with pytest.raises(services.PlayerNotEligibleError):
        services.assign_team(session=session, membership=ctx.pending_member, team=TeamAssignment.Team.A, assigned_by=ctx.coach.user)


def test_unassigned_zone_has_two_distinct_categories(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 8, 15), marked_by=ctx.coach.user)  # retard
    services.mark_arrival(session=session, membership=ctx.debtor, arrived_at=_at(session, 7, 40), marked_by=ctx.coach.user)  # présent, en dette

    groups = services.get_unassigned_players(session, actor=ctx.coach.user)
    to_place_ids = {m.pk for m, _a in groups.to_place_manually}
    cannot_play_ids = {m.pk for m, _p in groups.cannot_play}

    assert to_place_ids == {ctx.player.pk}
    assert cannot_play_ids == {ctx.debtor.pk}
    # Jamais dans les deux catégories à la fois.
    assert to_place_ids.isdisjoint(cannot_play_ids)


def test_player_late_and_ineligible_only_in_cannot_play(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.debtor, arrived_at=_at(session, 8, 15), marked_by=ctx.coach.user)  # retard + dette

    groups = services.get_unassigned_players(session, actor=ctx.coach.user)
    assert {m.pk for m, _p in groups.cannot_play} == {ctx.debtor.pk}
    assert {m.pk for m, _a in groups.to_place_manually} == set()


def test_regularized_present_player_joins_team_automatically(ctx, monkeypatch):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.debtor, arrived_at=_at(session, 7, 40), marked_by=ctx.coach.user)
    assert not TeamAssignment.all_objects.filter(club=ctx.club, session=session, membership=ctx.debtor).exists()

    # Régularisation simulée (paiement validé en Caisse Terrain Express) :
    # on ne recrée pas ici tout le mécanisme de paiement de
    # `finance-engine` (hors périmètre de ce module), on simule seulement
    # son effet observable — `is_in_good_standing` redevient vrai.
    import apps.treasury.services as treasury_services

    monkeypatch.setattr(
        treasury_services, "is_in_good_standing", lambda membership, at_date=None: (True, 0, "Le joueur est en ordre.")
    )

    services.sync_pending_regularizations(session, actor=ctx.coach.user)
    assert TeamAssignment.all_objects.filter(club=ctx.club, session=session, membership=ctx.debtor).exists()


def test_correct_arrival_time_reserved_to_coach(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    attendance = services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 7, 40), marked_by=ctx.coach.user)
    with pytest.raises(services.SportPermissionError):
        services.correct_arrival_time(attendance=attendance, new_arrived_at=_at(session, 8, 20), actor=ctx.president.user)


def test_correct_arrival_time_to_late_removes_team_assignment(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    attendance = services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 7, 40), marked_by=ctx.coach.user)
    assert TeamAssignment.all_objects.filter(club=ctx.club, session=session, membership=ctx.player).exists()

    services.correct_arrival_time(attendance=attendance, new_arrived_at=_at(session, 8, 30), actor=ctx.coach.user)
    attendance.refresh_from_db()
    assert attendance.status == Attendance.Status.LATE_ABSENT
    assert not TeamAssignment.all_objects.filter(club=ctx.club, session=session, membership=ctx.player).exists()


def test_excused_absence_marks_status_and_clears_assignment(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 7, 40), marked_by=ctx.coach.user)
    attendance = services.mark_excused_absence(event=session.event, membership=ctx.player, reason="Blessé", marked_by=ctx.coach.user)
    assert attendance.status == Attendance.Status.EXCUSED_ABSENT
    assert not TeamAssignment.all_objects.filter(club=ctx.club, session=session, membership=ctx.player).exists()
