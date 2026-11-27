"""Tests HTTP des cartes de joueurs et de leurs statistiques
(``clubs:players-cards``, ``clubs:player-stats``, ``clubs:players-compare``,
et le booléen ``is_unavailable`` de ``clubs:players-list``).

Points critiques : étanchéité entre clubs (un joueur d'un autre club n'est
lisible que par ses données PUBLIQUES, via la comparaison), confidentialité par
champ et par rôle (CDC 4.2, 10.2 n° 16), pagination sans doublon, requêtes
bornées.
"""

from __future__ import annotations

import datetime
import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership
from apps.medical.models import HealthRecord
from apps.sport.models import Evaluation, Suspension
from apps.sport.tests.conftest import build_sport_club_context, client_for, make_member
from apps.sport.tests.player_stats_helpers import build_dataset, make_match
from apps.sport.tests.stats_helpers import backdate_members

pytestmark = pytest.mark.django_db

FORBIDDEN_KEYS = {
    "weight_kg", "height_cm", "phone", "email", "birth_date", "balance", "amount_due", "debt", "currency",
    "medical_history", "allergies", "blood_group", "diagnosis", "comment", "comment_visible_to_player",
    "evaluator", "evaluators", "cause_detail", "issued_by", "recorded_by", "sponsor", "reason_code",
}
SENTINELS = ("TEL-0990000001", "MEDHIST-SECRET", "COMMENTAIRE-PRIVE-1", "COMMENTAIRE-VISIBLE", "Arbitre secret")


