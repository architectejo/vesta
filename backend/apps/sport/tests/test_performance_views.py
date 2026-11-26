"""Tests de performance : API REST, rôles, étanchéité, migrations."""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.factories import SuperuserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.sport import performance
from apps.sport.models import PerformanceResult
from apps.sport.tests.conftest import client_for, make_member
from apps.sport.tests.stats_helpers import pointed_session

pytestmark = pytest.mark.django_db

SPRINT_30 = {"name": "Sprint 30 m", "kind": "timed_distance", "distance_m": "30"}

STAFF_READERS = ("coach", "president", "vice_president", "sports_director")
OTHERS = ("captain", "doctor", "player", "debtor")


def api(user):
    return client_for(user)


def make_test(ctx, data=None):
    return performance.create_performance_test(club=ctx.club, actor=ctx.coach.user, data=data or SPRINT_30)


@pytest.fixture
def session(ctx):
    return pointed_session(ctx, ctx.player, ctx.captain, ctx.debtor)


@pytest.fixture
def measured(ctx, session):
    """Un test mesuré pour le joueur (4,52 s) et le capitaine (4,80 s)."""

    test = make_test(ctx)
    outcome = performance.record_results(
        event=session.event, test=test, method="stopwatch", actor=ctx.coach.user,
        items=[{"membership_id": ctx.player.pk, "time_ms": 4520}, {"membership_id": ctx.captain.pk, "time_ms": 4800}],
    )
    return test, [row["result"] for row in outcome["results"]]


def bulk_url(session):
    return reverse("sport:event-performance-results-bulk", args=[session.event.pk])


# ---------------------------------------------------------------------------
# Catalogue : création, lecture, rôles
# ---------------------------------------------------------------------------


