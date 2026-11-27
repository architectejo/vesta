"""Tableau de bord du Président et du Vice-président : endpoints, permissions,
cartes non financières, confidentialité médicale, étanchéité entre clubs,
périodes, erreurs isolées par carte, nombre de requêtes borné, destination
d'arrivée (``default_landing``).

Fiche : docs/ecrans/club-tableau-de-bord-bureau.md ; matrice 2.4 ; CLAUDE.md
règles 8, 9 et 11.
"""

from __future__ import annotations

import datetime
import json
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import SuperuserFactory
from apps.audit.models import AuditLog
from apps.clubs import board_dashboard
from apps.clubs.models import Membership, MembershipApplication, MembershipRole
from apps.clubs.tests.factories import MembershipApplicationFactory
from apps.logistics.models import Article, StockMovement
from apps.medical.models import HealthRecord
from apps.sport import services as sport_services
from apps.sport.models import Attendance, Evaluation, Incident, MatchGoal, MatchSheet
from apps.sport.session_stats import attendance_rate_percent
from apps.sport.tests.conftest import build_sport_club_context, client_for, make_member
from apps.sport.tests.factories import EventFactory, MatchFactory, SessionFactory

pytestmark = pytest.mark.django_db

URL = "clubs:board-dashboard"
SECTION_URL = "clubs:board-dashboard-section"
ROLE = MembershipRole.Role


@pytest.fixture
def ctx():
    c = build_sport_club_context()
    _backdate(c.club)
    return c


@pytest.fixture
def other_ctx():
    c = build_sport_club_context()
    _backdate(c.club)
    return c


def _more_seats(club):
    type(club.settings).objects.filter(club=club).update(board_seats_per_role=3)
    club.settings.board_seats_per_role = 3  # instance mise en cache par les factories


def _backdate(club, days=90):
    """Les adhésions existent depuis assez longtemps pour être « attendues » aux événements du jour."""

    Membership.all_objects.filter(club=club).update(joined_on=timezone.now().date() - datetime.timedelta(days=days))


def get(user, name=URL, args=None, **params):
    return client_for(user).get(reverse(name, args=args), params)


def get_section(user, section, **params):
    return get(user, SECTION_URL, args=[section], **params)


def make_session(c, *, day=None):
    event = SessionFactory(club=c.club, event__club=c.club, event__season=c.season, event__event_date=day or timezone.now().date()).event
    return event


def make_match(c, *, score=None, day=None, opponent="Les Aigles"):
    match = MatchFactory(
        club=c.club, event__club=c.club, event__season=c.season, event__event_date=day or timezone.now().date(), opponent_name=opponent
    )
    if score is not None:
        MatchSheet.all_objects.create(
            club=c.club, match=match, score_home=score[0], score_away=score[1], filled_by=c.coach.user, filled_at=timezone.now()
        )
    return match


def mark(c, event, membership, status_value):
    arrived = None
    if status_value in (Attendance.Status.PRESENT, Attendance.Status.LATE_ABSENT):
        arrived = timezone.now()
    Attendance.all_objects.create(
        club=c.club, event=event, membership=membership, status=status_value, marked_by=c.coach.user, arrived_at=arrived
    )


# ---------------------------------------------------------------------------
# Permissions (matrice 2.4)
# ---------------------------------------------------------------------------


class TestPermissions:
    def test_president_et_vice_president_lisent(self, ctx):
        assert get(ctx.president.user).status_code == status.HTTP_200_OK
        assert get(ctx.vice_president.user).status_code == status.HTTP_200_OK
        assert get_section(ctx.president.user, "attendance").status_code == status.HTTP_200_OK
        assert get_section(ctx.vice_president.user, "cash").status_code == status.HTTP_200_OK

    @pytest.mark.parametrize("who", ["sports_director", "doctor", "coach", "captain", "player", "debtor", "pending_member"])
    def test_les_autres_roles_sont_refuses(self, ctx, who):
        user = getattr(ctx, who).user
        assert get(user).status_code == status.HTTP_403_FORBIDDEN
        assert get_section(user, "fitness").status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize("role", [ROLE.TREASURER, ROLE.ASSISTANT_TREASURER, ROLE.SECRETARY, ROLE.STEWARD])
    def test_les_autres_membres_du_bureau_sont_refuses(self, ctx, role):
        member = make_member(ctx.club, roles=[role])
        assert get(member.user).status_code == status.HTTP_403_FORBIDDEN

    def test_anonyme_401(self, ctx):
        assert APIClient().get(reverse(URL)).status_code == status.HTTP_401_UNAUTHORIZED
        assert APIClient().get(reverse(SECTION_URL, args=["cash"])).status_code == status.HTTP_401_UNAUTHORIZED

    def test_superuser_sans_session_de_support_refuse(self, ctx):
        assert get(SuperuserFactory()).status_code == status.HTTP_403_FORBIDDEN

    def test_cumul_de_roles_union_des_droits(self, ctx):
        _more_seats(ctx.club)
        coach_vp = make_member(ctx.club, roles=[ROLE.COACH, ROLE.VICE_PRESIDENT])
        treasurer_vp = make_member(ctx.club, roles=[ROLE.TREASURER, ROLE.VICE_PRESIDENT])
        assert get(coach_vp.user).status_code == status.HTTP_200_OK
        assert get(treasurer_vp.user).status_code == status.HTTP_200_OK

    def test_president_qui_cumule_un_autre_role_garde_l_acces(self, ctx):
        MembershipRole.all_objects.create(
            club=ctx.club, membership=ctx.president, role=ROLE.TREASURER, appointed_by=ctx.president.user, appointed_at=timezone.now()
        )
        assert get(ctx.president.user).status_code == status.HTTP_200_OK

    def test_vice_president_revoque_perd_l_acces(self, ctx):
        MembershipRole.all_objects.filter(membership=ctx.vice_president, role=ROLE.VICE_PRESIDENT).update(
            revoked_at=timezone.now()
        )
        assert get(ctx.vice_president.user).status_code == status.HTTP_403_FORBIDDEN

    def test_poste_de_vp_vacant_le_president_voit_seul(self, ctx):
        MembershipRole.all_objects.filter(role=ROLE.VICE_PRESIDENT, club=ctx.club).update(revoked_at=timezone.now())
        assert get(ctx.president.user).status_code == status.HTTP_200_OK

    def test_methodes_d_ecriture_refusees(self, ctx):
        response = client_for(ctx.president.user).post(reverse(URL), {})
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ---------------------------------------------------------------------------
# Période, pagination, paramètres
# ---------------------------------------------------------------------------