def _keys(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            found |= _keys(item)
    elif isinstance(value, list):
        for item in value:
            found |= _keys(item)
    return found


def _assert_public_only(response) -> None:
    text = json.dumps(response.json(), default=str)
    assert not (_keys(response.json()) & FORBIDDEN_KEYS), _keys(response.json()) & FORBIDDEN_KEYS
    for sentinel in SENTINELS:
        assert sentinel not in text


@pytest.fixture
def ctx():
    return build_sport_club_context()


@pytest.fixture
def other_ctx():
    return build_sport_club_context()


@pytest.fixture
def world(ctx):
    """Club de test avec jeu de données, des valeurs privées « sentinelles » et
    un second club étanche."""

    backdate_members(ctx)
    p2 = make_member(ctx.club)
    backdate_members(ctx)
    data = build_dataset(ctx, p2)
    for membership in (ctx.player, p2):
        user = membership.user
        user.phone, user.weight_kg, user.height_cm = "TEL-0990000001", "77.0", "181.0"
        user.save()
    HealthRecord.all_objects.create(
        club=ctx.club, membership=ctx.player, medical_history="MEDHIST-SECRET",
        fitness_status=HealthRecord.FitnessStatus.FIT_WITH_RESTRICTION,
    )
    return {"p2": p2, **data}


def named_member(club, first_name, last_name, **kwargs):
    membership = make_member(club, **kwargs)
    membership.user.first_name, membership.user.last_name = first_name, last_name
    membership.user.save()
    return membership


def _cards(user, **params):
    return client_for(user).get(reverse("clubs:players-cards"), params)


def _stats(user, membership, **params):
    return client_for(user).get(reverse("clubs:player-stats", args=[membership.pk]), params)


def _compare(user, *memberships):
    return client_for(user).get(reverse("clubs:players-compare"), {"ids": ",".join(str(m.pk) for m in memberships)})


# ---------------------------------------------------------------------------
# Liste des cartes
# ---------------------------------------------------------------------------


def test_cards_list_shape_and_exact_values(ctx, world):
    response = _cards(ctx.player.user)

    assert response.status_code == 200
    body = response.json()
    assert body["season_label"] == ctx.season.label
    assert body["season_id"] == ctx.season.pk
    assert body["can_compare"] is True and body["can_see_availability"] is False
    assert set(body) == {
        "count", "limit", "offset", "has_more", "results", "season_id", "season_label", "seasons",
        "can_see_availability", "can_compare",
    }
    row = next(r for r in body["results"] if r["membership_id"] == ctx.player.pk)
    assert set(row) == {
        "membership_id", "first_name", "last_name", "photo", "jersey_number", "position", "position_label",
        "position_detail", "overall_rating", "stats", "recent_ratings", "availability",
    }
    assert row["overall_rating"] is None
    assert row["stats"] == {
        "matches_played": 2, "goals": 2, "assists": 1, "yellow_cards": 2, "red_cards": 1,
        "attendance_rate": 50, "average_rating": "6.8",
    }
    assert row["recent_ratings"] == ["7.5", "6.0"]
    assert row["position_label"] == "Milieu"
    assert row["availability"] is None


def test_cards_list_never_exposes_private_fields(ctx, world):
    for user in (ctx.player.user, ctx.coach.user, ctx.president.user, ctx.doctor.user):
        _assert_public_only(_cards(user))


def test_cards_list_is_limited_to_the_active_club(ctx, other_ctx, world):
    foreign = named_member(other_ctx.club, "Etranger", "Uniquenom", jersey_number=77)

    body = _cards(ctx.player.user).json()
    searched = _cards(ctx.player.user, search="Uniquenom").json()
    numbered = _cards(ctx.player.user, search="77").json()

    assert foreign.pk not in {row["membership_id"] for row in body["results"]}
    assert searched["count"] == 0 and numbered["count"] == 0
    assert "Uniquenom" not in json.dumps(body)


def test_cards_pending_members_are_not_listed(ctx, world):
    ids = {row["membership_id"] for row in _cards(ctx.player.user, limit=100).json()["results"]}

    assert ctx.pending_member.pk not in ids
    assert ctx.debtor.pk in ids


def test_pagination_has_no_duplicate_and_no_gap(ctx, world):
    for _ in range(6):
        make_member(ctx.club)
    everyone = _cards(ctx.player.user, limit=100, ordering="-goals").json()
    total = everyone["count"]
    seen: list[int] = []
    offset = 0
    while True:
        page = _cards(ctx.player.user, limit=4, offset=offset, ordering="-goals").json()
        seen += [row["membership_id"] for row in page["results"]]
        assert page["count"] == total
        if not page["has_more"]:
            break
        offset += 4

    assert len(seen) == len(set(seen)) == total
    assert seen == [row["membership_id"] for row in everyone["results"]]


def test_ordering_by_goals_puts_ties_in_name_order_and_missing_values_last(ctx, world):
    body = _cards(ctx.player.user, limit=100, ordering="-average_rating").json()
    ratings = [row["stats"]["average_rating"] for row in body["results"]]

    assert ratings[0] == "6.8"
    assert ratings[1:] == [None] * (len(ratings) - 1)  # « — » toujours en fin de liste
    ascending = _cards(ctx.player.user, limit=100, ordering="average_rating").json()
    assert [row["stats"]["average_rating"] for row in ascending["results"]][0] == "6.8"

    goals = _cards(ctx.player.user, limit=100, ordering="-goals").json()["results"]
    assert [r["stats"]["goals"] for r in goals][:2] == [2, 1]
    names = [(r["last_name"].casefold(), r["first_name"].casefold()) for r in goals if r["stats"]["goals"] == 0]
    assert names == sorted(names)


def test_ordering_by_number_and_name(ctx, world):
    Membership.all_objects.filter(pk=ctx.player.pk).update(jersey_number=9)
    Membership.all_objects.filter(pk=world["p2"].pk).update(jersey_number=3)

    by_number = _cards(ctx.player.user, ordering="number").json()["results"]
    assert [r["jersey_number"] for r in by_number][:2] == [3, 9]
    assert all(r["jersey_number"] is None for r in by_number[2:])
    by_name = _cards(ctx.player.user, limit=100, ordering="name").json()["results"]
    keys = [(r["last_name"].casefold(), r["first_name"].casefold()) for r in by_name]
    assert keys == sorted(keys)
    assert [r["membership_id"] for r in _cards(ctx.player.user, limit=100, ordering="-name").json()["results"]] == [
        r["membership_id"] for r in reversed(by_name)
    ]


def test_search_is_accent_and_case_insensitive_and_accepts_a_number(ctx, world):
    target = named_member(ctx.club, "Élodie", "Mbuyi", jersey_number=42)

    for query in ("elodie", "ÉLODIE", "mbuyi elo", "42"):
        ids = [r["membership_id"] for r in _cards(ctx.player.user, search=query).json()["results"]]
        assert ids == [target.pk], query
    assert _cards(ctx.player.user, search="introuvable").json()["count"] == 0


def test_filter_by_position_and_status(ctx, world):
    keeper = make_member(ctx.club, position=Membership.Position.GOALKEEPER)
    departed = make_member(
        ctx.club, status=Membership.Status.DEPARTED, left_on=datetime.date.today(),
        left_reason=Membership.LeftReason.RESIGNATION,
    )
    cancelled = make_member(
        ctx.club, status=Membership.Status.DEPARTED, left_on=datetime.date.today(),
        left_reason=Membership.LeftReason.CANCELLED,
    )

    keepers = _cards(ctx.player.user, position="goalkeeper").json()
    left = _cards(ctx.player.user, status="left").json()
    active = _cards(ctx.player.user, limit=100).json()

    assert [r["membership_id"] for r in keepers["results"]] == [keeper.pk]
    assert keepers["results"][0]["position_label"] == "Gardien"
    assert [r["membership_id"] for r in left["results"]] == [departed.pk]  # adhésion annulée : jamais listée
    assert departed.pk not in {r["membership_id"] for r in active["results"]}
    assert cancelled.pk not in {r["membership_id"] for r in left["results"]}


def test_season_parameter_selects_another_season_and_refuses_a_foreign_one(ctx, other_ctx, world):
    previous = world["old"]

    old = _cards(ctx.player.user, season=previous.pk).json()
    refused = _cards(ctx.player.user, season=other_ctx.season.pk)

    assert old["season_label"] == "Ancienne"
    row = next(r for r in old["results"] if r["membership_id"] == ctx.player.pk)
    assert row["stats"]["yellow_cards"] == 1 and row["stats"]["matches_played"] == 0
    assert {s["id"] for s in old["seasons"]} == {ctx.season.pk, previous.pk}
    assert refused.status_code == 400
    assert refused.json()["detail"] == "Cette saison n'existe pas dans ce club."


@pytest.mark.parametrize(
    "params",
    [{"ordering": "salaire"}, {"limit": 0}, {"limit": 101}, {"position": "x"}, {"status": "x"}, {"offset": -3}],
)
def test_invalid_parameters_get_a_french_400(ctx, world, params):
    response = _cards(ctx.player.user, **params)

    assert response.status_code == 400
    assert response.json()["detail"][0].isupper()


def test_unauthenticated_and_non_member_are_refused(ctx, world):
    from rest_framework.test import APIClient

    assert APIClient().get(reverse("clubs:players-cards")).status_code == 401
    assert APIClient().get(reverse("clubs:player-stats", args=[ctx.player.pk])).status_code == 401
    assert APIClient().get(reverse("clubs:players-compare")).status_code == 401
    assert client_for(UserFactory()).get(reverse("clubs:players-cards")).status_code == 403


def test_card_photo_is_an_absolute_url(ctx, world):
    user = ctx.player.user
    user.photo = "users/photos/jean.jpg"
    user.save()

    row = next(r for r in _cards(ctx.coach.user).json()["results"] if r["membership_id"] == ctx.player.pk)

    assert row["photo"] == "http://testserver/media/users/photos/jean.jpg"
    assert next(r for r in _cards(ctx.coach.user).json()["results"] if r["membership_id"] == world["p2"].pk)[
        "photo"
    ] is None


def test_card_list_queries_are_bounded_whatever_the_squad_size(ctx, world):
    _cards(ctx.coach.user)  # échauffement
    with CaptureQueriesContext(connection) as small:
        _cards(ctx.coach.user, limit=100)
    for _ in range(15):
        make_member(ctx.club)
    with CaptureQueriesContext(connection) as large:
        body = _cards(ctx.coach.user, limit=100).json()

    assert body["count"] >= 20
    assert len(large) == len(small)
    assert len(large) <= 40


# ---------------------------------------------------------------------------
# Disponibilité : filtre et libellé réservés au staff (10.2 n° 16)
# ---------------------------------------------------------------------------


@pytest.fixture
def blocked(ctx):
    suspended = make_member(ctx.club)
    unfit = make_member(ctx.club)
    Suspension.all_objects.create(
        club=ctx.club, membership=suspended, reason=Suspension.Reason.RED_CARD, season=ctx.season, matches_total=3,
        matches_served=1, starts_event=make_match(ctx, days_ago=1).event,
    )
    HealthRecord.all_objects.create(
        club=ctx.club, membership=unfit, fitness_status=HealthRecord.FitnessStatus.UNFIT,
        fitness_return_date=datetime.date(2027, 3, 1), medical_history="MEDHIST-SECRET",
    )
    return {"suspended": suspended, "unfit": unfit}


@pytest.mark.parametrize("role", ["coach", "president", "vice_president", "sports_director", "doctor"])
def test_staff_sees_availability_labels_without_any_financial_motive(ctx, world, blocked, role):
    body = _cards(getattr(ctx, role).user, limit=100).json()
    by_id = {r["membership_id"]: r for r in body["results"]}

    assert body["can_see_availability"] is True
    assert by_id[blocked["suspended"].pk]["availability"] == {
        "label": "Suspendu : encore 2 match(s).", "family": "suspension",
    }
    assert by_id[blocked["unfit"].pk]["availability"]["family"] == "unfit"
    assert by_id[blocked["unfit"].pk]["availability"]["label"].startswith("Inapte · retour prévu le ")
    # CDC 10.3 n° 188 : le Coach lit « Non éligible. », comme dans la
    # composition ; les autres rôles « Indisponible » (page sans finance).
    debt_label = "Non éligible." if role == "coach" else "Indisponible"
    assert by_id[ctx.debtor.pk]["availability"] == {"label": debt_label, "family": "unavailable"}
    assert by_id[ctx.player.pk]["availability"] is None
    text = json.dumps(body)
    assert "dette" not in text.lower() and "MEDHIST-SECRET" not in text


def test_assistant_coach_reads_non_eligible_for_a_debtor_on_the_cards(ctx, world, blocked):
    """CDC 10.3 n° 188 : l'Assistant du Coach, comme le Coach, ne lit que
    « Non éligible. » (``COACH_DEBT_MASKED_DETAIL``) : ni montant ni dette."""

    from apps.clubs.models import MembershipRole
    from apps.sport.services import COACH_DEBT_MASKED_DETAIL

    assistant = make_member(ctx.club, roles=[MembershipRole.Role.ASSISTANT_COACH])
    body = _cards(assistant.user, limit=100).json()
    by_id = {r["membership_id"]: r for r in body["results"]}

    assert by_id[ctx.debtor.pk]["availability"] == {"label": COACH_DEBT_MASKED_DETAIL, "family": "unavailable"}
    assert by_id[blocked["suspended"].pk]["availability"]["family"] == "suspension"
    text = json.dumps(body).lower()
    assert "dette" not in text and "amount_due" not in text


@pytest.mark.parametrize("who", ["player", "captain"])
def test_other_members_never_see_availability_nor_use_its_filter(ctx, world, blocked, who):
    user = getattr(ctx, who).user if who != "player" else ctx.player.user
    body = _cards(user, limit=100).json()

    assert body["can_see_availability"] is False
    assert all(row["availability"] is None for row in body["results"])
    refused = _cards(user, availability="unavailable")
    assert refused.status_code == 400
    assert refused.json()["detail"] == "Le filtre de disponibilité est réservé au staff du club."


def test_staff_availability_filter(ctx, world, blocked):
    unavailable = {r["membership_id"] for r in _cards(ctx.coach.user, availability="unavailable", limit=100).json()["results"]}
    available = {r["membership_id"] for r in _cards(ctx.coach.user, availability="available", limit=100).json()["results"]}

    assert unavailable == {blocked["suspended"].pk, blocked["unfit"].pk, ctx.debtor.pk}
    assert ctx.player.pk in available and not (available & unavailable)


# ---------------------------------------------------------------------------
# Statistiques détaillées
# ---------------------------------------------------------------------------


def test_stats_endpoint_shape_and_values(ctx, world):
    response = _stats(ctx.coach.user, ctx.player)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "membership_id", "season_id", "season_label", "overall_rating", "stats", "radar", "recent_form",
        "attendance", "discipline", "fitness", "performance",
    }
    assert body["stats"]["goals"] == 2 and body["stats"]["average_rating"] == "6.8"
    assert [row["rating"] for row in body["recent_form"]] == ["7.5", "6.0"]
    assert body["radar"]["axes"][0] == {"key": "technical", "label": "Technique", "value": "6.0"}
    assert {c["cause_label"] for c in body["discipline"]["cards"]} == {"Contestation", "Faute grossière"}
    assert set(body["recent_form"][0]) == {"date", "event_type", "label", "rating"}


