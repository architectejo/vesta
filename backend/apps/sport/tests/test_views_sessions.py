"""Vues API des séances et du pointage (tâche 3.6 : CDC 4.7, matrice 2.4).

Complète les tests de service déjà écrits (tâches 3.2-3.4) par la couche
HTTP : permissions par rôle, motif filtré par rôle (10.2 n° 16) tel que
renvoyé par l'API, étanchéité multi-club et verrouillage à minuit.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.sport import services
from apps.sport.models import TeamAssignment
from apps.sport.tests.conftest import client_for
from apps.sport.tests.factories import SessionFactory

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("Africa/Kinshasa")


def _arrived(session, hour=7, minute=40):
    return datetime.datetime.combine(session.event.event_date, datetime.time(hour, minute), tzinfo=TZ)


def test_only_coach_can_create_a_session(ctx):
    payload = {
        "event_date": timezone.now().date().isoformat(),
        "gathering_time": "07:30:00",
        "late_arrival_cutoff": "08:00:00",
    }

    denied = client_for(ctx.president.user).post(reverse("sport:session-list"), payload)
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    response = client_for(ctx.coach.user).post(reverse("sport:session-list"), payload)
    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["gathering_time"] == datetime.time(7, 30)
    assert response.data["is_locked"] is False


def test_any_active_member_reads_the_list_and_detail(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)

    listing = client_for(ctx.player.user).get(reverse("sport:session-list"))
    assert listing.status_code == status.HTTP_200_OK
    assert listing.data["count"] >= 1

    detail = client_for(ctx.player.user).get(reverse("sport:session-detail", args=[session.pk]))
    assert detail.status_code == status.HTTP_200_OK
    assert detail.data["id"] == session.pk


def test_mark_arrival_present_then_late(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:session-attendance-mark", args=[session.pk])

    present = client_for(ctx.coach.user).post(
        url, {"membership_id": ctx.player.pk, "arrived_at": _arrived(session, 7, 40).isoformat()}
    )
    assert present.status_code == status.HTTP_201_CREATED
    assert present.data["status"] == "present"

    late = client_for(ctx.coach.user).post(
        url, {"membership_id": ctx.captain.pk, "arrived_at": _arrived(session, 8, 15).isoformat()}
    )
    assert late.status_code == status.HTTP_201_CREATED
    assert late.data["status"] == "late_absent"

    # Un joueur en retard n'est PAS réparti automatiquement (10.2 n° 38) :
    # il reste dans « À placer à la main ».
    unassigned = client_for(ctx.coach.user).get(reverse("sport:session-unassigned", args=[session.pk]))
    assert any(item["membership_id"] == ctx.captain.pk for item in unassigned.data["to_place_manually"])


def test_only_coach_corrects_arrival_time(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    attendance = services.mark_arrival(
        session=session, membership=ctx.player, arrived_at=_arrived(session), marked_by=ctx.coach.user
    )
    url = reverse("sport:attendance-correction", args=[attendance.pk])

    denied = client_for(ctx.captain.user).patch(url, {"arrived_at": _arrived(session, 7, 45).isoformat()})
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    allowed = client_for(ctx.coach.user).patch(url, {"arrived_at": _arrived(session, 8, 20).isoformat()})
    assert allowed.status_code == status.HTTP_200_OK
    assert allowed.data["status"] == "late_absent"


def test_team_assignment_refuses_a_debtor_with_role_filtered_reason(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    services.mark_arrival(
        session=session, membership=ctx.debtor, arrived_at=_arrived(session), marked_by=ctx.coach.user
    )
    url = reverse("sport:team-assignment", args=[session.pk])

    response = client_for(ctx.coach.user).post(url, {"membership_id": ctx.debtor.pk, "team": "A"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "player_not_eligible"
    assert "dette" in response.data["detail"].lower()

    assert TeamAssignment.all_objects.filter(club=ctx.club, session=session, membership=ctx.debtor).count() == 0

    # La zone « Non répartis » applique le même filtrage de motif par rôle
    # (10.2 n° 16) que le service : Coach voit le montant, un coéquipier voit
    # seulement « Indisponible ».
    for_coach = client_for(ctx.coach.user).get(reverse("sport:session-unassigned", args=[session.pk]))
    debtor_entry = next(item for item in for_coach.data["cannot_play"] if item["membership_id"] == ctx.debtor.pk)
    assert "dette" in debtor_entry["reason"].lower()

    for_teammate = client_for(ctx.player.user).get(reverse("sport:session-unassigned", args=[session.pk]))
    debtor_entry_teammate = next(
        item for item in for_teammate.data["cannot_play"] if item["membership_id"] == ctx.debtor.pk
    )
    assert debtor_entry_teammate["reason"] == "Indisponible"


def test_locked_session_blocks_writes_and_superuser_can_unlock(ctx):
    from apps.accounts.tests.factories import SuperuserFactory
    from apps.licences.tests.factories import SupportSessionFactory

    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    session = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday
    )
    url = reverse("sport:session-attendance-mark", args=[session.pk])

    blocked = client_for(ctx.coach.user).post(
        url, {"membership_id": ctx.player.pk, "arrived_at": _arrived(session, 7, 40).isoformat()}
    )
    assert blocked.status_code == status.HTTP_409_CONFLICT
    assert blocked.data["code"] == "event_locked"

    superuser = SuperuserFactory()
    support_session = SupportSessionFactory(superuser=superuser, club=ctx.club)
    access = str(RefreshToken.for_user(superuser).access_token)

    unlock = APIClient().post(
        reverse("sport:event-unlock", args=[session.pk]),
        {"reason": "Correction demandée par le Président"},
        HTTP_AUTHORIZATION=f"Bearer {access}",
        HTTP_X_SUPPORT_SESSION=str(support_session.pk),
    )
    assert unlock.status_code == status.HTTP_200_OK, unlock.data
    assert unlock.data["is_locked"] is False


def test_session_of_another_club_is_not_found(ctx, other_ctx):
    other_session = SessionFactory(club=other_ctx.club, event__club=other_ctx.club, event__season=other_ctx.season)

    response = client_for(ctx.player.user).get(reverse("sport:session-detail", args=[other_session.pk]))

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_only_coach_updates_a_session(ctx):
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:session-detail", args=[session.pk])
    payload = {
        "event_date": session.event.event_date.isoformat(),
        "gathering_time": "07:45:00",
        "late_arrival_cutoff": "08:15:00",
        "location": "Terrain B",
        "team_a_color": "#00FF00",
        "team_b_color": "#FF00FF",
        "instructions": "Apporter les dossards.",
    }

    denied = client_for(ctx.president.user).patch(url, payload)
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    allowed = client_for(ctx.coach.user).patch(url, payload)
    assert allowed.status_code == status.HTTP_200_OK, allowed.data
    assert allowed.data["gathering_time"] == datetime.time(7, 45)
    assert allowed.data["location"] == "Terrain B"
    assert allowed.data["team_a_color"] == "#00FF00"


def test_update_session_is_blocked_once_locked(ctx):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    session = SessionFactory(
        club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday
    )
    url = reverse("sport:session-detail", args=[session.pk])
    payload = {
        "event_date": yesterday.isoformat(),
        "gathering_time": "07:30:00",
        "late_arrival_cutoff": "08:00:00",
    }

    response = client_for(ctx.coach.user).patch(url, payload)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "event_locked"


def test_unassigned_reason_code_is_hidden_from_teammates_and_captain(ctx):
    """D2 : le code de motif ne fuit pas aux coéquipiers/Capitaine ; Médecin/DS ne voient ni dette ni attente."""
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    for target in (ctx.debtor, ctx.pending_member):
        services.mark_arrival(
            session=session, membership=target, arrived_at=_arrived(session), marked_by=ctx.coach.user
        )
    url = reverse("sport:session-unassigned", args=[session.pk])

    def entry(viewer, target):
        response = client_for(viewer.user).get(url)
        assert response.status_code == status.HTTP_200_OK
        return next((i for i in response.data["cannot_play"] if i["membership_id"] == target.pk), None)

    for viewer in (ctx.player, ctx.captain):
        for target in (ctx.debtor, ctx.pending_member):
            item = entry(viewer, target)
            assert item is not None
            assert item["reason"] == "Indisponible"
            assert item["reason_code"] == "unavailable"
    for viewer in (ctx.doctor, ctx.sports_director):
        for target in (ctx.debtor, ctx.pending_member):
            item = entry(viewer, target)
            assert item is not None
            assert item["reason"] == "Indisponible"
            assert item["reason_code"] == "unavailable"
    coach_item = entry(ctx.coach, ctx.debtor)
    assert coach_item["reason_code"] == "debt"


def test_superuser_unlock_without_support_session_is_403_not_500(ctx):
    """D15 : hors Ghost Mode, refus explicite en français (pas de 500)."""
    from apps.accounts.tests.factories import SuperuserFactory

    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    access = str(RefreshToken.for_user(SuperuserFactory()).access_token)
    response = APIClient().post(
        reverse("sport:event-unlock", args=[session.pk]), {"reason": "Test"}, HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "session de support" in response.data["detail"]
