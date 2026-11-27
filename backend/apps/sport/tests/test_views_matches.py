"""Vues API des matchs, de la composition et de la discipline (tâche 3.6 :
CDC 4.8, 4.9, matrice 2.4)."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.clubs.models import Membership
from apps.sport import services
from apps.sport.models import Incident, Match, MatchComposition
from apps.sport.tests.conftest import client_for
from apps.sport.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("Africa/Kinshasa")


def _match_arrived(match, hour, minute):
    return datetime.datetime.combine(match.event.event_date, datetime.time(hour, minute), tzinfo=TZ)


def _match_payload():
    return {
        "event_date": timezone.now().date().isoformat(),
        "kickoff_time": "15:00:00",
        "match_type": Match.MatchType.FRIENDLY,
        "venue": Match.Venue.HOME,
        "opponent_name": "FC Adversaire",
    }


def test_only_coach_creates_a_match(ctx):
    denied = client_for(ctx.president.user).post(reverse("sport:match-list"), _match_payload())
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    created = client_for(ctx.coach.user).post(reverse("sport:match-list"), _match_payload())
    assert created.status_code == status.HTTP_201_CREATED, created.data
    assert created.data["opponent"] == "FC Adversaire"


def test_composition_refuses_a_debtor_with_reason_and_reserved_to_coach(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:match-composition-add", args=[match.pk])

    denied = client_for(ctx.captain.user).post(
        url, {"membership_id": ctx.player.pk, "role": "starter", "position": "midfielder", "jersey_number": 10}
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    refused = client_for(ctx.coach.user).post(
        url, {"membership_id": ctx.debtor.pk, "role": "starter", "position": "midfielder", "jersey_number": 9}
    )
    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert refused.data["code"] == "player_not_eligible"
    assert refused.data["detail"] == "Non éligible."  # 10.3 n° 188
    assert MatchComposition.all_objects.filter(club=ctx.club, match=match).count() == 0

    added = client_for(ctx.coach.user).post(
        url, {"membership_id": ctx.player.pk, "role": "starter", "position": "midfielder", "jersey_number": 10}
    )
    assert added.status_code == status.HTTP_201_CREATED
    assert added.data["no_longer_eligible"] is None


def test_composition_publish_and_remove(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    add_url = reverse("sport:match-composition-add", args=[match.pk])
    client_for(ctx.coach.user).post(
        add_url, {"membership_id": ctx.player.pk, "role": "starter", "position": "midfielder", "jersey_number": 10}
    )

    published = client_for(ctx.coach.user).post(reverse("sport:match-composition-publish", args=[match.pk]))
    assert published.status_code == status.HTTP_200_OK
    assert published.data["is_composition_published"] is True

    removed = client_for(ctx.coach.user).delete(
        reverse("sport:match-composition-remove", args=[match.pk, ctx.player.pk])
    )
    assert removed.status_code == status.HTTP_204_NO_CONTENT
    assert MatchComposition.all_objects.filter(club=ctx.club, match=match, membership=ctx.player).count() == 0


def test_score_and_goals(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)

    score = client_for(ctx.coach.user).post(
        reverse("sport:match-score", args=[match.pk]), {"score_home": 2, "score_away": 1}
    )
    assert score.status_code == status.HTTP_200_OK
    assert score.data["sheet"]["score_home"] == 2

    goal = client_for(ctx.coach.user).post(
        reverse("sport:match-goal-list", args=[match.pk]), {"scorer_membership_id": ctx.player.pk, "minute": 34}
    )
    assert goal.status_code == status.HTTP_201_CREATED
    assert goal.data["scorer"]["membership_id"] == ctx.player.pk

    listed = client_for(ctx.player.user).get(reverse("sport:match-goal-list", args=[match.pk]))
    assert listed.status_code == status.HTTP_200_OK
    assert len(listed.data) == 1


def test_incident_visibility_is_restricted_to_own_incidents_for_a_plain_player(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:event-incidents", args=[match.event_id])

    created = client_for(ctx.coach.user).post(
        url,
        {
            "membership_id": ctx.player.pk,
            "incident_type": Incident.IncidentType.YELLOW_CARD,
            "cause": Incident.Cause.BEHAVIOUR,
        },
    )
    assert created.status_code == status.HTTP_201_CREATED

    other_created = client_for(ctx.coach.user).post(
        url,
        {
            "membership_id": ctx.captain.pk,
            "incident_type": Incident.IncidentType.YELLOW_CARD,
            "cause": Incident.Cause.BEHAVIOUR,
        },
    )
    assert other_created.status_code == status.HTTP_201_CREATED

    # Le joueur concerné ne voit que ses propres incidents (matrice 2.4).
    as_player = client_for(ctx.player.user).get(url)
    assert as_player.data["count"] == 1
    assert as_player.data["results"][0]["player"]["membership_id"] == ctx.player.pk

    # Le Président (staff) voit tous les incidents de l'événement.
    as_president = client_for(ctx.president.user).get(url)
    assert as_president.data["count"] == 2


def test_fifth_yellow_card_creates_a_visible_suspension(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    for _ in range(5):
        match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
        services.record_incident(
            event=match.event,
            membership=ctx.player,
            incident_type=Incident.IncidentType.YELLOW_CARD,
            cause=Incident.Cause.BEHAVIOUR,
            recorded_by=ctx.coach.user,
        )

    response = client_for(ctx.coach.user).get(reverse("sport:suspension-list"), {"membership_id": ctx.player.pk})
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert response.data["results"][0]["reason"] == "cumulative_yellow"

    # Le joueur suspendu ne voit que sa propre suspension, jamais celle des
    # autres (filtrage par rôle, réutilisé de ``INCIDENT_FULL_VISIBILITY_ROLES``).
    as_player = client_for(ctx.player.user).get(reverse("sport:suspension-list"))
    assert all(item["membership_id"] == ctx.player.pk for item in as_player.data["results"])


def test_match_of_another_club_is_not_found(ctx, other_ctx):
    other_match = MatchFactory(club=other_ctx.club, event__club=other_ctx.club, event__season=other_ctx.season)

    response = client_for(ctx.player.user).get(reverse("sport:match-detail", args=[other_match.pk]))

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_only_coach_updates_a_match(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:match-detail", args=[match.pk])
    payload = {
        "event_date": match.event.event_date.isoformat(),
        "kickoff_time": "16:30:00",
        "match_type": Match.MatchType.CHAMPIONSHIP,
        "venue": Match.Venue.AWAY,
        "location": "Stade annexe",
        "opponent_name": "FC Rival",
    }

    denied = client_for(ctx.captain.user).patch(url, payload)
    assert denied.status_code == status.HTTP_403_FORBIDDEN

    allowed = client_for(ctx.coach.user).patch(url, payload)
    assert allowed.status_code == status.HTTP_200_OK, allowed.data
    assert allowed.data["kickoff_time"] == datetime.time(16, 30)
    assert allowed.data["venue"] == Match.Venue.AWAY
    assert allowed.data["opponent"] == "FC Rival"


def test_update_match_refuses_own_club_as_opponent_or_challenge_target(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:match-detail", args=[match.pk])
    payload = {
        "event_date": match.event.event_date.isoformat(),
        "kickoff_time": "16:30:00",
        "match_type": Match.MatchType.CHAMPIONSHIP,
        "venue": Match.Venue.AWAY,
    }

    own_opponent = client_for(ctx.coach.user).patch(url, {**payload, "opponent_club_id": ctx.club.pk})
    assert own_opponent.status_code == status.HTTP_400_BAD_REQUEST
    assert own_opponent.data["detail"] == "Votre propre club ne peut pas être l'adversaire d'un match."

    own_challenge = client_for(ctx.coach.user).patch(
        url, {**payload, "opponent_name": "FC Rival", "challenge_to_club_id": ctx.club.pk}
    )
    assert own_challenge.status_code == status.HTTP_400_BAD_REQUEST
    assert own_challenge.data["detail"] == "Vous ne pouvez pas lancer un défi à votre propre club."

    match.refresh_from_db()
    assert match.opponent_club_id is None


def test_update_match_ignores_opponent_change_for_an_accepted_challenge(ctx, other_ctx):
    match = MatchFactory(
        club=ctx.club,
        event__club=ctx.club,
        event__season=ctx.season,
        opponent_club=other_ctx.club,
        opponent_name="",
        challenge_status=Match.ChallengeStatus.ACCEPTED,
        challenge_to_club=other_ctx.club,
    )
    url = reverse("sport:match-detail", args=[match.pk])
    payload = {
        "event_date": match.event.event_date.isoformat(),
        "kickoff_time": "16:00:00",
        "match_type": match.match_type,
        "venue": match.venue,
        # Tentative de changement d'adversaire, malgré un défi accepté :
        # doit être silencieusement ignorée (§4.7).
        "opponent_name": "Une autre équipe",
    }

    response = client_for(ctx.coach.user).patch(url, payload)
    assert response.status_code == status.HTTP_200_OK, response.data
    assert response.data["opponent"] == other_ctx.club.name
    assert response.data["kickoff_time"] == datetime.time(16, 0)


def test_update_match_is_blocked_once_locked(ctx):
    yesterday = timezone.now().date() - datetime.timedelta(days=1)
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season, event__event_date=yesterday)
    url = reverse("sport:match-detail", args=[match.pk])
    payload = {
        "event_date": yesterday.isoformat(),
        "kickoff_time": "15:00:00",
        "match_type": match.match_type,
        "venue": match.venue,
        "opponent_name": match.opponent_name,
    }

    response = client_for(ctx.coach.user).patch(url, payload)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "event_locked"


def test_match_attendance_mark_present_then_late_without_team_assignment(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:match-attendance-mark", args=[match.pk])

    present = client_for(ctx.coach.user).post(
        url, {"membership_id": ctx.player.pk, "arrived_at": _match_arrived(match, 14, 30).isoformat()}
    )
    assert present.status_code == status.HTTP_201_CREATED
    assert present.data["status"] == "present"

    late = client_for(ctx.coach.user).post(
        url, {"membership_id": ctx.captain.pk, "arrived_at": _match_arrived(match, 15, 10).isoformat()}
    )
    assert late.status_code == status.HTTP_201_CREATED
    assert late.data["status"] == "late_absent"

    # Sans répartition A/B pour un match (sport-feuille-de-match.md §7,
    # point ouvert 2) : le pointage apparaît dans la feuille de match,
    # mais aucune répartition n'est possible ni créée automatiquement.
    detail = client_for(ctx.coach.user).get(reverse("sport:match-detail", args=[match.pk]))
    statuses = {item["membership_id"]: item["status"] for item in detail.data["attendances"]}
    assert statuses[ctx.player.pk] == "present"
    assert statuses[ctx.captain.pk] == "late_absent"


def test_match_attendance_mark_requires_a_recorder_role(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:match-attendance-mark", args=[match.pk])

    denied = client_for(ctx.player.user).post(
        url, {"membership_id": ctx.player.pk, "arrived_at": _match_arrived(match, 14, 30).isoformat()}
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN


def test_unpublished_composition_is_staff_only(ctx):
    """D3 : brouillon de composition invisible hors staff tant que non publié (CDC 4.8)."""
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    add = client_for(ctx.coach.user).post(
        reverse("sport:match-composition-add", args=[match.pk]),
        {"membership_id": ctx.player.pk, "role": "starter", "position": "midfielder", "jersey_number": 10},
    )
    assert add.status_code == status.HTTP_201_CREATED, add.data
    url = reverse("sport:match-detail", args=[match.pk])

    assert len(client_for(ctx.coach.user).get(url).data["starters"]) == 1
    for viewer in (ctx.player, ctx.captain):
        data = client_for(viewer.user).get(url).data
        assert data["starters"] == [] and data["substitutes"] == []

    match.is_composition_published = True
    match.save()
    assert len(client_for(ctx.player.user).get(url).data["starters"]) == 1


def test_create_match_without_opponent_is_400_and_leaves_no_orphan_event(ctx):
    from apps.sport.models import Event

    payload = _match_payload()
    payload.pop("opponent_name")
    before = Event.all_objects.filter(club=ctx.club).count()
    response = client_for(ctx.coach.user).post(reverse("sport:match-list"), payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "adverse" in response.data["detail"]
    assert Event.all_objects.filter(club=ctx.club).count() == before


def test_composition_refuses_a_jersey_number_already_taken(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    url = reverse("sport:match-composition-add", args=[match.pk])
    client = client_for(ctx.coach.user)
    assert client.post(
        url, {"membership_id": ctx.player.pk, "role": "starter", "position": "midfielder", "jersey_number": 10}
    ).status_code == status.HTTP_201_CREATED
    dup = client.post(
        url, {"membership_id": ctx.captain.pk, "role": "starter", "position": "midfielder", "jersey_number": 10}
    )
    assert dup.status_code == status.HTTP_400_BAD_REQUEST
    assert "déjà attribué" in dup.data["detail"]


def test_goal_refuses_assist_equal_to_scorer(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    client_for(ctx.coach.user).post(reverse("sport:match-score", args=[match.pk]), {"score_home": 1, "score_away": 0})
    response = client_for(ctx.coach.user).post(
        reverse("sport:match-goal-list", args=[match.pk]),
        {"scorer_membership_id": ctx.player.pk, "assist_membership_id": ctx.player.pk, "minute": 5},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "différent du buteur" in response.data["detail"]
