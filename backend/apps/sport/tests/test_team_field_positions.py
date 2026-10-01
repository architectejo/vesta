"""Formation par équipe et placement terrain/banc (extension client du
30/09/2026, hors CDC écrit à ce jour -- comparable par sa nature aux
extensions actées au 10.2 comme le n° 24 ; voir le compte rendu de cette
tâche). Complète ``test_attendance_and_teams.py`` (:func:`assign_team`)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.sport import services
from apps.sport.models import Formation, TacticalPlan, TeamAssignment
from apps.sport.tests.conftest import make_debtor, make_member
from apps.sport.tests.factories import SessionFactory

pytestmark = pytest.mark.django_db


def _at(session, hour, minute):
    tz = services._club_tz(services._club_settings(session.club))
    return datetime.datetime.combine(session.event.event_date, datetime.time(hour, minute), tzinfo=tz)


def _assign(session, membership, team, *, actor):
    services.mark_arrival(session=session, membership=membership, arrived_at=_at(session, 7, 40), marked_by=actor)
    return services.assign_team(session=session, membership=membership, team=team, assigned_by=actor)


# ---------------------------------------------------------------------------
# Bibliothèque de formations partagée avec le plan tactique (pas de
# duplication du TextChoices).
# ---------------------------------------------------------------------------


def test_formation_enum_shared_with_tactical_plan():
    assert TacticalPlan.Formation is Formation


# ---------------------------------------------------------------------------
# set_team_formation
# ---------------------------------------------------------------------------


def test_coach_sets_independent_formations_per_team(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)

    services.set_team_formation(
        session=session, team=TeamAssignment.Team.A, formation=Formation.F_4_4_2, actor=ctx.coach.user
    )
    services.set_team_formation(
        session=session, team=TeamAssignment.Team.B, formation=Formation.F_4_3_3, actor=ctx.coach.user
    )

    session.refresh_from_db()
    assert session.team_a_formation == Formation.F_4_4_2
    assert session.team_b_formation == Formation.F_4_3_3


def test_president_and_captain_can_also_set_formation(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)

    services.set_team_formation(
        session=session, team=TeamAssignment.Team.A, formation=Formation.F_3_5_2, actor=ctx.president.user
    )
    services.set_team_formation(
        session=session, team=TeamAssignment.Team.B, formation=Formation.F_5_3_2, actor=ctx.captain.user
    )
    session.refresh_from_db()
    assert session.team_a_formation == Formation.F_3_5_2
    assert session.team_b_formation == Formation.F_5_3_2


def test_set_team_formation_forbidden_to_plain_player(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    with pytest.raises(services.SportPermissionError):
        services.set_team_formation(
            session=session, team=TeamAssignment.Team.A, formation=Formation.F_4_4_2, actor=ctx.player.user
        )


def test_set_team_formation_invalid_team_rejected(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    with pytest.raises(services.SportValidationError):
        services.set_team_formation(session=session, team="Z", formation=Formation.F_4_4_2, actor=ctx.coach.user)


def test_set_team_formation_is_logged(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.set_team_formation(
        session=session, team=TeamAssignment.Team.A, formation=Formation.F_4_2_3_1, actor=ctx.coach.user
    )
    assert AuditLog.objects.filter(
        action_type="sport.session_team_formation_set", object_id=str(session.pk)
    ).exists()


def test_set_team_formation_blocked_on_locked_session(ctx):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    session = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday
    )
    with pytest.raises(services.EventLockedError):
        services.set_team_formation(
            session=session, team=TeamAssignment.Team.A, formation=Formation.F_4_4_2, actor=ctx.coach.user
        )


# ---------------------------------------------------------------------------
# place_team_player : cas nominaux
# ---------------------------------------------------------------------------


def test_place_eligible_assigned_player_on_field(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)

    assignment = services.place_team_player(
        session=session, team=TeamAssignment.Team.A, membership=ctx.player,
        x_coord=Decimal("50.00"), y_coord=Decimal("80.00"), actor=ctx.coach.user,
    )
    assert assignment.is_on_field is True
    assert assignment.x_coord == Decimal("50.00")
    assert assignment.y_coord == Decimal("80.00")


def test_place_team_player_is_logged(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)

    assignment = services.place_team_player(
        session=session, team=TeamAssignment.Team.A, membership=ctx.player,
        x_coord=Decimal("50"), y_coord=Decimal("80"), actor=ctx.coach.user,
    )
    assert AuditLog.objects.filter(
        action_type="sport.team_assignment_placed", object_id=str(assignment.pk)
    ).exists()


def test_player_not_assigned_to_team_cannot_be_placed(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    # Pointé en retard (jamais réparti automatiquement, 10.2 n° 38) et
    # jamais réparti manuellement non plus via assign_team.
    services.mark_arrival(session=session, membership=ctx.player, arrived_at=_at(session, 8, 15), marked_by=ctx.coach.user)
    assert not TeamAssignment.all_objects.filter(club=ctx.club, session=session, membership=ctx.player).exists()

    with pytest.raises(services.SportValidationError):
        services.place_team_player(
            session=session, team=TeamAssignment.Team.A, membership=ctx.player,
            x_coord=Decimal("50"), y_coord=Decimal("80"), actor=ctx.coach.user,
        )


def test_send_player_back_to_bench_clears_coordinates(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)
    services.place_team_player(
        session=session, team=TeamAssignment.Team.A, membership=ctx.player,
        x_coord=Decimal("50"), y_coord=Decimal("80"), actor=ctx.coach.user,
    )

    assignment = services.place_team_player(
        session=session, team=TeamAssignment.Team.A, membership=ctx.player,
        x_coord=None, y_coord=None, actor=ctx.coach.user,
    )
    assert assignment.is_on_field is False
    assert assignment.x_coord is None
    assert assignment.y_coord is None


def test_place_team_player_requires_both_coordinates_or_neither(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)

    with pytest.raises(services.SportValidationError):
        services.place_team_player(
            session=session, team=TeamAssignment.Team.A, membership=ctx.player,
            x_coord=Decimal("50"), y_coord=None, actor=ctx.coach.user,
        )


# ---------------------------------------------------------------------------
# Plafond à 11 et échange de place
# ---------------------------------------------------------------------------


def _fill_field_with_eleven(ctx, session):
    """Place 11 joueurs distincts sur le terrain de l'équipe A, chacun sur
    une case différente."""

    members = [make_member(ctx.club) for _ in range(11)]
    for index, member in enumerate(members):
        _assign(session, member, TeamAssignment.Team.A, actor=ctx.coach.user)
        services.place_team_player(
            session=session, team=TeamAssignment.Team.A, membership=member,
            x_coord=Decimal(index * 5), y_coord=Decimal(10), actor=ctx.coach.user,
        )
    return members


def test_twelfth_player_on_empty_cell_is_refused(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _fill_field_with_eleven(ctx, session)

    twelfth = make_member(ctx.club)
    _assign(session, twelfth, TeamAssignment.Team.A, actor=ctx.coach.user)

    with pytest.raises(services.SportValidationError):
        services.place_team_player(
            session=session, team=TeamAssignment.Team.A, membership=twelfth,
            x_coord=Decimal("99"), y_coord=Decimal("99"), actor=ctx.coach.user,
        )
    assert TeamAssignment.all_objects.get(club=ctx.club, session=session, membership=twelfth).is_on_field is False


def test_twelfth_player_on_occupied_cell_swaps_places(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    eleven = _fill_field_with_eleven(ctx, session)
    occupant = eleven[0]
    occupant_assignment = TeamAssignment.all_objects.get(club=ctx.club, session=session, membership=occupant)
    occupied_x, occupied_y = occupant_assignment.x_coord, occupant_assignment.y_coord

    twelfth = make_member(ctx.club)
    _assign(session, twelfth, TeamAssignment.Team.A, actor=ctx.coach.user)

    new_assignment = services.place_team_player(
        session=session, team=TeamAssignment.Team.A, membership=twelfth,
        x_coord=occupied_x, y_coord=occupied_y, actor=ctx.coach.user,
    )
    occupant_assignment.refresh_from_db()

    assert new_assignment.is_on_field is True
    assert (new_assignment.x_coord, new_assignment.y_coord) == (occupied_x, occupied_y)
    assert occupant_assignment.is_on_field is False
    assert occupant_assignment.x_coord is None
    assert occupant_assignment.y_coord is None

    # Toujours 11 joueurs sur le terrain, jamais 12 (pas de dépassement).
    on_field_count = TeamAssignment.all_objects.filter(
        club=ctx.club, session=session, team=TeamAssignment.Team.A, is_on_field=True
    ).count()
    assert on_field_count == 11


def test_swap_logs_both_players(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    eleven = _fill_field_with_eleven(ctx, session)
    occupant = eleven[0]
    occupant_assignment = TeamAssignment.all_objects.get(club=ctx.club, session=session, membership=occupant)

    twelfth = make_member(ctx.club)
    _assign(session, twelfth, TeamAssignment.Team.A, actor=ctx.coach.user)
    services.place_team_player(
        session=session, team=TeamAssignment.Team.A, membership=twelfth,
        x_coord=occupant_assignment.x_coord, y_coord=occupant_assignment.y_coord, actor=ctx.coach.user,
    )

    assert AuditLog.objects.filter(
        action_type="sport.team_assignment_benched", object_id=str(occupant_assignment.pk)
    ).exists()


def test_teams_a_and_b_caps_are_independent(ctx):
    """11 joueurs sur le terrain en équipe A n'empêche pas de placer un
    joueur en équipe B (chaque équipe a son propre plafond)."""

    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _fill_field_with_eleven(ctx, session)

    b_player = make_member(ctx.club)
    _assign(session, b_player, TeamAssignment.Team.B, actor=ctx.coach.user)
    assignment = services.place_team_player(
        session=session, team=TeamAssignment.Team.B, membership=b_player,
        x_coord=Decimal("50"), y_coord=Decimal("50"), actor=ctx.coach.user,
    )
    assert assignment.is_on_field is True


# ---------------------------------------------------------------------------
# Éligibilité (CLAUDE.md règle n° 5) et permissions
# ---------------------------------------------------------------------------


def test_debtor_cannot_be_placed_on_field_even_if_already_assigned(ctx):
    """``assign_team`` bloque déjà un débiteur à la répartition elle-même
    (CLAUDE.md règle n° 5) : pour vérifier que ``place_team_player``
    applique bien son propre contrôle (défense en profondeur), on
    simule ici une ligne déjà existante (ex. créée avant l'apparition de
    la dette), en contournant volontairement ``assign_team``."""

    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    TeamAssignment.all_objects.create(
        club=ctx.club, session=session, membership=ctx.debtor, team=TeamAssignment.Team.A,
        arrival_order=1, assigned_by=ctx.coach.user,
    )

    with pytest.raises(services.PlayerNotEligibleError):
        services.place_team_player(
            session=session, team=TeamAssignment.Team.A, membership=ctx.debtor,
            x_coord=Decimal("50"), y_coord=Decimal("50"), actor=ctx.coach.user,
        )


def test_player_who_becomes_debtor_after_assignment_cannot_be_placed(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)
    make_debtor(ctx.club, ctx.player)

    with pytest.raises(services.PlayerNotEligibleError):
        services.place_team_player(
            session=session, team=TeamAssignment.Team.A, membership=ctx.player,
            x_coord=Decimal("50"), y_coord=Decimal("50"), actor=ctx.coach.user,
        )


def test_place_team_player_forbidden_to_plain_player(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    _assign(session, ctx.player, TeamAssignment.Team.A, actor=ctx.coach.user)

    other = make_member(ctx.club)
    with pytest.raises(services.SportPermissionError):
        services.place_team_player(
            session=session, team=TeamAssignment.Team.A, membership=ctx.player,
            x_coord=Decimal("50"), y_coord=Decimal("50"), actor=other.user,
        )


def test_place_team_player_blocked_on_locked_session(ctx):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    session = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday
    )
    # On force la répartition directement (assign_team est aussi verrouillé) pour
    # isoler le test sur le verrouillage de place_team_player lui-même.
    TeamAssignment.all_objects.create(
        club=ctx.club, session=session, membership=ctx.player, team=TeamAssignment.Team.A,
        arrival_order=1, assigned_by=ctx.coach.user,
    )
    with pytest.raises(services.EventLockedError):
        services.place_team_player(
            session=session, team=TeamAssignment.Team.A, membership=ctx.player,
            x_coord=Decimal("50"), y_coord=Decimal("50"), actor=ctx.coach.user,
        )


# ---------------------------------------------------------------------------
# Étanchéité multi-club (CLAUDE.md règle n° 8)
# ---------------------------------------------------------------------------


def test_cannot_place_a_player_from_another_club(ctx, other_ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    with pytest.raises(Exception):
        services.place_team_player(
            session=session, team=TeamAssignment.Team.A, membership=other_ctx.player,
            x_coord=Decimal("50"), y_coord=Decimal("50"), actor=ctx.coach.user,
        )


def test_team_formations_do_not_leak_across_clubs(ctx, other_ctx):
    session_a = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    session_b = SessionFactory(club=other_ctx.club, event__club=other_ctx.club, event__season=other_ctx.season)

    services.set_team_formation(
        session=session_a, team=TeamAssignment.Team.A, formation=Formation.F_4_4_2, actor=ctx.coach.user
    )
    services.set_team_formation(
        session=session_b, team=TeamAssignment.Team.A, formation=Formation.F_3_4_3, actor=other_ctx.coach.user
    )

    session_a.refresh_from_db()
    session_b.refresh_from_db()
    assert session_a.team_a_formation == Formation.F_4_4_2
    assert session_b.team_a_formation == Formation.F_3_4_3