class TestParameters:
    def test_defaut_mois_courant(self, ctx):
        data = get(ctx.president.user).data
        today = timezone.now().date()
        assert data["period"]["mode"] == "month"
        assert data["period"]["month"][:4] == str(today.year)[:4]

    def test_mois_explicite_et_saison(self, ctx):
        data = get(ctx.president.user, period="month", month="2026-01").data
        assert data["period"]["month"] == "2026-01"
        data = get(ctx.president.user, period="season", season=ctx.season.pk).data
        assert data["period"]["mode"] == "season" and data["period"]["season_id"] == ctx.season.pk

    def test_saison_courante_par_defaut(self, ctx):
        type(ctx.season).all_objects.filter(pk=ctx.season.pk).update(is_current=True)
        data = get(ctx.president.user, period="season").data
        assert data["period"]["season_id"] == ctx.season.pk

    def test_saison_sans_saison_courante_400(self, ctx):
        response = get(ctx.president.user, period="season")
        assert response.status_code == 400 and "saison" in response.data["detail"].lower()

    @pytest.mark.parametrize(
        "params",
        [{"month": "novembre"}, {"month": "2099-01"}, {"period": "annee"}, {"period": "season", "season": "9999999"}, {"month": ""}],
    )
    def test_periode_invalide_400_en_francais(self, ctx, params):
        for response in (get(ctx.president.user, **params), get_section(ctx.president.user, "attendance", **params)):
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.data["detail"]

    def test_saison_d_un_autre_club_400(self, ctx, other_ctx):
        response = get(ctx.president.user, period="season", season=other_ctx.season.pk)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.parametrize("params", [{"limit": "0"}, {"limit": "abc"}, {"limit": "101"}, {"offset": "-1"}, {"offset": "x"}])
    def test_pagination_invalide_400(self, ctx, params):
        response = get_section(ctx.president.user, "attendance", **params)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_section_inconnue_404_et_liste_inconnue_400(self, ctx):
        assert get_section(ctx.president.user, "inconnue").status_code == status.HTTP_404_NOT_FOUND
        assert get_section(ctx.president.user, "attendance", only="nope").status_code == status.HTTP_400_BAD_REQUEST
        assert get_section(ctx.president.user, "cash", only="nope").status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Club vide, formes, finance
# ---------------------------------------------------------------------------


EXPECTED_CARDS = {
    "contributions", "squad_status", "cash", "expenses_by_category", "upcoming_finance", "attendance",
    "newcomers", "results", "discipline", "squad_trend", "fitness", "upcoming", "attendance_ranking",
    "to_process", "equipment_out", "coach_notes", "feed_activity",
}


class TestShape:
    def test_club_sans_activite_aucune_carte_en_erreur(self):
        c = build_sport_club_context()  # un club « vide » : aucun événement ni paiement
        data = get(c.president.user).data
        assert EXPECTED_CARDS <= set(data)
        for key in EXPECTED_CARDS:
            assert "error" not in data[key], key
        assert data["attendance"]["average_rate"] is None and data["attendance"]["events_count"] == 0
        assert data["results"]["played"] == 0 and data["results"]["form"] == []
        assert data["discipline"]["suspended_count"] == 0
        assert data["fitness"]["no_information"] is True
        assert data["equipment_out"]["lines_count"] == 0
        assert data["to_process"]["total"] == 0

    @pytest.mark.parametrize("section", sorted(EXPECTED_CARDS))
    def test_chaque_section_repond(self, ctx, section):
        response = get_section(ctx.president.user, section)
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["section"] == section and "period" in response.data

    def test_cartes_financieres_reprises_sans_modification(self, ctx):
        from apps.treasury import dashboard

        data = get(ctx.president.user).data
        reference = dashboard.finance_cards(ctx.club, None)
        for key in ("contributions", "cash", "expenses_by_category", "upcoming_finance"):
            assert data[key] == reference[key]
        assert data["currency"] == reference["currency"]

    def test_une_carte_qui_plante_ne_casse_pas_les_autres(self, ctx, monkeypatch):
        def boom(_ctx):
            raise RuntimeError("secret interne")

        monkeypatch.setitem(board_dashboard._BUILDERS, "results", boom)
        response = get(ctx.president.user)
        assert response.status_code == 200
        assert response.data["results"] == {"error": "Impossible de charger les résultats."}
        assert "secret interne" not in json.dumps(response.data)
        assert "error" not in response.data["attendance"] and "error" not in response.data["cash"]

    def test_la_lecture_n_est_pas_journalisee_et_n_ecrit_rien(self, ctx):
        before = AuditLog.objects.count()
        get(ctx.president.user)
        for section in board_dashboard.ALL_SECTIONS:
            get_section(ctx.president.user, section)
        assert AuditLog.objects.count() == before


# ---------------------------------------------------------------------------
# Présences et assiduité
# ---------------------------------------------------------------------------