@pytest.mark.parametrize("viewer", ["coach", "president", "vice_president", "sports_director", "doctor", "captain", "player"])
def test_stats_never_expose_private_fields_nor_evaluators_nor_comments(ctx, world, viewer):
    response = _stats(getattr(ctx, viewer).user, ctx.player)

    assert response.status_code == 200
    _assert_public_only(response)


def test_evaluation_comments_visible_or_not_are_never_served(ctx, world):
    assert Evaluation.all_objects.filter(club=ctx.club, comment_visible_to_player=True).exists()

    text = _stats(ctx.player.user, ctx.player).content.decode() + _cards(ctx.player.user).content.decode()

    assert "COMMENTAIRE-VISIBLE" not in text and "COMMENTAIRE-PRIVE-1" not in text


def test_suspension_and_fitness_only_for_staff_and_the_player_himself(ctx, world, blocked):
    suspended, unfit = blocked["suspended"], blocked["unfit"]

    for viewer in (ctx.coach.user, ctx.president.user, ctx.sports_director.user, ctx.doctor.user, suspended.user):
        body = _stats(viewer, suspended).json()
        assert body["discipline"]["active_suspension"]["matches_remaining"] == 2
        assert body["discipline"]["active_suspension"]["label"] == "Suspendu : encore 2 match(s)."
        assert body["fitness"]["status"] == "fit"
    for viewer in (ctx.player.user, ctx.captain.user, ctx.debtor.user):
        body = _stats(viewer, suspended).json()
        assert body["discipline"]["active_suspension"] is None
        assert body["fitness"] is None

    own = _stats(unfit.user, unfit).json()["fitness"]
    assert own == {"status": "unfit", "label": "Inapte", "return_date": "2027-03-01"}
    assert _stats(ctx.player.user, unfit).json()["fitness"] is None
    coach_view = _stats(ctx.coach.user, unfit)
    assert coach_view.json()["fitness"] == own
    assert "MEDHIST-SECRET" not in coach_view.content.decode()  # aptitude et retour seulement, jamais de diagnostic


