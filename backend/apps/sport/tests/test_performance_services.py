"""Tests de performance : services (sport-statistiques-seance.md, partie C)."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.utils import timezone as django_timezone

from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.notifications.models import Notification
from apps.sport import performance, services
from apps.sport.models import (
    PerformanceResult,
    PerformanceResultCorrection,
    PerformanceRun,
    PerformanceTest,
)
from apps.sport.tests.conftest import make_member
from apps.sport.tests.factories import MatchFactory
from apps.sport.tests.stats_helpers import club_today, make_session, point, pointed_session

pytestmark = pytest.mark.django_db

SPRINT_30 = {"name": "Sprint 30 m", "kind": "timed_distance", "distance_m": "30"}
COOPER = {"name": "Cooper 12 min", "kind": "distance_in_time", "duration_s": 720}
SHOTS = {"name": "Tirs cadrés", "kind": "repetitions", "attempts": 10}
FREE = {"name": "Précision", "kind": "free", "unit": "points", "decimals": 1, "higher_is_better": True}


def make_test(ctx, data=None, actor=None):
    return performance.create_performance_test(club=ctx.club, actor=actor or ctx.coach.user, data=data or SPRINT_30)


def record(ctx, session, test, items, *, method="stopwatch", actor=None, **kwargs):
    return performance.record_results(
        event=session.event, test=test, method=method, items=items, actor=actor or ctx.coach.user, **kwargs
    )


def result_of(outcome, index=0):
    return outcome["results"][index]["result"]


@pytest.fixture
def session(ctx):
    return pointed_session(ctx, ctx.player, ctx.captain, ctx.debtor)


@pytest.fixture
def set_now(monkeypatch):
    def _set(moment):
        monkeypatch.setattr(django_timezone, "now", lambda: moment)

    return _set


# ---------------------------------------------------------------------------
# Catalogue de tests
# ---------------------------------------------------------------------------


def test_coach_and_assistant_create_tests_and_it_is_journaled(ctx):
    assistant = make_member(ctx.club, roles=[MembershipRole.Role.ASSISTANT_COACH])
    test = make_test(ctx)
    other = make_test(ctx, COOPER, actor=assistant.user)
    assert (test.kind, test.distance_m, test.higher_is_better, test.unit) == ("timed_distance", Decimal("30.00"), False, "seconds")
    assert (other.duration_s, other.higher_is_better, other.unit) == (720, True, "meters")
    entry = AuditLog.objects.get(action_type="sport.performance_test_created", object_id=str(test.pk))
    assert entry.actor_id == ctx.coach.user.pk and entry.club_id == ctx.club.pk


@pytest.mark.parametrize("role_attr", ["president", "vice_president", "captain", "sports_director", "doctor", "player"])
def test_other_roles_cannot_create_or_measure(ctx, session, role_attr):
    actor = getattr(ctx, role_attr).user
    with pytest.raises(services.SportPermissionError):
        make_test(ctx, actor=actor)
    test = make_test(ctx)
    with pytest.raises(services.SportPermissionError):
        record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4520}], actor=actor)


def test_test_name_is_unique_among_active_tests(ctx):
    test = make_test(ctx)
    with pytest.raises(services.SportValidationError, match="Un test porte déjà ce nom."):
        make_test(ctx, {**SPRINT_30, "name": "sprint 30 M"})
    performance.archive_performance_test(test=test, actor=ctx.coach.user)
    assert make_test(ctx).pk != test.pk  # le nom d'un test archivé peut être réutilisé


def test_names_are_not_shared_across_clubs(ctx, other_ctx):
    make_test(ctx)
    assert make_test(other_ctx, actor=other_ctx.coach.user).club_id == other_ctx.club.pk


@pytest.mark.parametrize(
    "data, message",
    [
        ({**SPRINT_30, "distance_m": "0"}, "distance entre 1 et 5"),
        ({**SPRINT_30, "distance_m": "5001"}, "distance entre 1 et 5"),
        ({"name": "x", "kind": "timed_distance"}, "distance entre 1 et 5"),
        ({**COOPER, "duration_s": 5}, "durée entre 10 secondes"),
        ({**COOPER, "duration_s": 3601}, "durée entre 10 secondes"),
        ({**SHOTS, "attempts": 101}, "entre 1 et 100"),
        ({**SHOTS, "attempts": 0}, "entre 1 et 100"),
        ({**FREE, "unit": "kg"}, "unité dans la liste"),
        ({**FREE, "unit": "bpm"}, "unité dans la liste"),
        ({**FREE, "unit": "cm"}, "unité dans la liste"),
        ({**FREE, "unit": ""}, "unité dans la liste"),
        ({**FREE, "decimals": 3}, "0, 1 ou 2"),
        ({**FREE, "higher_is_better": None}, "sens du classement"),
        ({**FREE, "name": ""}, "Saisissez un nom"),
        ({**FREE, "name": "x" * 61}, "60 caractères"),
        ({**FREE, "description": "x" * 301}, "300 caractères"),
        ({**FREE, "kind": "vo2max"}, "type de test"),
    ],
)
def test_invalid_test_definitions_are_refused(ctx, data, message):
    with pytest.raises(services.SportValidationError, match=message):
        make_test(ctx, data)
    assert PerformanceTest.all_objects.filter(club=ctx.club).count() == 0


def test_unit_list_is_closed_and_has_no_health_unit():
    assert set(PerformanceTest.Unit.values) == {"seconds", "meters", "kmh", "repetitions", "points", "percent"}
    assert performance.HEALTH_HELP.startswith("Les tests mesurent une performance sportive.")


def test_templates_are_served_from_code_without_creating_anything(ctx):
    templates = performance.list_templates()
    assert {"Sprint 30 m", "Sprint 10 m", "Navette 5 × 10 m", "Test de Cooper (12 min)", "Tirs cadrés sur 10",
            "Jongles en 1 minute"} == {t["name"] for t in templates}
    assert PerformanceTest.all_objects.count() == 0


def test_type_and_parameters_are_frozen_once_results_exist(ctx, session):
    test = make_test(ctx)
    performance.update_performance_test(test=test, actor=ctx.coach.user, data={"distance_m": "40"})  # sans résultat : permis
    record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 5000}])
    with pytest.raises(services.SportValidationError, match="des résultats existent"):
        performance.update_performance_test(test=test, actor=ctx.coach.user, data={"distance_m": "30"})
    with pytest.raises(services.SportValidationError, match="des résultats existent"):
        performance.update_performance_test(test=test, actor=ctx.coach.user, data={"kind": "repetitions"})
    renamed = performance.update_performance_test(
        test=test, actor=ctx.coach.user, data={"name": "Sprint 40 m", "description": "Départ lancé"}
    )
    assert renamed.name == "Sprint 40 m" and renamed.distance_m == Decimal("40.00")
    entry = AuditLog.objects.filter(action_type="sport.performance_test_updated", object_id=str(test.pk)).order_by("pk").last()
    assert entry.before["name"] == "Sprint 30 m" and entry.after["name"] == "Sprint 40 m"


def test_archived_test_is_no_longer_offered_but_results_stay_readable(ctx, session):
    test = make_test(ctx)
    record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4520}])
    performance.archive_performance_test(test=test, actor=ctx.coach.user)
    assert AuditLog.objects.filter(action_type="sport.performance_test_archived", object_id=str(test.pk)).exists()
    with pytest.raises(services.SportValidationError, match="archivé"):
        record(ctx, session, test, [{"membership_id": ctx.captain.pk, "time_ms": 4600}])
    with pytest.raises(services.SportValidationError, match="archivé"):
        performance.update_performance_test(test=test, actor=ctx.coach.user, data={"name": "Autre"})
    assert PerformanceResult.all_objects.filter(club=ctx.club, run__test=test).count() == 1
    active_names = {row["name"] for row in performance.get_tests_overview(club=ctx.club)}
    assert "Sprint 30 m" not in active_names
    archived = performance.get_tests_overview(club=ctx.club, include_archived="only")
    assert [row["name"] for row in archived] == ["Sprint 30 m"]
    with pytest.raises(services.SportValidationError, match="déjà archivé"):
        performance.archive_performance_test(test=test, actor=ctx.coach.user)


# ---------------------------------------------------------------------------
# Calculs exacts (Decimal)
# ---------------------------------------------------------------------------


def test_timed_distance_speed_is_exact_decimal(ctx, session):
    test = make_test(ctx)
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4520}])
    payload = performance.serialize_result_value(test, result_of(outcome))
    assert payload["display"] == "4,52 s"
    assert payload["derived"]["speed_ms"] == "6.64"  # 30 / 4,52 = 6,637
    assert payload["derived"]["speed_kmh"] == "23.9"  # 23,894
    assert payload["derived"]["speed_display"] == "23,9 km/h"
    assert payload["derived"]["speed_ms_display"] == "6,64 m/s"
    assert isinstance(result_of(outcome).time_ms, int)


@pytest.mark.parametrize(
    "distance, time_ms, speed_ms, speed_kmh",
    [
        ("100", 10000, "10.00", "36.0"),
        ("30", 4000, "7.50", "27.0"),
        ("10", 3000, "3.33", "12.0"),  # 3,3333 m/s ; 12 km/h exactement
        ("50", 7777, "6.43", "23.1"),
        ("5000", 1_200_000, "4.17", "15.0"),
    ],
)
def test_speed_rounding_table(ctx, session, distance, time_ms, speed_ms, speed_kmh):
    test = make_test(ctx, {"name": f"Test {distance}", "kind": "timed_distance", "distance_m": distance})
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": time_ms}])
    derived = performance.derived_values(test, result_of(outcome))
    assert (derived["speed_ms"], derived["speed_kmh"]) == (speed_ms, speed_kmh)


def test_long_times_are_displayed_in_minutes():
    assert performance.format_time_ms(65300) == "1 min 05,30 s"
    assert performance.format_time_ms(59994) == "59,99 s"
    assert performance.format_time_ms(59996) == "1 min 00,00 s"
    assert performance.format_time_ms(120000) == "2 min 00,00 s"


def test_cooper_speed_is_distance_over_duration(ctx, session):
    test = make_test(ctx, COOPER)
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "distance_m": "2650"}], method="manual")
    payload = performance.serialize_result_value(test, result_of(outcome))
    assert payload["display"] == "2 650 m"
    assert payload["derived"]["speed_ms"] == "3.68" and payload["derived"]["speed_kmh"] == "13.3"  # 13,25 arrondi


def test_repetitions_success_rate(ctx, session):
    test = make_test(ctx, SHOTS)
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "count": 7}], method="manual")
    payload = performance.serialize_result_value(test, result_of(outcome))
    assert payload["display"] == "7 sur 10" and payload["derived"]["success_rate"] == 70


def test_free_value_follows_decimals_and_unit(ctx, session):
    test = make_test(ctx, FREE)
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "value": "17.25"}], method="manual")
    assert result_of(outcome).value == Decimal("17.30")  # arrondi à 1 décimale, jamais en float
    assert performance.display_value(test, result_of(outcome)) == "17,3 pts"


def test_json_numbers_are_read_without_float_arithmetic(ctx, session):
    test = make_test(ctx, COOPER)
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "distance_m": 2650.1}], method="manual")
    assert result_of(outcome).distance_m == Decimal("2650.10")


def test_implausible_speed_gives_a_non_blocking_warning(ctx, session):
    test = make_test(ctx)
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 2000}], method="manual")
    item = outcome["results"][0]
    assert item["outcome"] == "created"  # non bloquant
    assert "paraît trop court" in item["warning"] and "2,4" in item["warning"]
    normal = record(ctx, session, test, [{"membership_id": ctx.captain.pk, "time_ms": 4500}], method="manual")
    assert normal["results"][0]["warning"] == ""


# ---------------------------------------------------------------------------
# Enregistrement : validations, joueurs mesurables, idempotence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "item, message",
    [
        ({"time_ms": 0}, "temps supérieur à 0"),
        ({"time_ms": -5}, "temps supérieur à 0"),
        ({}, "temps supérieur à 0"),
        ({"time_ms": "abc"}, "temps supérieur à 0"),
        ({"time_ms": 4520, "count": 3}, "ne correspond pas"),
        ({"outcome": "dnf", "time_ms": 4000}, "aucune valeur"),
        ({"outcome": "weird"}, "invalide"),
    ],
)
def test_invalid_chrono_items_are_refused_with_a_message(ctx, session, item, message):
    test = make_test(ctx)
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, **item}])
    assert outcome["results"][0]["outcome"] == "refused"
    assert message in outcome["results"][0]["message"]
    assert PerformanceResult.all_objects.count() == 0 and PerformanceRun.all_objects.count() == 0


def test_other_kinds_bounds(ctx, session):
    cooper, shots, free = make_test(ctx, COOPER), make_test(ctx, SHOTS), make_test(ctx, {**FREE, "unit": "percent"})
    player = ctx.player.pk
    assert "entre 0 et 10 000 m" in record(ctx, session, cooper, [{"membership_id": player, "distance_m": 10001}], method="manual")["results"][0]["message"]
    assert "entre 0 et 10 000 m" in record(ctx, session, cooper, [{"membership_id": player, "distance_m": 0}], method="manual")["results"][0]["message"]
    assert "ne peut pas dépasser 10 tentatives" in record(ctx, session, shots, [{"membership_id": player, "count": 11}], method="manual")["results"][0]["message"]
    assert record(ctx, session, shots, [{"membership_id": player, "count": 0}], method="manual")["results"][0]["outcome"] == "created"
    assert "entre 0 et 100" in record(ctx, session, free, [{"membership_id": player, "value": 101}], method="manual")["results"][0]["message"]
    assert "valeur positive" in record(ctx, session, free, [{"membership_id": player, "value": -1}], method="manual")["results"][0]["message"]


def test_stopwatch_only_for_timed_kinds_and_start_mode(ctx, session):
    shots = make_test(ctx, SHOTS)
    with pytest.raises(services.SportValidationError, match="chronomètre n'est pas disponible"):
        record(ctx, session, shots, [{"membership_id": ctx.player.pk, "count": 3}], method="stopwatch")
    with pytest.raises(services.SportValidationError, match="méthode"):
        record(ctx, session, shots, [{"membership_id": ctx.player.pk, "count": 3}], method="oracle")
    sprint = make_test(ctx)
    record(ctx, session, sprint, [{"membership_id": ctx.player.pk, "time_ms": 4500}])
    assert PerformanceRun.all_objects.get(test=sprint).start_mode == "group"  # défaut
    record(ctx, session, sprint, [{"membership_id": ctx.captain.pk, "time_ms": 4500}], start_mode="individual")
    assert PerformanceRun.all_objects.filter(test=sprint, start_mode="individual").count() == 1


def test_empty_and_oversized_batches(ctx, session):
    test = make_test(ctx)
    with pytest.raises(services.SportValidationError, match="au moins un joueur"):
        record(ctx, session, test, [])
    too_many = [{"membership_id": ctx.player.pk, "time_ms": 4000}] * (performance.BULK_MAX_ITEMS + 1)
    with pytest.raises(services.SportValidationError, match="ne peut pas dépasser"):
        record(ctx, session, test, too_many)


def test_only_pointed_players_are_measurable(ctx, session):
    test = make_test(ctx)
    outcome = record(ctx, session, test, [{"membership_id": ctx.president.pk, "time_ms": 4500}])
    assert outcome["results"][0]["outcome"] == "refused"
    assert "n'est pas pointé" in outcome["results"][0]["message"]
    assert PerformanceRun.all_objects.count() == 0


def test_player_in_debt_and_late_arrival_are_measurable(ctx):
    """C-Q4 : seule l'inaptitude bloque ; dette, retard : mesurables."""

    late = make_member(ctx.club)
    session = pointed_session(ctx, ctx.debtor)
    point(ctx, session, late, status="late_absent")
    test = make_test(ctx)
    outcome = record(
        ctx, session, test,
        [{"membership_id": ctx.debtor.pk, "time_ms": 4800}, {"membership_id": late.pk, "time_ms": 5000}],
    )
    assert outcome["counts"] == {"created": 2, "skipped": 0, "refused": 0}
    assert services.get_playability(ctx.debtor).eligible is False  # bien en dette, et pourtant mesuré