class TestAttendance:
    @pytest.fixture
    def trained(self, ctx):
        s1, s2 = make_session(ctx), make_session(ctx)
        everyone = list(Membership.all_objects.filter(club=ctx.club, status=Membership.Status.ACTIVE))
        # s1 : tout le monde présent sauf le joueur (absent) et le Coach (retard) ; s2 : tout le monde présent
        for m in everyone:
            if m.pk == ctx.player.pk:
                mark(ctx, s1, m, Attendance.Status.EXCUSED_ABSENT)
            elif m.pk == ctx.coach.pk:
                mark(ctx, s1, m, Attendance.Status.LATE_ABSENT)
            else:
                mark(ctx, s1, m, Attendance.Status.PRESENT)
            mark(ctx, s2, m, Attendance.Status.PRESENT)
        return {"s1": s1, "s2": s2, "n": len(everyone)}

    def test_taux_et_compteurs(self, ctx, trained):
        card = get(ctx.president.user).data["attendance"]
        n = trained["n"]
        assert card["events_count"] == 2
        assert card["totals"]["expected"] == 2 * n
        assert card["totals"]["late"] == 1 and card["totals"]["excused"] == 1
        # retard compté absent (défaut du club) : (n-2) + n présents sur 2n
        assert card["average_rate"] == str(attendance_rate_percent(2 * n - 2, 2 * n))
        assert len(card["points"]) == 2 and card["points"][0]["rate"] == str(attendance_rate_percent(n - 2, n))
        assert card["by_kind"]["session"]["events"] == 2 and card["by_kind"]["match"]["events"] == 0

    def test_taux_arrondi_a_l_unite_comme_la_page_entrainements(self, ctx, trained):
        """Spec §9 : le taux affiché ici est égal à celui de
        ``GET /sport/sessions/{id}/stats/`` (arrondi à l'unité, A4.1)."""

        assert board_dashboard._pct(10, 29) == "34"  # 34,48 % -> 34
        assert board_dashboard._pct(1, 8) == "13"  # 12,5 % -> 13 (demi vers le haut)
        assert board_dashboard._pct(0, 0) is None
        points = {p["event_id"]: p["rate"] for p in get(ctx.president.user).data["attendance"]["points"]}
        for event in (trained["s1"], trained["s2"]):
            url = reverse("sport:session-stats", args=[event.session.pk])
            sport_rate = client_for(ctx.coach.user).get(url).data["attendance"]["rate"]
            assert points[event.pk] == str(sport_rate)

    def test_retard_compte_present_selon_le_club(self, ctx, trained):
        type(ctx.club.settings).objects.filter(club=ctx.club).update(late_arrival_counts_absent=False)
        card = get(ctx.president.user).data["attendance"]
        n = trained["n"]
        assert card["average_rate"] == str(attendance_rate_percent(2 * n - 1, 2 * n))

    def test_detail_seances_et_ranking(self, ctx, trained):
        data = get_section(ctx.president.user, "attendance").data
        assert data["sessions"]["count"] == 2
        assert {"present", "late", "excused", "absent", "rate", "date"} <= set(data["sessions"]["items"][0])
        ranking = get_section(ctx.president.user, "attendance_ranking").data
        names = [p["player_name"] for p in ranking["players"]["items"]]
        assert len(names) == trained["n"] and ranking["players"]["items"][-1]["rate"] in ("50", "100")
        card = get(ctx.president.user).data["attendance_ranking"]
        assert len(card["top"]) == 5 and card["top"][0]["rate"] == "100"
        assert not {p["membership_id"] for p in card["top"]} & {p["membership_id"] for p in card["bottom"]}

    def test_joueur_arrive_apres_l_evenement_non_attendu(self, ctx):
        # Séance pointée : une séance sans aucun pointage n'est plus comptée (CDC 10.3 n° 185).
        mark(ctx, make_session(ctx), ctx.player, Attendance.Status.PRESENT)
        newcomer = make_member(ctx.club)  # joined_on = aujourd'hui + 0 : attendu aujourd'hui
        Membership.all_objects.filter(pk=newcomer.pk).update(joined_on=timezone.now().date() + datetime.timedelta(days=5))
        card = get(ctx.president.user).data["attendance"]
        expected_members = Membership.all_objects.filter(club=ctx.club, status=Membership.Status.ACTIVE).count() - 1
        assert card["totals"]["expected"] == expected_members

    def test_seance_du_jour_non_pointee_ni_moyenne_ni_courbe(self, ctx):
        """Une séance sans aucun pointage (dont celle du jour, pas encore
        pointée) n'entre ni dans la moyenne ni dans la courbe : taux ``null``,
        jamais 0 % (CDC 10.3 n° 185)."""

        today = sport_services.get_club_today(ctx.club)

        pointed = make_session(ctx, day=today)
        mark(ctx, pointed, ctx.player, Attendance.Status.PRESENT)
        mark(ctx, pointed, ctx.captain, Attendance.Status.PRESENT)
        rate_before = get(ctx.president.user).data["attendance"]["average_rate"]
        unmarked = make_session(ctx, day=today)  # séance du jour, personne n'est encore pointé
        card = get(ctx.president.user).data["attendance"]
        assert card["average_rate"] == rate_before and card["average_rate"] not in (None, "0")
        assert card["events_count"] == 1 and card["unmarked_count"] == 1
        assert [p["event_id"] for p in card["points"]] == [pointed.pk]
        assert card["last_rate"] == card["points"][-1]["rate"]
        month = next(s for s in card["series"] if s["month"] == today.strftime("%Y-%m"))
        assert month["events"] == 1 and month["rate"] == rate_before
        sessions = get_section(ctx.president.user, "attendance").data["sessions"]["items"]
        row = next(s for s in sessions if s["event_id"] == unmarked.pk)
        assert row["rate"] is None and row["marked"] is False

    def test_seule_seance_non_pointee_aucune_moyenne(self, ctx):
        make_session(ctx, day=sport_services.get_club_today(ctx.club))
        card = get(ctx.president.user).data["attendance"]
        assert card["average_rate"] is None and card["last_rate"] is None
        assert card["points"] == [] and card["events_count"] == 0 and card["unmarked_count"] == 1
        assert get(ctx.president.user).data["attendance_ranking"]["players_count"] == 0

    def test_matchs_hors_moyenne_avec_leur_propre_taux(self, ctx):
        today = sport_services.get_club_today(ctx.club)
        session = make_session(ctx, day=today)
        for m in Membership.all_objects.filter(club=ctx.club, status=Membership.Status.ACTIVE):
            mark(ctx, session, m, Attendance.Status.PRESENT)
        match = make_match(ctx, day=today).event
        mark(ctx, match, ctx.player, Attendance.Status.ABSENT)  # match pointé : personne présent
        card = get(ctx.president.user).data["attendance"]
        assert card["average_rate"] == "100"  # le match à 0 % n'entre pas dans la moyenne
        assert card["by_kind"]["session"] == {"events": 1, "average_rate": "100"}
        assert card["by_kind"]["match"] == {"events": 1, "average_rate": "0"}
        assert all(p["kind"] == "session" for p in card["points"])
        sessions = get_section(ctx.president.user, "attendance").data["sessions"]["items"]
        assert {s["event_id"] for s in sessions} == {session.pk}
        ranking = get_section(ctx.president.user, "attendance_ranking", limit=100).data["players"]["items"]
        assert all(p["rate"] == "100" and p["expected"] == 1 for p in ranking)

    def test_pagination_du_detail(self, ctx):
        for _ in range(3):
            make_session(ctx)
        data = get_section(ctx.president.user, "attendance", limit=2).data
        assert len(data["sessions"]["items"]) == 2 and data["sessions"]["next_offset"] == 2
        page = get_section(ctx.president.user, "attendance", limit=2, offset=2, only="sessions").data
        assert len(page["sessions"]["items"]) == 1 and page["sessions"]["next_offset"] is None