def test_cards_of_the_season_stay_visible_to_every_teammate(ctx, world):
    # Position provisoire : les cartons sont des statistiques sportives publiques.
    body = _stats(ctx.captain.user, ctx.player).json()

    assert len(body["discipline"]["cards"]) == 3


def test_performance_block_is_for_staff_and_the_player_only(ctx, world):
    assert _stats(ctx.coach.user, ctx.player).json()["performance"] == []
    assert _stats(ctx.player.user, ctx.player).json()["performance"] == []
    assert _stats(ctx.captain.user, ctx.player).json()["performance"] is None
    assert _stats(world["p2"].user, ctx.player).json()["performance"] is None


def test_stats_of_a_foreign_club_player_is_404_and_leaks_nothing(ctx, other_ctx, world):
    foreign = named_member(other_ctx.club, "Etranger", "Uniquenom")
    user = foreign.user
    user.card_publication_consent_at = timezone.now()
    user.save()

    response = _stats(ctx.coach.user, foreign)

    assert response.status_code == 404
    assert response.json() == {"detail": "Ce joueur n'existe pas dans ce club."}
    assert _stats(ctx.coach.user, ctx.player, season=other_ctx.season.pk).status_code == 400


def test_stats_with_a_bad_season_value_is_a_400(ctx, world):
    assert _stats(ctx.coach.user, ctx.player, season="abc").status_code == 400


