"""Évaluations des performances (CDC 4.10)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone as django_timezone

from apps.sport import services
from apps.sport.models import Attendance
from apps.sport.tests.factories import SessionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def set_now(monkeypatch):
    """Fige ``django.utils.timezone.now`` (même convention que
    apps.treasury.tests.expense_review_helpers)."""

    def _set(moment: datetime.datetime):
        assert moment.tzinfo is not None
        monkeypatch.setattr(django_timezone, "now", lambda: moment)

    return _set


def _present_session(ctx, membership):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    tz = services._club_tz(services._club_settings(ctx.club))
    arrived_at = datetime.datetime.combine(session.event.event_date, datetime.time(7, 40), tzinfo=tz)
    services.mark_arrival(session=session, membership=membership, arrived_at=arrived_at, marked_by=ctx.coach.user)
    return session


def test_evaluation_within_window_succeeds(ctx):
    session = _present_session(ctx, ctx.player)
    evaluation = services.submit_evaluation(
        event=session.event, membership=ctx.player, evaluator=ctx.coach.user, overall_score=Decimal("8.0")
    )
    assert evaluation.overall_score == Decimal("8.0")


def test_evaluation_of_absent_player_is_refused(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    with pytest.raises(services.SportValidationError):
        services.submit_evaluation(
            event=session.event, membership=ctx.player, evaluator=ctx.coach.user, overall_score=Decimal("7.0")
        )


def test_evaluation_locked_after_48h(ctx, set_now):
    session = _present_session(ctx, ctx.player)
    locks_at = services.evaluation_locks_at(session.event)
    set_now(locks_at + datetime.timedelta(minutes=1))
    with pytest.raises(services.SportValidationError):
        services.submit_evaluation(
            event=session.event, membership=ctx.player, evaluator=ctx.coach.user, overall_score=Decimal("6.0")
        )


def test_evaluation_still_possible_just_before_lock(ctx, set_now):
    session = _present_session(ctx, ctx.player)
    locks_at = services.evaluation_locks_at(session.event)
    set_now(locks_at - datetime.timedelta(minutes=1))
    evaluation = services.submit_evaluation(
        event=session.event, membership=ctx.player, evaluator=ctx.coach.user, overall_score=Decimal("6.0")
    )
    assert evaluation.pk is not None


def test_average_score_from_multiple_evaluators_is_computed_not_stored(ctx):
    session = _present_session(ctx, ctx.player)
    services.submit_evaluation(event=session.event, membership=ctx.player, evaluator=ctx.coach.user, overall_score=Decimal("6.0"))
    services.submit_evaluation(event=session.event, membership=ctx.player, evaluator=ctx.president.user, overall_score=Decimal("8.0"))

    average = services.get_average_evaluation(session.event, ctx.player)
    assert average == Decimal("7.0")


def test_same_evaluator_updates_existing_evaluation(ctx):
    session = _present_session(ctx, ctx.player)
    services.submit_evaluation(event=session.event, membership=ctx.player, evaluator=ctx.coach.user, overall_score=Decimal("5.0"))
    services.submit_evaluation(event=session.event, membership=ctx.player, evaluator=ctx.coach.user, overall_score=Decimal("9.0"))

    from apps.sport.models import Evaluation

    assert Evaluation.all_objects.filter(club=ctx.club, event=session.event, membership=ctx.player, evaluator=ctx.coach.user).count() == 1
    assert services.get_average_evaluation(session.event, ctx.player) == Decimal("9.0")