class TestAttendanceEqualsTrainingPage:
    """Spec §9 : le taux de présence du tableau de bord est **égal** à celui de
    la page « Entraînements » pour la même période (définition unique,
    CDC 10.3 n° 185 : séances seulement, séance non pointée exclue, total des
    présents ÷ total des attendus arrondi une seule fois)."""

    @pytest.fixture
    def season_data(self, ctx):
        today = sport_services.get_club_today(ctx.club)

        def day(days_ago):
            return max(today - datetime.timedelta(days=days_ago), ctx.season.start_date)

        active = list(Membership.all_objects.filter(club=ctx.club, status=Membership.Status.ACTIVE))
        s1 = make_session(ctx, day=day(5))  # seul le joueur est présent
        mark(ctx, s1, ctx.player, Attendance.Status.PRESENT)
        s2 = make_session(ctx, day=day(4))  # tout le monde présent sauf un retard (compté absent par défaut)
        for m in active:
            mark(ctx, s2, m, Attendance.Status.LATE_ABSENT if m.pk == ctx.coach.pk else Attendance.Status.PRESENT)
        match = make_match(ctx, day=day(3)).event  # match pointé : hors moyenne
        mark(ctx, match, ctx.captain, Attendance.Status.PRESENT)
        mark(ctx, match, ctx.player, Attendance.Status.ABSENT)
        make_session(ctx, day=day(2))  # séance passée jamais pointée
        make_session(ctx, day=today)  # séance du jour pas encore pointée
        return {"n": len(active), "s1": s1, "s2": s2}

    def test_moyenne_egale_a_la_page_entrainements(self, ctx, season_data):
        n = season_data["n"]
        board = get(ctx.president.user, period="season", season=ctx.season.pk).data["attendance"]
        history = client_for(ctx.coach.user).get(reverse("sport:session-stats-history"), {"period": "season"}).data

        expected = attendance_rate_percent(1 + (n - 1), 2 * n)
        assert history["average_attendance_rate"] == expected
        assert board["average_rate"] == str(expected)
        # Le jeu de données distingue bien la nouvelle définition de l'ancienne
        # (moyenne des taux par séance déjà arrondis).
        old_mean = attendance_rate_percent(
            attendance_rate_percent(1, n) + attendance_rate_percent(n - 1, n), 200
        )
        assert old_mean != expected, (n, old_mean, expected)

        # Courbe : mêmes séances pointées, mêmes taux.
        sport_rates = {r["session_id"]: r["attendance_rate"] for r in history["results"]}
        board_points = {p["event_id"]: p["rate"] for p in board["points"]}
        session_ids = {season_data["s1"].pk, season_data["s2"].pk}
        assert set(board_points) == session_ids
        assert {sid: str(rate) for sid, rate in sport_rates.items() if rate is not None} == board_points
        assert sum(1 for rate in sport_rates.values() if rate is None) == 2 == board["unmarked_count"]
        assert board["events_count"] == 2

    def test_assiduite_egale_a_la_page_entrainements(self, ctx, season_data):
        board = get_section(
            ctx.president.user, "attendance_ranking", period="season", season=ctx.season.pk, limit=100
        ).data["players"]["items"]
        sport = client_for(ctx.coach.user).get(reverse("sport:attendance-ranking"), {"period": "season"}).data
        assert sport["sessions_count"] == 2
        sport_rates = {r["player"]["membership_id"]: (r["sessions"], r["rate"]) for r in sport["results"]}
        assert board, "l'assiduité doit lister les joueurs"
        for row in board:
            sessions, rate = sport_rates[row["membership_id"]]
            assert (row["expected"], row["rate"]) == (sessions, str(rate))
        player = next(r for r in board if r["membership_id"] == ctx.player.pk)
        assert (player["expected"], player["present"], player["rate"]) == (2, 2, "100")  # le match n'est pas compté
        me = client_for(ctx.player.user).get(reverse("sport:attendance-me"), {"period": "season"}).data
        assert str(me["rate"]) == player["rate"]

    def test_retard_compte_present_egalite_conservee(self, ctx, season_data):
        type(ctx.club.settings).objects.filter(club=ctx.club).update(late_arrival_counts_absent=False)
        n = season_data["n"]
        board = get(ctx.president.user, period="season", season=ctx.season.pk).data["attendance"]
        history = client_for(ctx.coach.user).get(reverse("sport:session-stats-history"), {"period": "season"}).data
        assert history["average_attendance_rate"] == attendance_rate_percent(1 + n, 2 * n)
        assert board["average_rate"] == str(history["average_attendance_rate"])

    def test_etancheite_autre_club_sans_effet(self, ctx, other_ctx, season_data):
        before = get(ctx.president.user, period="season", season=ctx.season.pk).data["attendance"]
        other = make_session(other_ctx, day=sport_services.get_club_today(other_ctx.club))
        for m in Membership.all_objects.filter(club=other_ctx.club, status=Membership.Status.ACTIVE):
            mark(other_ctx, other, m, Attendance.Status.ABSENT)
        after = get(ctx.president.user, period="season", season=ctx.season.pk).data["attendance"]
        assert after == before