def test_unfit_player_is_never_measurable(ctx, session, monkeypatch):
    test = make_test(ctx)
    monkeypatch.setattr(
        performance, "_get_medical_unfitness",
        lambda membership, at_date=None: ("Inapte · retour prévu le 01/12/2026", None) if membership.pk == ctx.player.pk else None,
    )
    outcome = record(
        ctx, session, test,
        [{"membership_id": ctx.player.pk, "time_ms": 4500}, {"membership_id": ctx.captain.pk, "time_ms": 4700}],
    )
    first, second = outcome["results"]
    assert first["outcome"] == "refused"
    assert first["message"].endswith("est inapte : il ne peut pas être mesuré.")
    assert "retour" not in first["message"] and "01/12" not in first["message"]  # jamais de détail médical
    assert second["outcome"] == "created"


def test_restricted_fitness_is_still_measurable(ctx, session, monkeypatch):
    test = make_test(ctx)
    monkeypatch.setattr(performance, "_get_medical_unfitness", lambda membership, at_date=None: None)
    assert record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4500}])["counts"]["created"] == 1


def test_only_sessions_and_same_club_objects(ctx, other_ctx, session):
    test = make_test(ctx)
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)
    with pytest.raises(services.SportValidationError, match="séance d'entraînement"):
        record(ctx, match, test, [{"membership_id": ctx.player.pk, "time_ms": 4500}])
    foreign_test = make_test(other_ctx, actor=other_ctx.coach.user)
    with pytest.raises(services.SportValidationError, match="n'existe pas dans ce club"):
        record(ctx, session, foreign_test, [{"membership_id": ctx.player.pk, "time_ms": 4500}])
    outcome = record(ctx, session, test, [{"membership_id": other_ctx.player.pk, "time_ms": 4500}])
    assert outcome["results"][0]["outcome"] == "refused"
    assert "n'existe pas dans ce club" in outcome["results"][0]["message"]