def test_player_without_any_data_gets_zeros(ctx, world):
    newcomer = make_member(ctx.club)

    body = _stats(ctx.coach.user, newcomer).json()

    assert body["stats"] == {
        "matches_played": 0, "goals": 0, "assists": 0, "yellow_cards": 0, "red_cards": 0,
        "attendance_rate": None, "average_rating": None,
    }
    assert body["recent_form"] == [] and body["discipline"]["cards"] == []
    assert body["attendance"]["rate"] is None


def test_stats_queries_are_bounded(ctx, world):
    _stats(ctx.coach.user, ctx.player)
    with CaptureQueriesContext(connection) as queries:
        _stats(ctx.coach.user, ctx.player)

    assert len(queries) <= 40


def test_club_with_no_season_still_answers(ctx):
    from apps.clubs.models import Season

    Season.all_objects.filter(club=ctx.club).delete()

    body = _cards(ctx.player.user).json()
    stats = _stats(ctx.player.user, ctx.player).json()

    assert body["season_label"] is None and body["seasons"] == []
    assert stats["season_label"] is None and stats["stats"]["matches_played"] == 0


# ---------------------------------------------------------------------------
# Comparaison (données publiques entre clubs)
# ---------------------------------------------------------------------------


@pytest.fixture
def foreign(other_ctx):
    backdate_members(other_ctx)
    mate = make_member(other_ctx.club)
    mate.user.card_publication_consent_at = timezone.now()
    mate.user.birth_date = datetime.date(1990, 5, 5)
    mate.user.phone, mate.user.weight_kg = "TEL-0990000001", "90.0"
    mate.user.save()
    build_dataset(other_ctx, make_member(other_ctx.club))
    return mate


