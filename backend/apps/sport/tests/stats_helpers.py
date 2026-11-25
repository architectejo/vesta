"""Aides communes aux tests des statistiques de séance et des tests de
performance. Les données sont créées directement (sans passer par les
services de pointage) pour pouvoir fabriquer des séances passées."""

from __future__ import annotations

import datetime
from decimal import Decimal

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.models import Membership
from apps.sport import services
from apps.sport.models import Attendance, Evaluation
from apps.sport.tests.conftest import make_member
from apps.sport.tests.factories import SessionFactory


def club_today(ctx):
    return services.get_club_today(ctx.club)


def backdate_members(ctx, days: int = 200) -> None:
    Membership.all_objects.filter(club=ctx.club).update(joined_on=club_today(ctx) - datetime.timedelta(days=days))


def make_session(ctx, *, days_ago: int = 0):
    event_date = club_today(ctx) - datetime.timedelta(days=days_ago)
    return SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=event_date
    )


def point(ctx, session, membership, *, status=Attendance.Status.PRESENT, reason=""):
    """Crée un pointage directement (présent à 07:40, en retard à 08:30)."""

    tz = services._club_tz(services._club_settings(ctx.club))
    arrived_at = None
    if status == Attendance.Status.PRESENT:
        arrived_at = datetime.datetime.combine(session.event.event_date, datetime.time(7, 40), tzinfo=tz)
    elif status == Attendance.Status.LATE_ABSENT:
        arrived_at = datetime.datetime.combine(session.event.event_date, datetime.time(8, 30), tzinfo=tz)
    return Attendance.all_objects.create(
        club=ctx.club, event=session.event, membership=membership, status=status, arrived_at=arrived_at,
        excused_reason=reason, marked_by=SuperuserFactory(),
    )


def evaluate(ctx, session, membership, score, *, evaluator=None, comment="", visible=False, **criteria):
    return Evaluation.all_objects.create(
        club=ctx.club, event=session.event, membership=membership, evaluator=evaluator or ctx.coach.user,
        overall_score=Decimal(str(score)), comment=comment, comment_visible_to_player=visible, **criteria,
    )


def extra_players(ctx, count: int):
    return [make_member(ctx.club) for _ in range(count)]


def pointed_session(ctx, *members, days_ago: int = 0):
    session = make_session(ctx, days_ago=days_ago)
    for membership in members:
        point(ctx, session, membership)
    return session