def test_client_uuid_makes_the_upload_idempotent(ctx, session):
    test = make_test(ctx)
    run_uuid, item_uuid = uuid.uuid4(), uuid.uuid4()
    items = [{"membership_id": ctx.player.pk, "time_ms": 4520, "client_uuid": item_uuid}]
    first = record(ctx, session, test, items, client_uuid=run_uuid)
    again = record(ctx, session, test, items, client_uuid=run_uuid)
    assert first["counts"]["created"] == 1
    assert again["counts"] == {"created": 0, "skipped": 1, "refused": 0}
    assert again["results"][0]["result"].pk == first["results"][0]["result"].pk
    assert PerformanceRun.all_objects.count() == 1 and PerformanceResult.all_objects.count() == 1
    assert AuditLog.objects.filter(action_type="sport.performance_result_recorded").count() == 1


def test_item_uuid_cannot_be_reused_for_another_player(ctx, session):
    test = make_test(ctx)
    shared = uuid.uuid4()
    record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4520, "client_uuid": shared}])
    outcome = record(ctx, session, test, [{"membership_id": ctx.captain.pk, "time_ms": 4600, "client_uuid": shared}])
    assert outcome["results"][0]["outcome"] == "refused"
    assert PerformanceResult.all_objects.count() == 1


def test_run_uuid_cannot_be_reused_for_another_test(ctx, session):
    sprint, cooper = make_test(ctx), make_test(ctx, COOPER)
    shared = uuid.uuid4()
    record(ctx, session, sprint, [{"membership_id": ctx.player.pk, "time_ms": 4520}], client_uuid=shared)
    with pytest.raises(services.SportValidationError, match="déjà utilisé"):
        record(ctx, session, cooper, [{"membership_id": ctx.player.pk, "distance_m": 2000}], method="manual", client_uuid=shared)


