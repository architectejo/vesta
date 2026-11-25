"""Calculs des cartes de joueurs (``apps.sport.player_stats``) : chiffres exacts
sur un jeu construit à la main (voir ``player_stats_helpers.build_dataset``),
joueur sans donnée, disponibilité groupée identique à ``get_playability``,
nombre de requêtes fixe."""

from __future__ import annotations

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.clubs.models import Membership
from apps.medical.models import HealthRecord
from apps.sport import player_stats, services
from apps.sport.models import Suspension
from apps.sport.tests.conftest import make_member
from apps.sport.tests.player_stats_helpers import build_dataset, make_match
from apps.sport.tests.stats_helpers import backdate_members, make_session

pytestmark = pytest.mark.django_db


@pytest.fixture
def data(ctx):
    backdate_members(ctx)
    p2 = make_member(ctx.club)
    backdate_members(ctx)
    return {"p2": p2, **build_dataset(ctx, p2)}


def test_exact_statistics_of_the_first_player(ctx, data):
    aggregate = player_stats.compute_aggregates(ctx.club, ctx.season)[ctx.player.pk]

    assert player_stats.stats_block(aggregate) == {
        "matches_played": 2,  # m3 sans score : non joué
        "goals": 2,
        "assists": 1,
        "yellow_cards": 2,  # le jaune d'une autre saison et la sanction interne sont exclus
        "red_cards": 1,
        "attendance_rate": 50,
        "average_rating": "6.8",  # (7,5 + 6,0) / 2 = 6,75 arrondi à 0,1
    }
    assert (aggregate.sessions_expected, aggregate.sessions_present) == (4, 2)
    assert (aggregate.late, aggregate.excused, aggregate.absent) == (0, 1, 1)


def test_exact_statistics_of_the_second_player(ctx, data):
    aggregate = player_stats.compute_aggregates(ctx.club, ctx.season)[data["p2"].pk]

    assert aggregate.matches_played == 2  # remplaçant de m1 + buteur de m2 hors composition
    assert (aggregate.goals, aggregate.assists) == (1, 1)
    assert aggregate.attendance_rate == 75  # le retard est compté absent (réglage par défaut)
    assert (aggregate.sessions_present, aggregate.late) == (3, 1)
    assert aggregate.average_rating is None
    assert aggregate.ratings == []


def test_late_arrival_counts_present_when_the_club_allows_it(ctx, data):
    from apps.clubs.models import ClubSettings

    ClubSettings.objects.filter(club=ctx.club).update(late_arrival_counts_absent=False)

    aggregate = player_stats.compute_aggregates(ctx.club, ctx.season)[data["p2"].pk]

    assert aggregate.attendance_rate == 100
    assert aggregate.late == 1


def test_player_without_any_match_has_zeros_and_no_rate_or_rating(ctx, data):
    newcomer = make_member(ctx.club)
    aggregates = player_stats.compute_aggregates(ctx.club, ctx.season)

    assert player_stats.stats_block(player_stats.aggregate_of(aggregates, newcomer.pk)) == {
        "matches_played": 0,
        "goals": 0,
        "assists": 0,
        "yellow_cards": 0,
        "red_cards": 0,
        "attendance_rate": None,
        "average_rating": None,
    }
    stats = player_stats.get_player_stats(membership=newcomer, viewer=newcomer.user)
    assert stats["recent_form"] == []
    assert stats["discipline"]["cards"] == []
    assert all(axis["value"] is None for axis in stats["radar"]["axes"])
    assert stats["overall_rating"] is None


def test_pending_member_is_never_expected_at_sessions(ctx, data):
    aggregate = player_stats.aggregate_of(player_stats.compute_aggregates(ctx.club, ctx.season), ctx.pending_member.pk)

    assert aggregate.attendance_rate is None
    assert aggregate.sessions_expected == 0


def test_season_without_data_and_club_without_season(ctx, data):
    aggregates = player_stats.compute_aggregates(ctx.club, data["old"])

    # L'ancienne saison ne contient que le jaune de son propre match.
    assert player_stats.stats_block(aggregates[ctx.player.pk])["yellow_cards"] == 1
    assert aggregates[ctx.player.pk].matches_played == 0
    assert data["p2"].pk not in aggregates
    assert player_stats.compute_aggregates(ctx.club, None) == {}


def test_detailed_stats_shape_recent_form_and_radar(ctx, data):
    stats = player_stats.get_player_stats(membership=ctx.player, viewer=ctx.coach.user)

    assert stats["season_label"] == ctx.season.label
    assert [(row["event_type"], row["label"], row["rating"]) for row in stats["recent_form"]] == [
        ("session", "Séance", "7.5"),
        ("match", f"Match contre {data['m1'].opponent_name}", "6.0"),
    ]  # la plus récente d'abord (s1 date de 4 jours, m1 de 5 jours)
    assert {axis["key"]: axis["value"] for axis in stats["radar"]["axes"]} == {
        "technical": "6.0",
        "physical": "9.0",
        "tactical": None,
        "mental": None,
        "attitude": None,
    }
    assert [axis["label"] for axis in stats["radar"]["axes"]] == ["Technique", "Physique", "Tactique", "Mental", "Attitude"]
    assert stats["attendance"] == {
        "sessions_expected": 4,
        "sessions_present": 2,
        "late": 0,
        "excused": 1,
        "absent": 1,
        "rate": 50,
        "late_counts_as_absent": True,
    }