# ---------------------------------------------------------------------------
# Résultats, discipline, effectif
# ---------------------------------------------------------------------------


class TestResultsAndDiscipline:
    def test_resultats(self, ctx):
        today = timezone.now().date()
        m1 = make_match(ctx, score=(3, 1), day=today)
        make_match(ctx, score=(1, 1), day=today)
        make_match(ctx, score=(0, 2), day=today)
        make_match(ctx, day=today)  # sans feuille de match : non joué
        sheet = MatchSheet.all_objects.get(match=m1)
        MatchGoal.all_objects.create(
            club=ctx.club, match_sheet=sheet, scorer_membership=ctx.player, assist_membership=ctx.coach, created_by=ctx.coach.user
        )
        card = get(ctx.president.user).data["results"]
        assert (card["played"], card["wins"], card["draws"], card["losses"]) == (3, 1, 1, 1)
        assert (card["goals_for"], card["goals_against"]) == (4, 4)
        assert len(card["form"]) == 3 and {f["result"] for f in card["form"]} == {"V", "N", "D"}
        data = get_section(ctx.president.user, "results").data
        assert data["matches"]["count"] == 3
        assert data["top_scorers"][0]["membership_id"] == ctx.player.pk
        assert data["top_assists"][0]["membership_id"] == ctx.coach.pk

    def test_discipline_et_suspension_en_cours(self, ctx):
        event = make_session(ctx)
        sport_services.record_incident(
            event=event, membership=ctx.player, incident_type=Incident.IncidentType.RED_CARD,
            cause=Incident.Cause.SERIOUS_FOUL, recorded_by=ctx.coach.user,
        )
        sport_services.record_incident(
            event=event, membership=ctx.captain, incident_type=Incident.IncidentType.YELLOW_CARD,
            cause=Incident.Cause.BEHAVIOUR, recorded_by=ctx.coach.user,
        )
        card = get(ctx.president.user).data["discipline"]
        assert (card["yellow_cards"], card["red_cards"], card["suspended_count"]) == (1, 1, 1)
        data = get_section(ctx.president.user, "discipline").data
        assert data["suspensions"]["items"][0]["membership_id"] == ctx.player.pk
        assert data["suspensions"]["items"][0]["matches_remaining"] >= 1
        assert data["incidents"]["count"] == 2 and data["incidents"]["items"][0]["cause_label"]
        assert data["most_sanctioned"]

    def test_segment_suspendu_et_somme_egale_au_total(self, ctx):
        event = make_session(ctx)
        for target in (ctx.player, ctx.debtor):  # un joueur en ordre et un joueur en dette, tous deux suspendus
            sport_services.record_incident(
                event=event, membership=target, incident_type=Incident.IncidentType.RED_CARD,
                cause=Incident.Cause.SERIOUS_FOUL, recorded_by=ctx.coach.user,
            )
        card = get(ctx.president.user).data["squad_status"]
        assert card["suspended"]["count"] == 2 and card["suspended"]["also_in_debt_count"] == 1
        total = sum(card[k]["count"] for k in ("in_good_standing", "in_debt", "pending", "suspended"))
        assert total == card["total"]
        detail = get_section(ctx.president.user, "squad_status").data
        assert detail["summary"]["suspended"]["count"] == 2
        assert {i["membership_id"] for i in detail["suspended"]["items"]} == {ctx.player.pk, ctx.debtor.pk}
        debt_items = detail["in_debt"]["items"]
        assert debt_items and debt_items[0]["is_suspended"] is True and "photo" in debt_items[0]
        only = get_section(ctx.president.user, "squad_status", only="suspended").data
        assert only["suspended"]["count"] == 2

    def test_effectif_sans_suspension(self, ctx):
        card = get(ctx.president.user).data["squad_status"]
        assert card["suspended"] == {"count": 0, "rate": "0.00", "also_in_debt_count": 0, "also_in_debt_amount": "0.00"}
        assert card["in_debt"]["count"] == 1 and card["pending"]["count"] == 1