def test_replay_after_the_window_is_skipped_not_refused(ctx, session, set_now):
    test = make_test(ctx)
    item_uuid = uuid.uuid4()
    items = [{"membership_id": ctx.player.pk, "time_ms": 4520, "client_uuid": item_uuid}]
    record(ctx, session, test, items)
    set_now(services.evaluation_locks_at(session.event) + datetime.timedelta(minutes=1))
    assert record(ctx, session, test, items)["results"][0]["outcome"] == "skipped"


def test_attempt_numbers_are_assigned_per_player_and_never_clash(ctx, session):
    test = make_test(ctx)
    first = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4700}])
    second = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4500, "attempt_no": 1}])  # un autre téléphone
    third = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4600}])
    assert [result_of(o).attempt_no for o in (first, second, third)] == [1, 2, 3]
    assert {r.run.recorded_by_id for r in PerformanceResult.all_objects.select_related("run")} == {ctx.coach.user.pk}


def test_dnf_is_stored_without_value_and_never_ranked(ctx, session):
    test = make_test(ctx)
    record(ctx, session, test, [
        {"membership_id": ctx.player.pk, "outcome": "dnf"},
        {"membership_id": ctx.captain.pk, "time_ms": 4800},
    ])
    dnf = PerformanceResult.all_objects.get(membership=ctx.player)
    assert (dnf.time_ms, dnf.outcome) == (None, "dnf")
    board = performance.get_leaderboard(club=ctx.club, test=test, period="last")
    assert [row["player"]["membership_id"] for row in board["results"]] == [ctx.captain.pk]
    data = performance.get_event_results(
        event=session.event, test=test, viewer=ctx.coach.user, viewer_membership=ctx.coach, sees_all=True
    )
    assert [row["player"]["membership_id"] for row in data["dnf"]] == [ctx.player.pk]
    assert data["summary"]["measured_count"] == 1