def test_recent_form_keeps_only_the_five_latest_notes(ctx):
    backdate_members(ctx)
    from apps.sport.tests.stats_helpers import evaluate

    for days_ago in range(1, 8):
        evaluate(ctx, make_session(ctx, days_ago=days_ago), ctx.player, days_ago)  # note = 1..7

    stats = player_stats.get_player_stats(membership=ctx.player, viewer=ctx.player.user)

    assert [row["rating"] for row in stats["recent_form"]] == ["1.0", "2.0", "3.0", "4.0", "5.0"]
    assert stats["stats"]["average_rating"] == "4.0"


def test_discipline_lists_cards_with_category_but_never_free_text_or_referee(ctx, data):
    stats = player_stats.get_player_stats(membership=ctx.player, viewer=ctx.player.user)

    cards = stats["discipline"]["cards"]
    # Du plus récent au plus ancien : m2 (rouge saisi après le jaune), puis m1.
    assert [card["incident_type"] for card in cards] == ["red_card", "yellow_card", "yellow_card"]
    assert {card["cause_label"] for card in cards} == {"Contestation", "Faute grossière"}
    flat = str(stats)
    assert "Insulte" not in flat and "Arbitre secret" not in flat


def test_overall_rating_stays_null_until_the_client_decides(ctx, data):
    assert player_stats.get_player_stats(membership=ctx.player, viewer=ctx.coach.user)["overall_rating"] is None


# ---------------------------------------------------------------------------
# Disponibilité groupée = règle de composition (get_playability)
# ---------------------------------------------------------------------------


def test_grouped_availability_matches_playability_for_every_reason(ctx):
    suspended = make_member(ctx.club)
    unfit = make_member(ctx.club)
    event = make_match(ctx, days_ago=1).event
    Suspension.all_objects.create(
        club=ctx.club, membership=suspended, reason=Suspension.Reason.RED_CARD, season=ctx.season, matches_total=2,
        starts_event=event,
    )
    HealthRecord.all_objects.create(
        club=ctx.club, membership=unfit, fitness_status=HealthRecord.FitnessStatus.UNFIT,
        fitness_return_date=datetime.date(2027, 3, 1),
    )
    members = list(Membership.all_objects.filter(club=ctx.club).select_related("club"))

    availabilities = player_stats.get_availabilities(ctx.club, members)

    for membership in members:
        playability = services.get_playability(membership)
        assert availabilities[membership.pk].code == playability.reason_code, membership.pk
    assert availabilities[suspended.pk].matches_remaining == 2
    assert availabilities[unfit.pk].return_date == datetime.date(2027, 3, 1)
    assert availabilities[ctx.debtor.pk].code == "debt"
    assert availabilities[ctx.pending_member.pk].code == "pending_membership"
    assert availabilities[ctx.player.pk].code == ""


def test_a_debt_is_never_named_on_the_sports_page(ctx):
    availabilities = player_stats.get_availabilities(ctx.club, [ctx.debtor])

    assert player_stats.staff_availability(availabilities[ctx.debtor.pk]) == {
        "label": "Indisponible",
        "family": "unavailable",
    }


def test_availability_query_count_does_not_grow_with_the_squad(ctx):
    members = list(Membership.all_objects.filter(club=ctx.club))
    with CaptureQueriesContext(connection) as small:
        player_stats.get_availabilities(ctx.club, members)
    more = [make_member(ctx.club) for _ in range(12)]
    members = list(Membership.all_objects.filter(club=ctx.club))
    with CaptureQueriesContext(connection) as large:
        player_stats.get_availabilities(ctx.club, members)

    assert len(more) == 12
    assert len(large) == len(small)


def test_aggregate_query_count_is_fixed(ctx):
    backdate_members(ctx)
    with CaptureQueriesContext(connection) as small:
        player_stats.compute_aggregates(ctx.club, ctx.season)
    p2 = make_member(ctx.club)
    build_dataset(ctx, p2)
    for _ in range(10):
        make_member(ctx.club)
    with CaptureQueriesContext(connection) as large:
        player_stats.compute_aggregates(ctx.club, ctx.season)

    assert len(large) == len(small)
    assert len(large) <= 10


def test_unavailable_ids_are_a_bare_set_without_reason(ctx):
    members = list(Membership.all_objects.filter(club=ctx.club))

    ids = player_stats.unavailable_membership_ids(ctx.club, members)

    assert ids == {ctx.debtor.pk, ctx.pending_member.pk}


def test_parameters_are_validated_in_french(ctx):
    for bad in (
        {"ordering": "salaire"},
        {"position": "arbitre"},
        {"status": "autre"},
        {"availability": "peut-etre"},
        {"limit": "0"},
        {"limit": "101"},
        {"limit": "abc"},
        {"offset": "-1"},
    ):
        with pytest.raises(player_stats.PlayerStatsError) as excinfo:
            player_stats.parse_cards_params(bad)
        assert str(excinfo.value)[0].isupper()
    for bad_ids in ("", "1", "1,2,3,4,5", "1,1", "a,b"):
        with pytest.raises(player_stats.PlayerStatsError):
            player_stats.parse_compare_ids(bad_ids)
    assert player_stats.parse_compare_ids("3, 4") == [3, 4]


def test_unknown_season_is_refused(ctx):
    with pytest.raises(player_stats.PlayerStatsError):
        player_stats.resolve_season(ctx.club, 999999)