def test_compare_two_players_of_the_club_gives_stats_and_radar(ctx, world):
    response = _compare(ctx.player.user, ctx.player, world["p2"])

    assert response.status_code == 200
    first, second = response.json()["results"]
    assert (first["membership_id"], second["membership_id"]) == (ctx.player.pk, world["p2"].pk)
    assert first["scope"] == "club" and first["consultable"] is True
    assert first["stats"]["goals"] == 2 and second["stats"]["goals"] == 1
    assert first["radar"]["axes"][1]["value"] == "9.0"
    assert first["club"]["name"] == ctx.club.name
    _assert_public_only(response)


def test_compare_with_a_foreign_player_serves_public_data_only(ctx, other_ctx, world, foreign):
    response = _compare(ctx.player.user, ctx.player, foreign)

    assert response.status_code == 200
    other = response.json()["results"][1]
    assert other["scope"] == "public" and other["consultable"] is True
    assert other["radar"] is None  # attributs non publics (point ouvert 13)
    assert other["club"]["id"] == foreign.club_id
    assert other["season_label"] == other_ctx.season.label  # la saison de SON club, pas celle du lecteur
    assert set(other) == {
        "membership_id", "first_name", "last_name", "photo", "jersey_number", "position", "position_label",
        "consultable", "scope", "club", "season_id", "season_label", "overall_rating", "stats", "radar",
    }
    _assert_public_only(response)
    assert "90.0" not in response.content.decode()


