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
from apps.sport.tests.factories import SessionFactory

pytestmark = pytest.mark.django_db


def test_no_event_today_returns_empty_locker_room(ctx):
    response = client_for(ctx.player.user).get(reverse("sport:locker-room"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["session"] is None
    assert response.data["match"] is None


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