def test_window_closes_after_the_evaluation_period(ctx, session, set_now):
    test = make_test(ctx)
    set_now(services.evaluation_locks_at(session.event) + datetime.timedelta(minutes=1))
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4520}])
    assert outcome["results"][0]["outcome"] == "refused"
    assert "période de saisie des mesures" in outcome["results"][0]["message"]


def test_each_result_is_journaled_with_its_author(ctx, session):
    test = make_test(ctx)
    outcome = record(ctx, session, test, [
        {"membership_id": ctx.player.pk, "time_ms": 4520},
        {"membership_id": ctx.captain.pk, "time_ms": 4600},
    ])
    entries = AuditLog.objects.filter(action_type="sport.performance_result_recorded").order_by("pk")
    assert entries.count() == 2
    assert {e.actor_id for e in entries} == {ctx.coach.user.pk}
    assert {e.after["run_id"] for e in entries} == {outcome["run_id"]}
    assert entries[0].after["time_ms"] == 4520 and entries[0].after["event_id"] == session.event.pk


# ---------------------------------------------------------------------------
# Corrections et retraits
# ---------------------------------------------------------------------------


@pytest.fixture
def recorded(ctx, session):
    test = make_test(ctx)
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4520}])
    return test, result_of(outcome)


def test_correction_creates_a_line_with_reason_and_author(ctx, recorded):
    test, result = recorded
    corrected = performance.correct_result(result=result, actor=ctx.coach.user, reason="Chrono arrêté trop tôt", data={"time_ms": 4610})
    assert corrected.time_ms == 4610
    correction = PerformanceResultCorrection.all_objects.get(result=result)
    assert (correction.old_time_ms, correction.new_time_ms) == (4520, 4610)
    assert correction.reason == "Chrono arrêté trop tôt" and correction.actor_id == ctx.coach.user.pk
    assert (correction.old_status, correction.new_status) == ("active", "active")
    entry = AuditLog.objects.get(action_type="sport.performance_result_corrected")
    assert entry.before["time_ms"] == 4520 and entry.after["time_ms"] == 4610
    assert entry.after["reason"] == "Chrono arrêté trop tôt" and entry.actor_id == ctx.coach.user.pk
    detail = performance.get_result_detail(result=corrected, viewer=ctx.coach.user)
    assert detail["corrections"][0]["before"]["display"] == "4,52 s" and detail["corrections"][0]["after"]["display"] == "4,61 s"


def test_correction_needs_a_reason_a_change_and_a_coach(ctx, recorded):
    _test, result = recorded
    with pytest.raises(services.SportValidationError, match="Indiquez le motif"):
        performance.correct_result(result=result, actor=ctx.coach.user, reason="  ", data={"time_ms": 4610})
    with pytest.raises(services.SportValidationError, match="Aucun changement"):
        performance.correct_result(result=result, actor=ctx.coach.user, reason="x", data={"time_ms": 4520})
    with pytest.raises(services.SportPermissionError):
        performance.correct_result(result=result, actor=ctx.president.user, reason="x", data={"time_ms": 4610})
    with pytest.raises(services.SportValidationError, match="temps supérieur à 0"):
        performance.correct_result(result=result, actor=ctx.coach.user, reason="x", data={"time_ms": 0})
    assert PerformanceResultCorrection.all_objects.count() == 0


def test_correction_is_locked_after_the_window(ctx, recorded, set_now):
    _test, result = recorded
    set_now(services.evaluation_locks_at(result.run.event) + datetime.timedelta(minutes=1))
    with pytest.raises(services.SportValidationError, match="Résultat verrouillé"):
        performance.correct_result(result=result, actor=ctx.coach.user, reason="x", data={"time_ms": 4610})
    with pytest.raises(services.SportValidationError, match="Résultat verrouillé"):
        performance.void_result(result=result, actor=ctx.coach.user, reason="x")


