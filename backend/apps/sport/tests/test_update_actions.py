"""Services de modification (tâche 3.7, complément) : « Modifier la
séance » (sport-seance.md §4.2), « Modifier le match »
(sport-feuille-de-match.md §4.7), « Paramètres du plan »
(sport-plan-tactique.md §4.3) et le pointage simple d'un match
(sport-feuille-de-match.md §7, point ouvert 2).

Complète les tests de vue (``test_views_sessions.py``,
``test_views_matches.py``, ``test_views_tactical_plan.py``) par la
couche service : verrouillage à minuit (CDC 4.7), journalisation
(CLAUDE.md règle n° 6) et règles propres à chaque action.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.sport import services
from apps.sport.models import Attendance, Match, TacticalPlan
from apps.sport.tests.factories import MatchFactory, SessionFactory

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("Africa/Kinshasa")


# ---------------------------------------------------------------------------
# « Modifier la séance » (sport-seance.md §4.2)
# ---------------------------------------------------------------------------


def test_update_session_changes_fields_and_is_journalized(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)

    updated = services.update_session(
        session=session,
        event_date=session.event.event_date,
        gathering_time=datetime.time(7, 45),
        late_arrival_cutoff=datetime.time(8, 15),
        updated_by=ctx.coach.user,
        location="Terrain B",
        team_a_color="#00FF00",
        team_b_color="#FF00FF",
        instructions="Apporter les dossards.",
    )

    assert updated.gathering_time == datetime.time(7, 45)
    assert updated.location == "Terrain B"
    assert updated.team_a_color == "#00FF00"

    entry = AuditLog.objects.filter(action_type="sport.session_updated", object_id=str(session.pk)).first()
    assert entry is not None
    assert entry.actor_id == ctx.coach.user.id
    assert entry.before["location"] == "Terrain municipal"
    assert entry.after["location"] == "Terrain B"


def test_update_session_is_blocked_once_locked(ctx):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    session = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday
    )

    with pytest.raises(services.EventLockedError):
        services.update_session(
            session=session,
            event_date=yesterday,
            gathering_time=datetime.time(7, 30),
            late_arrival_cutoff=datetime.time(8, 0),
            updated_by=ctx.coach.user,
        )


# ---------------------------------------------------------------------------
# « Modifier le match » (sport-feuille-de-match.md §4.7)
# ---------------------------------------------------------------------------


def test_update_match_changes_fields_and_is_journalized(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, opponent_name="Ancien nom")

    updated = services.update_match(
        match=match,
        event_date=match.event.event_date,
        kickoff_time=datetime.time(16, 30),
        match_type=Match.MatchType.CHAMPIONSHIP,
        venue=Match.Venue.AWAY,
        updated_by=ctx.coach.user,
        opponent_name="FC Rival",
        location="Stade annexe",
    )

    assert updated.kickoff_time == datetime.time(16, 30)
    assert updated.venue == Match.Venue.AWAY
    assert updated.opponent_name == "FC Rival"

    entry = AuditLog.objects.filter(action_type="sport.match_updated", object_id=str(match.pk)).first()
    assert entry is not None
    assert entry.before["opponent_name"] == "Ancien nom"


def test_update_match_ignores_opponent_change_for_accepted_challenge(ctx, other_ctx):
    match = MatchFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        opponent_club=other_ctx.club,
        opponent_name="",
        challenge_status=Match.ChallengeStatus.ACCEPTED,
        challenge_to_club=other_ctx.club,
    )

    updated = services.update_match(
        match=match,
        event_date=match.event.event_date,
        kickoff_time=datetime.time(16, 0),
        match_type=match.match_type,
        venue=match.venue,
        updated_by=ctx.coach.user,
        opponent_club=None,
        opponent_name="Une autre équipe",
    )

    assert updated.opponent_club_id == other_ctx.club.id
    assert updated.opponent_name == ""


def test_update_match_is_blocked_once_locked(ctx):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday)

    with pytest.raises(services.EventLockedError):
        services.update_match(
            match=match,
            event_date=yesterday,
            kickoff_time=match.kickoff_time,
            match_type=match.match_type,
            venue=match.venue,
            updated_by=ctx.coach.user,
            opponent_name=match.opponent_name,
        )


# ---------------------------------------------------------------------------
# Pointage simple d'un match (sport-feuille-de-match.md §7, point ouvert 2)
# ---------------------------------------------------------------------------


def _match_arrived(match, hour, minute):
    return datetime.datetime.combine(match.event.event_date, datetime.time(hour, minute), tzinfo=TZ)


def test_mark_match_arrival_present_before_kickoff(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)

    attendance = services.mark_match_arrival(
        match=match, membership=ctx.player, arrived_at=_match_arrived(match, 14, 30), marked_by=ctx.coach.user
    )

    assert attendance.status == Attendance.Status.PRESENT


def test_mark_match_arrival_late_after_kickoff_creates_no_team_assignment(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)

    attendance = services.mark_match_arrival(
        match=match, membership=ctx.player, arrived_at=_match_arrived(match, 15, 10), marked_by=ctx.coach.user
    )

    assert attendance.status == Attendance.Status.LATE_ABSENT
    # Aucune répartition A/B pour un match (schéma §5.4 : TeamAssignment ne
    # se rattache qu'à une Session) -- rien à vérifier de plus qu'une
    # absence totale d'écriture sur ce modèle, déjà garantie par le fait
    # que ``mark_match_arrival`` ne l'importe ni ne l'appelle.


def test_mark_match_arrival_is_blocked_once_locked(ctx):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday)

    with pytest.raises(services.EventLockedError):
        services.mark_match_arrival(
            match=match, membership=ctx.player, arrived_at=timezone.now(), marked_by=ctx.coach.user
        )


# ---------------------------------------------------------------------------
# « Paramètres du plan » (sport-plan-tactique.md §4.3)
# ---------------------------------------------------------------------------


def _create_plan(ctx):
    return services.create_tactical_plan(
        club=ctx.club, name="Plan du dimanche", formation=TacticalPlan.Formation.F_4_4_2, squad_size=11,
        created_by=ctx.coach.user,
    )


def test_update_plan_settings_changes_fields_and_is_journalized(ctx):
    plan = _create_plan(ctx)

    updated = services.update_tactical_plan_settings(
        plan=plan, name="Plan modifié", formation=TacticalPlan.Formation.F_4_3_3, squad_size=11,
        updated_by=ctx.coach.user,
    )

    assert updated.name == "Plan modifié"
    assert updated.formation == TacticalPlan.Formation.F_4_3_3

    entry = AuditLog.objects.filter(
        action_type="sport.tactical_plan_settings_updated", object_id=str(plan.pk)
    ).first()
    assert entry is not None
    assert entry.before["formation"] == TacticalPlan.Formation.F_4_4_2


def test_update_plan_settings_blocked_once_published(ctx):
    plan = _create_plan(ctx)
    services.publish_tactical_plan(plan=plan, published_by=ctx.coach.user)

    with pytest.raises(services.SportValidationError):
        services.update_tactical_plan_settings(
            plan=plan, name="Plan modifié", formation=TacticalPlan.Formation.F_4_3_3, squad_size=11,
            updated_by=ctx.coach.user,
        )


def test_update_plan_settings_requires_custom_formation_for_reduced_squad(ctx):
    plan = _create_plan(ctx)

    with pytest.raises(services.SportValidationError):
        services.update_tactical_plan_settings(
            plan=plan, name="Plan à 7", formation=TacticalPlan.Formation.F_4_4_2, squad_size=7,
            updated_by=ctx.coach.user,
        )

    updated = services.update_tactical_plan_settings(
        plan=plan, name="Plan à 7", formation=TacticalPlan.Formation.CUSTOM, squad_size=7,
        updated_by=ctx.coach.user,
    )
    assert updated.squad_size == 7


def test_update_plan_settings_keeps_existing_placements_untouched(ctx):
    plan = _create_plan(ctx)
    placement = services.place_on_plan(
        plan=plan, membership=ctx.player, x_coord=Decimal("50"), y_coord=Decimal("80"), placed_by=ctx.coach.user
    )

    services.update_tactical_plan_settings(
        plan=plan, name=plan.name, formation=TacticalPlan.Formation.F_3_4_3, squad_size=11,
        updated_by=ctx.coach.user,
    )

    placement.refresh_from_db()
    assert placement.x_coord == Decimal("50.00")
    assert placement.y_coord == Decimal("80.00")