def test_compare_hides_foreign_players_without_consent_minors_and_departed(ctx, world, foreign, other_ctx):
    no_consent = make_member(other_ctx.club)
    minor = make_member(other_ctx.club)
    minor.user.card_publication_consent_at = timezone.now()
    minor.user.birth_date = datetime.date.today().replace(year=datetime.date.today().year - 15)
    minor.user.save()
    gone = make_member(other_ctx.club, status=Membership.Status.DEPARTED, left_on=datetime.date.today(),
                       left_reason=Membership.LeftReason.RESIGNATION)
    gone.user.card_publication_consent_at = timezone.now()
    gone.user.save()
    pending = make_member(other_ctx.club, status=Membership.Status.PENDING, sponsor=foreign)
    pending.user.card_publication_consent_at = timezone.now()
    pending.user.save()
    expected = {"membership_id": None, "consultable": False, "detail": "Ce joueur n'est plus consultable."}

    for hidden in (no_consent, minor, gone, pending):
        row = _compare(ctx.player.user, ctx.player, hidden).json()["results"][1]
        assert row == {**expected, "membership_id": hidden.pk}
    unknown = _compare(ctx.player.user, ctx.player, ctx.player.__class__(pk=999999)).json()["results"][1]
    assert unknown["consultable"] is False  # même réponse qu'un joueur masqué : aucune fuite d'existence


def test_compare_one_consent_withdrawn_between_calls(ctx, world, foreign):
    assert _compare(ctx.player.user, ctx.player, foreign).json()["results"][1]["consultable"] is True
    foreign.user.card_publication_consent_at = None
    foreign.user.save()

    assert _compare(ctx.player.user, ctx.player, foreign).json()["results"][1]["consultable"] is False


@pytest.mark.parametrize("ids", ["", "5", "1,2,3,4,5", "7,7", "a,b"])
def test_compare_requires_two_to_four_distinct_players(ctx, world, ids):
    response = client_for(ctx.player.user).get(reverse("clubs:players-compare"), {"ids": ids})

    assert response.status_code == 400
    assert response.json()["detail"][0].isupper()


def test_compare_four_players_is_accepted(ctx, world):
    extra = [make_member(ctx.club), make_member(ctx.club)]

    response = _compare(ctx.player.user, ctx.player, world["p2"], *extra)

    assert response.status_code == 200 and response.json()["count"] == 4


# ---------------------------------------------------------------------------
# Booléen « bloqué » de la liste des joueurs (pointage groupé)
# ---------------------------------------------------------------------------


def _list(user):
    return client_for(user).get(reverse("clubs:players-list")).json()


@pytest.mark.parametrize("viewer", ["player", "captain", "coach", "president", "doctor"])
def test_players_list_gives_is_unavailable_without_motive_to_every_role(ctx, world, blocked, viewer):
    rows = {row["membership_id"]: row for row in _list(getattr(ctx, viewer).user)}

    assert rows[ctx.player.pk]["is_unavailable"] is False
    assert rows[ctx.debtor.pk]["is_unavailable"] is True
    assert rows[blocked["suspended"].pk]["is_unavailable"] is True
    assert rows[blocked["unfit"].pk]["is_unavailable"] is True
    assert rows[ctx.pending_member.pk]["is_unavailable"] is True
    for row in rows.values():
        assert isinstance(row["is_unavailable"], bool)
        assert not (set(row) & {"reason", "reason_code", "availability", "fitness", "suspension", "amount_due"})


def test_players_list_is_unavailable_stays_in_the_active_club(ctx, other_ctx, world):
    rows = _list(ctx.player.user)

    assert other_ctx.debtor.pk not in {row["membership_id"] for row in rows}


def test_card_endpoint_also_carries_the_flag(ctx, world):
    response = client_for(ctx.player.user).get(reverse("clubs:player-card", args=[ctx.debtor.pk]))

    assert response.json()["is_unavailable"] is True


def test_club_without_configured_settings_never_crashes_the_players_list(ctx):
    from apps.clubs.models import ClubSettings

    ClubSettings.objects.filter(club=ctx.club).delete()

    list_response = client_for(ctx.player.user).get(reverse("clubs:players-list"))
    cards_response = _cards(ctx.player.user)

    assert list_response.status_code == 200
    assert all(row["is_unavailable"] is (row["membership_id"] == ctx.pending_member.pk) for row in list_response.json())
    assert cards_response.status_code == 400  # message français explicite, jamais une erreur 500
    assert "paramètres du club" in cards_response.json()["detail"]
