"""Assistant du Coach (CDC 10.3 n179, decision client du 13/11/2026) :
memes droits que le Coach sauf nommer/retirer un assistant, nomme et retire
par le Coach seul, un seul assistant par Coach, poste conserve quand le Coach
change, journal et notification."""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.audit.models import AuditLog
from apps.clubs import services
from apps.clubs.models import COACHING_STAFF_ROLES, Membership, MembershipRole
from apps.clubs.tests.factories import MembershipRoleFactory
from apps.core.roles import get_active_roles
from apps.medical.tests.conftest import build_medical_club_context
from apps.notifications.models import Notification
from apps.sport.models import Incident, Match
from apps.sport.tests.conftest import build_sport_club_context, client_for, make_member
from apps.sport.tests.factories import MatchFactory, SessionFactory

pytestmark = pytest.mark.django_db

COACH = MembershipRole.Role.COACH
ASSISTANT = MembershipRole.Role.ASSISTANT_COACH
APPOINT = "clubs:assistant-coach-appoint"
REVOKE = "clubs:assistant-coach-revoke"


def _active_assistants(club):
    return MembershipRole.all_objects.filter(club=club, role=ASSISTANT, revoked_at__isnull=True)


def _appoint(coach, target):
    return services.appoint_assistant_coach(coach_user=coach.user, target_membership=target)


# ---------------------------------------------------------------------------
# Role et libelle
# ---------------------------------------------------------------------------


def test_role_key_label_and_staff_set():
    assert ASSISTANT == "assistant_coach"
    assert MembershipRole.Role(ASSISTANT).label == "Assistant du Coach"
    assert COACHING_STAFF_ROLES == {COACH, ASSISTANT}


# ---------------------------------------------------------------------------
# Nomination / retrait
# ---------------------------------------------------------------------------


def test_coach_appoints_through_api_with_journal_and_notification():
    ctx = build_sport_club_context()
    target = ctx.player

    response = client_for(ctx.coach.user).post(reverse(APPOINT), {"membership_id": target.pk}, format="json")

    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["role"] == "assistant_coach"
    assert response.data["role_label"] == "Assistant du Coach"
    assert ASSISTANT in get_active_roles(target.user, club=ctx.club)
    role = _active_assistants(ctx.club).get()
    assert role.appointed_by_id == ctx.coach.user_id

    entry = AuditLog.objects.get(action_type="role.appointed", object_id=str(role.pk))
    assert entry.actor_id == ctx.coach.user_id
    assert entry.after["role"] == "assistant_coach"
    notification = Notification.objects.get(recipient=target.user, event_type="role_appointed_or_revoked")
    assert "Assistant du Coach" in notification.body


