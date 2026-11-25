"""Grille des cotisations -- services (tâche 2.6 ; CDC 4.4.3, 4.4.7 ;
10.2 n° 4 ; CLAUDE.md règles n° 2 et 3).

Invariants vérifiés :
- la grille ne stocke rien : chaque cellule vient des montants dus et de la
  projection de répartition 4.4.3 (répartition affichée = répartition
  réelle) ;
- l'état « impayé échu » suit exactement la règle du solde (échéance +
  tolérance) et la somme des impayés échus d'un type = montant à
  régulariser de ``get_balance_summary`` ;
- un type libre n'est jamais « impayé » ;
- recherche, tri, filtre « avec impayés », rôles, étanchéité entre clubs.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from apps.clubs.models import Membership
from apps.core.tenant import TenantMismatchError
from apps.treasury import services
from apps.treasury.models import PaymentAllocation
from apps.treasury.tests.grid_helpers import (
    NOW,
    TODAY,
    YEAR,
    attach,
    attached_type,
    free_monthly_type,
    grid_for,
    make_dues,
    pay,
    period,
    player,
    row_of,
)

pytestmark = pytest.mark.django_db

D = Decimal


def states(row):
    return [cell.state for cell in row.cells]


def allocated(row):
    return [cell.allocated for cell in row.cells]


class TestRepartitionAffichee:
    def test_exemple_du_cdc_40_en_mars_couvre_mars_a_juin(self, ctx):
        """CDC 4.4.3 : joueur à 10 $ à jour fin février, 40 $ en mars ->
        mars, avril, mai, juin."""

        ctype = attached_type(ctx)
        member = player(ctx, "Adolphe", "Akeba")
        attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, range(1, 10))
        pay(ctx, member, ctype, "20", datetime.date(2026, 2, 5))
        pay(ctx, member, ctype, "40", datetime.date(2026, 3, 5))

        row = row_of(grid_for(ctx, ctype), member)
        assert allocated(row) == [D("10.00")] * 6 + [D("0.00")] * 6
        assert states(row) == ["paid"] * 6 + ["overdue"] * 3 + ["upcoming"] * 3
        assert row.total == D("60.00")
        assert row.overdue_amount == D("30.00") and row.has_unpaid

    def test_cellules_egales_aux_repartitions_enregistrees(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Gaston", "Lutete")
        attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, range(1, 10))
        pay(ctx, member, ctype, "60", datetime.date(2026, 1, 3))
        pay(ctx, member, ctype, "15", datetime.date(2026, 8, 1))

        row = row_of(grid_for(ctx, ctype), member)
        stored = {
            allocation.period: allocation.amount
            for allocation in PaymentAllocation.all_objects.filter(membership=member, contribution_type=ctype)
        }
        for cell in row.cells:
            assert cell.allocated == stored.get(cell.period, D("0.00"))
        # 75 $ : janvier à juillet payés, août partiel (5 $), septembre échu.
        assert states(row)[:9] == ["paid"] * 7 + ["partial", "overdue"]
        assert row.cells[7].allocated == D("5.00") and row.cells[7].overdue_amount == D("5.00")

    def test_paiement_anticipe_s_etale_sur_les_mois_futurs(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Fabien", "Tshala")
        attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, range(1, 10))
        pay(ctx, member, ctype, "120", datetime.date(2026, 1, 4))

        row = row_of(grid_for(ctx, ctype), member)
        assert states(row) == ["paid"] * 12
        assert row.total == D("120.00") and not row.has_unpaid
        # Octobre à décembre : pas encore de montant dû, montant attendu = tarif.
        assert [cell.amount_due for cell in row.cells[9:]] == [D("10.00")] * 3

    def test_annulation_rend_le_mois_impaye(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Serge", "Lokwa")
        attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, [1])
        payment = pay(ctx, member, ctype, "10", datetime.date(2026, 1, 5))
        assert row_of(grid_for(ctx, ctype), member).cells[0].state == "paid"

        reversal = services.request_payment_reversal(
            payment=payment, reason="Saisie en double", requested_by=ctx.treasurer.user, now=NOW
        )
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, now=NOW)
        cell = row_of(grid_for(ctx, ctype), member).cells[0]
        assert (cell.state, cell.allocated, cell.overdue_amount) == ("overdue", D("0.00"), D("10.00"))


class TestEtatsEtEcheance:
    def test_mois_courant_avant_echeance_est_a_venir(self, ctx):
        """10.2 n° 4 : échéance le 10 sans tolérance ; le 5 septembre, le
        montant dû de septembre n'est pas encore une dette."""

        ctype = attached_type(ctx)
        member = player(ctx, "Joel", "Pindi")
        attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, [9])
        cell = row_of(grid_for(ctx, ctype, today=datetime.date(2026, 9, 5)), member).cells[8]
        assert (cell.state, cell.overdue_amount) == ("upcoming", D("0.00"))
        cell = row_of(grid_for(ctx, ctype, today=datetime.date(2026, 9, 11)), member).cells[8]
        assert (cell.state, cell.overdue_amount) == ("overdue", D("10.00"))

    def test_tolerance_du_club_repousse_l_echeance(self, ctx):
        settings_obj = ctx.club.settings
        settings_obj.debt_tolerance_days = 5
        settings_obj.save()
        ctype = attached_type(ctx)
        member = player(ctx, "Fredy", "Sumbu")
        attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, [9])
        assert row_of(grid_for(ctx, ctype, today=datetime.date(2026, 9, 15)), member).cells[8].state == "upcoming"
        assert row_of(grid_for(ctx, ctype, today=datetime.date(2026, 9, 16)), member).cells[8].state == "overdue"

    def test_mois_avant_le_rattachement_non_dus(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Alain", "Tondo")
        attach(ctx, member, ctype, starts_on=period(4))
        make_dues(ctx, member, ctype, range(4, 10))
        row = row_of(grid_for(ctx, ctype), member)
        assert states(row)[:3] == ["not_due"] * 3
        assert [cell.amount_due for cell in row.cells[:3]] == [None] * 3
        assert states(row)[3:9] == ["overdue"] * 6

    def test_suspension_mois_futurs_non_dus(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Jose", "Banza")
        attach(ctx, member, ctype)
        services.create_contribution_suspension(
            membership=member, starts_on=period(10), reason="Blessure longue durée", decided_by=ctx.president.user
        )
        row = row_of(grid_for(ctx, ctype), member)
        assert states(row)[9:] == ["not_due"] * 3

    def test_changement_de_tarif_ne_touche_que_les_mois_futurs(self, ctx):
        """Invariant 7 : les montants dus passés gardent leur montant figé ;
        les mois futurs affichent le nouveau tarif."""

        ctype = attached_type(ctx)
        member = player(ctx, "Deo", "Kikuni")
        attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, range(1, 10))
        services.update_contribution_type(contribution_type=ctype, updated_by=ctx.president.user, amount="15", now=NOW)
        row = row_of(grid_for(ctx, ctype), member)
        assert [cell.amount_due for cell in row.cells[:9]] == [D("10.00")] * 9
        assert [cell.amount_due for cell in row.cells[9:]] == [D("15.00")] * 3

    def test_joueur_arrive_en_cours_d_annee(self, ctx):
        """Type « Tous » : les mois précédant l'entrée du joueur ne sont pas
        dus ; son mois d'arrivée l'est en entier (10.2 n° 5) s'il a été
        généré."""

        ctype = services.create_contribution_type(
            club=ctx.club,
            created_by=ctx.president.user,
            name="Mensuelle tous",
            nature="mandatory",
            periodicity="monthly",
            amount="10",
            now=datetime.datetime(2025, 1, 5, tzinfo=datetime.timezone.utc),
        )
        member = player(ctx, "Arrive", "Enjuin", joined_on=datetime.date(2026, 6, 20))
        make_dues(ctx, member, ctype, [6, 7, 8, 9])
        row = row_of(grid_for(ctx, ctype), member)
        assert states(row)[:5] == ["not_due"] * 5
        assert states(row)[5:9] == ["overdue"] * 4


class TestCoherenceAvecLeSolde:
    @pytest.mark.parametrize(
        "payments",
        [
            [],
            [("10", 1)],
            [("25", 2)],
            [("40", 3), ("5", 8)],
            [("90", 1)],
            [("200", 1)],
        ],
    )
    def test_impayes_echus_egaux_au_montant_a_regulariser(self, ctx, payments):
        ctype = attached_type(ctx)
        member = player(ctx, "Jean", "Lufu")
        attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, range(1, 10))
        for amount, month in payments:
            pay(ctx, member, ctype, amount, datetime.date(2026, month, 5))
        row = row_of(grid_for(ctx, ctype), member)
        summary = services.get_balance_summary(member, at_date=TODAY)
        assert row.overdue_amount == summary.amount_due
        assert row.has_unpaid is (not summary.is_in_good_standing)


