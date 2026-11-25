"""Notification « Séance ou match créé » (CDC 4.17) : tous les joueurs du
club, in-app, un envoi par joueur, jamais un autre club."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.clubs.models import Membership
from apps.notifications.models import Notification
from apps.sport import services
from apps.sport.models import Match

pytestmark = pytest.mark.django_db


def _create_session(ctx):
    return services.create_session(
        club=ctx.club, season=ctx.season, event_date=timezone.now().date(), gathering_time=datetime.time(7, 30),
        late_arrival_cutoff=datetime.time(8, 0), created_by=ctx.coach.user, location="Stade A",
    )


def _create_match(ctx):
    return services.create_match(
        club=ctx.club, season=ctx.season, event_date=timezone.now().date(), kickoff_time=datetime.time(15, 0),
        match_type=Match.MatchType.FRIENDLY, venue=Match.Venue.HOME, created_by=ctx.coach.user, opponent_name="FC Test",
    )


def _active_users(club):
    return set(Membership.all_objects.filter(club=club, status=Membership.Status.ACTIVE).values_list("user_id", flat=True))


def test_session_creation_notifies_each_active_player_once(ctx):
    session = _create_session(ctx)
    notifications = Notification.objects.filter(event_type=Notification.EventType.EVENT_CREATED)
    assert notifications.count() == len(_active_users(ctx.club))
    assert set(notifications.values_list("recipient_id", flat=True)) == _active_users(ctx.club)
    first = notifications.first()
    assert first.club_id == ctx.club.pk
    assert first.link_object_type == "Session"
    assert first.link_object_id == session.pk
    assert first.title == "Séance ou match créé"
    assert "Stade A" in first.body
    assert first.email_requested is False
    assert not notifications.filter(recipient=ctx.pending_member.user).exists()


def test_match_creation_notifies_with_match_link(ctx):
    match = _create_match(ctx)
    notifications = Notification.objects.filter(event_type=Notification.EventType.EVENT_CREATED)
    assert notifications.count() == len(_active_users(ctx.club))
    assert {n.link_object_type for n in notifications} == {"Match"}
    assert {n.link_object_id for n in notifications} == {match.pk}
    assert "FC Test" in notifications.first().body


def test_event_created_never_reaches_another_club(ctx, other_ctx):
    _create_session(ctx)
    _create_match(ctx)
    other_users = _active_users(other_ctx.club) - _active_users(ctx.club)
    assert other_users
    leaked = Notification.objects.filter(recipient_id__in=other_users) | Notification.objects.filter(club=other_ctx.club)
    assert not leaked.exists()
    assert set(Notification.objects.values_list("club_id", flat=True)) == {ctx.club.pk}