def test_coach_removes_through_api_with_journal_and_notification():
    ctx = build_sport_club_context()
    role = _appoint(ctx.coach, ctx.player)
    Notification.objects.all().delete()

    response = client_for(ctx.coach.user).post(
        reverse(REVOKE), {"role_id": role.pk, "reason": "Changement d'organisation"}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK, response.data
    assert ASSISTANT not in get_active_roles(ctx.player.user, club=ctx.club)
    role.refresh_from_db()
    assert role.revoked_by_id == ctx.coach.user_id
    assert AuditLog.objects.filter(action_type="role.revoked", object_id=str(role.pk), actor=ctx.coach.user).exists()
    assert Notification.objects.filter(recipient=ctx.player.user, title="Fin de rôle").exists()


def test_president_cannot_appoint_or_remove_an_assistant():
    ctx = build_sport_club_context()
    role = _appoint(ctx.coach, ctx.player)

    appoint = client_for(ctx.president.user).post(reverse(APPOINT), {"membership_id": ctx.captain.pk}, format="json")
    revoke = client_for(ctx.president.user).post(reverse(REVOKE), {"role_id": role.pk}, format="json")
    assert appoint.status_code == status.HTTP_403_FORBIDDEN
    assert revoke.status_code == status.HTTP_403_FORBIDDEN

    # Ni par le chemin generique reserve au President.
    generic = client_for(ctx.president.user).post(
        reverse("clubs:role-appoint"), {"membership_id": ctx.captain.pk, "role": "assistant_coach"}, format="json"
    )
    assert generic.status_code == status.HTTP_400_BAD_REQUEST
    generic_revoke = client_for(ctx.president.user).post(
        reverse("clubs:role-revoke"), {"role_id": role.pk}, format="json"
    )
    assert generic_revoke.status_code == status.HTTP_400_BAD_REQUEST
    assert _active_assistants(ctx.club).count() == 1


def test_assistant_cannot_appoint_or_remove_an_assistant():
    ctx = build_sport_club_context()
    assistant = ctx.player
    role = _appoint(ctx.coach, assistant)

    appoint = client_for(assistant.user).post(reverse(APPOINT), {"membership_id": ctx.captain.pk}, format="json")
    revoke = client_for(assistant.user).post(reverse(REVOKE), {"role_id": role.pk}, format="json")
    assert appoint.status_code == status.HTTP_403_FORBIDDEN
    assert revoke.status_code == status.HTTP_403_FORBIDDEN

    # Defense en profondeur cote service.
    with pytest.raises(PermissionError):
        services.appoint_assistant_coach(coach_user=assistant.user, target_membership=ctx.captain)
    with pytest.raises(PermissionError):
        services.remove_assistant_coach(coach_user=assistant.user, role=role)
    assert _active_assistants(ctx.club).get().pk == role.pk


def test_plain_player_cannot_appoint():
    ctx = build_sport_club_context()
    response = client_for(ctx.player.user).post(reverse(APPOINT), {"membership_id": ctx.captain.pk}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_target_must_be_an_active_member_of_the_club():
    ctx = build_sport_club_context()
    other = build_sport_club_context()

    unknown = client_for(ctx.coach.user).post(reverse(APPOINT), {"membership_id": other.player.pk}, format="json")
    assert unknown.status_code == status.HTTP_404_NOT_FOUND

    with pytest.raises(services.RoleManagementError):
        _appoint(ctx.coach, ctx.pending_member)
    left = make_member(ctx.club, status=Membership.Status.DEPARTED)
    with pytest.raises(services.RoleManagementError):
        _appoint(ctx.coach, left)
    assert not _active_assistants(ctx.club).exists()


def test_cannot_appoint_oneself_or_another_coach():
    ctx = build_sport_club_context()
    with pytest.raises(services.RoleManagementError):
        _appoint(ctx.coach, ctx.coach)
    ctx.club.settings.board_seats_per_role = 2
    ctx.club.settings.save()
    second_coach = make_member(ctx.club, roles=[COACH])
    with pytest.raises(services.RoleManagementError):
        _appoint(ctx.coach, second_coach)


def test_appointing_the_same_player_twice_is_refused():
    ctx = build_sport_club_context()
    _appoint(ctx.coach, ctx.player)
    with pytest.raises(services.RoleManagementError):
        _appoint(ctx.coach, ctx.player)


def test_a_new_assistant_replaces_the_previous_one_with_journal_and_notifications():
    ctx = build_sport_club_context()
    first = _appoint(ctx.coach, ctx.player)
    Notification.objects.all().delete()

    second = _appoint(ctx.coach, ctx.captain)

    active = _active_assistants(ctx.club)
    assert [r.pk for r in active] == [second.pk]
    first.refresh_from_db()
    assert first.revoked_at is not None
    assert first.revoked_by_id == ctx.coach.user_id
    assert AuditLog.objects.filter(action_type="role.revoked", object_id=str(first.pk)).exists()
    assert Notification.objects.filter(recipient=ctx.player.user, title="Fin de rôle").exists()
    assert Notification.objects.filter(recipient=ctx.captain.user, title="Nouveau rôle").exists()


def test_each_coach_keeps_his_own_assistant_when_there_are_two_coaches():
    ctx = build_sport_club_context()
    ctx.club.settings.board_seats_per_role = 2
    ctx.club.settings.save()
    second_coach = make_member(ctx.club, roles=[COACH])
    other_player = make_member(ctx.club)
    mine = _appoint(ctx.coach, ctx.player)
    theirs = _appoint(second_coach, other_player)

    assert {r.pk for r in _active_assistants(ctx.club)} == {mine.pk, theirs.pk}
    # Un Coach ne retire pas l'assistant d'un autre Coach encore en poste.
    with pytest.raises(PermissionError):
        services.remove_assistant_coach(coach_user=ctx.coach.user, role=theirs)


# ---------------------------------------------------------------------------
# Changement de Coach (decision d)
# ---------------------------------------------------------------------------


def test_assistant_keeps_the_post_when_the_coach_loses_the_role_and_new_coach_can_replace():
    ctx = build_sport_club_context()
    role = _appoint(ctx.coach, ctx.player)

    # Le President retire le Coach et nomme un nouveau Coach.
    coach_role = MembershipRole.all_objects.get(membership=ctx.coach, role=COACH, revoked_at__isnull=True)
    services.revoke_president_nominated_role(president_user=ctx.president.user, role=coach_role)
    new_coach = make_member(ctx.club)
    services.appoint_president_nominated_role(
        president_user=ctx.president.user, target_membership=new_coach, role=COACH
    )

    role.refresh_from_db()
    assert role.revoked_at is None
    assert ASSISTANT in get_active_roles(ctx.player.user, club=ctx.club)
    # Droits conserves.
    response = client_for(ctx.player.user).post(
        reverse("sport:session-list"),
        {
            "event_date": timezone.now().date().isoformat(),
            "gathering_time": "07:30:00",
            "late_arrival_cutoff": "08:00:00",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data

    # L'ancien Coach (plus Coach) ne peut plus rien decider.
    with pytest.raises(PermissionError):
        services.remove_assistant_coach(coach_user=ctx.coach.user, role=role)

    # Le nouveau Coach peut remplacer l'assistant orphelin.
    replacement = _appoint(new_coach, ctx.captain)
    role.refresh_from_db()
    assert role.revoked_at is not None and role.revoked_by_id == new_coach.user_id
    assert [r.pk for r in _active_assistants(ctx.club)] == [replacement.pk]


def test_new_coach_can_remove_an_orphan_assistant():
    ctx = build_sport_club_context()
    role = _appoint(ctx.coach, ctx.player)
    coach_role = MembershipRole.all_objects.get(membership=ctx.coach, role=COACH, revoked_at__isnull=True)
    services.revoke_president_nominated_role(president_user=ctx.president.user, role=coach_role)
    new_coach = make_member(ctx.club)
    services.appoint_president_nominated_role(
        president_user=ctx.president.user, target_membership=new_coach, role=COACH
    )

    response = client_for(new_coach.user).post(reverse(REVOKE), {"role_id": role.pk}, format="json")
    assert response.status_code == status.HTTP_200_OK, response.data
    assert not _active_assistants(ctx.club).exists()


# ---------------------------------------------------------------------------
# Etancheite entre clubs
# ---------------------------------------------------------------------------


def test_cross_club_isolation():
    ctx = build_sport_club_context()
    other = build_sport_club_context()
    foreign_role = _appoint(other.coach, other.player)

    # Un Coach ne retire pas l'assistant d'un autre club.
    response = client_for(ctx.coach.user).post(reverse(REVOKE), {"role_id": foreign_role.pk}, format="json")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    with pytest.raises(PermissionError):
        services.remove_assistant_coach(coach_user=ctx.coach.user, role=foreign_role)

    # L'assistant d'un club n'a aucun droit de staff dans un autre club.
    assert get_active_roles(other.player.user, club=ctx.club) == frozenset()
    own_assistant = _appoint(ctx.coach, ctx.player)
    assert own_assistant.club_id == ctx.club.id
    # Remplacer dans son club ne touche pas l'assistant de l'autre club.
    _appoint(ctx.coach, ctx.captain)
    assert _active_assistants(other.club).get().pk == foreign_role.pk


# ---------------------------------------------------------------------------
# Droits identiques au Coach, par famille d'endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def staff_ctx():
    ctx = build_sport_club_context()
    assistant = make_member(ctx.club, roles=[ASSISTANT])
    return ctx, assistant


@pytest.mark.parametrize("who", ["coach", "assistant"])
def test_sport_families_are_open_to_coach_and_assistant(staff_ctx, who):
    ctx, assistant = staff_ctx
    actor = ctx.coach if who == "coach" else assistant
    client = client_for(actor.user)

    # Seances.
    created = client.post(
        reverse("sport:session-list"),
        {
            "event_date": timezone.now().date().isoformat(),
            "gathering_time": "07:30:00",
            "late_arrival_cutoff": "08:00:00",
        },
    )
    assert created.status_code == status.HTTP_201_CREATED, created.data

    # Presences.
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    arrival = datetime.datetime.combine(
        session.event.event_date, datetime.time(7, 40), tzinfo=datetime.timezone.utc
    )
    marked = client.post(
        reverse("sport:session-attendance-mark", args=[session.pk]),
        {"membership_id": ctx.player.pk, "arrived_at": arrival.isoformat()},
    )
    assert marked.status_code == status.HTTP_201_CREATED, marked.data

    # Matchs et composition.
    match_created = client.post(
        reverse("sport:match-list"),
        {
            "event_date": timezone.now().date().isoformat(),
            "kickoff_time": "15:00:00",
            "match_type": Match.MatchType.FRIENDLY,
            "venue": Match.Venue.HOME,
            "opponent_name": "FC Adversaire",
        },
    )
    assert match_created.status_code == status.HTTP_201_CREATED, match_created.data
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    refused = client.post(
        reverse("sport:match-composition-add", args=[match.pk]),
        {"membership_id": ctx.debtor.pk, "role": "starter", "position": "midfielder", "jersey_number": 9},
    )
    # Le refus d'un joueur en dette s'applique a l'assistant comme au Coach (400, jamais 403).
    assert refused.status_code == status.HTTP_400_BAD_REQUEST

    # Discipline.
    incident = client.post(
        reverse("sport:event-incidents", args=[match.event_id]),
        {
            "membership_id": ctx.player.pk,
            "incident_type": Incident.IncidentType.YELLOW_CARD,
            "cause": Incident.Cause.BEHAVIOUR,
        },
    )
    assert incident.status_code == status.HTTP_201_CREATED, incident.data
    assert client.get(reverse("sport:suspension-list")).status_code == status.HTTP_200_OK

    # Plan tactique : creation, brouillon visible, suppression.
    plan = client.post(
        reverse("sport:tactical-plan-list"), {"name": "Plan", "formation": "4-4-2", "squad_size": 11}
    )
    assert plan.status_code == status.HTTP_201_CREATED, plan.data
    detail_url = reverse("sport:tactical-plan-detail", args=[plan.data["id"]])
    assert client.get(detail_url).status_code == status.HTTP_200_OK
    assert client.delete(detail_url).status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.parametrize("who", ["coach", "assistant"])
def test_evaluations_open_to_coach_and_assistant(staff_ctx, who):
    ctx, assistant = staff_ctx
    actor = ctx.coach if who == "coach" else assistant
    session = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    from apps.sport import services as sport_services

    tz = sport_services._club_tz(sport_services._club_settings(ctx.club))
    arrived = datetime.datetime.combine(session.event.event_date, datetime.time(7, 40), tzinfo=tz)
    sport_services.mark_arrival(session=session, membership=ctx.player, arrived_at=arrived, marked_by=ctx.coach.user)

    response = client_for(actor.user).post(
        reverse("sport:event-evaluations", args=[session.event_id]),
        {"membership_id": ctx.player.pk, "overall_score": "7.5"},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data


def test_sport_denies_remain_for_non_staff_like_for_coach(staff_ctx):
    ctx, _assistant = staff_ctx
    denied = client_for(ctx.captain.user).post(
        reverse("sport:tactical-plan-list"), {"name": "Plan", "formation": "4-4-2", "squad_size": 11}
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN


def test_assistant_sees_draft_tactical_plans_like_the_coach(staff_ctx):
    ctx, assistant = staff_ctx
    created = client_for(ctx.coach.user).post(
        reverse("sport:tactical-plan-list"), {"name": "Plan", "formation": "4-4-2", "squad_size": 11}
    )
    detail_url = reverse("sport:tactical-plan-detail", args=[created.data["id"]])
    assert client_for(assistant.user).get(detail_url).status_code == status.HTTP_200_OK
    assert client_for(ctx.player.user).get(detail_url).status_code == status.HTTP_403_FORBIDDEN


def test_assistant_can_choose_the_captain_like_the_coach(staff_ctx):
    ctx, assistant = staff_ctx
    # Le poste de Capitaine est deja pourvu : le Capitaine actuel est retire par l'assistant.
    role = MembershipRole.all_objects.get(membership=ctx.captain, role=MembershipRole.Role.CAPTAIN)
    revoked = client_for(assistant.user).post(
        reverse("clubs:captain-revoke"), {"role_id": role.pk}, format="json"
    )
    assert revoked.status_code == status.HTTP_200_OK, revoked.data
    appointed = client_for(assistant.user).post(
        reverse("clubs:captain-appoint"), {"membership_id": ctx.player.pk}, format="json"
    )
    assert appointed.status_code == status.HTTP_201_CREATED, appointed.data


def test_assistant_gets_the_same_card_notifications_as_the_coach(staff_ctx):
    ctx, assistant = staff_ctx
    from apps.sport import services as sport_services

    event = SessionFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season).event
    sport_services.record_incident(
        event=event,
        membership=ctx.player,
        incident_type=Incident.IncidentType.RED_CARD,
        cause=Incident.Cause.SERIOUS_FOUL,
        recorded_by=ctx.coach.user,
    )
    assert Notification.objects.filter(recipient=assistant.user, event_type="card_or_suspension").exists()


@pytest.mark.parametrize("who", ["coach", "assistant"])
def test_medical_is_limited_to_aptitude_for_coach_and_assistant(who):
    ctx = build_medical_club_context()
    assistant = make_member(ctx.club, roles=[ASSISTANT])
    actor = ctx.coach if who == "coach" else assistant
    client = client_for(actor.user)

    # Page Medical (liste d'aptitudes) accessible et consultation journalisee.
    page = client.get(reverse("medical:page-unfit"))
    assert page.status_code == status.HTTP_200_OK
    assert AuditLog.objects.filter(action_type="medical.fitness_list.viewed", actor=actor.user).exists()

    # Declaration d'une blessure : permise.
    injury = client.post(
        reverse("medical:injury-list"),
        {"membership_id": ctx.player.pk, "circumstances": "Chute au sol."},
        format="json",
    )
    assert injury.status_code == status.HTTP_201_CREATED, injury.data

    # Jamais le dossier medical ni l'ecriture clinique.
    assert client.get(reverse("medical:health-record-detail", args=[ctx.player.pk])).status_code == 403
    assert (
        client.patch(
            reverse("medical:fitness-update", args=[ctx.player.pk]), {"fitness_status": "fit"}, format="json"
        ).status_code
        == 403
    )
    assert client.get(reverse("medical:page-to-complete")).status_code == 403


def test_assistant_shape_of_fitness_list_is_identical_to_the_coach():
    ctx = build_medical_club_context()
    assistant = make_member(ctx.club, roles=[ASSISTANT])
    coach_page = client_for(ctx.coach.user).get(reverse("medical:page-unfit")).data
    assistant_page = client_for(assistant.user).get(reverse("medical:page-unfit")).data
    assert coach_page == assistant_page


def test_logistics_and_mercato_follow_the_coach(staff_ctx):
    ctx, assistant = staff_ctx
    for actor in (ctx.coach, assistant):
        assert client_for(actor.user).get(reverse("logistics:overview")).status_code == status.HTTP_200_OK
        assert client_for(actor.user).get(reverse("mercato:market-list")).status_code == status.HTTP_200_OK
    assert client_for(ctx.player.user).get(reverse("logistics:overview")).status_code == status.HTTP_403_FORBIDDEN


def test_assistant_still_subject_to_the_usual_player_rules(staff_ctx):
    """Un assistant en dette reste non composable (regle 5 de CLAUDE.md)."""

    from apps.sport import services as sport_services
    from apps.sport.tests.conftest import make_debtor

    ctx, assistant = staff_ctx
    make_debtor(ctx.club, assistant)
    assert sport_services.get_playability(assistant).eligible is False


@pytest.mark.django_db(transaction=True)
def test_migration_0012_is_reversible_on_the_test_database():
    """Aller-retour sur la base de test uniquement (jamais sur db.sqlite3)."""

    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    previous = [("clubs", "0011_add_secretary_role")]
    latest = [("clubs", "0012_add_assistant_coach_role")]
    # Revenir a 0011 deroule aussi les migrations dependantes des autres apps :
    # on reapplique toutes les feuilles du graphe pour restaurer la base de test.
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        executor = MigrationExecutor(connection)
        assert latest[0] not in executor.loader.applied_migrations
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(leaves)
    assert latest[0] in MigrationExecutor(connection).loader.applied_migrations