class TestTypeLibre:
    def test_type_libre_jamais_rouge(self, ctx):
        """CLAUDE.md règle n° 3 : une cotisation libre ne crée jamais de
        dette ; les mois sans versement sont « — » (état free, 0)."""

        ctype = free_monthly_type(ctx)
        member = player(ctx, "Libre", "Donateur")
        pay(ctx, member, ctype, "5", datetime.date(2026, 3, 12))
        row = row_of(grid_for(ctx, ctype), member)
        assert set(states(row)) == {"free"}
        assert row.cells[2].allocated == D("5.00")
        assert all(cell.overdue_amount == 0 for cell in row.cells)
        assert row.total == D("5.00") and not row.has_unpaid
        assert all(cell.amount_due is None for cell in row.cells)
        assert services.get_balance_summary(member, at_date=TODAY).balance == D("0.00")


class TestLignes:
    def test_seuls_les_joueurs_rattaches_ou_avec_donnees(self, ctx):
        ctype = attached_type(ctx)
        attached = player(ctx, "Rattache", "Un")
        not_attached = player(ctx, "Non", "Rattache")
        attach(ctx, attached, ctype)
        ids = {row.membership.pk for row in grid_for(ctx, ctype).rows}
        assert attached.pk in ids and not_attached.pk not in ids

    def test_joueur_parti_garde_son_historique(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Parti", "Historique")
        attach(ctx, member, ctype, ends_on=datetime.date(2026, 3, 31))
        make_dues(ctx, member, ctype, [1, 2, 3])
        member.status = Membership.Status.DEPARTED
        member.left_on = datetime.date(2026, 3, 31)
        member.left_reason = Membership.LeftReason.RESIGNATION
        member.left_by = ctx.president.user
        member.save()
        row = row_of(grid_for(ctx, ctype), member)
        assert states(row)[:3] == ["overdue"] * 3 and states(row)[3:] == ["not_due"] * 9

    def test_annee_sans_donnees(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Vide", "Annee")
        attach(ctx, member, ctype)
        grid = grid_for(ctx, ctype, year=2025)
        assert grid.rows == ()

    def test_annee_invalide(self, ctx):
        ctype = attached_type(ctx)
        with pytest.raises(services.TreasuryValidationError):
            grid_for(ctx, ctype, year=1999)
        with pytest.raises(services.TreasuryValidationError):
            grid_for(ctx, ctype, year="abc")


class TestRechercheTriFiltre:
    @pytest.fixture
    def grid(self, ctx):
        ctype = attached_type(ctx)
        members = {
            "akeba": player(ctx, "Adolphe", "Akeba", jersey=1),
            "dimbu": player(ctx, "Dunga", "Dimbu", jersey=16),
            "kalala": player(ctx, "Patrick", "Kalala", jersey=36),
            "eleve": player(ctx, "Élodie", "Été", jersey=7),
        }
        for member in members.values():
            attach(ctx, member, ctype)
            make_dues(ctx, member, ctype, range(1, 10))
        pay(ctx, members["akeba"], ctype, "90", datetime.date(2026, 1, 5))
        pay(ctx, members["dimbu"], ctype, "30", datetime.date(2026, 1, 5))
        pay(ctx, members["kalala"], ctype, "120", datetime.date(2026, 1, 5))
        pay(ctx, members["eleve"], ctype, "50", datetime.date(2026, 1, 5))
        return grid_for(ctx, ctype), members

    @staticmethod
    def names(rows):
        return [row.membership.user.last_name for row in rows]

    def test_tri_par_nom_par_defaut(self, grid):
        rows = services.filter_grid_rows(grid[0])
        assert self.names(rows) == ["Akeba", "Dimbu", "Été", "Kalala"]
        assert self.names(services.filter_grid_rows(grid[0], ordering="-name")) == ["Kalala", "Été", "Dimbu", "Akeba"]

    def test_tri_sur_le_total(self, grid):
        assert self.names(services.filter_grid_rows(grid[0], ordering="total")) == ["Dimbu", "Été", "Akeba", "Kalala"]
        assert self.names(services.filter_grid_rows(grid[0], ordering="-total"))[0] == "Kalala"

    def test_tri_inconnu(self, grid):
        with pytest.raises(services.TreasuryValidationError):
            services.filter_grid_rows(grid[0], ordering="solde")

    def test_recherche_insensible_casse_et_accents(self, grid):
        assert self.names(services.filter_grid_rows(grid[0], query="ete")) == ["Été"]
        assert self.names(services.filter_grid_rows(grid[0], query="PATRICK kal")) == ["Kalala"]
        assert self.names(services.filter_grid_rows(grid[0], query="16")) == ["Dimbu"]
        assert services.filter_grid_rows(grid[0], query="inconnu") == []

    def test_filtre_avec_impayes(self, grid):
        rows = services.filter_grid_rows(grid[0], unpaid_only=True)
        assert self.names(rows) == ["Dimbu", "Été"]


class TestRolesEtEtancheite:
    @pytest.mark.parametrize("role", ["president", "vice_president", "treasurer", "assistant_treasurer"])
    def test_lecture_autorisee(self, ctx, role):
        ctype = attached_type(ctx)
        grid_for(ctx, ctype, user=getattr(ctx, role))

    def test_joueur_refuse(self, ctx):
        ctype = attached_type(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            grid_for(ctx, ctype, user=ctx.player)

    def test_bureau_d_un_autre_club_refuse(self, ctx, other_ctx):
        ctype = attached_type(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            grid_for(ctx, ctype, user=other_ctx.treasurer)

    def test_joueur_d_un_autre_club_refuse_dans_le_detail(self, ctx, other_ctx):
        ctype = attached_type(ctx)
        with pytest.raises(TenantMismatchError):
            grid_for(ctx, ctype, membership=other_ctx.player)

    def test_aucune_donnee_d_un_autre_club(self, ctx, other_ctx):
        ctype = attached_type(ctx)
        other_type = attached_type(other_ctx)
        mine = player(ctx, "Mien", "Club")
        attach(ctx, mine, ctype)
        theirs = player(other_ctx, "Autre", "Club")
        attach(other_ctx, theirs, other_type)
        make_dues(other_ctx, theirs, other_type, range(1, 10))
        ids = {row.membership.pk for row in grid_for(ctx, ctype).rows}
        assert ids == {mine.pk}


class TestDetailDuMois:
    def test_paiements_du_mois_avec_part_affectee_et_etalement(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Deny", "Wamba")
        attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, range(1, 10))
        first = pay(ctx, member, ctype, "15", datetime.date(2026, 1, 5))
        second = pay(ctx, member, ctype, "40", datetime.date(2026, 2, 5))

        detail = services.get_grid_month_detail(
            contribution_type=ctype, membership=member, year=YEAR, month=2,
            requested_by=ctx.treasurer.user, today=TODAY,
        )
        assert detail.cell.state == "paid" and detail.cell.allocated == D("10.00")
        by_payment = {item.payment.pk: item for item in detail.payments}
        assert by_payment[first.pk].allocated == D("5.00")
        assert by_payment[second.pk].allocated == D("5.00")
        assert (by_payment[second.pk].first_period, by_payment[second.pk].last_period) == (period(2), period(6))

    def test_mois_invalide(self, ctx):
        ctype = attached_type(ctx)
        with pytest.raises(services.TreasuryValidationError):
            services.get_grid_month_detail(
                contribution_type=ctype, membership=ctx.player, year=YEAR, month=13, requested_by=ctx.treasurer.user
            )


class TestExportCsv:
    def test_contenu_exact_et_nom_de_fichier(self, ctx):
        ctype = attached_type(ctx, name="Mensuelle catégorie 10 $")
        member = player(ctx, "Adolphe", "Akeba", jersey=1)
        other = player(ctx, "Injection", "=HYPERLINK")
        for item in (member, other):
            attach(ctx, item, ctype)
            make_dues(ctx, item, ctype, range(1, 10))
        pay(ctx, member, ctype, "45", datetime.date(2026, 1, 5))
        grid = grid_for(ctx, ctype)
        filename, content = services.export_contribution_grid_csv(grid, services.filter_grid_rows(grid))

        assert filename == "grille-mensuelle-categorie-10-2026.csv"
        assert ctx.club.name.lower() not in filename.lower()
        text = content.decode("utf-8")
        assert text.startswith("﻿")
        lines = text.lstrip("﻿").split("\r\n")
        assert lines[0] == (
            "Joueur;N°;janv. 2026;févr. 2026;mars 2026;avr. 2026;mai 2026;juin 2026;"
            "juil. 2026;août 2026;sept. 2026;oct. 2026;nov. 2026;déc. 2026;Total (USD)"
        )
        assert "Akeba Adolphe;1;10.00;10.00;10.00;10.00;5.00;0.00;0.00;0.00;0.00;;;;45.00" in lines
        # Cellule commençant par « = » neutralisée (injection CSV).
        assert "'=HYPERLINK Injection;;0.00;0.00;0.00;0.00;0.00;0.00;0.00;0.00;0.00;;;;0.00" in lines
        assert len([line for line in lines if line]) == 3

    def test_nom_de_fichier_sans_caractere_exploitable(self, ctx):
        ctype = attached_type(ctx, name="???")
        filename, _ = services.export_contribution_grid_csv(grid_for(ctx, ctype))
        assert filename == f"grille-type-{ctype.pk}-2026.csv"
