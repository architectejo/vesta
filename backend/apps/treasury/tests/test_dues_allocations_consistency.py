"""Corrections de la revue de conformite de la tresorerie (B7 a B10 ;
CDC 4.4.1, 4.4.2, 4.4.3, 4.4.7 ; 10.2 n° 4 et 5).

- B7 : mois d'arrivee du en entier (PROPOSITION PAR DEFAUT 10.2 n° 5,
  non tranchee par le client), echeance selon la regle normale ; solde,
  grille et repartition alignes sur les `Due` reellement crees.
- B8 : la repartition 4.4.3 (`PaymentAllocation`) est recalculee apres une
  generation de montants dus, une suspension (creation, levee), une fin de
  rattachement, un changement de tarif -- la grille n'est jamais perimee.
- B9 : la nature d'un type ayant des montants dus n'est plus modifiable.
- B10 : aucun montant du invente pour une obligatoire annuelle/ponctuelle
  (point ouvert Q3, a trancher par le client).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.treasury import services
from apps.treasury.models import ContributionType, Due, PaymentAllocation
from apps.treasury.tests.cash_helpers import monthly_type
from apps.treasury.tests.grid_helpers import (
    NOW,
    TODAY,
    attach,
    attached_type,
    grid_for,
    make_dues,
    pay,
    period,
    player,
    row_of,
)

pytestmark = pytest.mark.django_db

D = Decimal


def allocations(membership, ctype):
    return list(
        PaymentAllocation.all_objects.filter(membership=membership, contribution_type=ctype)
        .order_by("period")
        .values_list("period", "amount")
    )


def cell(ctx, ctype, membership, month, *, today=TODAY, year=2026):
    row = row_of(grid_for(ctx, ctype, today=today, year=year, membership=membership), membership)
    return next(c for c in row.cells if c.period == period(month, year))


# ---------------------------------------------------------------------------
# B7 : mois d'arrivee (proposition par defaut 10.2 n° 5, non tranchee)
# ---------------------------------------------------------------------------


class TestMoisDArrivee:
    def test_arrivee_avant_l_echeance_echeance_normale_du_mois(self, ctx):
        ctype = monthly_type(ctx)
        member = player(ctx, "Arrive", "Tot", joined_on=datetime.date(2026, 9, 5))

        created = services.generate_dues_for_period(club=ctx.club, period=period(9), actor=ctx.treasurer.user, now=NOW)

        due = next(d for d in created if d.membership_id == member.pk)
        assert (due.amount, due.due_date, due.source) == (D("10.00"), datetime.date(2026, 9, 10), Due.Source.ARRIVAL)
        assert ctype.pk == due.contribution_type_id

    def test_arrivee_le_jour_de_l_echeance_echeance_normale(self, ctx):
        monthly_type(ctx)
        member = player(ctx, "Arrive", "Le10", joined_on=datetime.date(2026, 9, 10))
        services.run_monthly_dues(ctx.club, now=NOW)
        assert Due.all_objects.get(membership=member).due_date == datetime.date(2026, 9, 10)

    def test_arrivee_apres_l_echeance_meme_delai_qu_un_mois_normal_puis_tolerance(self, ctx):
        monthly_type(ctx)
        member = player(ctx, "Arrive", "Tard", joined_on=datetime.date(2026, 9, 12))

        run = services.run_monthly_dues(ctx.club, now=NOW)

        due = Due.all_objects.get(membership=member)
        assert due.due_date == datetime.date(2026, 9, 21)  # 12 + 9 jours (10 - 1)
        assert run.arrival_count >= 1
        # Personne n'est bloque a son arrivee ; la tolerance du club s'ajoute.
        ctx.club.settings.debt_tolerance_days = 3
        ctx.club.settings.save()

        def standing(day):
            return services.is_in_good_standing(member, at_date=datetime.date(2026, 9, day))[:2]

        assert standing(12) == (True, D("0.00"))
        assert standing(24) == (True, D("0.00"))
        assert standing(25) == (False, D("10.00"))

    def test_type_a_jour_d_echeance_personnalise(self, ctx):
        ctype = services.create_contribution_type(
            club=ctx.club,
            created_by=ctx.president.user,
            name="Mensuelle echeance 5",
            nature=ContributionType.Nature.MANDATORY,
            periodicity=ContributionType.Periodicity.MONTHLY,
            amount="10",
            due_day=5,
            now=datetime.datetime(2025, 1, 5, 12, tzinfo=datetime.timezone.utc),
        )
        member = player(ctx, "Arrive", "Le8", joined_on=datetime.date(2026, 9, 8))
        services.run_monthly_dues(ctx.club, now=NOW)
        due = Due.all_objects.get(membership=member, contribution_type=ctype)
        assert due.due_date == datetime.date(2026, 9, 12)  # 8 + 4 jours (5 - 1)

    def test_solde_grille_et_repartition_alignes_sur_le_montant_du_cree(self, ctx):
        ctype = monthly_type(ctx)
        member = player(ctx, "Arrive", "Aligne", joined_on=datetime.date(2026, 9, 12))
        services.run_monthly_dues(ctx.club, now=NOW)
        after_due = datetime.date(2026, 9, 25)

        summary = services.get_balance_summary(member, at_date=after_due)
        september = cell(ctx, ctype, member, 9, today=after_due)

        assert summary.amount_due == D("10.00")
        assert september.state == services.GRID_STATE_OVERDUE
        assert september.amount_due == D("10.00")
        assert september.overdue_amount == summary.amount_due
        # Avant l'echeance du mois d'arrivee : « a venir », jamais rouge.
        assert cell(ctx, ctype, member, 9, today=TODAY).state == services.GRID_STATE_UPCOMING

    def test_paiement_avant_la_generation_puis_montant_du_reste_affecte_au_mois_d_arrivee(self, ctx):
        ctype = monthly_type(ctx)
        member = player(ctx, "Paye", "Davance", joined_on=datetime.date(2026, 9, 12))
        pay(ctx, member, ctype, "10", datetime.date(2026, 9, 14))
        assert allocations(member, ctype) == [(period(9), D("10.00"))]

        services.run_monthly_dues(ctx.club, now=NOW)

        assert allocations(member, ctype) == [(period(9), D("10.00"))]
        assert services.get_balance(member, at_date=datetime.date(2026, 10, 1)) == D("0.00")
        assert cell(ctx, ctype, member, 9, today=datetime.date(2026, 10, 1)).state == services.GRID_STATE_PAID


# ---------------------------------------------------------------------------
# B8 : la repartition suit chaque evenement qui change la capacite des mois
# ---------------------------------------------------------------------------


class TestRecalculDeLaRepartition:
    def test_paiement_d_avance_puis_changement_de_tarif(self, ctx):
        ctype = monthly_type(ctx)
        member = player(ctx, "Avance", "Tarif")
        make_dues(ctx, member, ctype, [9])
        pay(ctx, member, ctype, "40", datetime.date(2026, 9, 15))
        assert [amount for _, amount in allocations(member, ctype)] == [D("10.00")] * 4

        services.update_contribution_type(contribution_type=ctype, updated_by=ctx.president.user, amount="20", now=NOW)

        # Nouveau tarif a partir d'octobre seulement (CDC 4.4.1) ; septembre
        # garde son montant du a 10.
        assert allocations(member, ctype) == [
            (period(9), D("10.00")),
            (period(10), D("20.00")),
            (period(11), D("10.00")),
        ]
        assert cell(ctx, ctype, member, 10).state == services.GRID_STATE_PAID
        assert cell(ctx, ctype, member, 11).state == services.GRID_STATE_PARTIAL
        assert cell(ctx, ctype, member, 12).allocated == D("0.00")
        assert AuditLog.objects.filter(
            action_type="treasury.payment_allocation.recomputed", actor_id=ctx.president.user.pk
        ).exists()

    def test_paiement_d_avance_puis_suspension_puis_levee(self, ctx):
        ctype = monthly_type(ctx)
        member = player(ctx, "Avance", "Suspendu")
        make_dues(ctx, member, ctype, [9])
        pay(ctx, member, ctype, "40", datetime.date(2026, 9, 15))
        assert [p for p, _ in allocations(member, ctype)] == [period(9), period(10), period(11), period(12)]

        suspension = services.create_contribution_suspension(
            membership=member,
            starts_on=period(10),
            ends_on=datetime.date(2026, 11, 30),
            reason="Blessure longue durée",
            decided_by=ctx.president.user,
        )

        # Octobre et novembre suspendus : l'avance se reporte au-dela.
        assert [p for p, _ in allocations(member, ctype)] == [
            period(9), period(12), period(1, 2027), period(2, 2027)
        ]
        assert cell(ctx, ctype, member, 10).allocated == D("0.00")

        services.end_contribution_suspension(
            suspension=suspension, ends_on=datetime.date(2026, 10, 31), ended_by=ctx.president.user
        )

        # Novembre redevient du : la repartition est recalculee a la levee.
        assert [p for p, _ in allocations(member, ctype)] == [period(9), period(11), period(12), period(1, 2027)]

    def test_paiement_d_avance_puis_fin_de_rattachement(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Avance", "Detache")
        assignment = attach(ctx, member, ctype)
        make_dues(ctx, member, ctype, [9])
        pay(ctx, member, ctype, "30", datetime.date(2026, 9, 15))
        assert [p for p, _ in allocations(member, ctype)] == [period(9), period(10), period(11)]

        services.end_contribution_assignment(
            assignment=assignment, ends_on=datetime.date(2026, 10, 31), ended_by=ctx.president.user
        )

        assert allocations(member, ctype) == [(period(9), D("10.00")), (period(10), D("10.00"))]
        assert cell(ctx, ctype, member, 11).allocated == D("0.00")

    def test_rattachement_cree_apres_un_paiement_recalcule_la_repartition(self, ctx):
        ctype = attached_type(ctx)
        member = player(ctx, "Paye", "Avant")
        # Rattache seulement jusqu'a fin septembre : l'avance reste en partie
        # non affectee ; un nouveau rattachement a partir d'octobre l'absorbe.
        attach(ctx, member, ctype, ends_on=datetime.date(2026, 9, 30))
        make_dues(ctx, member, ctype, [9])
        pay(ctx, member, ctype, "20", datetime.date(2026, 9, 15))
        assert allocations(member, ctype) == [(period(9), D("10.00"))]

        attach(ctx, member, ctype, starts_on=period(10))

        assert allocations(member, ctype) == [(period(9), D("10.00")), (period(10), D("10.00"))]

    def test_generation_des_montants_dus_par_le_cron_recalcule_la_repartition(self, ctx):
        ctype = monthly_type(ctx)
        member = player(ctx, "Rattrapage", "Aout")
        pay(ctx, member, ctype, "10", datetime.date(2026, 9, 15))
        # Aucun montant du encore : le paiement couvre le mois courant.
        assert allocations(member, ctype) == [(period(9), D("10.00"))]

        # Rattrapage du mois d'aout manque par la tache cron.
        services.run_monthly_dues(ctx.club, period=period(8), now=NOW)

        # Repartition 4.4.3 : le mois impaye le plus ancien d'abord.
        assert allocations(member, ctype) == [(period(8), D("10.00"))]
        assert cell(ctx, ctype, member, 8).state == services.GRID_STATE_PAID
        # Tache cron sans acteur reel : aucune entree de journal au nom de personne.
        assert not AuditLog.objects.filter(
            action_type="treasury.payment_allocation.recomputed", actor__isnull=True
        ).exists()

    def test_generation_manuelle_journalisee_au_nom_de_l_acteur(self, ctx):
        ctype = monthly_type(ctx)
        member = player(ctx, "Rattrapage", "Manuel")
        pay(ctx, member, ctype, "10", datetime.date(2026, 9, 15))
        before = AuditLog.objects.filter(action_type="treasury.payment_allocation.recomputed").count()

        services.generate_dues_for_period(club=ctx.club, period=period(8), actor=ctx.treasurer.user, now=NOW)

        assert allocations(member, ctype) == [(period(8), D("10.00"))]
        assert AuditLog.objects.filter(action_type="treasury.payment_allocation.recomputed").count() > before

    def test_generation_sans_paiement_ne_cree_aucune_repartition(self, ctx):
        monthly_type(ctx)
        services.run_monthly_dues(ctx.club, now=NOW)
        assert not PaymentAllocation.all_objects.exists()

    def test_interface_exposee_pour_un_depart_du_club(self, ctx):
        ctype = monthly_type(ctx)
        member = player(ctx, "Depart", "Anticipe")
        make_dues(ctx, member, ctype, [9])
        pay(ctx, member, ctype, "30", datetime.date(2026, 9, 15))
        assert len(allocations(member, ctype)) == 3

        member.left_on = datetime.date(2026, 10, 20)
        # Contrainte membership_left_reason_required_if_left_on : un depart porte un motif.
        member.left_reason = member.LeftReason.RESIGNATION
        member.save()
        recomputed = services.refresh_member_allocations(member, actor=ctx.president.user)

        assert recomputed == 1
        # Sortie en octobre : octobre reste du (mois entame), novembre non.
        assert allocations(member, ctype) == [(period(9), D("10.00")), (period(10), D("10.00"))]


# ---------------------------------------------------------------------------
# B9 : nature figee des qu'un montant du existe
# ---------------------------------------------------------------------------


class TestNatureFigee:
    def test_obligatoire_vers_libre_refuse_des_qu_un_montant_du_existe(self, ctx):
        ctype = monthly_type(ctx)
        member = player(ctx, "Endette", "Sanspaiement")
        make_dues(ctx, member, ctype, [8])
        balance_before = services.get_balance(member, at_date=TODAY)
        assert balance_before == D("-10.00")

        with pytest.raises(services.TreasuryValidationError, match="montants dus"):
            services.update_contribution_type(
                contribution_type=ctype, updated_by=ctx.president.user, nature=ContributionType.Nature.FREE
            )

        ctype.refresh_from_db()
        assert ctype.nature == ContributionType.Nature.MANDATORY
        assert services.get_balance(member, at_date=TODAY) == balance_before
        assert not AuditLog.objects.filter(action_type="treasury.contribution_type.updated").exists()

    def test_nature_modifiable_sans_montant_du_ni_paiement(self, ctx):
        ctype = monthly_type(ctx)
        services.update_contribution_type(
            contribution_type=ctype, updated_by=ctx.president.user, nature=ContributionType.Nature.FREE
        )
        ctype.refresh_from_db()
        assert ctype.nature == ContributionType.Nature.FREE


# ---------------------------------------------------------------------------
# B10 : annuelles et ponctuelles obligatoires -- point ouvert Q3
# ---------------------------------------------------------------------------


class TestAnnuellesEtPonctuelles:
    def test_aucun_montant_du_invente_pour_une_obligatoire_annuelle(self, ctx):
        """Point ouvert (Q3, a trancher par le client) : le CDC ne dit pas
        quand generer le montant du d'une obligatoire annuelle ou ponctuelle.
        Aucune regle n'est inventee : aucun montant du n'est cree."""

        annual = services.create_contribution_type(
            club=ctx.club,
            created_by=ctx.president.user,
            name="Annuelle",
            nature=ContributionType.Nature.MANDATORY,
            periodicity=ContributionType.Periodicity.ANNUAL,
            amount="50",
            due_day=10,
            due_month=9,
            now=datetime.datetime(2025, 1, 5, 12, tzinfo=datetime.timezone.utc),
        )
        player(ctx, "Annuel", "Joueur")

        services.run_monthly_dues(ctx.club, now=NOW)

        assert not Due.all_objects.filter(contribution_type=annual).exists()