def test_void_keeps_the_row_and_removes_it_from_rankings(ctx, session, recorded):
    test, result = recorded
    other = record(ctx, session, test, [{"membership_id": ctx.captain.pk, "time_ms": 4800}])
    performance.void_result(result=result, actor=ctx.coach.user, reason="Joueur parti avant le signal")
    result.refresh_from_db()
    assert result.status == "voided" and PerformanceResult.all_objects.filter(pk=result.pk).exists()
    correction = PerformanceResultCorrection.all_objects.get(result=result)
    assert (correction.old_status, correction.new_status, correction.reason) == ("active", "voided", "Joueur parti avant le signal")
    board = performance.get_leaderboard(club=ctx.club, test=test, period="last")
    assert [row["player"]["membership_id"] for row in board["results"]] == [ctx.captain.pk]
    assert AuditLog.objects.filter(action_type="sport.performance_result_voided", object_id=str(result.pk)).exists()
    with pytest.raises(services.SportValidationError, match="retiré"):
        performance.correct_result(result=result, actor=ctx.coach.user, reason="x", data={"time_ms": 4000})
    with pytest.raises(services.SportValidationError, match="Indiquez le motif"):
        performance.void_result(result=result_of(other), actor=ctx.coach.user, reason="")


def test_a_voided_attempt_number_is_never_reused(ctx, session, recorded):
    test, result = recorded
    performance.void_result(result=result, actor=ctx.coach.user, reason="Erreur")
    again = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4500}])
    assert result_of(again).attempt_no == 2


def test_results_and_corrections_are_never_deleted_or_rewritten(ctx, recorded):
    _test, result = recorded
    with pytest.raises(ProtectedError):
        result.delete()
    performance.correct_result(result=result, actor=ctx.coach.user, reason="x", data={"time_ms": 4610})
    correction = PerformanceResultCorrection.all_objects.get(result=result)
    with pytest.raises(ProtectedError):
        correction.delete()
    from django.core.exceptions import ValidationError

    correction.reason = "réécrit"
    with pytest.raises(ValidationError):
        correction.save()


# ---------------------------------------------------------------------------
# Lectures : classement, évolution, synthèses
# ---------------------------------------------------------------------------


def test_best_attempt_is_retained_and_ranks_share_ties(ctx, session):
    test = make_test(ctx)
    record(ctx, session, test, [
        {"membership_id": ctx.player.pk, "time_ms": 4700},
        {"membership_id": ctx.captain.pk, "time_ms": 4500},
        {"membership_id": ctx.debtor.pk, "time_ms": 4500},
    ])
    record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4400}])  # essai 2, meilleur
    record(ctx, session, test, [{"membership_id": ctx.captain.pk, "time_ms": 9000}])  # essai 2, moins bon
    data = performance.get_event_results(
        event=session.event, test=test, viewer=ctx.coach.user, viewer_membership=None, sees_all=True
    )
    rows = data["results"]
    assert [(r["player"]["membership_id"], r["rank"], r["time_ms"]) for r in rows] == [
        (ctx.player.pk, 1, 4400), (ctx.captain.pk, 2, 4500), (ctx.debtor.pk, 2, 4500),
    ]
    assert rows[0]["attempt_no"] == 2 and rows[0]["attempts_count"] == 2
    assert rows[1]["attempt_no"] == 1 and rows[1]["attempts_count"] == 2
    assert rows[0]["personal_record"] is True
    assert data["summary"]["best"] == "4,40 s"


def test_higher_is_better_kinds_rank_descending(ctx, session):
    test = make_test(ctx, COOPER)
    record(ctx, session, test, [
        {"membership_id": ctx.player.pk, "distance_m": 2400},
        {"membership_id": ctx.captain.pk, "distance_m": 2650},
    ], method="manual")
    board = performance.get_leaderboard(club=ctx.club, test=test, period="last")
    assert [row["player"]["membership_id"] for row in board["results"]] == [ctx.captain.pk, ctx.player.pk]


def test_leaderboard_last_and_season_scopes_with_trend(ctx):
    from apps.sport.tests.stats_helpers import backdate_members

    backdate_members(ctx)
    test = make_test(ctx)
    old = pointed_session(ctx, ctx.player, ctx.captain, days_ago=5)
    recent = pointed_session(ctx, ctx.player, days_ago=0)
    # Séance passée : saisie directe (la fenêtre est fermée) par le Superuser, comme le support le ferait.
    from apps.accounts.tests.factories import SuperuserFactory

    performance.record_results(
        event=old.event, test=test, method="manual", actor=SuperuserFactory(),
        items=[{"membership_id": ctx.player.pk, "time_ms": 4600}, {"membership_id": ctx.captain.pk, "time_ms": 4300}],
    )
    record(ctx, recent, test, [{"membership_id": ctx.player.pk, "time_ms": 4480}])

    last = performance.get_leaderboard(club=ctx.club, test=test, period="last")
    assert last["event"]["id"] == recent.event.pk
    assert [row["player"]["membership_id"] for row in last["results"]] == [ctx.player.pk]
    assert last["results"][0]["trend"] == {
        "direction": "progress", "delta": "-120", "delta_display": "0,12 s", "text": "en progrès de 0,12 s",
    }
    season = performance.get_leaderboard(club=ctx.club, test=test, period="season")
    assert [(r["player"]["membership_id"], r["rank"]) for r in season["results"]] == [(ctx.captain.pk, 1), (ctx.player.pk, 2)]
    assert season["results"][1]["measures_count"] == 2
    assert season["results"][0]["trend"] is None  # une seule mesure
    with pytest.raises(services.SportValidationError, match="Période invalide"):
        performance.get_leaderboard(club=ctx.club, test=test, period="year")