class TestNewcomersAndTrend:
    def test_nouveaux_venus_et_en_attente(self, ctx):
        today = timezone.now().date()
        recruit = make_member(ctx.club)
        Membership.all_objects.filter(pk=recruit.pk).update(joined_on=today, sponsor=ctx.player)
        left = make_member(ctx.club)
        Membership.all_objects.filter(pk=left.pk).update(
            joined_on=today, status=Membership.Status.DEPARTED, left_on=today, left_reason=Membership.LeftReason.RESIGNATION
        )
        MembershipApplicationFactory(membership=ctx.pending_member)
        card = get(ctx.president.user).data["newcomers"]
        assert card["arrivals_count"] == 2 and card["departures_count"] == 1 and card["pending_count"] == 1
        assert len(card["avatars"]) <= 5 and card["series"][-1]["arrivals"] == 2
        data = get_section(ctx.president.user, "newcomers").data
        first = data["arrivals"]["items"][0]
        assert {"player_name", "photo", "position_label", "joined_on", "sponsor_name"} <= set(first)
        pending = data["pending"]["items"][0]
        assert pending["membership_id"] == ctx.pending_member.pk
        assert pending["stage"] in {"fee_unpaid", "sponsor_signature"} and pending["missing_steps"]
        trend = get(ctx.president.user).data["squad_trend"]
        assert trend["series"][-1]["departures"] == 1 and trend["current_count"] >= 1

    def test_adhesion_annulee_exclue_des_arrivees(self, ctx):
        recruit = make_member(ctx.club)
        Membership.all_objects.filter(pk=recruit.pk).update(
            status=Membership.Status.DEPARTED, left_on=timezone.now().date(), left_reason=Membership.LeftReason.CANCELLED
        )
        card = get(ctx.president.user).data["newcomers"]
        assert card["arrivals_count"] == 0 and card["departures_count"] == 0

    def test_adhesion_bloquee_dans_a_traiter(self, ctx):
        app = MembershipApplicationFactory(membership=ctx.pending_member)
        type(app).all_objects.filter(pk=app.pk).update(sponsor_decision=MembershipApplication.SponsorDecision.REFUSED)
        card = get(ctx.president.user).data["to_process"]
        assert card["counts"]["blocked_applications"] == 1 and card["total"] >= 1


# ---------------------------------------------------------------------------
# Aptitude : aucun diagnostic, même avec consentement (règle 11)
# ---------------------------------------------------------------------------


SECRETS = ["DIAGNOSTIC-SECRET", "ALLERGIE-SECRETE", "TRAITEMENT-SECRET", "DECLARATION-SECRETE", "URGENCE-SECRETE", "0899000111"]


class TestFitnessPrivacy:
    @pytest.fixture
    def injured(self, ctx):
        record = HealthRecord(
            club=ctx.club,
            membership=ctx.player,
            fitness_status=HealthRecord.FitnessStatus.UNFIT,
            fitness_return_date=timezone.now().date() + datetime.timedelta(days=10),
            medical_history=SECRETS[0],
            allergies=SECRETS[1],
            ongoing_treatments=SECRETS[2],
            self_declaration=SECRETS[3],
            emergency_contact_name=SECRETS[4],
            emergency_contact_phone=SECRETS[5],
            president_access_granted_at=timezone.now(),  # consentement du joueur au Président
        )
        record.save()
        type(ctx.player.user).objects.filter(pk=ctx.player.user.pk).update(phone="0899000111")
        return record

    def test_aptitude_et_date_de_retour_seulement(self, ctx, injured):
        for user in (ctx.president.user, ctx.vice_president.user):
            card = get(user).data["fitness"]
            assert card["unfit"] == 1
            assert card["unfit_players"][0]["membership_id"] == ctx.player.pk
            assert card["unfit_players"][0]["return_date"] == injured.fitness_return_date.isoformat()
            data = get_section(user, "fitness").data
            assert data["unfit"]["items"][0]["fitness_status"] == "unfit"

    def test_aucun_diagnostic_ni_donnee_privee_dans_les_reponses(self, ctx, injured):
        blob = json.dumps(get(ctx.president.user).data, default=str)
        blob += json.dumps(get_section(ctx.president.user, "fitness").data, default=str)
        for section in board_dashboard.ALL_SECTIONS:
            blob += json.dumps(get_section(ctx.president.user, section, limit=100).data, default=str)
        for secret in SECRETS:
            assert secret not in blob
        for key in ("medical_history", "allergies", "ongoing_treatments", "self_declaration", "emergency_contact", "diagnos", "phone", "email"):
            assert key not in blob.lower(), key

    def test_consultation_non_journalisee_comme_acces_medical(self, ctx, injured):
        before = AuditLog.objects.count()
        get_section(ctx.president.user, "fitness")
        assert AuditLog.objects.count() == before

    def test_sans_fiche_tous_aptes(self, ctx):
        card = get(ctx.president.user).data["fitness"]
        assert card["unfit"] == 0 and card["fit"] == card["total"] and card["no_information"] is True


# ---------------------------------------------------------------------------
# Échéances, matériel, notes, fil
# ---------------------------------------------------------------------------