def test_coach_creates_a_test_through_the_api(ctx):
    response = api(ctx.coach.user).post(reverse("sport:performance-test-list"), SPRINT_30, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    body = response.data
    assert (body["name"], body["kind"], body["distance_m"], body["unit"], body["higher_is_better"]) == (
        "Sprint 30 m", "timed_distance", "30.00", "seconds", False,
    )
    assert body["kind_text"] == "Chrono sur 30 m" and body["stopwatch_available"] is True
    assert body["archived"] is False and body["has_results"] is False


def test_invalid_test_returns_a_french_error(ctx):
    response = api(ctx.coach.user).post(
        reverse("sport:performance-test-list"), {"name": "Poids", "kind": "free", "unit": "kg", "higher_is_better": True}, format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["detail"] == "Choisissez une unité dans la liste."


@pytest.mark.parametrize("role", ["president", "vice_president", "captain", "sports_director", "doctor", "player"])
def test_only_coach_and_assistant_write_tests(ctx, role):
    user = getattr(ctx, role).user
    assert api(user).post(reverse("sport:performance-test-list"), SPRINT_30, format="json").status_code == status.HTTP_403_FORBIDDEN
    test = make_test(ctx)
    assert api(user).patch(reverse("sport:performance-test-detail", args=[test.pk]), {"name": "Autre"}, format="json").status_code == status.HTTP_403_FORBIDDEN
    assert api(user).post(reverse("sport:performance-test-archive", args=[test.pk])).status_code == status.HTTP_403_FORBIDDEN


def test_assistant_coach_can_write(ctx):
    assistant = make_member(ctx.club, roles=[MembershipRole.Role.ASSISTANT_COACH])
    assert api(assistant.user).post(reverse("sport:performance-test-list"), SPRINT_30, format="json").status_code == status.HTTP_201_CREATED


@pytest.mark.parametrize("role", STAFF_READERS)
def test_staff_roles_read_the_catalogue(ctx, role):
    make_test(ctx)
    response = api(getattr(ctx, role).user).get(reverse("sport:performance-test-list"))
    assert response.status_code == status.HTTP_200_OK
    assert [row["name"] for row in response.data["results"]] == ["Sprint 30 m"]


@pytest.mark.parametrize("role", OTHERS)
def test_other_players_do_not_read_the_catalogue_or_rankings(ctx, role):
    test = make_test(ctx)
    user = getattr(ctx, role).user
    assert api(user).get(reverse("sport:performance-test-list")).status_code == status.HTTP_403_FORBIDDEN
    assert api(user).get(reverse("sport:performance-test-detail", args=[test.pk])).status_code == status.HTTP_403_FORBIDDEN
    assert api(user).get(reverse("sport:performance-test-leaderboard", args=[test.pk])).status_code == status.HTTP_403_FORBIDDEN


def test_patch_and_archive_through_the_api(ctx):
    test = make_test(ctx)
    client = api(ctx.coach.user)
    patched = client.patch(reverse("sport:performance-test-detail", args=[test.pk]), {"description": "Départ arrêté"}, format="json")
    assert patched.status_code == status.HTTP_200_OK and patched.data["description"] == "Départ arrêté"
    archived = client.post(reverse("sport:performance-test-archive", args=[test.pk]))
    assert archived.status_code == status.HTTP_200_OK and archived.data["archived"] is True
    listing = client.get(reverse("sport:performance-test-list"))
    assert listing.data["results"] == []
    only_archived = client.get(reverse("sport:performance-test-list"), {"archived": "only"})
    assert [row["name"] for row in only_archived.data["results"]] == ["Sprint 30 m"]
    assert client.post(reverse("sport:performance-test-archive", args=[test.pk])).status_code == status.HTTP_400_BAD_REQUEST


def test_templates_endpoint(ctx):
    response = api(ctx.coach.user).get(reverse("sport:performance-test-templates"))
    assert response.status_code == status.HTTP_200_OK
    assert {row["code"] for row in response.data["results"]} >= {"sprint_30", "cooper_12"}
    assert "donnée de santé" in response.data["health_help"]
    assert api(ctx.player.user).get(reverse("sport:performance-test-templates")).status_code == status.HTTP_403_FORBIDDEN


def test_tests_of_another_club_are_invisible(ctx, other_ctx):
    foreign = performance.create_performance_test(
        club=other_ctx.club, actor=other_ctx.coach.user, data=SPRINT_30
    )
    client = api(ctx.coach.user)
    assert client.get(reverse("sport:performance-test-list")).data["results"] == []
    for name in ("performance-test-detail", "performance-test-leaderboard"):
        assert client.get(reverse(f"sport:{name}", args=[foreign.pk])).status_code == status.HTTP_404_NOT_FOUND
    assert client.patch(reverse("sport:performance-test-detail", args=[foreign.pk]), {"name": "x"}, format="json").status_code == status.HTTP_404_NOT_FOUND
    assert client.post(reverse("sport:performance-test-archive", args=[foreign.pk])).status_code == status.HTTP_404_NOT_FOUND


def test_superuser_without_support_session_is_refused(ctx):
    test = make_test(ctx)
    superuser = SuperuserFactory()
    assert api(superuser).get(reverse("sport:performance-test-list")).status_code in (401, 403)
    assert api(superuser).post(reverse("sport:performance-test-archive", args=[test.pk])).status_code in (401, 403, 404)


# ---------------------------------------------------------------------------
# Enregistrement : forme JSON, idempotence, rôles
# ---------------------------------------------------------------------------


def test_bulk_endpoint_records_chrono_results(ctx, session):
    test = make_test(ctx)
    payload = {
        "test_id": test.pk, "method": "stopwatch", "start_mode": "group", "client_uuid": str(uuid.uuid4()),
        "items": [
            {"membership_id": ctx.player.pk, "attempt_no": 1, "time_ms": 4520, "client_uuid": str(uuid.uuid4())},
            {"membership_id": ctx.captain.pk, "time_ms": 4800, "client_uuid": str(uuid.uuid4())},
            {"membership_id": ctx.debtor.pk, "outcome": "dnf"},
            {"membership_id": ctx.president.pk, "time_ms": 4000},
        ],
    }
    response = api(ctx.coach.user).post(bulk_url(session), payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["counts"] == {"created": 3, "skipped": 0, "refused": 1}
    first = response.data["results"][0]
    assert first["outcome"] == "created" and first["message"] == "Mesure enregistrée." and first["warning"] == ""
    assert first["result"]["time_ms"] == 4520 and first["result"]["display"] == "4,52 s"
    assert first["result"]["derived"]["speed_kmh"] == "23.9" and first["result"]["derived"]["speed_ms"] == "6.64"
    assert response.data["results"][2]["result"]["outcome"] == "dnf" and response.data["results"][2]["result"]["display"] == "Abandon"
    refused = response.data["results"][3]
    assert refused["outcome"] == "refused" and "n'est pas pointé" in refused["message"] and refused["result"] is None
    # Renvoi à l'identique (coupure réseau) : rien n'est dupliqué.
    again = api(ctx.coach.user).post(bulk_url(session), payload, format="json")
    assert again.status_code == status.HTTP_200_OK
    assert again.data["counts"]["created"] == 0 and again.data["counts"]["skipped"] == 3
    assert PerformanceResult.all_objects.filter(club=ctx.club).count() == 3


@pytest.mark.parametrize("role", ["president", "vice_president", "captain", "sports_director", "doctor", "player"])
def test_bulk_is_forbidden_to_other_roles(ctx, session, role):
    test = make_test(ctx)
    payload = {"test_id": test.pk, "method": "manual", "items": [{"membership_id": ctx.player.pk, "time_ms": 4520}]}
    assert api(getattr(ctx, role).user).post(bulk_url(session), payload, format="json").status_code == status.HTTP_403_FORBIDDEN
    assert PerformanceResult.all_objects.count() == 0


def test_bulk_rejects_foreign_event_test_and_players(ctx, other_ctx, session):
    foreign_session = pointed_session(other_ctx, other_ctx.player)
    foreign_test = performance.create_performance_test(club=other_ctx.club, actor=other_ctx.coach.user, data=SPRINT_30)
    test = make_test(ctx)
    client = api(ctx.coach.user)
    item = [{"membership_id": ctx.player.pk, "time_ms": 4520}]
    assert client.post(bulk_url(foreign_session), {"test_id": test.pk, "method": "manual", "items": item}, format="json").status_code == status.HTTP_404_NOT_FOUND
    assert client.post(bulk_url(session), {"test_id": foreign_test.pk, "method": "manual", "items": item}, format="json").status_code == status.HTTP_404_NOT_FOUND
    foreign_player = [{"membership_id": other_ctx.player.pk, "time_ms": 4520}]
    response = client.post(bulk_url(session), {"test_id": test.pk, "method": "manual", "items": foreign_player}, format="json")
    assert response.data["counts"]["refused"] == 1 and PerformanceResult.all_objects.count() == 0


def test_bulk_lot_errors_are_in_french(ctx, session):
    test = make_test(ctx)
    client = api(ctx.coach.user)
    empty = client.post(bulk_url(session), {"test_id": test.pk, "method": "manual", "items": []}, format="json")
    assert empty.status_code == status.HTTP_400_BAD_REQUEST and empty.data["detail"] == "Cochez au moins un joueur."
    bad_method = client.post(bulk_url(session), {"test_id": test.pk, "method": "x", "items": [{"membership_id": ctx.player.pk, "time_ms": 1}]}, format="json")
    assert bad_method.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Lecture des résultats d'une séance : staff = tout, joueur = les siens
# ---------------------------------------------------------------------------


def results_url(session):
    return reverse("sport:event-performance-results", args=[session.event.pk])


def test_staff_reads_all_results_of_a_session(ctx, session, measured):
    test, _ = measured
    for role in STAFF_READERS:
        response = api(getattr(ctx, role).user).get(results_url(session), {"test": test.pk})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["scope"] == "all" and response.data["summary"]["measured_count"] == 2
        assert [row["rank"] for row in response.data["results"]] == [1, 2]
        assert response.data["results"][0]["player"]["membership_id"] == ctx.player.pk


def test_player_reads_only_his_own_results(ctx, session, measured):
    test, _ = measured
    response = api(ctx.player.user).get(results_url(session), {"test": test.pk})
    assert response.status_code == status.HTTP_200_OK and response.data["scope"] == "mine"
    assert [row["player"]["membership_id"] for row in response.data["results"]] == [ctx.player.pk]
    assert response.data["my_best_overall"]["display"] == "4,52 s"
    assert "4,80" not in str(response.data) and "4800" not in str(response.data)
    # Le capitaine et le médecin sont des joueurs comme les autres : leurs seules mesures.
    captain = api(ctx.captain.user).get(results_url(session), {"test": test.pk})
    assert [row["player"]["membership_id"] for row in captain.data["results"]] == [ctx.captain.pk]
    doctor = api(ctx.doctor.user).get(results_url(session), {"test": test.pk})
    assert doctor.data["results"] == [] and doctor.data["my_best_overall"] is None


def test_results_require_a_test_and_stay_in_the_club(ctx, other_ctx, session, measured):
    test, _ = measured
    assert api(ctx.coach.user).get(results_url(session)).status_code == status.HTTP_400_BAD_REQUEST
    assert api(other_ctx.coach.user).get(results_url(session), {"test": test.pk}).status_code == status.HTTP_404_NOT_FOUND
    foreign_test = performance.create_performance_test(club=other_ctx.club, actor=other_ctx.coach.user, data=SPRINT_30)
    assert api(ctx.coach.user).get(results_url(session), {"test": foreign_test.pk}).status_code == status.HTTP_404_NOT_FOUND


def test_results_are_not_public(ctx, session, measured):
    from rest_framework.test import APIClient

    test, _ = measured
    assert APIClient().get(results_url(session), {"test": test.pk}).status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Détail, correction, retrait
# ---------------------------------------------------------------------------


def test_result_detail_visibility(ctx, measured):
    _test, (mine, theirs) = measured
    own = api(ctx.player.user).get(reverse("sport:performance-result-detail", args=[mine.pk]))
    assert own.status_code == status.HTTP_200_OK and own.data["display"] == "4,52 s"
    assert own.data["recorded_by"]["name"] == f"{ctx.coach.user.first_name} {ctx.coach.user.last_name}".strip()
    assert api(ctx.player.user).get(reverse("sport:performance-result-detail", args=[theirs.pk])).status_code == status.HTTP_404_NOT_FOUND
    assert api(ctx.president.user).get(reverse("sport:performance-result-detail", args=[theirs.pk])).status_code == status.HTTP_200_OK


def test_correct_and_void_through_the_api(ctx, measured):
    _test, (first, second) = measured
    client = api(ctx.coach.user)
    url = reverse("sport:performance-result-detail", args=[first.pk])
    missing_reason = client.patch(url, {"time_ms": 4600}, format="json")
    assert missing_reason.status_code == status.HTTP_400_BAD_REQUEST and missing_reason.data["detail"] == "Indiquez le motif."
    done = client.patch(url, {"time_ms": 4600, "reason": "Chrono arrêté trop tôt"}, format="json")
    assert done.status_code == status.HTTP_200_OK and done.data["display"] == "4,60 s"
    correction = done.data["corrections"][0]
    assert correction["reason"] == "Chrono arrêté trop tôt"
    assert (correction["before"]["display"], correction["after"]["display"]) == ("4,52 s", "4,60 s")
    assert correction["actor"]["id"] == ctx.coach.user.pk
    voided = client.post(reverse("sport:performance-result-void", args=[second.pk]), {"reason": "Joueur gêné"}, format="json")
    assert voided.status_code == status.HTTP_200_OK and voided.data["status"] == "voided"
    assert client.post(reverse("sport:performance-result-void", args=[second.pk]), {"reason": "x"}, format="json").status_code == status.HTTP_400_BAD_REQUEST
    no_reason = client.post(reverse("sport:performance-result-void", args=[first.pk]), {}, format="json")
    assert no_reason.status_code == status.HTTP_400_BAD_REQUEST and no_reason.data["detail"] == "Indiquez le motif."
    actions = set(AuditLog.objects.filter(club=ctx.club).values_list("action_type", flat=True))
    assert {"sport.performance_result_corrected", "sport.performance_result_voided"} <= actions


@pytest.mark.parametrize("role", ["president", "vice_president", "captain", "sports_director", "doctor", "player"])
def test_correction_and_void_are_coach_only(ctx, measured, role):
    _test, (first, _second) = measured
    client = api(getattr(ctx, role).user)
    assert client.patch(reverse("sport:performance-result-detail", args=[first.pk]), {"time_ms": 4000, "reason": "x"}, format="json").status_code == status.HTTP_403_FORBIDDEN
    assert client.post(reverse("sport:performance-result-void", args=[first.pk]), {"reason": "x"}, format="json").status_code == status.HTTP_403_FORBIDDEN
    first.refresh_from_db()
    assert first.time_ms == 4520 and first.status == "active"


def test_results_of_another_club_cannot_be_touched(ctx, other_ctx, measured):
    _test, (first, _second) = measured
    client = api(other_ctx.coach.user)
    assert client.get(reverse("sport:performance-result-detail", args=[first.pk])).status_code == status.HTTP_404_NOT_FOUND
    assert client.patch(reverse("sport:performance-result-detail", args=[first.pk]), {"time_ms": 1, "reason": "x"}, format="json").status_code == status.HTTP_404_NOT_FOUND
    assert client.post(reverse("sport:performance-result-void", args=[first.pk]), {"reason": "x"}, format="json").status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Classement, évolution, « mes mesures »
# ---------------------------------------------------------------------------


def test_leaderboard_shape(ctx, measured):
    test, _ = measured
    response = api(ctx.president.user).get(reverse("sport:performance-test-leaderboard", args=[test.pk]), {"period": "season"})
    assert response.status_code == status.HTTP_200_OK
    row = response.data["results"][0]
    assert row["rank"] == 1 and row["player"]["membership_id"] == ctx.player.pk
    assert row["display"] == "4,52 s" and row["measures_count"] == 1 and row["trend"] is None
    assert row["derived"]["speed_kmh"] == "23.9" and row["personal_record"] is True
    assert response.data["period"] == "season" and response.data["test"]["id"] == test.pk
    bad = api(ctx.president.user).get(reverse("sport:performance-test-leaderboard", args=[test.pk]), {"period": "all"})
    assert bad.status_code == status.HTTP_400_BAD_REQUEST


def test_player_endpoint_staff_or_self_only(ctx, measured):
    test, _ = measured
    url = reverse("sport:player-performance", args=[ctx.player.pk])
    assert api(ctx.player.user).get(url, {"test": test.pk}).status_code == status.HTTP_200_OK
    for role in STAFF_READERS:
        assert api(getattr(ctx, role).user).get(url, {"test": test.pk}).status_code == status.HTTP_200_OK
    for role in ("captain", "doctor", "debtor"):
        assert api(getattr(ctx, role).user).get(url, {"test": test.pk}).status_code == status.HTTP_404_NOT_FOUND
    overview = api(ctx.player.user).get(url)
    assert [row["test"]["name"] for row in overview.data["tests"]] == ["Sprint 30 m"]


def test_player_endpoint_does_not_cross_clubs(ctx, other_ctx, measured):
    test, _ = measured
    url = reverse("sport:player-performance", args=[ctx.player.pk])
    assert api(other_ctx.coach.user).get(url, {"test": test.pk}).status_code == status.HTTP_404_NOT_FOUND


def test_my_performance(ctx, measured):
    test, _ = measured
    client = api(ctx.player.user)
    overview = client.get(reverse("sport:performance-me"))
    assert overview.status_code == status.HTTP_200_OK
    assert overview.data["tests"][0]["best"]["display"] == "4,52 s" and overview.data["tests"][0]["results_count"] == 1
    evolution = client.get(reverse("sport:performance-me"), {"test": test.pk})
    assert evolution.data["best"]["display"] == "4,52 s" and evolution.data["progression"] is None
    assert [p["display"] for p in evolution.data["points"]] == ["4,52 s"]
    # Un joueur sans mesure reçoit des listes vides, jamais celles des autres.
    assert api(ctx.doctor.user).get(reverse("sport:performance-me")).data["tests"] == []
    assert api(SuperuserFactory()).get(reverse("sport:performance-me")).status_code in (401, 403)


def test_session_stats_embed_measures_by_role(ctx, session, measured):
    staff = api(ctx.coach.user).get(reverse("sport:session-stats", args=[session.pk])).data["measures"]
    assert staff[0]["name"] == "Sprint 30 m" and staff[0]["measured_count"] == 2
    assert staff[0]["best"]["player"]["membership_id"] == ctx.player.pk
    mine = api(ctx.captain.user).get(reverse("sport:session-stats", args=[session.pk])).data["measures"]
    assert mine[0]["measured_count"] == 1 and mine[0]["best"]["player"]["membership_id"] == ctx.captain.pk
    assert api(ctx.doctor.user).get(reverse("sport:session-stats", args=[session.pk])).data["measures"] == []


def test_no_health_data_in_any_payload(ctx, session, measured):
    test, _ = measured
    text = str(api(ctx.coach.user).get(results_url(session), {"test": test.pk}).data).lower()
    for forbidden in ("diagnostic", "blessure", "vo2", "vma", "kg", "bpm"):
        assert forbidden not in text


# ---------------------------------------------------------------------------
# Migrations : aller-retour sur la base de test uniquement
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_performance_migration_is_reversible_on_the_test_database():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    latest = [("sport", "0004_performance_tests")]
    previous = [("sport", "0003_match_result_post")]
    # Reappliquer toutes les feuilles du graphe : le retour arriere deroule
    # aussi les migrations dependantes des autres apps.
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        executor = MigrationExecutor(connection)
        assert latest[0] not in executor.loader.applied_migrations
        assert "sport_performancetest" not in connection.introspection.table_names()
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(leaves)
    assert latest[0] in MigrationExecutor(connection).loader.applied_migrations
    assert "sport_performancetest" in connection.introspection.table_names()


@pytest.mark.django_db(transaction=True)
def test_notification_event_migration_is_reversible_on_the_test_database():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    latest = [("notifications", "0008_performance_results_event")]
    previous = [("notifications", "0007_i_paid_rejected_event")]
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        assert latest[0] not in MigrationExecutor(connection).loader.applied_migrations
    finally:
        MigrationExecutor(connection).migrate(leaves)
    assert latest[0] in MigrationExecutor(connection).loader.applied_migrations


def test_migrations_create_no_data(ctx):
    from apps.sport.models import PerformanceTest

    assert PerformanceTest.all_objects.count() == 0
