"""Statistiques de séance et évolution (sport-statistiques-seance.md, parties A et B)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from apps.clubs.models import Membership
from apps.sport.models import Attendance
from apps.sport.tests.conftest import client_for, make_member
from apps.sport.tests.stats_helpers import (
    backdate_members,
    club_today,
    evaluate,
    extra_players,
    make_session,
    point,
    pointed_session,
)

pytestmark = pytest.mark.django_db

ROSTER_SIZE = 8  # président, VP, DS, médecin, coach, capitaine, joueur, joueur en dette (l'adhésion en attente est exclue)


def stats_url(session):
    return reverse("sport:session-stats", args=[session.pk])


def get_stats(user, session):
    return client_for(user).get(stats_url(session))


# ---------------------------------------------------------------------------
# A : présence
# ---------------------------------------------------------------------------


def test_attendance_counts_sum_to_expected_and_exclude_pending(ctx):
    session = make_session(ctx)
    point(ctx, session, ctx.player)
    point(ctx, session, ctx.captain, status=Attendance.Status.LATE_ABSENT)
    point(ctx, session, ctx.coach, status=Attendance.Status.EXCUSED_ABSENT, reason="Blessé : genou gauche")
    point(ctx, session, ctx.president, status=Attendance.Status.ABSENT)

    response = get_stats(ctx.player.user, session)
    assert response.status_code == status.HTTP_200_OK
    attendance = response.data["attendance"]
    assert attendance["expected"] == ROSTER_SIZE
    assert (attendance["present"], attendance["late"], attendance["excused"], attendance["absent"]) == (1, 1, 1, 5)
    assert attendance["present"] + attendance["late"] + attendance["excused"] + attendance["absent"] == ROSTER_SIZE
    # Retard compté absent par défaut (10.2 n° 25) : 1 présent sur 8 = 12,5 % -> 13.
    assert attendance["rate"] == 13
    assert attendance["late_counts_as_absent"] is True
    assert attendance["late_label"] == "En retard, compté absent"
    assert attendance["late_family"] == "danger"
    assert ctx.pending_member.pk not in {p["membership_id"] for p in attendance["absent_list"]}
    assert [p["membership_id"] for p in attendance["late_list"]] == [ctx.captain.pk]
    assert attendance["late_list"][0]["arrived_at"] is not None


def test_excused_list_never_exposes_the_detail(ctx):
    session = make_session(ctx)
    point(ctx, session, ctx.coach, status=Attendance.Status.EXCUSED_ABSENT, reason="Blessé : genou gauche, IRM lundi")
    point(ctx, session, ctx.captain, status=Attendance.Status.EXCUSED_ABSENT, reason="texte libre inattendu")

    response = get_stats(ctx.player.user, session)
    reasons = {item["membership_id"]: item["reason"] for item in response.data["attendance"]["excused_list"]}
    assert reasons == {ctx.coach.pk: "Blessé", ctx.captain.pk: "Autre"}
    assert "genou" not in str(response.data)


def test_late_counts_as_present_when_the_club_decides_so(ctx):
    from apps.clubs.models import ClubSettings

    ClubSettings.objects.filter(club=ctx.club).update(late_arrival_counts_absent=False)
    session = make_session(ctx)
    point(ctx, session, ctx.player)
    point(ctx, session, ctx.captain, status=Attendance.Status.LATE_ABSENT)

    attendance = get_stats(ctx.player.user, session).data["attendance"]
    assert attendance["rate"] == 25  # (1 présent + 1 retardataire) sur 8
    assert attendance["late_label"] == "En retard"
    assert attendance["late_family"] == "warning"


def test_nobody_marked_gives_no_rate(ctx):
    attendance = get_stats(ctx.player.user, make_session(ctx)).data["attendance"]
    assert attendance["rate"] is None
    assert attendance["nobody_marked"] is True
    assert attendance["present"] == 0 and attendance["absent"] == ROSTER_SIZE


def test_expected_players_depend_on_the_session_date(ctx):
    backdate_members(ctx)
    today = club_today(ctx)
    session = make_session(ctx, days_ago=10)
    # Arrivé après la séance : pas attendu. Parti après la séance : attendu ce jour-là.
    late_joiner = make_member(ctx.club, joined_on=today - datetime.timedelta(days=2))
    leaver = make_member(
        ctx.club, status=Membership.Status.DEPARTED, joined_on=today - datetime.timedelta(days=100),
        left_on=today - datetime.timedelta(days=3), left_reason=Membership.LeftReason.RESIGNATION,
    )
    cancelled = make_member(
        ctx.club, status=Membership.Status.DEPARTED, joined_on=today - datetime.timedelta(days=100),
        left_on=today - datetime.timedelta(days=50), left_reason=Membership.LeftReason.CANCELLED,
    )
    point(ctx, session, ctx.player)

    attendance = get_stats(ctx.player.user, session).data["attendance"]
    absent_ids = {p["membership_id"] for p in attendance["absent_list"]}
    assert late_joiner.pk not in absent_ids
    assert leaver.pk in absent_ids
    assert cancelled.pk not in absent_ids
    assert attendance["expected"] == ROSTER_SIZE + 1


def test_attendance_delta_needs_three_previous_sessions(ctx):
    backdate_members(ctx)
    everyone = [ctx.president, ctx.vice_president, ctx.sports_director, ctx.doctor, ctx.coach, ctx.captain, ctx.player, ctx.debtor]
    for days_ago in (3, 2):  # seulement 2 séances antérieures : pas d'écart
        pointed_session(ctx, *everyone[:4], days_ago=days_ago)
    current = pointed_session(ctx, *everyone, days_ago=0)
    assert get_stats(ctx.player.user, current).data["attendance"]["delta_vs_average"] is None

    pointed_session(ctx, *everyone[:4], days_ago=4)  # 3e séance antérieure : 50 % chacune
    assert get_stats(ctx.player.user, current).data["attendance"]["delta_vs_average"] == 50  # 100 % - 50 %


# ---------------------------------------------------------------------------
# A : notes du Coach, visibilité par rôle
# ---------------------------------------------------------------------------


@pytest.fixture
def rated(ctx):
    """Séance du jour : 5 joueurs pointés, 4 évalués (note retenue = moyenne des évaluateurs)."""

    players = extra_players(ctx, 3)
    session = pointed_session(ctx, ctx.player, ctx.captain, *players)
    evaluate(ctx, session, ctx.player, "8.0", evaluator=ctx.coach.user, technical_score=Decimal("7"), comment="Très bien", visible=True)
    evaluate(ctx, session, ctx.player, "9.0", evaluator=ctx.president.user, comment="Note privée", visible=False)
    evaluate(ctx, session, ctx.captain, "5.0")
    evaluate(ctx, session, players[0], "6.5")
    evaluate(ctx, session, players[1], "2.0")
    return session, players


def test_notes_block_aggregates_retained_notes(ctx, rated):
    session, players = rated
    block = get_stats(ctx.coach.user, session).data["evaluations"]
    # Note retenue du joueur 1 : moyenne (8 + 9) / 2 = 8,5. Moyenne séance : (8,5 + 5 + 6,5 + 2) / 4 = 5,5.
    assert block["average"] == "5.5"
    assert (block["evaluated"], block["eligible"]) == (4, 5)
    assert block["remaining"] == 1
    # 4 évalués : les deux listes se partagent l'effectif (2 + 2), sans répétition.
    assert [(row["rank"], row["note"]) for row in block["best"]] == [(1, "8.5"), (2, "6.5")]
    assert block["best"][0]["player"]["membership_id"] == ctx.player.pk
    assert [(row["rank"], row["note"]) for row in block["lowest"]] == [(1, "2.0"), (2, "5.0")]
    assert block["ranking_available"] is True
    distribution = {row["label"]: row["count"] for row in block["distribution"]}
    assert distribution == {"0 à 2": 0, "2 à 4": 1, "4 à 6": 1, "6 à 8": 1, "8 à 10": 1}
    mine = next(row for row in block["players"] if row["player"]["membership_id"] == ctx.player.pk)
    assert mine["overall"] == "8.5" and mine["evaluators_count"] == 2 and mine["technical"] == "7.0"
    assert {c["text"] for c in mine["comments"]} == {"Très bien", "Note privée"}
    assert [p["membership_id"] for p in block["not_evaluated"]] == [players[2].pk]
    assert block["locked"] is False and block["hours_left"] > 0


def test_ties_share_a_rank_and_are_all_listed(ctx):
    players = extra_players(ctx, 6)
    session = pointed_session(ctx, *players)
    for membership in players:
        evaluate(ctx, session, membership, "7.0")
    block = get_stats(ctx.coach.user, session).data["evaluations"]
    assert [row["rank"] for row in block["best"]] == [1, 1, 1, 1, 1]  # au plus 5 lignes
    assert block["lowest"] == []


@pytest.mark.parametrize(
    "notes, best, lowest",
    [
        (["8.0", "4.0"], ["8.0"], ["4.0"]),
        (["8.0", "6.0", "4.0"], ["8.0", "6.0"], ["4.0"]),
        (["9.0", "8.0", "7.0", "6.0", "5.0"], ["9.0", "8.0", "7.0"], ["5.0", "6.0"]),
        (["9.0", "8.0", "7.0", "6.0", "5.0", "4.0", "3.0"], ["9.0", "8.0", "7.0"], ["3.0", "4.0", "5.0"]),
    ],
)
def test_lowest_notes_shown_for_small_squads(ctx, notes, best, lowest):
    """Décision par défaut (A4.2 muette) : sous 6 évalués, meilleures = moitié
    haute, plus faibles = le reste ; jamais un joueur dans les deux listes."""

    players = extra_players(ctx, len(notes))
    session = pointed_session(ctx, *players)
    for membership, note in zip(players, notes):
        evaluate(ctx, session, membership, note)
    block = get_stats(ctx.coach.user, session).data["evaluations"]
    assert [row["note"] for row in block["best"]] == best
    assert [row["note"] for row in block["lowest"]] == lowest
    best_ids = {row["player"]["membership_id"] for row in block["best"]}
    assert not best_ids & {row["player"]["membership_id"] for row in block["lowest"]}


def test_ties_across_the_split_are_kept_with_the_best(ctx):
    players = extra_players(ctx, 3)
    session = pointed_session(ctx, *players)
    for membership in players:
        evaluate(ctx, session, membership, "7.0")
    block = get_stats(ctx.coach.user, session).data["evaluations"]
    assert [row["rank"] for row in block["best"]] == [1, 1, 1]
    assert block["lowest"] == []


def test_not_enough_notes_for_a_ranking(ctx):
    session = pointed_session(ctx, ctx.player)
    evaluate(ctx, session, ctx.player, "7.0")
    block = get_stats(ctx.coach.user, session).data["evaluations"]
    assert block["ranking_available"] is False and block["best"] == [] and block["lowest"] == []
    assert block["average"] == "7.0"


def test_unevaluated_players_never_count_as_zero(ctx):
    session = pointed_session(ctx, ctx.player, ctx.captain)
    evaluate(ctx, session, ctx.player, "8.0")
    assert get_stats(ctx.coach.user, session).data["evaluations"]["average"] == "8.0"


def test_no_evaluation_at_all(ctx):
    session = pointed_session(ctx, ctx.player)
    block = get_stats(ctx.coach.user, session).data["evaluations"]
    assert block["average"] is None and block["evaluated"] == 0 and block["eligible"] == 1


@pytest.mark.parametrize("role_attr", ["coach", "president", "vice_president", "sports_director"])
def test_notes_block_visible_to_allowed_roles(ctx, rated, role_attr):
    session, _players = rated
    data = get_stats(getattr(ctx, role_attr).user, session).data
    assert data["evaluations"] is not None and data["evaluations"]["average"] == "5.5"


@pytest.mark.parametrize("role_attr", ["captain", "doctor", "player", "debtor"])
def test_notes_block_hidden_from_other_players(ctx, rated, role_attr):
    session, _players = rated
    data = get_stats(getattr(ctx, role_attr).user, session).data
    assert data["evaluations"] is None
    # Aucune note d'un autre joueur ne fuit, même indirectement.
    assert "players" not in str(data.get("evaluations"))
    assert "8.5" not in str({k: v for k, v in data.items() if k != "my_evaluation"})


def test_player_sees_only_his_note_and_visible_comments(ctx, rated):
    session, _players = rated
    data = get_stats(ctx.player.user, session).data
    mine = data["my_evaluation"]
    assert mine["overall"] == "8.5"
    assert mine["criteria"]["technical"] == "7.0" and mine["criteria"]["physical"] is None
    assert mine["comments"] == ["Très bien"]  # le commentaire marqué non visible est filtré
    assert "Note privée" not in str(data)
    # Un joueur évalué par personne : my_evaluation est null.
    assert get_stats(ctx.debtor.user, session).data["my_evaluation"] is None


def test_capabilities_follow_roles_and_window(ctx, rated):
    session, _players = rated
    assert get_stats(ctx.coach.user, session).data["capabilities"] == {"can_evaluate": True, "can_measure": True}
    assert get_stats(ctx.president.user, session).data["capabilities"] == {"can_evaluate": True, "can_measure": False}
    assert get_stats(ctx.sports_director.user, session).data["capabilities"] == {
        "can_evaluate": False, "can_measure": False,
    }
    assert get_stats(ctx.player.user, session).data["capabilities"] == {"can_evaluate": False, "can_measure": False}


def test_notes_delta_against_previous_sessions(ctx):
    backdate_members(ctx)
    for days_ago, note in ((4, "6.0"), (3, "6.0"), (2, "6.0")):
        session = pointed_session(ctx, ctx.player, days_ago=days_ago)
        evaluate(ctx, session, ctx.player, note)
    current = pointed_session(ctx, ctx.player)
    evaluate(ctx, current, ctx.player, "7.0")
    block = get_stats(ctx.coach.user, current).data["evaluations"]
    assert block["delta_vs_average"] == "1.0"


# ---------------------------------------------------------------------------
# Étanchéité, erreurs, requêtes
# ---------------------------------------------------------------------------


def test_stats_of_another_club_are_not_reachable(ctx, other_ctx):
    foreign = make_session(other_ctx)
    assert get_stats(ctx.coach.user, foreign).status_code == status.HTTP_404_NOT_FOUND
    assert get_stats(other_ctx.coach.user, foreign).status_code == status.HTTP_200_OK


def test_stats_require_authentication(ctx):
    from rest_framework.test import APIClient

    assert APIClient().get(stats_url(make_session(ctx))).status_code == status.HTTP_401_UNAUTHORIZED


def test_other_club_data_never_enters_the_counts(ctx, other_ctx):
    session = make_session(ctx)
    foreign_session = make_session(other_ctx)
    point(other_ctx, foreign_session, other_ctx.player)
    evaluate(other_ctx, foreign_session, other_ctx.player, "9.0")
    data = get_stats(ctx.coach.user, session).data
    assert data["attendance"]["present"] == 0
    assert data["evaluations"]["evaluated"] == 0


def test_stats_use_a_bounded_number_of_queries(ctx, django_assert_max_num_queries):
    backdate_members(ctx)
    players = extra_players(ctx, 15)
    for days_ago in range(1, 6):
        pointed_session(ctx, ctx.player, *players, days_ago=days_ago)
    current = pointed_session(ctx, ctx.player, *players)
    for membership in players:
        evaluate(ctx, current, membership, "6.0")
    client = client_for(ctx.coach.user)
    client.get(stats_url(current))  # amorçage (cache de contenu, etc.)
    with django_assert_max_num_queries(25):
        response = client.get(stats_url(current))
    assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# B : évolution, assiduité
# ---------------------------------------------------------------------------


def history(user, period="last10"):
    return client_for(user).get(reverse("sport:session-stats-history"), {"period": period})


def test_history_returns_one_point_per_session_in_date_order(ctx):
    backdate_members(ctx)
    for days_ago in (5, 3, 1):
        session = pointed_session(ctx, ctx.player, ctx.captain, days_ago=days_ago)
        evaluate(ctx, session, ctx.player, "7.0")
    data = history(ctx.coach.user).data
    assert [row["date"] for row in data["results"]] == sorted(row["date"] for row in data["results"])
    assert len(data["results"]) == 3
    assert data["results"][0]["attendance_rate"] == 25  # 2 présents sur 8
    assert data["results"][0]["average_rating"] == "7.0"
    assert data["average_attendance_rate"] == 25 and data["average_rating"] == "7.0"
    assert data["results"][0]["my_rating"] is None  # le Coach n'a pas de note personnelle


def test_history_player_sees_only_his_ratings(ctx):
    backdate_members(ctx)
    session = pointed_session(ctx, ctx.player, ctx.captain, days_ago=1)
    evaluate(ctx, session, ctx.player, "7.0")
    evaluate(ctx, session, ctx.captain, "3.0")
    data = history(ctx.player.user).data
    row = data["results"][0]
    assert row["average_rating"] is None and row["my_rating"] == "7.0"
    assert data["average_rating"] is None and data["my_average_rating"] == "7.0"
    assert "3.0" not in str(data)


def test_history_skips_sessions_without_pointage_in_the_rate(ctx):
    backdate_members(ctx)
    pointed_session(ctx, ctx.player, days_ago=2)
    make_session(ctx, days_ago=1)  # séance sans aucun pointage
    results = history(ctx.coach.user).data["results"]
    assert [row["attendance_rate"] for row in results] == [13, None]  # 1 présent sur 8 = 12,5 -> 13 ; jamais 0


def test_history_average_is_total_present_over_total_expected_rounded_once(ctx):
    """CDC 10.3 n° 185 : moyenne = total des présents ÷ total des attendus,
    arrondie une seule fois (et non moyenne des taux par séance arrondis)."""

    backdate_members(ctx)
    pointed_session(ctx, ctx.player, days_ago=3)  # 1 sur 8 = 12,5 -> 13
    everyone = list(Membership.all_objects.filter(club=ctx.club, status=Membership.Status.ACTIVE))
    assert len(everyone) == ROSTER_SIZE
    pointed_session(ctx, *everyone, days_ago=2)  # 8 sur 8 = 100
    make_session(ctx, days_ago=1)  # non pointée : exclue
    make_session(ctx)  # séance du jour pas encore pointée : exclue
    data = history(ctx.coach.user).data
    assert [row["attendance_rate"] for row in data["results"]] == [13, 100, None, None]
    # 9 / 16 = 56,25 -> 56 ; l'ancienne moyenne des taux arrondis aurait donné (13 + 100) / 2 = 56,5 -> 57.
    assert data["average_attendance_rate"] == 56


def test_history_average_is_null_when_nothing_is_marked(ctx):
    backdate_members(ctx)
    make_session(ctx)
    assert history(ctx.coach.user).data["average_attendance_rate"] is None


def test_history_last10_is_capped_and_season_covers_the_season(ctx):
    backdate_members(ctx)
    for days_ago in range(0, 12):
        make_session(ctx, days_ago=days_ago)
    assert len(history(ctx.coach.user, "last10").data["results"]) == 10
    season = history(ctx.coach.user, "season").data
    assert len(season["results"]) >= 10
    assert season["season"]["id"] == ctx.season.pk


def test_history_ignores_sessions_of_other_clubs(ctx, other_ctx):
    make_session(other_ctx)
    assert history(ctx.coach.user).data["results"] == []


def test_invalid_period_is_refused_in_french(ctx):
    response = history(ctx.coach.user, "all")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Période invalide" in response.data["detail"]


def test_attendance_ranking_is_restricted_and_sorted(ctx):
    backdate_members(ctx)
    for days_ago in (3, 2, 1):
        pointed_session(ctx, ctx.player, days_ago=days_ago)
    pointed_session(ctx, ctx.captain, days_ago=4)
    url = reverse("sport:attendance-ranking")

    for allowed in (ctx.coach, ctx.president, ctx.vice_president, ctx.sports_director):
        assert client_for(allowed.user).get(url, {"period": "season"}).status_code == status.HTTP_200_OK
    for denied in (ctx.player, ctx.captain, ctx.doctor):
        assert client_for(denied.user).get(url).status_code == status.HTTP_403_FORBIDDEN

    data = client_for(ctx.coach.user).get(url, {"period": "season"}).data
    assert data["sessions_count"] == 4
    first = data["results"][0]
    assert first["player"]["membership_id"] == ctx.player.pk
    assert (first["sessions"], first["present"], first["rate"]) == (4, 3, 75)
    rates = [row["rate"] for row in data["results"]]
    assert rates == sorted(rates, reverse=True)


def test_my_attendance(ctx):
    backdate_members(ctx)
    for days_ago in (3, 2, 1):
        pointed_session(ctx, ctx.player, days_ago=days_ago)
    pointed_session(ctx, ctx.captain, days_ago=4)
    data = client_for(ctx.player.user).get(reverse("sport:attendance-me"), {"period": "season"}).data
    assert (data["sessions"], data["attended"], data["rate"]) == (4, 3, 75)
    # Le joueur ne reçoit aucune ligne des autres joueurs.
    assert "results" not in data


def test_attendance_endpoints_are_isolated_between_clubs(ctx, other_ctx):
    backdate_members(other_ctx)
    pointed_session(other_ctx, other_ctx.player, days_ago=1)
    data = client_for(ctx.coach.user).get(reverse("sport:attendance-ranking"), {"period": "season"}).data
    assert data["sessions_count"] == 0 and data["results"] == []


def test_decimal_values_are_strings_not_floats(ctx, rated):
    session, _ = rated
    block = get_stats(ctx.coach.user, session).data["evaluations"]
    assert isinstance(block["average"], str)
    assert all(isinstance(row["note"], str) for row in block["best"])