def test_regress_direction_follows_the_test_sense(ctx):
    from apps.accounts.tests.factories import SuperuserFactory
    from apps.sport.tests.stats_helpers import backdate_members

    backdate_members(ctx)
    test = make_test(ctx, COOPER)
    first = pointed_session(ctx, ctx.player, days_ago=3)
    second = pointed_session(ctx, ctx.player, days_ago=0)
    performance.record_results(event=first.event, test=test, method="manual", actor=SuperuserFactory(),
                               items=[{"membership_id": ctx.player.pk, "distance_m": 2700}])
    record(ctx, second, test, [{"membership_id": ctx.player.pk, "distance_m": 2650}], method="manual")
    evolution = performance.get_player_evolution(membership=ctx.player, test=test)
    assert evolution["progression"]["direction"] == "regress"
    assert evolution["progression"]["text"] == "en recul de 50 m depuis la première mesure"
    assert evolution["best"]["display"] == "2 700 m" and evolution["last"]["display"] == "2 650 m"
    assert [p["display"] for p in evolution["points"]] == ["2 700 m", "2 650 m"]
    assert evolution["results"][1]["personal_record"] is True and evolution["results"][0]["personal_record"] is False


def test_evolution_legend_for_time_tests_and_overview(ctx):
    from apps.accounts.tests.factories import SuperuserFactory
    from apps.sport.tests.stats_helpers import backdate_members

    backdate_members(ctx)
    test = make_test(ctx)
    first = pointed_session(ctx, ctx.player, days_ago=3)
    second = pointed_session(ctx, ctx.player, days_ago=0)
    performance.record_results(event=first.event, test=test, method="manual", actor=SuperuserFactory(),
                               items=[{"membership_id": ctx.player.pk, "time_ms": 4830}])
    record(ctx, second, test, [{"membership_id": ctx.player.pk, "time_ms": 4520}])
    evolution = performance.get_player_evolution(membership=ctx.player, test=test)
    assert evolution["progression"]["direction"] == "progress"
    assert evolution["progression"]["text"] == "en progrès de 0,31 s depuis la première mesure"
    assert evolution["progression"]["legend"] == "Plus bas = plus rapide"
    overview = performance.get_player_overview(membership=ctx.player)
    assert [row["test"]["name"] for row in overview["tests"]] == ["Sprint 30 m"]
    assert overview["tests"][0]["best"]["display"] == "4,52 s"
    assert overview["tests"][0]["results_count"] == 2
    assert performance.get_player_overview(membership=ctx.captain)["tests"] == []


def test_session_measures_summary_by_viewer(ctx, session):
    test = make_test(ctx)
    record(ctx, session, test, [
        {"membership_id": ctx.player.pk, "time_ms": 4700},
        {"membership_id": ctx.captain.pk, "time_ms": 4210},
    ])
    staff = performance.session_measures_summary(session.event, sees_all=True, viewer_membership=None)
    assert staff[0]["measured_count"] == 2 and staff[0]["best"]["player"]["membership_id"] == ctx.captain.pk
    assert staff[0]["best"]["display"] == "4,21 s"
    mine = performance.session_measures_summary(session.event, sees_all=False, viewer_membership=ctx.player)
    assert mine[0]["measured_count"] == 1 and mine[0]["best"]["player"]["membership_id"] == ctx.player.pk
    assert performance.session_measures_summary(session.event, sees_all=False, viewer_membership=ctx.debtor) == []


def test_reads_are_isolated_between_clubs(ctx, other_ctx, session):
    test = make_test(ctx)
    record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4500}])
    foreign_session = pointed_session(other_ctx, other_ctx.player)
    foreign_test = make_test(other_ctx, actor=other_ctx.coach.user)
    performance.record_results(event=foreign_session.event, test=foreign_test, method="manual",
                               actor=other_ctx.coach.user, items=[{"membership_id": other_ctx.player.pk, "time_ms": 4000}])
    board = performance.get_leaderboard(club=ctx.club, test=test, period="season")
    assert [row["player"]["membership_id"] for row in board["results"]] == [ctx.player.pk]
    assert [row["name"] for row in performance.get_tests_overview(club=ctx.club)] == ["Sprint 30 m"]
    assert performance.get_player_overview(membership=other_ctx.player)["tests"][0]["test"]["id"] == foreign_test.pk


# ---------------------------------------------------------------------------
# Notification « Vos mesures sont disponibles » (C-Q9)
# ---------------------------------------------------------------------------


def _notifications(user):
    return Notification.objects.filter(
        recipient=user, event_type=Notification.EventType.PERFORMANCE_RESULTS_AVAILABLE
    )


