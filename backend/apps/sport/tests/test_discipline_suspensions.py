"""Discipline et suspensions automatiques (CDC 4.9 ; tâche 3.4 ; 10.2 n° 8)."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.notifications.models import Notification
from apps.sport import services
from apps.sport.models import Incident, Match, Suspension
from apps.sport.tests.factories import EventFactory, MatchFactory, SessionFactory

pytestmark = pytest.mark.django_db


def _record_yellow(ctx, event, membership=None):
    return services.record_incident(
        event=event, membership=membership or ctx.player, incident_type=Incident.IncidentType.YELLOW_CARD,
        cause=Incident.Cause.BEHAVIOUR, recorded_by=ctx.coach.user,
    )


def test_no_suspension_before_fifth_yellow(ctx):
    for _ in range(4):
        event = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season).event
        _record_yellow(ctx, event)
    assert not Suspension.all_objects.filter(club=ctx.club, membership=ctx.player).exists()
    assert services.get_playability(ctx.player).eligible is True


def test_fifth_yellow_of_season_triggers_suspension(ctx):
    for _ in range(5):
        event = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season).event
        _record_yellow(ctx, event)

    suspension = Suspension.all_objects.get(club=ctx.club, membership=ctx.player)
    assert suspension.reason == Suspension.Reason.CUMULATIVE_YELLOW
    assert suspension.matches_total == ctx.club.settings.yellow_card_suspension_matches
    assert suspension.is_active is True
    assert services.get_playability(ctx.player).eligible is False

    # Notifie le joueur et le Coach (CDC 4.9).
    assert Notification.objects.filter(
        recipient=ctx.player.user, event_type=Notification.EventType.CARD_OR_SUSPENSION
    ).exists()
    assert Notification.objects.filter(
        recipient=ctx.coach.user, event_type=Notification.EventType.CARD_OR_SUSPENSION
    ).exists()


def test_red_card_triggers_immediate_suspension(ctx):
    event = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season).event
    services.record_incident(
        event=event, membership=ctx.player, incident_type=Incident.IncidentType.RED_CARD,
        cause=Incident.Cause.SERIOUS_FOUL, recorded_by=ctx.coach.user,
    )
    suspension = Suspension.all_objects.get(club=ctx.club, membership=ctx.player)
    assert suspension.reason == Suspension.Reason.RED_CARD
    assert suspension.matches_total == ctx.club.settings.red_card_suspension_matches


def test_suspension_reset_by_season(ctx):
    """Le comptage des jaunes est scopé par ``Season`` : une nouvelle saison
    remet le compteur à zéro (10.2 n° 8)."""

    from apps.clubs.tests.factories import SeasonFactory

    for _ in range(4):
        event = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season).event
        _record_yellow(ctx, event)

    next_season = SeasonFactory(
        club=ctx.club, start_date=ctx.season.end_date + datetime.timedelta(days=1),
        end_date=ctx.season.end_date + datetime.timedelta(days=365),
    )
    new_season_event = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=next_season, event__event_date=next_season.start_date
    ).event
    _record_yellow(ctx, new_season_event)  # 5e jaune "toutes saisons confondues", mais 1er de la nouvelle saison

    assert not Suspension.all_objects.filter(club=ctx.club, membership=ctx.player).exists()


def test_advance_suspensions_increments_and_lifts(ctx):
    # Les cartons se saisissent le jour même (événement non verrouillé,
    # CDC 4.7) : on ne recule jamais la date d'un événement pour ce test.
    # C'est l'instant transmis à la commande cron (``now``) qui avance,
    # pas la date de déclenchement — même principe que les commandes cron
    # de apps.treasury (ex. test_cron_tache_2_3.py).
    today = timezone.now().date()
    for _ in range(5):
        event = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=today).event
        _record_yellow(ctx, event)
    suspension = Suspension.all_objects.get(club=ctx.club, membership=ctx.player)
    assert suspension.matches_total == 1
    assert suspension.starts_event.event_date == today

    # Match postérieur au déclenchement (today), que l'on considère
    # « écoulé » au moment où la commande cron tourne (now = today + 3 j).
    services.create_match(
        club=ctx.club, season=ctx.season, event_date=today + datetime.timedelta(days=1),
        kickoff_time=datetime.time(15, 0), match_type=Match.MatchType.FRIENDLY, venue=Match.Venue.HOME,
        created_by=ctx.coach.user, opponent_name="FC Test",
    )

    cron_now = timezone.now() + datetime.timedelta(days=3)
    credited = services.advance_suspensions_for_elapsed_matches(club=ctx.club, now=cron_now)
    assert credited == 1

    suspension.refresh_from_db()
    assert suspension.matches_served == 1
    assert suspension.lifted_at is not None
    assert suspension.is_active is False
    assert services.get_playability(ctx.player).eligible is True


def test_advance_suspensions_is_idempotent(ctx):
    today = timezone.now().date()
    event = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=today).event
    services.record_incident(
        event=event, membership=ctx.player, incident_type=Incident.IncidentType.RED_CARD,
        cause=Incident.Cause.SERIOUS_FOUL, recorded_by=ctx.coach.user,
    )
    services.create_match(
        club=ctx.club, season=ctx.season, event_date=today + datetime.timedelta(days=1),
        kickoff_time=datetime.time(15, 0), match_type=Match.MatchType.FRIENDLY, venue=Match.Venue.HOME,
        created_by=ctx.coach.user, opponent_name="FC Test",
    )

    cron_now = timezone.now() + datetime.timedelta(days=3)
    first_run = services.advance_suspensions_for_elapsed_matches(club=ctx.club, now=cron_now)
    second_run = services.advance_suspensions_for_elapsed_matches(club=ctx.club, now=cron_now)
    assert first_run == 1
    assert second_run == 0  # le même match ne compte jamais deux fois


def test_advance_suspensions_ignores_matches_before_trigger(ctx):
    """Un match déjà joué avant le carton ne doit jamais compter comme purgé."""

    old_match = services.create_match(
        club=ctx.club, season=ctx.season, event_date=timezone.now().date() - datetime.timedelta(days=10),
        kickoff_time=datetime.time(15, 0), match_type=Match.MatchType.FRIENDLY, venue=Match.Venue.HOME,
        created_by=ctx.coach.user, opponent_name="FC Ancien",
    )
    event = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season).event
    services.record_incident(
        event=event, membership=ctx.player, incident_type=Incident.IncidentType.RED_CARD,
        cause=Incident.Cause.SERIOUS_FOUL, recorded_by=ctx.coach.user,
    )
    credited = services.advance_suspensions_for_elapsed_matches(club=ctx.club)
    assert credited == 0
    suspension = Suspension.all_objects.get(club=ctx.club, membership=ctx.player)
    assert suspension.matches_served == 0
