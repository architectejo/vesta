"""`apps.sport.services.get_next_upcoming_event` (complément sport-vestiaire.md
§6, ligne « Aucun événement aujourd'hui » ; club-accueil.md §4 point 5).

Couvre le constat de la tâche : l'API ne renvoyait jamais la précision
« Prochain rendez-vous » quand aucun événement n'a lieu exactement
aujourd'hui, ce qui est la situation normale la plupart des jours."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.sport import services
from apps.sport.tests.factories import MatchFactory, SessionFactory

pytestmark = pytest.mark.django_db


def test_no_future_event_returns_none(ctx):
    assert services.get_next_upcoming_event(ctx.club) is None


def test_past_or_today_events_are_ignored(ctx):
    today = services.get_club_today(ctx.club)
    SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=today)
    MatchFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        event__event_date=today - datetime.timedelta(days=1),
    )

    assert services.get_next_upcoming_event(ctx.club) is None


def test_future_session_only(ctx):
    today = services.get_club_today(ctx.club)
    session = SessionFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        event__event_date=today + datetime.timedelta(days=5),
    )

    result = services.get_next_upcoming_event(ctx.club)

    assert result is not None
    assert result.pk == session.pk
    assert isinstance(result, type(session))


def test_future_match_only(ctx):
    today = services.get_club_today(ctx.club)
    match = MatchFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        event__event_date=today + datetime.timedelta(days=3),
    )

    result = services.get_next_upcoming_event(ctx.club)

    assert result is not None
    assert result.pk == match.pk


def test_closest_event_wins_between_session_and_match(ctx):
    today = services.get_club_today(ctx.club)
    far_session = SessionFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        event__event_date=today + datetime.timedelta(days=10),
    )
    close_match = MatchFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        event__event_date=today + datetime.timedelta(days=2),
    )

    result = services.get_next_upcoming_event(ctx.club)

    assert result is not None
    assert result.pk == close_match.pk
    assert far_session.pk != result.pk


def test_session_wins_tie_on_same_future_date(ctx):
    """Critère de départage non tranché par le CDC (décision par défaut
    signalée au compte rendu) : à date égale, la séance l'emporte."""

    today = services.get_club_today(ctx.club)
    same_date = today + datetime.timedelta(days=4)
    session = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=same_date
    )
    MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=same_date)

    result = services.get_next_upcoming_event(ctx.club)

    assert result is not None
    assert result.pk == session.pk
