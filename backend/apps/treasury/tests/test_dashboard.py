"""Tableau de bord du Président et du Vice-président : partie financière
(docs/ecrans/club-tableau-de-bord-bureau.md §4 cartes 2, 6, 7, 8 et §5 ;
CDC 4.4.2, 4.4.6, 4.5 ; CLAUDE.md règles 2 et 3).

Fonctions pures de lecture (``apps.treasury.dashboard``) : valeurs exactes
sur un jeu construit, annulation (écriture d'annulation) déduite des
encaissements, cotisation libre jamais en dette, égalité avec le tableau de
bord Trésorerie (même définition), périodes mois et saison, club vide,
étanchéité entre clubs, aucune écriture, nombre de requêtes borné.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.clubs.tests.factories import SeasonFactory
from apps.core.tenant import TenantMismatchError, active_club
from apps.treasury import dashboard, services
from apps.treasury.models import Due, Transaction
from apps.treasury.tests.cash_helpers import club_today, free_type, local_dt, monthly_type, named_member, put_in_debt
from apps.treasury.tests.expense_helpers import make_category, make_expense, pdf_file

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------


def month_start(ctx, months_ago: int) -> datetime.date:
    period = club_today(ctx).replace(day=1)
    for _ in range(months_ago):
        period = (period - datetime.timedelta(days=1)).replace(day=1)
    return period


def month_key(day: datetime.date) -> str:
    return day.strftime("%Y-%m")


def month_period(day: datetime.date) -> dict:
    return {"mode": "month", "month": month_key(day)}


def month_end(day: datetime.date) -> datetime.date:
    nxt = datetime.date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1)
    return nxt - datetime.timedelta(days=1)


def pay(ctx, membership, ctype, *, amount, paid_on):
    return services.record_payment(
        membership=membership,
        contribution_type=ctype,
        amount=amount,
        method="cash",
        reference="",
        paid_on=paid_on,
        recorded_by=ctx.treasurer.user,
    )


def reverse_payment(ctx, payment):
    reversal = services.request_payment_reversal(payment=payment, reason="Saisie en double", requested_by=ctx.treasurer.user)
    return services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)


def release_at(ctx, expense, day: datetime.date):
    return services.release_expense(expense=expense, released_by=ctx.vice_president.user, now=local_dt(ctx, day, 10))


@pytest.fixture
def board(ctx):
    """Jeu construit (M0 = mois en cours, M1 = mois précédent, M2 = il y a
    deux mois), type mensuel obligatoire à 10 $ et type libre :

    - dus : M2 -> A, B, C (10 chacun) ; M1 -> A, C (10 chacun) ;
    - paiements obligatoires : A 10 (M2), A 10 (M1), B 4 (M2), D 10 (M2)
      puis annulé (écriture d'annulation approuvée par le Président) ;
    - paiement libre : A 3 (M2) ;
    - dépenses (M1) : Transport 5 $ libérée, délai de justification dépassé
      (bloquante) ; Matériel 3 $ libérée puis justifiée ; Transport 40 $ en
      attente (aujourd'hui).

    Soldes du jour : A 0, B -6, C -20, D 0. Effectif : 5 inscrits du
    contexte + A, B, C, D ; 1 en attente d'adhésion.
    """

    ctype = monthly_type(ctx)
    free = free_type(ctx)
    m2, m1 = month_start(ctx, 2), month_start(ctx, 1)
    a = named_member(ctx, first_name="Alain", last_name="Aa")
    b = named_member(ctx, first_name="Bruno", last_name="Bb")
    c = named_member(ctx, first_name="Cedric", last_name="Cc")
    d = named_member(ctx, first_name="Denis", last_name="Dd")
    for member in (a, b, c):
        put_in_debt(ctx, member, ctype, amount="10", months_ago=2)
    for member in (a, c):
        put_in_debt(ctx, member, ctype, amount="10", months_ago=1)
    pay_a2 = pay(ctx, a, ctype, amount="10", paid_on=m2.replace(day=15))
    pay_a1 = pay(ctx, a, ctype, amount="10", paid_on=m1.replace(day=5))
    pay_b = pay(ctx, b, ctype, amount="4", paid_on=m2.replace(day=15))
    pay_free = pay(ctx, a, free, amount="3", paid_on=m2.replace(day=15))
    pay_d = pay(ctx, d, ctype, amount="10", paid_on=m2.replace(day=15))
    reverse_payment(ctx, pay_d)

    transport = make_category(ctx, name="Transport")
    material = make_category(ctx, name="Matériel")
    e1 = make_expense(ctx, transport, amount="5", expense_date=m1.replace(day=12))
    e2 = make_expense(ctx, material, amount="3", expense_date=m1.replace(day=12))
    release_at(ctx, e1, m1.replace(day=12))
    release_at(ctx, e2, m1.replace(day=12))
    services.justify_expense(expense=e2, uploaded_by=ctx.treasurer.user, file=pdf_file())
    e3 = make_expense(ctx, transport, amount="40")
    return {
        "ctype": ctype, "free": free, "m2": m2, "m1": m1, "a": a, "b": b, "c": c, "d": d,
        "pay_a2": pay_a2, "pay_a1": pay_a1, "pay_b": pay_b, "pay_free": pay_free, "pay_d": pay_d,
        "transport": transport, "material": material, "e1": e1, "e2": e2, "e3": e3,
    }


# ---------------------------------------------------------------------------
# Période
# ---------------------------------------------------------------------------


class TestPeriod:
    def test_mois_par_defaut_mois_en_cours_du_club(self, ctx):
        data = dashboard.finance_cards(ctx.club, None)
        today = club_today(ctx)
        assert data["period"]["mode"] == "month"
        assert data["period"]["month"] == month_key(today)
        assert data["period"]["season_id"] is None
        assert data["period"]["start"] == today.replace(day=1).isoformat()
        assert data["period"]["end"] == month_end(today).isoformat()
        assert data["period"]["label"] == services.french_month_label(today.replace(day=1))
        assert data["currency"] == "USD"

    @pytest.mark.parametrize("month", ["2026-13", "abc", "", "2026-1", 202611])
    def test_mois_invalide(self, ctx, month):
        with pytest.raises(services.TreasuryValidationError) as exc:
            dashboard.finance_cards(ctx.club, {"mode": "month", "month": month})
        assert "AAAA-MM" in str(exc.value)

    def test_mois_futur_refuse(self, ctx):
        nxt = month_end(club_today(ctx)) + datetime.timedelta(days=1)
        with pytest.raises(services.TreasuryValidationError, match="futur"):
            dashboard.finance_cards(ctx.club, month_period(nxt))

    def test_mode_inconnu(self, ctx):
        with pytest.raises(services.TreasuryValidationError, match="période"):
            dashboard.finance_cards(ctx.club, {"mode": "week"})

    def test_saison_inconnue_ou_d_un_autre_club(self, ctx, other_ctx):
        other_season = SeasonFactory(club=other_ctx.club)
        for season_id in (other_season.pk, 999999, "x", None):
            with pytest.raises(services.TreasuryValidationError, match="Saison introuvable"):
                dashboard.finance_cards(ctx.club, {"mode": "season", "season_id": season_id})

    def test_saison_mois_limites_au_mois_en_cours(self, ctx):
        m2 = month_start(ctx, 2)
        season = SeasonFactory(
            club=ctx.club, label="2026-2027", start_date=m2, end_date=month_end(club_today(ctx)) + datetime.timedelta(days=200)
        )
        data = dashboard.finance_cards(ctx.club, {"mode": "season", "season_id": season.pk})
        assert data["period"]["mode"] == "season"
        assert data["period"]["season_id"] == season.pk
        assert data["period"]["month"] is None
        assert data["period"]["label"] == "Saison 2026-2027"
        assert data["period"]["start"] == m2.isoformat()
        assert data["period"]["months"] == [month_key(month_start(ctx, n)) for n in (2, 1, 0)]

    def test_mois_serie_de_douze_mois(self, ctx):
        data = dashboard.finance_cards(ctx.club, month_period(month_start(ctx, 1)))
        months = data["period"]["months"]
        assert len(months) == 12
        assert months[-1] == month_key(month_start(ctx, 1))
        assert months[0] == month_key(month_start(ctx, 12))


# ---------------------------------------------------------------------------
# Cartes : valeurs exactes
# ---------------------------------------------------------------------------


class TestFinanceCards:
    def test_cotisations_mois_m2(self, ctx, board):
        data = dashboard.finance_cards(ctx.club, month_period(board["m2"]))
        contributions = data["contributions"]
        # 10 (A) + 4 (B) + 10 (D) - 10 (annulation de D) = 14 ; + 3 (libre).
        assert contributions["collected"] == "17.00"
        assert contributions["collected_mandatory"] == "14.00"
        assert contributions["collected_free"] == "3.00"
        assert contributions["due_total"] == "30.00"
        assert contributions["matured_due_total"] == "30.00"
        assert contributions["matured_due_covered"] == "14.00"
        assert contributions["collection_rate"] == "46.67"
        series = {row["month"]: row for row in contributions["series"]}
        assert series[month_key(board["m2"])]["collected"] == "17.00"
        assert series[month_key(board["m2"])]["collection_rate"] == "46.67"
        assert series[month_key(board["m2"])]["label"] == services.french_month_label(board["m2"])
        assert month_key(board["m1"]) not in series  # série arrêtée au mois choisi

    def test_cotisations_mois_m1(self, ctx, board):
        contributions = dashboard.finance_cards(ctx.club, month_period(board["m1"]))["contributions"]
        assert contributions["collected"] == "10.00"
        assert contributions["collected_free"] == "0.00"
        assert contributions["matured_due_total"] == "20.00"
        assert contributions["matured_due_covered"] == "10.00"
        assert contributions["collection_rate"] == "50.00"

    def test_meme_definition_que_le_tableau_de_bord_tresorerie(self, ctx, board):
        for month in (board["m2"], board["m1"]):
            contributions = dashboard.finance_cards(ctx.club, month_period(month))["contributions"]
            summary = services.get_treasury_dashboard_summary(ctx.club, period=month)
            assert contributions["collected"] == f"{summary.collected:.2f}"
            assert contributions["matured_due_total"] == f"{summary.matured_due_total:.2f}"
            assert contributions["matured_due_covered"] == f"{summary.matured_due_covered:.2f}"
            assert contributions["collection_rate"] == f"{summary.collection_rate:.2f}"

    def test_cotisations_saison(self, ctx, board):
        season = SeasonFactory(club=ctx.club, start_date=board["m2"], end_date=month_end(club_today(ctx)))
        contributions = dashboard.finance_cards(ctx.club, {"mode": "season", "season_id": season.pk})["contributions"]
        assert contributions["collected"] == "27.00"
        assert contributions["collected_mandatory"] == "24.00"
        assert contributions["collected_free"] == "3.00"
        assert contributions["matured_due_total"] == "50.00"
        assert contributions["matured_due_covered"] == "24.00"
        assert contributions["collection_rate"] == "48.00"
        assert [row["month"] for row in contributions["series"]] == [
            month_key(month_start(ctx, n)) for n in (2, 1, 0)
        ]
        assert [row["collected"] for row in contributions["series"]] == ["17.00", "10.00", "0.00"]

    def test_situation_de_l_effectif(self, ctx, board):
        squad = dashboard.finance_cards(ctx.club, None)["squad_status"]
        assert squad["as_of"] == club_today(ctx).isoformat()
        assert squad["total"] == 10
        assert squad["in_good_standing"] == {"count": 7, "rate": "70.00"}
        assert squad["in_debt"] == {"count": 2, "rate": "20.00", "amount": "26.00"}
        assert squad["pending"] == {"count": 1, "rate": "10.00"}
        # Aucun montant individuel sur la carte (fiche §4).
        assert "items" not in squad

    def test_situation_independante_de_la_periode(self, ctx, board):
        a = dashboard.finance_cards(ctx.club, month_period(board["m2"]))["squad_status"]
        b = dashboard.finance_cards(ctx.club, None)["squad_status"]
        assert a == b

    def test_joueur_parti_exclu(self, ctx, board):
        gone = named_member(ctx, first_name="Parti", last_name="Pp", status=Membership.Status.DEPARTED)
        put_in_debt(ctx, gone, board["ctype"], amount="50", months_ago=1)
        squad = dashboard.finance_cards(ctx.club, None)["squad_status"]
        assert squad["total"] == 10
        assert squad["in_debt"]["amount"] == "26.00"

    def test_caisse(self, ctx, board):
        m1 = dashboard.finance_cards(ctx.club, month_period(board["m1"]))["cash"]
        assert m1["collected"] == "10.00"
        assert m1["spent"] == "8.00"
        assert m1["net"] == "2.00"
        # Caisse disponible = encaissements - dépenses libérées, toujours celle du jour.
        assert m1["available_cash"] == "19.00" == f"{services.get_available_cash(ctx.club):.2f}"
        m2 = dashboard.finance_cards(ctx.club, month_period(board["m2"]))["cash"]
        assert (m2["collected"], m2["spent"], m2["net"]) == ("17.00", "0.00", "17.00")
        series = {row["month"]: row for row in m1["series"]}
        assert series[month_key(board["m2"])] == {
            "month": month_key(board["m2"]),
            "label": services.french_month_label(board["m2"]),
            "collected": "17.00",
            "spent": "0.00",
        }
        assert series[month_key(board["m1"])]["spent"] == "8.00"

    def test_depenses_par_categorie(self, ctx, board):
        expenses = dashboard.finance_cards(ctx.club, month_period(board["m1"]))["expenses_by_category"]
        assert expenses["total_spent"] == "8.00"
        assert expenses["categories"] == [
            {"category_id": board["transport"].pk, "name": "Transport", "amount": "5.00", "count": 1},
            {"category_id": board["material"].pk, "name": "Matériel", "amount": "3.00", "count": 1},
        ]
        assert expenses["pending_count"] == 1
        assert expenses["pending_amount"] == "40.00"
        assert expenses["unjustified_count"] == 1
        assert expenses["release_blocked"] is True
        assert expenses["release_blocked_reason"] == services.EXPENSE_BLOCKED_MESSAGE
        # Aucun bénéficiaire sur la carte (fiche §4, carte 8).
        assert "beneficiary_name" not in str(expenses)

    def test_depenses_cinq_categories_puis_autres(self, ctx):
        m1 = month_start(ctx, 1)
        amounts = ["1", "2", "3", "4", "5", "6", "7"]
        for index, amount in enumerate(amounts):
            category = make_category(ctx, name=f"Catégorie {index}", receipt_required=False)
            release_at(ctx, make_expense(ctx, category, amount=amount, expense_date=m1), m1)
        expenses = dashboard.finance_cards(ctx.club, month_period(m1))["expenses_by_category"]
        assert [row["amount"] for row in expenses["categories"]] == ["7.00", "6.00", "5.00", "4.00", "3.00", "3.00"]
        assert expenses["categories"][-1] == {"category_id": None, "name": "Autres", "amount": "3.00", "count": 2}
        assert expenses["total_spent"] == "28.00"
        assert expenses["release_blocked"] is False

    def test_prochaines_echeances(self, ctx, board):
        today = club_today(ctx)
        m0 = today.replace(day=1)
        # B doit 10 $ au mois en cours, échéance dans 5 jours (pas encore une dette).
        Due(
            club=ctx.club, membership=board["b"], contribution_type=board["ctype"], period=m0,
            amount=Decimal("10"), due_date=today + datetime.timedelta(days=5),
            source=Due.Source.SCHEDULER, created_at=local_dt(ctx, today, 1),
        ).save()
        upcoming = dashboard.finance_cards(ctx.club, None)["upcoming_finance"]
        assert upcoming["as_of"] == today.isoformat()
        assert upcoming["until"] == (today + datetime.timedelta(days=30)).isoformat()
        kinds = [item["kind"] for item in upcoming["items"]]
        assert "contribution_due" in kinds
        due_item = next(item for item in upcoming["items"] if item["kind"] == "contribution_due")
        assert due_item == {
            "kind": "contribution_due",
            "date": (today + datetime.timedelta(days=5)).isoformat(),
            "debt_on": (today + datetime.timedelta(days=6)).isoformat(),
            "label": "Échéance « Mensuelle 10 »",
            "contribution_type_id": board["ctype"].pk,
            "players_count": 1,
            "amount": "10.00",
        }
        # Le solde n'a pas bougé : l'échéance n'est pas échue.
        assert services.get_balance(board["b"]) == Decimal("-6.00")

    def test_justificatif_attendu_dans_les_echeances(self, ctx):
        today = club_today(ctx)
        category = make_category(ctx, name="Arbitrage")
        expense = make_expense(ctx, category, amount="12")
        services.release_expense(expense=expense, released_by=ctx.president.user)
        items = dashboard.finance_cards(ctx.club, None)["upcoming_finance"]["items"]
        assert items == [
            {
                "kind": "expense_justification",
                "date": (today + datetime.timedelta(days=7)).isoformat(),
                "label": "Justificatif attendu : Arbitrage",
                "expense_id": expense.pk,
                "amount": "12.00",
            }
        ]


# ---------------------------------------------------------------------------
# Règles : annulation, cotisation libre, club vide, étanchéité, lecture seule
# ---------------------------------------------------------------------------


class TestRules:
    def test_paiement_annule_non_compte(self, ctx):
        ctype = monthly_type(ctx)
        member = named_member(ctx, first_name="Eric", last_name="Ee")
        m1 = month_start(ctx, 1)
        payment = pay(ctx, member, ctype, amount="25", paid_on=m1.replace(day=3))
        before = dashboard.finance_cards(ctx.club, month_period(m1))
        assert before["contributions"]["collected"] == "25.00"
        assert before["cash"]["available_cash"] == "25.00"

        reverse_payment(ctx, payment)
        after = dashboard.finance_cards(ctx.club, month_period(m1))
        assert after["contributions"]["collected"] == "0.00"
        assert after["contributions"]["collected_mandatory"] == "0.00"
        assert after["cash"]["collected"] == "0.00"
        assert after["cash"]["available_cash"] == "0.00"
        # Le paiement d'origine n'est jamais supprimé (écriture d'annulation).
        assert Transaction.all_objects.filter(club=ctx.club, payment=payment).exists()

    def test_cotisation_libre_jamais_en_dette(self, ctx):
        free = free_type(ctx)
        member = named_member(ctx, first_name="Fabrice", last_name="Ff")
        m1 = month_start(ctx, 1)
        pay(ctx, member, free, amount="7", paid_on=m1.replace(day=8))
        data = dashboard.finance_cards(ctx.club, month_period(m1))
        assert data["contributions"]["collected_free"] == "7.00"
        assert data["contributions"]["collected_mandatory"] == "0.00"
        assert data["contributions"]["due_total"] == "0.00"
        assert data["contributions"]["collection_rate"] is None
        assert data["squad_status"]["in_debt"] == {"count": 0, "rate": "0.00", "amount": "0.00"}
        section = dashboard.finance_section(ctx.club, "contributions", month_period(m1))
        free_row = next(row for row in section["by_type"] if row["contribution_type_id"] == free.pk)
        assert free_row["nature"] == "free"
        assert free_row["collected"] == "7.00"
        assert free_row["due_total"] is None
        assert free_row["collection_rate"] is None
        assert section["debtors"]["items"] == []

    def test_club_vide(self, ctx):
        data = dashboard.finance_cards(ctx.club, None)
        contributions = data["contributions"]
        assert contributions["collected"] == "0.00"
        assert contributions["due_total"] == "0.00"
        assert contributions["collection_rate"] is None
        assert all(row["collected"] == "0.00" for row in contributions["series"])
        # Le contexte : 5 inscrits sans dette et un joueur en attente d'adhésion.
        assert data["squad_status"]["in_good_standing"] == {"count": 5, "rate": "83.33"}
        assert data["squad_status"]["pending"] == {"count": 1, "rate": "16.67"}
        assert data["cash"] == {**data["cash"], "collected": "0.00", "spent": "0.00", "net": "0.00", "available_cash": "0.00"}
        assert data["expenses_by_category"]["categories"] == []
        assert data["expenses_by_category"]["release_blocked"] is False
        assert data["upcoming_finance"]["items"] == []
        for section in dashboard.FINANCE_SECTIONS:
            assert dashboard.finance_section(ctx.club, section, None)["section"] == section

    def test_etancheite_entre_clubs(self, ctx, other_ctx, board):
        theirs = dashboard.finance_cards(other_ctx.club, month_period(board["m2"]))
        assert theirs["currency"] == "CDF"
        assert theirs["contributions"]["collected"] == "0.00"
        assert theirs["cash"]["available_cash"] == "0.00"
        assert theirs["squad_status"]["total"] == 6
        assert theirs["squad_status"]["in_debt"]["count"] == 0
        assert theirs["expenses_by_category"]["pending_count"] == 0
        for section in dashboard.FINANCE_SECTIONS:
            detail = dashboard.finance_section(other_ctx.club, section, month_period(board["m2"]))
            for key in ("payments", "debtors", "expenses", "in_debt", "upcoming"):
                if key in detail:
                    assert detail[key]["items"] == [], (section, key)
        names = str(dashboard.finance_section(other_ctx.club, "squad_status", None))
        assert "Bruno" not in names and "Cedric" not in names
        ours = dashboard.finance_cards(ctx.club, month_period(board["m2"]))
        assert ours["contributions"]["collected"] == "17.00"

    def test_club_actif_different_refuse(self, ctx, other_ctx):
        with active_club(other_ctx.club):
            with pytest.raises(TenantMismatchError):
                dashboard.finance_cards(ctx.club, None)
            with pytest.raises(TenantMismatchError):
                dashboard.finance_section(ctx.club, "cash", None)

    def test_lecture_seule_aucune_ecriture(self, ctx, board):
        logs = AuditLog.objects.count()
        txns = Transaction.all_objects.count()
        with CaptureQueriesContext(connection) as captured:
            dashboard.finance_cards(ctx.club, None)
            for section in dashboard.FINANCE_SECTIONS:
                dashboard.finance_section(ctx.club, section, None)
        writes = [
            q["sql"] for q in captured.captured_queries
            if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        assert writes == []
        assert AuditLog.objects.count() == logs
        assert Transaction.all_objects.count() == txns

    def test_section_inconnue(self, ctx):
        with pytest.raises(services.TreasuryValidationError, match="Section inconnue"):
            dashboard.finance_section(ctx.club, "attendance", None)

    def test_montants_en_chaines_a_deux_decimales(self, ctx, board):
        data = dashboard.finance_cards(ctx.club, month_period(board["m2"]))
        for key in ("collected", "collected_mandatory", "collected_free", "due_total"):
            value = data["contributions"][key]
            assert isinstance(value, str) and value == f"{Decimal(value):.2f}"
        assert isinstance(data["squad_status"]["total"], int)

    def test_section_en_erreur_n_empeche_pas_les_autres(self, ctx, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("panne")

        monkeypatch.setattr(dashboard, "_cash_card", boom)
        data = dashboard.finance_cards(ctx.club, None)
        assert data["cash"] == {"error": "Impossible de charger la caisse."}
        assert data["contributions"]["collected"] == "0.00"


# ---------------------------------------------------------------------------
# Détail des cartes (modales)
# ---------------------------------------------------------------------------


class TestFinanceSection:
    def test_cotisations_detail(self, ctx, board):
        section = dashboard.finance_section(ctx.club, "contributions", month_period(board["m2"]))
        assert section["section"] == "contributions"
        assert section["currency"] == "USD"
        assert section["summary"]["collected"] == "17.00"
        assert "series" not in section["summary"]
        assert len(section["series"]) == 12
        by_type = {row["contribution_type_id"]: row for row in section["by_type"]}
        mandatory = by_type[board["ctype"].pk]
        assert mandatory == {
            "contribution_type_id": board["ctype"].pk,
            "name": "Mensuelle 10",
            "nature": "mandatory",
            "nature_label": "Obligatoire",
            "collected": "14.00",
            "due_total": "30.00",
            "matured_due_total": "30.00",
            "matured_due_covered": "14.00",
            "collection_rate": "46.67",
        }
        assert by_type[board["free"].pk]["collected"] == "3.00"

        payments = section["payments"]
        assert payments["count"] == 4
        assert payments["next_offset"] is None
        by_id = {item["payment_id"]: item for item in payments["items"]}
        assert set(by_id) == {board[k].pk for k in ("pay_a2", "pay_b", "pay_free", "pay_d")}
        assert by_id[board["pay_d"].pk]["status"] == "cancelled"
        assert by_id[board["pay_d"].pk]["status_label"] == "Annulé"
        assert by_id[board["pay_b"].pk] == {
            "payment_id": board["pay_b"].pk,
            "paid_on": board["m2"].replace(day=15).isoformat(),
            "membership_id": board["b"].pk,
            "player_name": "Bruno Bb",
            "contribution_type_id": board["ctype"].pk,
            "contribution_type_name": "Mensuelle 10",
            "nature": "mandatory",
            "amount": "4.00",
            "status": "validated",
            "status_label": "Validé",
        }

        debtors = section["debtors"]
        assert debtors["as_of"] == club_today(ctx).isoformat()
        assert debtors["items"] == [
            {"membership_id": board["c"].pk, "player_name": "Cedric Cc", "amount_due": "20.00"},
            {"membership_id": board["b"].pk, "player_name": "Bruno Bb", "amount_due": "6.00"},
        ]
        assert debtors["count"] == 2

    def test_pagination_voir_plus(self, ctx, board):
        first = dashboard.finance_section(ctx.club, "contributions", month_period(board["m2"]), limit=3)
        assert len(first["payments"]["items"]) == 3
        assert first["payments"]["next_offset"] == 3
        second = dashboard.finance_section(
            ctx.club, "contributions", month_period(board["m2"]), limit=3, offset=3, only="payments"
        )
        assert set(second) == {"section", "period", "currency", "payments"}
        assert len(second["payments"]["items"]) == 1
        assert second["payments"]["next_offset"] is None
        seen = {i["payment_id"] for i in first["payments"]["items"] + second["payments"]["items"]}
        assert len(seen) == 4

    @pytest.mark.parametrize("kwargs,message", [
        ({"limit": 0}, "limite"),
        ({"limit": 101}, "limite"),
        ({"offset": -1}, "décalage"),
        ({"only": "inconnue"}, "Liste inconnue"),
    ])
    def test_parametres_de_liste_invalides(self, ctx, kwargs, message):
        with pytest.raises(services.TreasuryValidationError, match=message):
            dashboard.finance_section(ctx.club, "contributions", None, **kwargs)

    def test_situation_detail_onglets(self, ctx, board):
        section = dashboard.finance_section(ctx.club, "squad_status", month_period(board["m2"]))
        assert section["summary"]["total"] == 10
        assert section["in_debt"]["items"] == [
            {"membership_id": board["c"].pk, "player_name": "Cedric Cc", "amount_due": "20.00"},
            {"membership_id": board["b"].pk, "player_name": "Bruno Bb", "amount_due": "6.00"},
        ]
        good = section["in_good_standing"]
        assert good["count"] == 7
        assert {"membership_id": board["a"].pk, "player_name": "Alain Aa"} in good["items"]
        assert all("amount_due" not in item for item in good["items"])
        assert section["pending"]["count"] == 1
        assert section["pending"]["items"] == [
            {"membership_id": ctx.pending_member.pk, "player_name": services._membership_name(ctx.pending_member)}
        ]

    def test_caisse_detail_cumul(self, ctx, board):
        season = SeasonFactory(club=ctx.club, start_date=board["m2"], end_date=month_end(club_today(ctx)))
        section = dashboard.finance_section(ctx.club, "cash", {"mode": "season", "season_id": season.pk})
        assert section["summary"]["available_cash"] == "19.00"
        assert section["opening_cash"] == "0.00"
        assert section["months"] == [
            {"month": month_key(board["m2"]), "label": services.french_month_label(board["m2"]),
             "collected": "17.00", "spent": "0.00", "net": "17.00", "cash_end": "17.00"},
            {"month": month_key(board["m1"]), "label": services.french_month_label(board["m1"]),
             "collected": "10.00", "spent": "8.00", "net": "2.00", "cash_end": "19.00"},
            {"month": month_key(month_start(ctx, 0)), "label": services.french_month_label(month_start(ctx, 0)),
             "collected": "0.00", "spent": "0.00", "net": "0.00", "cash_end": "19.00"},
        ]
        m1_only = dashboard.finance_section(ctx.club, "cash", month_period(board["m1"]))
        assert m1_only["months"][-1]["cash_end"] == "19.00"
        assert m1_only["months"][-2]["cash_end"] == "17.00"

    def test_depenses_detail(self, ctx, board):
        section = dashboard.finance_section(ctx.club, "expenses_by_category", month_period(board["m1"]))
        assert section["summary"]["total_spent"] == "8.00"
        assert [row["name"] for row in section["categories"]] == ["Transport", "Matériel"]
        items = {item["expense_id"]: item for item in section["expenses"]["items"]}
        assert set(items) == {board["e1"].pk, board["e2"].pk}
        e1 = items[board["e1"].pk]
        assert e1["status"] == "released"
        assert e1["status_label"] == "Libérée"
        assert e1["is_overdue"] is True
        assert e1["amount"] == "5.00"
        assert e1["category_name"] == "Transport"
        assert e1["beneficiary_name"] == "Station Total Gombe"
        assert items[board["e2"].pk]["status"] == "justified"
        assert items[board["e2"].pk]["is_overdue"] is False
        # La dépense en attente d'aujourd'hui apparaît dans la période en cours.
        current = dashboard.finance_section(ctx.club, "expenses_by_category", None)
        assert [item["expense_id"] for item in current["expenses"]["items"]] == [board["e3"].pk]
        assert current["expenses"]["items"][0]["status_label"] == "En attente"

    def test_echeances_detail(self, ctx, board):
        section = dashboard.finance_section(ctx.club, "upcoming_finance", None)
        assert section["section"] == "upcoming_finance"
        assert section["upcoming"]["items"] == []
        assert section["upcoming"]["count"] == 0


# ---------------------------------------------------------------------------
# Performance : requêtes agrégées, nombre borné
# ---------------------------------------------------------------------------


def _count_queries(func) -> int:
    with CaptureQueriesContext(connection) as captured:
        func()
    return len(captured.captured_queries)


class TestQueryCount:
    def test_nombre_de_requetes_independant_du_volume(self, ctx, board):
        cards = lambda: dashboard.finance_cards(ctx.club, month_period(board["m2"]))  # noqa: E731
        sections = {
            name: (lambda name=name: dashboard.finance_section(ctx.club, name, month_period(board["m2"])))
            for name in dashboard.FINANCE_SECTIONS
        }
        before = _count_queries(cards)
        before_sections = {name: _count_queries(func) for name, func in sections.items()}

        for index in range(15):
            member = named_member(ctx, first_name=f"Joueur{index}", last_name="Vol")
            put_in_debt(ctx, member, board["ctype"], amount="10", months_ago=2)
            pay(ctx, member, board["ctype"], amount="3", paid_on=board["m2"].replace(day=20))
            pay(ctx, member, board["free"], amount="1", paid_on=board["m2"].replace(day=20))

        assert _count_queries(cards) == before
        assert before <= 25
        for name, func in sections.items():
            assert _count_queries(func) == before_sections[name], name
            assert before_sections[name] <= 20, name
