"""Vue « Vestiaire du jour » (tâche 3.6 : sport-vestiaire.md) : lecture
seule pure, agrège la séance/le match du jour et applique le même
filtrage de motif par rôle (10.2 n° 16) que la page Séance."""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.sport import services
from apps.sport.tests.conftest import client_for
from apps.sport.tests.factories import MatchFactory, SessionFactory

pytestmark = pytest.mark.django_db


def test_no_event_today_returns_empty_locker_room(ctx):
    response = client_for(ctx.player.user).get(reverse("sport:locker-room"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["session"] is None
    assert response.data["match"] is None
    assert response.data["next_event"] is None


def test_no_event_today_exposes_next_upcoming_session(ctx):
    """sport-vestiaire.md §6 : « Prochain rendez-vous : {Séance · dimanche
    4 octobre · 07:30} » si l'API en renvoie un -- régression du constat
    initial de la tâche (l'API ne renvoyait jamais cette précision)."""

    today = services.get_club_today(ctx.club)
    session = SessionFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        event__event_date=today + datetime.timedelta(days=4),
        gathering_time=datetime.time(7, 30),
    )

    response = client_for(ctx.player.user).get(reverse("sport:locker-room"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["session"] is None
    assert response.data["match"] is None
    assert response.data["next_event"] == {
        "type": "session",
        "id": session.event_id,
        "event_date": session.event.event_date,
        "gathering_time": datetime.time(7, 30),
        "location": session.location,
    }


def test_no_event_today_exposes_next_upcoming_match(ctx):
    today = services.get_club_today(ctx.club)
    match = MatchFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        event__event_date=today + datetime.timedelta(days=2),
        kickoff_time=datetime.time(15, 0),
    )

    response = client_for(ctx.player.user).get(reverse("sport:locker-room"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["next_event"]["type"] == "match"
    assert response.data["next_event"]["id"] == match.event_id
    assert response.data["next_event"]["kickoff_time"] == datetime.time(15, 0)


def test_next_event_is_absent_when_an_event_happens_today(ctx):
    """Le champ ne doit JAMAIS apparaître quand l'événement du jour n'est
    pas vide (``session``/``match`` déjà renseignés) : ne pas alourdir ce
    cas, demande explicite de la tâche."""

    today = services.get_club_today(ctx.club)
    SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=today)
    MatchFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        event__event_date=today + datetime.timedelta(days=3),
    )

    response = client_for(ctx.player.user).get(reverse("sport:locker-room"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["session"] is not None
    assert response.data["next_event"] is None


def test_locker_room_reflects_todays_session_and_own_situation(ctx):
    session = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=timezone.now().date()
    )
    tz = services._club_tz(services._club_settings(ctx.club))
    arrived_at = datetime.datetime.combine(session.event.event_date, datetime.time(7, 40), tzinfo=tz)
    services.mark_arrival(session=session, membership=ctx.player, arrived_at=arrived_at, marked_by=ctx.coach.user)

    response = client_for(ctx.player.user).get(reverse("sport:locker-room"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["session"]["id"] == session.pk
    assert response.data["my_situation"]["attendance"]["status"] == "present"
    assert response.data["my_situation"]["eligible"] is True


def test_debtor_sees_own_full_reason_but_teammates_see_only_indisponible(ctx):
    session = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=timezone.now().date()
    )
    tz = services._club_tz(services._club_settings(ctx.club))
    arrived_at = datetime.datetime.combine(session.event.event_date, datetime.time(7, 40), tzinfo=tz)
    services.mark_arrival(session=session, membership=ctx.debtor, arrived_at=arrived_at, marked_by=ctx.coach.user)

    as_debtor = client_for(ctx.debtor.user).get(reverse("sport:locker-room"))
    assert as_debtor.data["my_situation"]["eligible"] is False
    assert "dette" in as_debtor.data["my_situation"]["reason"].lower()

    as_teammate = client_for(ctx.player.user).get(reverse("sport:locker-room"))
    cannot_play = as_teammate.data["session"]["unassigned"]["cannot_play"]
    debtor_entry = next(item for item in cannot_play if item["membership_id"] == ctx.debtor.pk)
    assert debtor_entry["reason"] == "Indisponible"