class TestOtherCards:
    def test_prochaines_echeances(self, ctx):
        today = timezone.now().date()
        make_session(ctx, day=today + datetime.timedelta(days=2))
        make_match(ctx, day=today + datetime.timedelta(days=3), opponent="Rivaux")
        make_session(ctx, day=today + datetime.timedelta(days=31))  # hors fenêtre
        from apps.assemblies.models import Assembly

        Assembly.all_objects.create(
            club=ctx.club, assembly_type=Assembly.AssemblyType.ORDINARY, scheduled_date=today + datetime.timedelta(days=10),
            scheduled_time=datetime.time(10, 0), created_by=ctx.president.user,
        )
        card = get(ctx.president.user).data["upcoming"]
        assert card["count"] == 3 and [i["kind"] for i in card["items"]] == ["session", "match", "assembly"]
        assert "Rivaux" in card["items"][1]["label"]

    def test_materiel_a_retourner(self, ctx):
        today = timezone.now().date()
        past_match = make_match(ctx, day=today - datetime.timedelta(days=10))
        article = Article.all_objects.create(
            club=ctx.club, name="Maillot", category=Article.Category.JERSEY, created_at=timezone.now(), created_by=ctx.coach.user
        )
        for kind, qty, extra in (
            (StockMovement.MovementType.IN_DONATION, 20, {}),
            (StockMovement.MovementType.OUT_LOAN, 11, {"match": past_match, "membership": ctx.player}),
            (StockMovement.MovementType.IN_RETURN, 4, {"match": past_match}),
        ):
            StockMovement.all_objects.create(
                club=ctx.club, article=article, movement_type=kind, quantity=qty, movement_date=today - datetime.timedelta(days=10),
                recorded_by=ctx.coach.user, created_at=timezone.now(), **extra,
            )
        card = get(ctx.president.user).data["equipment_out"]
        assert card["lines_count"] == 1 and card["articles_count"] == 7 and card["overdue_count"] == 1
        item = card["items"][0]
        assert item["article_name"] == "Maillot" and item["overdue_days"] == 3 and item["membership_id"] == ctx.player.pk

    def test_materiel_pas_en_retard_dans_le_delai(self, ctx):
        from apps.clubs.board_dashboard import EQUIPMENT_OVERDUE_AFTER_DAYS

        assert EQUIPMENT_OVERDUE_AFTER_DAYS == 7
        today = timezone.now().date()
        match = make_match(ctx, day=today - datetime.timedelta(days=EQUIPMENT_OVERDUE_AFTER_DAYS))
        article = Article.all_objects.create(
            club=ctx.club, name="Chasuble", category=Article.Category.JERSEY, created_at=timezone.now(), created_by=ctx.coach.user
        )
        for kind, qty, extra in (
            (StockMovement.MovementType.IN_DONATION, 5, {}),
            (StockMovement.MovementType.OUT_LOAN, 2, {"match": match, "membership": ctx.player}),
        ):
            StockMovement.all_objects.create(
                club=ctx.club, article=article, movement_type=kind, quantity=qty, movement_date=today,
                recorded_by=ctx.coach.user, created_at=timezone.now(), **extra,
            )
        card = get(ctx.president.user).data["equipment_out"]
        assert card["lines_count"] == 1 and card["overdue_count"] == 0
        assert card["items"][0]["overdue_days"] == 0 and card["items"][0]["is_overdue"] is False

    def test_a_traiter_depenses_et_assistance(self, ctx):
        from apps.treasury.tests.expense_helpers import make_category

        data = get(ctx.president.user).data
        assert data["to_process"]["counts"] == {
            "expenses_to_validate": 0, "assistance_requests": 0, "minutes_to_sign": 0, "blocked_applications": 0
        }
        assert data["expenses_by_category"]["pending_count"] == 0
        assert make_category  # le détail des dépenses est couvert par les tests de apps.treasury

    def test_notes_du_coach(self, ctx):
        event = make_session(ctx)
        for score in ("6.0", "8.0"):
            Evaluation.all_objects.create(
                club=ctx.club, event=event, membership=ctx.player, evaluator=ctx.coach.user, overall_score=score
            ) if score == "6.0" else Evaluation.all_objects.create(
                club=ctx.club, event=event, membership=ctx.captain, evaluator=ctx.coach.user, overall_score=score
            )
        card = get(ctx.president.user).data["coach_notes"]
        assert card["average"] == "7.00" and card["evaluations"] == 2

    def test_activite_du_fil(self, ctx):
        from apps.social.models import Comment, Like, Post

        post = Post.all_objects.create(club=ctx.club, author=ctx.player.user, body="Bravo l'équipe", visibility=Post.Visibility.CLUB_ONLY)
        Comment.all_objects.create(club=ctx.club, post=post, author=ctx.coach.user, body="Merci")
        Like.all_objects.create(club=ctx.club, post=post, user=ctx.coach.user)
        deleted = Post.all_objects.create(club=ctx.club, author=ctx.player.user, body="x", visibility=Post.Visibility.CLUB_ONLY)
        Post.all_objects.filter(pk=deleted.pk).update(deleted_at=timezone.now())
        card = get(ctx.president.user).data["feed_activity"]
        assert (card["posts_count"], card["comments_count"], card["likes_count"]) == (1, 1, 1)
        assert card["granularity"] == "week" and sum(s["posts"] for s in card["series"]) == 1
        items = get_section(ctx.president.user, "feed_activity").data["posts"]["items"]
        assert items[0]["excerpt"] == "Bravo l'équipe"


# ---------------------------------------------------------------------------
# Étanchéité entre clubs
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    def test_aucune_donnee_d_un_autre_club(self, ctx, other_ctx):
        today = timezone.now().date()
        event = make_session(other_ctx)
        for m in Membership.all_objects.filter(club=other_ctx.club):
            mark(other_ctx, event, m, Attendance.Status.PRESENT)
        make_match(other_ctx, score=(5, 0), opponent="AdversaireSecret")
        make_session(other_ctx, day=today + datetime.timedelta(days=2))
        sport_services.record_incident(
            event=event, membership=other_ctx.player, incident_type=Incident.IncidentType.RED_CARD,
            cause=Incident.Cause.SERIOUS_FOUL, recorded_by=other_ctx.coach.user,
        )
        HealthRecord(
            club=other_ctx.club, membership=other_ctx.player, fitness_status=HealthRecord.FitnessStatus.UNFIT
        ).save()
        make_member(other_ctx.club)  # nouveau venu de l'autre club
        data = get(ctx.president.user).data
        assert data["attendance"]["events_count"] == 0
        assert data["results"]["played"] == 0
        assert data["discipline"]["red_cards"] == 0 and data["discipline"]["suspended_count"] == 0
        assert data["fitness"]["unfit"] == 0
        assert data["upcoming"]["count"] == 0
        assert data["newcomers"]["arrivals_count"] == 0
        assert data["squad_status"]["suspended"]["count"] == 0
        blob = json.dumps(data, default=str) + json.dumps(get_section(ctx.president.user, "results").data, default=str)
        assert "AdversaireSecret" not in blob
        # Noms complets et limites de mot : les noms Faker de l'autre club ne
        # doivent pas donner de faux positif (« Chan » contenu dans « Chandler »).
        def full_names(club):
            return {
                f"{m.user.first_name} {m.user.last_name}".strip()
                for m in Membership.all_objects.filter(club=club).select_related("user")
                if m.user.last_name
            }

        other_names = full_names(other_ctx.club) - full_names(ctx.club)
        for section in ("newcomers", "attendance_ranking", "discipline", "fitness", "squad_status"):
            text = json.dumps(get_section(ctx.president.user, section, limit=100).data, default=str)
            for name in other_names:
                assert not re.search(rf"\b{re.escape(name)}\b", text), f"{name} (autre club) dans la section {section}"

    def test_le_president_d_un_autre_club_ne_voit_que_son_club(self, ctx, other_ctx):
        make_match(other_ctx, score=(2, 2))
        assert get(other_ctx.president.user).data["results"]["played"] == 1
        assert get(ctx.president.user).data["results"]["played"] == 0


