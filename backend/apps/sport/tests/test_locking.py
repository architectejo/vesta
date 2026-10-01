"""Verrouillage a minuit des seances/matchs (CDC 4.7 ; tache 3.3)."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.sport import services
from apps.sport.models import Event
from apps.sport.tests.factories import EventFactory, SessionFactory

pytestmark = pytest.mark.django_db


def test_event_today_is_not_locked(ctx):
    event = EventFactory(club=ctx.club, season=ctx.season, event_date=timezone.now().date())
    assert services.is_event_locked(event) is False


def test_event_yesterday_is_locked(ctx):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    event = EventFactory(club=ctx.club, season=ctx.season, event_date=yesterday)
    assert services.is_event_locked(event) is True


def test_writable_check_raises_for_locked_event(ctx):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday)
    with pytest.raises(services.EventLockedError):
        services.mark_arrival(
            session=session, membership=ctx.player, arrived_at=timezone.now(), marked_by=ctx.coach.user
        )


def test_superuser_bypasses_lock(ctx, django_user_model=None):
    from apps.accounts.tests.factories import SuperuserFactory

    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday)
    superuser = SuperuserFactory()
    # Un Superuser n'est jamais bloqué par ensure_event_writable (CDC 4.7).
    services.ensure_event_writable(session.event, actor=superuser)


def test_unlock_event_requires_superuser(ctx):
    from apps.accounts.tests.factories import SuperuserFactory

    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    event = EventFactory(club=ctx.club, season=ctx.season, event_date=yesterday)
    with pytest.raises(services.SportPermissionError):
        services.unlock_event(event, superuser=ctx.president.user, reason="Correction demandée")


def test_unlock_event_requires_reason(ctx):
    from apps.accounts.tests.factories import SuperuserFactory

    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    event = EventFactory(club=ctx.club, season=ctx.season, event_date=yesterday)
    superuser = SuperuserFactory()
    with pytest.raises(services.SportValidationError):
        services.unlock_event(event, superuser=superuser, reason="   ")


def test_unlock_event_is_journalized_and_reopens_writes(ctx):
    from apps.accounts.tests.factories import SuperuserFactory

    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday)
    superuser = SuperuserFactory()

    services.unlock_event(session.event, superuser=superuser, reason="Correction du pointage sur demande du Président")

    session.event.refresh_from_db()
    assert services.is_event_locked(session.event) is False

    entry = AuditLog.objects.filter(action_type="sport.event_unlocked", object_id=str(session.event.pk)).first()
    assert entry is not None
    assert entry.actor_id == superuser.id
    assert entry.after["unlock_reason"]

    # L'evenement redevient effectivement modifiable.
    attendance = services.mark_arrival(
        session=session, membership=ctx.player, arrived_at=timezone.now(), marked_by=superuser
    )
    assert attendance.pk is not None
