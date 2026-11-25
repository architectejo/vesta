"""Pointage groupé (sport-pointage-selection-multiple.md ; décisions du 15/11/2026).

Heure simulée : 10:00 (fuseau du club) le jour de l'événement, pour que
« pas dans le futur » et le verrou de minuit soient déterministes.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.sport import services
from apps.sport.models import Attendance, TeamAssignment
from apps.sport.tests.conftest import client_for, make_member
from apps.sport.tests.factories import MatchFactory, SessionFactory

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("Africa/Kinshasa")


def _at(event_date, hour, minute=0):
    return datetime.datetime.combine(event_date, datetime.time(hour, minute), tzinfo=TZ)


@pytest.fixture
def session(ctx, monkeypatch):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    fake_now = _at(session.event.event_date, 10, 0)
    monkeypatch.setattr(services.timezone, "now", lambda: fake_now)
    return session


def _url(session):
    return reverse("sport:session-attendance-bulk", args=[session.pk])


def _items(*members):
    return [{"membership_id": m.pk, "selection_rank": i + 1} for i, m in enumerate(members)]


def _arrive(client, session, *members, **extra):
    return client.post(_url(session), {"action": "arrive", "items": _items(*members), **extra}, format="json")


def test_arrival_status_is_computed_never_forced(ctx, session):
    # 10:00 simulé > limite 08:00 : le lot est enregistré « en retard ».
    response = _arrive(client_for(ctx.coach.user), session, ctx.player, ctx.captain)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["counts"] == {"created": 2, "skipped": 0, "refused": 0}
    for result in response.data["results"]:
        assert result["attendance"]["status"] == "late_absent"
        assert "retard" in result["message"] and "compté absent" in result["message"]


def test_common_time_before_cutoff_gives_present_for_coach(ctx, session):
    response = _arrive(
        client_for(ctx.coach.user), session, ctx.player, arrived_at=_at(session.event.event_date, 7, 50).isoformat()
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"][0]["attendance"]["status"] == "present"
    assert response.data["results"][0]["message"] == "Pointé à 07:50."


def test_assistant_coach_can_set_common_time_and_excuse(ctx, session):
    assistant = make_member(ctx.club, roles=[MembershipRole.Role.ASSISTANT_COACH])
    client = client_for(assistant.user)
    ok = _arrive(client, session, ctx.player, arrived_at=_at(session.event.event_date, 7, 50).isoformat())
    assert ok.status_code == 200 and ok.data["counts"]["created"] == 1
    excuse = client.post(
        _url(session),
        {"action": "excuse", "reason_code": "travel", "items": _items(ctx.captain)},
        format="json",
    )
    assert excuse.status_code == 200 and excuse.data["counts"]["created"] == 1


@pytest.mark.parametrize("role", ["captain", "president"])
def test_captain_and_president_arrive_but_no_common_time_no_excuse(ctx, session, role):
    actor = getattr(ctx, role)
    client = client_for(actor.user)
    assert _arrive(client, session, ctx.player).status_code == 200
    refused_time = _arrive(
        client, session, ctx.debtor, arrived_at=_at(session.event.event_date, 7, 50).isoformat()
    )
    assert refused_time.status_code == status.HTTP_403_FORBIDDEN
    refused_excuse = client.post(
        _url(session), {"action": "excuse", "reason_code": "other", "items": _items(ctx.debtor)}, format="json"
    )
    assert refused_excuse.status_code == status.HTTP_403_FORBIDDEN
    assert not Attendance.all_objects.filter(club=ctx.club, membership=ctx.debtor).exists()


@pytest.mark.parametrize("role", ["player", "doctor", "vice_president", "sports_director"])
def test_other_roles_are_refused(ctx, session, role):
    response = _arrive(client_for(getattr(ctx, role).user), session, ctx.captain)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not Attendance.all_objects.filter(club=ctx.club).exists()


def test_other_club_is_not_found_and_foreign_players_refused(ctx, other_ctx, session):
    foreign_session = SessionFactory(club=other_ctx.club, event__club=other_ctx.club, event__season=other_ctx.season)
    assert _arrive(client_for(ctx.coach.user), foreign_session, ctx.player).status_code == status.HTTP_404_NOT_FOUND

    response = _arrive(client_for(ctx.coach.user), session, other_ctx.player, ctx.player)
    assert response.status_code == 200
    by_id = {r["membership_id"]: r for r in response.data["results"]}
    assert by_id[other_ctx.player.pk]["outcome"] == "refused"
    assert by_id[other_ctx.player.pk]["message"] == "Ce joueur n'existe pas dans ce club."
    assert by_id[ctx.player.pk]["outcome"] == "created"
    assert not Attendance.all_objects.filter(membership=other_ctx.player).exists()


def test_blocked_players_are_pointable_but_never_placed(ctx, session, monkeypatch):
    fake_now = _at(session.event.event_date, 7, 40)
    monkeypatch.setattr(services.timezone, "now", lambda: fake_now)
    response = _arrive(client_for(ctx.coach.user), session, ctx.debtor, ctx.pending_member, ctx.player)
    assert response.data["counts"]["created"] == 3
    assert all(r["attendance"]["status"] == "present" for r in response.data["results"])
    placed = set(TeamAssignment.all_objects.filter(club=ctx.club, session=session).values_list("membership_id", flat=True))
    assert placed == {ctx.player.pk}


def test_arrival_order_follows_selection_rank_for_team_alternation(ctx, session, monkeypatch):
    fake_now = _at(session.event.event_date, 7, 40)
    monkeypatch.setattr(services.timezone, "now", lambda: fake_now)
    second = make_member(ctx.club)
    items = [
        {"membership_id": second.pk, "selection_rank": 2},
        {"membership_id": ctx.player.pk, "selection_rank": 1},
    ]
    client_for(ctx.coach.user).post(_url(session), {"action": "arrive", "items": items}, format="json")
    first = TeamAssignment.all_objects.get(club=ctx.club, session=session, membership=ctx.player)
    assert (first.arrival_order, first.team) == (1, "A")


def test_idempotent_does_not_overwrite_time(ctx, session, monkeypatch):
    client = client_for(ctx.coach.user)
    first_time = _at(session.event.event_date, 7, 50)
    _arrive(client, session, ctx.player, arrived_at=first_time.isoformat())
    second = _arrive(client, session, ctx.player)  # 10:00 simulé
    assert second.data["counts"] == {"created": 0, "skipped": 1, "refused": 0}
    assert second.data["results"][0]["message"] == "Déjà pointé à 07:50."
    attendance = Attendance.all_objects.get(club=ctx.club, membership=ctx.player)
    assert attendance.arrived_at == first_time and attendance.status == "present"
    assert AuditLog.objects.filter(action_type="sport.attendance_marked").count() == 1


def test_client_uuid_replay_is_skipped(ctx, session):
    import uuid

    uid = uuid.uuid4()
    item = {"membership_id": ctx.player.pk, "client_uuid": str(uid), "client_recorded_at": "2026-11-15T07:40:00+01:00"}
    client = client_for(ctx.coach.user)
    body = {"action": "arrive", "items": [item]}
    assert client.post(_url(session), body, format="json").data["counts"]["created"] == 1
    assert client.post(_url(session), body, format="json").data["counts"]["skipped"] == 1


def test_partial_success_one_failure_does_not_block_others(ctx, session, monkeypatch):
    real = services.mark_arrival

    def flaky(*, membership, **kwargs):
        if membership.pk == ctx.captain.pk:
            raise services.SportValidationError("Refus simulé.")
        return real(membership=membership, **kwargs)

    monkeypatch.setattr(services, "mark_arrival", flaky)
    response = _arrive(client_for(ctx.coach.user), session, ctx.player, ctx.captain, ctx.debtor)
    assert response.status_code == 200
    assert response.data["counts"] == {"created": 2, "skipped": 0, "refused": 1}
    refused = [r for r in response.data["results"] if r["outcome"] == "refused"][0]
    assert refused["membership_id"] == ctx.captain.pk and refused["message"] == "Refus simulé."
    assert refused["attendance"] is None
    assert not Attendance.all_objects.filter(membership=ctx.captain).exists()


def test_audit_one_entry_per_player_with_batch_id(ctx, session):
    response = _arrive(client_for(ctx.coach.user), session, ctx.player, ctx.captain, ctx.debtor)
    batch_id = response.data["batch_id"]
    entries = AuditLog.objects.filter(action_type="sport.attendance_marked")
    assert entries.count() == 3
    assert {e.after["batch_id"] for e in entries} == {batch_id}
    assert all(e.after["batch_size"] == 3 and e.actor_id == ctx.coach.user.pk for e in entries)
    assert not any("common_time_entered_by_coach" in e.after for e in entries)

    common = _arrive(
        client_for(ctx.coach.user),
        session,
        ctx.president,
        arrived_at=_at(session.event.event_date, 7, 45).isoformat(),
    )
    entry = AuditLog.objects.get(after__batch_id=common.data["batch_id"])
    assert entry.after["common_time_entered_by_coach"] is True


def test_excuse_only_unpointed_and_audited(ctx, session):
    client = client_for(ctx.coach.user)
    _arrive(client, session, ctx.player)
    response = client.post(
        _url(session),
        {
            "action": "excuse",
            "reason_code": "injured",
            "reason_detail": "  genou  ",
            "items": _items(ctx.player, ctx.captain),
        },
        format="json",
    )
    by_id = {r["membership_id"]: r for r in response.data["results"]}
    assert by_id[ctx.player.pk]["outcome"] == "skipped"
    assert by_id[ctx.captain.pk]["outcome"] == "created"
    attendance = Attendance.all_objects.get(club=ctx.club, membership=ctx.captain)
    assert attendance.status == "excused_absent" and attendance.excused_reason == "Blessé : genou"
    entry = AuditLog.objects.get(after__batch_id=response.data["batch_id"])
    assert entry.after["reason_code"] == "injured" and "genou" not in str(entry.after)


def test_excuse_requires_reason(ctx, session):
    response = client_for(ctx.coach.user).post(
        _url(session), {"action": "excuse", "items": _items(ctx.player)}, format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_midnight_lock_refuses_whole_batch_but_not_superuser_rule(ctx):
    yesterday = datetime.date.today() - datetime.timedelta(days=3)
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday)
    response = _arrive(client_for(ctx.coach.user), session, ctx.player)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "event_locked"
    assert "verrouillée depuis minuit" in response.data["detail"]
    assert not Attendance.all_objects.filter(club=ctx.club).exists()


def test_invalid_common_time(ctx, session):
    client = client_for(ctx.coach.user)
    future = _arrive(client, session, ctx.player, arrived_at=_at(session.event.event_date, 11, 0).isoformat())
    assert future.status_code == 400 and "futur" in future.data["detail"]
    other_day = _arrive(
        client, session, ctx.player, arrived_at=_at(session.event.event_date - datetime.timedelta(days=1), 9).isoformat()
    )
    assert other_day.status_code == 400 and "journée" in other_day.data["detail"]


def test_empty_and_oversized_batches_are_refused(ctx, session):
    client = client_for(ctx.coach.user)
    assert client.post(_url(session), {"action": "arrive", "items": []}, format="json").status_code == 400
    big = [{"membership_id": i + 1} for i in range(101)]
    response = client.post(_url(session), {"action": "arrive", "items": big}, format="json")
    assert response.status_code == 400 and "100" in response.data["detail"]


def test_match_bulk_arrival_no_team_assignment(ctx, monkeypatch):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    fake_now = _at(match.event.event_date, 10, 0)
    monkeypatch.setattr(services.timezone, "now", lambda: fake_now)
    url = reverse("sport:match-attendance-bulk", args=[match.pk])
    response = client_for(ctx.captain.user).post(
        url, {"action": "arrive", "items": _items(ctx.player)}, format="json"
    )
    assert response.status_code == 200
    assert response.data["results"][0]["attendance"]["status"] == "present"  # coup d'envoi 15:00
    assert client_for(ctx.player.user).post(url, {"action": "arrive", "items": _items(ctx.captain)}, format="json").status_code == 403


def test_capabilities_in_session_detail(ctx, session):
    def caps(member):
        return client_for(member.user).get(reverse("sport:session-detail", args=[session.pk])).data["capabilities"]

    assert caps(ctx.coach) == {"can_bulk_mark": True, "can_bulk_excuse": True, "can_set_arrival_time": True}
    assert caps(ctx.captain) == {"can_bulk_mark": True, "can_bulk_excuse": False, "can_set_arrival_time": False}
    assert caps(ctx.player) == {"can_bulk_mark": False, "can_bulk_excuse": False, "can_set_arrival_time": False}