def test_notification_is_sent_one_hour_after_the_last_measure_once_per_player(ctx, session):
    sprint, cooper = make_test(ctx), make_test(ctx, COOPER)
    record(ctx, session, sprint, [{"membership_id": ctx.player.pk, "time_ms": 4500}])
    record(ctx, session, cooper, [{"membership_id": ctx.player.pk, "distance_m": 2500},
                                  {"membership_id": ctx.captain.pk, "distance_m": 2400}], method="manual")
    now = django_timezone.now()
    assert performance.notify_performance_results(club=ctx.club, now=now) == 0  # trop tôt
    later = now + datetime.timedelta(hours=1, minutes=1)
    assert performance.notify_performance_results(club=ctx.club, now=later) == 2
    assert performance.notify_performance_results(club=ctx.club, now=later) == 0  # idempotent
    assert _notifications(ctx.player.user).count() == 1  # une seule malgré deux tests
    note = _notifications(ctx.player.user).get()
    expected_date = session.event.event_date.strftime("%d/%m/%Y")
    assert note.body == f"Vos mesures de la séance du {expected_date} sont disponibles."
    assert note.club_id == ctx.club.pk and _notifications(ctx.debtor.user).count() == 0


def test_notification_waits_for_new_measures_and_is_not_repeated(ctx, session):
    test = make_test(ctx)
    record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4500}])
    later = django_timezone.now() + datetime.timedelta(hours=2)
    assert performance.notify_performance_results(club=ctx.club, now=later) == 1
    record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4400}])
    assert performance.notify_performance_results(club=ctx.club, now=later + datetime.timedelta(hours=3)) == 0


def test_voided_or_dnf_results_do_not_trigger_notifications(ctx, session):
    test = make_test(ctx)
    outcome = record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4500},
                                          {"membership_id": ctx.captain.pk, "outcome": "dnf"}])
    performance.void_result(result=result_of(outcome), actor=ctx.coach.user, reason="Erreur")
    assert performance.notify_performance_results(club=ctx.club, now=django_timezone.now() + datetime.timedelta(hours=2)) == 0


def test_notification_command_runs_for_every_club(ctx, other_ctx, session):
    from django.core.management import call_command

    test = make_test(ctx)
    record(ctx, session, test, [{"membership_id": ctx.player.pk, "time_ms": 4500}])
    foreign_session = pointed_session(other_ctx, other_ctx.player)
    foreign_test = make_test(other_ctx, actor=other_ctx.coach.user)
    performance.record_results(event=foreign_session.event, test=foreign_test, method="manual",
                               actor=other_ctx.coach.user, items=[{"membership_id": other_ctx.player.pk, "time_ms": 4000}])
    PerformanceResult.all_objects.update(created_at=django_timezone.now() - datetime.timedelta(hours=2))
    call_command("notify_performance_results")
    assert _notifications(ctx.player.user).count() == 1 and _notifications(other_ctx.player.user).count() == 1
    assert _notifications(ctx.player.user).get().club_id == ctx.club.pk
    call_command("notify_performance_results", "--club", str(ctx.club.pk))
    assert _notifications(ctx.player.user).count() == 1


# ---------------------------------------------------------------------------
# Contraintes de base de données (au-delà des contrôles de service)
# ---------------------------------------------------------------------------


def test_database_constraints_reject_invalid_rows(ctx, session):
    test = make_test(ctx)
    run = PerformanceRun.all_objects.create(club=ctx.club, event=session.event, test=test, method="manual", recorded_by=ctx.coach.user)
    base = dict(club=ctx.club, run=run, membership=ctx.player, attempt_no=1)
    good = PerformanceResult(**base, time_ms=4500)
    PerformanceResult.all_objects.bulk_create([good])
    for bad in (
        PerformanceResult(**base, time_ms=4600),  # même joueur, même épreuve, même essai
        PerformanceResult(club=ctx.club, run=run, membership=ctx.captain, attempt_no=1, time_ms=0),
        PerformanceResult(club=ctx.club, run=run, membership=ctx.captain, attempt_no=1, distance_m=Decimal("0")),
        PerformanceResult(club=ctx.club, run=run, membership=ctx.captain, attempt_no=1, distance_m=Decimal("10001")),
        PerformanceResult(club=ctx.club, run=run, membership=ctx.captain, attempt_no=1, value=Decimal("-1")),
        PerformanceResult(club=ctx.club, run=run, membership=ctx.captain, attempt_no=0, time_ms=4000),
        PerformanceResult(club=ctx.club, run=run, membership=ctx.captain, attempt_no=1, outcome="dnf", time_ms=4000),
    ):
        with pytest.raises(IntegrityError):
            from django.db import transaction

            with transaction.atomic():
                PerformanceResult.all_objects.bulk_create([bad])


def test_database_constraints_on_tests(ctx):
    from django.db import transaction

    for kwargs in (
        dict(kind="timed_distance", distance_m=Decimal("0")),
        dict(kind="timed_distance", distance_m=Decimal("5001")),
        dict(kind="distance_in_time", duration_s=9),
        dict(kind="repetitions", attempts=101),
        dict(kind="free", unit="kg"),
        dict(kind="free", unit="points", decimals=3),
    ):
        bad = PerformanceTest(club=ctx.club, name="x", created_by=ctx.coach.user, **kwargs)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                PerformanceTest.all_objects.bulk_create([bad])


def test_club_is_mandatory_and_cross_club_links_are_rejected(ctx, other_ctx):
    from django.core.exceptions import ValidationError

    test = make_test(ctx)
    foreign_session = make_session(other_ctx)
    with pytest.raises(ValidationError):
        PerformanceRun.all_objects.create(club=ctx.club, event=foreign_session.event, test=test, method="manual", recorded_by=ctx.coach.user)
    assert club_today(ctx) is not None