# ---------------------------------------------------------------------------
# Requêtes bornées
# ---------------------------------------------------------------------------


class TestQueryCount:
    def _count(self, user):
        client = client_for(user)
        with CaptureQueriesContext(connection) as queries:
            assert client.get(reverse(URL)).status_code == 200
        return len(queries)

    def test_le_nombre_de_requetes_ne_depend_pas_du_volume(self, ctx):
        small = self._count(ctx.president.user)
        today = timezone.now().date()
        players = [make_member(ctx.club) for _ in range(20)]
        _backdate(ctx.club)
        for i in range(4):
            event = make_session(ctx, day=today - datetime.timedelta(days=i % 2))
            for m in players:
                mark(ctx, event, m, Attendance.Status.PRESENT)
            make_match(ctx, score=(i, 1))
        today_event = make_session(ctx)  # un événement du jour reste modifiable
        for m in players[:5]:
            sport_services.record_incident(
                event=today_event, membership=m, incident_type=Incident.IncidentType.YELLOW_CARD,
                cause=Incident.Cause.BEHAVIOUR, recorded_by=ctx.coach.user,
            )
        for m in players[5:8]:
            HealthRecord(club=ctx.club, membership=m, fitness_status=HealthRecord.FitnessStatus.UNFIT).save()
        big = self._count(ctx.president.user)
        assert big <= small + 2, (small, big)

    def test_budget_de_requetes_absolu(self, ctx):
        assert self._count(ctx.president.user) < 150


# ---------------------------------------------------------------------------
# Destination d'arrivée (default_landing)
# ---------------------------------------------------------------------------


def profile(user):
    return client_for(user).get(reverse("clubs:profile-me"))


class TestDefaultLanding:
    def test_profil_selon_les_roles(self, ctx):
        for membership, expected in (
            (ctx.president, "board_dashboard"),
            (ctx.vice_president, "board_dashboard"),
            (ctx.coach, "home"),
            (ctx.player, "home"),
            (ctx.doctor, "home"),
        ):
            data = profile(membership.user).data
            assert data["default_landing"] == expected, membership
            assert data["capabilities"]["can_view_board_dashboard"] is (expected == "board_dashboard")

    def test_cumul_president_et_autre_role(self, ctx):
        MembershipRole.all_objects.create(
            club=ctx.club, membership=ctx.president, role=ROLE.TREASURER, appointed_by=ctx.president.user, appointed_at=timezone.now()
        )
        assert profile(ctx.president.user).data["default_landing"] == "board_dashboard"
        _more_seats(ctx.club)
        coach_vp = make_member(ctx.club, roles=[ROLE.COACH, ROLE.VICE_PRESIDENT])
        assert profile(coach_vp.user).data["default_landing"] == "board_dashboard"

    def test_vp_revoque_retombe_sur_l_accueil_sans_nouveau_jeton(self, ctx):
        client = client_for(ctx.vice_president.user)  # un seul jeton, réutilisé : rien n'est figé dedans
        assert client.get(reverse("clubs:profile-me")).data["default_landing"] == "board_dashboard"
        MembershipRole.all_objects.filter(membership=ctx.vice_president, role=ROLE.VICE_PRESIDENT).update(
            revoked_at=timezone.now()
        )
        data = client.get(reverse("clubs:profile-me")).data
        assert data["default_landing"] == "home" and data["capabilities"]["can_view_board_dashboard"] is False

    def test_connexion_renvoie_default_landing(self, ctx):
        client = APIClient()
        for membership, expected in ((ctx.president, "board_dashboard"), (ctx.player, "home")):
            response = client.post(
                reverse("accounts:login"), {"email": membership.user.email, "password": "MotDePasse123"}, format="json"
            )
            assert response.status_code == 200, response.data
            assert response.data["default_landing"] == expected
            assert response.data["capabilities"]["can_view_board_dashboard"] is (expected == "board_dashboard")


# ---------------------------------------------------------------------------
# Fuseau du club dans « Mon profil » (demande dev-b B8, CLAUDE.md section 7)
# ---------------------------------------------------------------------------


class TestProfileClubTimezone:
    def test_profil_renvoie_le_fuseau_du_club(self, ctx):
        data = profile(ctx.player.user).data
        assert data["club"]["timezone"] == "Africa/Kinshasa"

    def test_fuseau_propre_a_chaque_club(self, ctx):
        other = build_sport_club_context(timezone_name="Europe/Paris")
        assert profile(ctx.coach.user).data["club"]["timezone"] == "Africa/Kinshasa"
        assert profile(other.coach.user).data["club"]["timezone"] == "Europe/Paris"

    def test_fuseau_absent_si_parametres_non_configures(self, ctx):
        from apps.clubs.models import ClubSettings

        ClubSettings.objects.filter(club_id=ctx.club.id).delete()
        response = profile(ctx.player.user)
        assert response.status_code == 200
        assert response.data["club"]["timezone"] is None
