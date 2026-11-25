"""Frais d'adhésion = une somme à payer (décision du client du 17/11/2026 ;
CDC 4.3, 4.4.2 ; 10.3 n° 100 confirmée).

Un montant dû UNIQUE est créé à l'ouverture de l'adhésion (tarif des frais
d'adhésion du club à la date d'entrée, échéance à la date d'entrée, type
obligatoire). Le paiement des frais s'alloue à ce dû : une fois payé, le
solde du joueur est à 0 et ses mensualités ne sont pas touchées. Le solde
reste calculé (CLAUDE.md règle 2), une cotisation libre ne crée jamais de
dette (règle 3), rien n'est jamais supprimé (règle 4) : l'annulation d'une
adhésion neutralise le dû par une écriture d'annulation (`DueCancellation`).
"""

from __future__ import annotations

import datetime
import io
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.clubs import services as clubs_services
from apps.clubs.models import Membership, MembershipApplication
from apps.core.tenant import TenantMismatchError, active_club
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import (
    ContributionType,
    Due,
    DueCancellation,
    LedgerImmutableError,
    Payment,
    PaymentAllocation,
)
from apps.treasury.tests.conftest import make_member
from apps.treasury.tests.factories import MembershipFeeTypeFactory

pytestmark = pytest.mark.django_db

FEE = Decimal("5.00")


def today_utc() -> datetime.date:
    # Kinshasa (UTC+1) : la date UTC n'est jamais posterieure a la date du club.
    return timezone.now().date()


def club_today(ctx) -> datetime.date:
    return services.get_club_today(ctx.club)


def add_recruit(ctx, *, email=None):
    return clubs_services.add_player_with_sponsor(
        club=ctx.club,
        email=email or f"recrue-{ctx.club.id}@example.com",
        first_name="Recrue",
        last_name="Test",
        added_by=ctx.president.user,
        sponsor=ctx.player,
        position=Membership.Position.MIDFIELDER,
    )


def pay_fee(ctx, membership, amount, *, paid_on=None):
    return services.record_membership_fee_payment(
        membership=membership,
        amount=amount,
        method="cash",
        paid_on=paid_on or today_utc(),
        validated_by=ctx.treasurer.user,
    )


def pay_application(ctx, application, amount):
    return clubs_services.record_membership_fee_payment_for_application(
        application=application,
        amount=amount,
        method="cash",
        paid_on=today_utc(),
        validated_by=ctx.treasurer.user,
    )


def fee_dues(membership):
    return Due.all_objects.filter(membership=membership, contribution_type__is_membership_fee=True)


def balance(ctx, membership, at_date=None):
    return services.get_balance(membership, at_date=at_date or club_today(ctx))


# ---------------------------------------------------------------------------
# Création du montant dû
# ---------------------------------------------------------------------------


class TestCreationDuDu:
    def test_ajout_par_le_president_cree_un_du_unique(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)

        due = fee_dues(membership).get()
        assert due.contribution_type_id == fee_type.pk
        assert due.amount == FEE
        assert due.due_date == membership.joined_on
        assert due.period == membership.joined_on.replace(day=1)
        assert due.source == Due.Source.MEMBERSHIP_FEE
        log = AuditLog.objects.get(action_type="treasury.due.generated", object_id=str(due.pk))
        assert log.actor_id == ctx.president.user_id
        assert log.club_id == ctx.club.id

    def test_solde_moins_5_avant_paiement(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)

        assert balance(ctx, membership) == Decimal("-5.00")
        in_order, amount_due, reason = services.is_in_good_standing(membership)
        assert in_order is False
        assert amount_due == FEE
        assert "adhésion" in reason.lower()

    def test_sans_type_adhesion_aucun_du_et_message_clair_au_paiement(self, ctx):
        membership, _application = add_recruit(ctx)

        assert not fee_dues(membership).exists()
        assert balance(ctx, membership) == Decimal("0.00")
        with pytest.raises(services.TreasuryValidationError) as exc:
            pay_fee(ctx, membership, "5")
        assert "adhésion" in str(exc.value)

    def test_type_adhesion_libre_ne_cree_jamais_de_dette(self, ctx):
        MembershipFeeTypeFactory(
            club=ctx.club, created_by=ctx.president.user, nature=ContributionType.Nature.FREE
        )
        membership, _application = add_recruit(ctx)

        assert not fee_dues(membership).exists()
        assert balance(ctx, membership) == Decimal("0.00")

    def test_tarif_en_vigueur_a_la_date_d_entree(self, ctx):
        fee_type = services.create_contribution_type(
            club=ctx.club,
            created_by=ctx.president.user,
            name="Adhésion",
            nature=ContributionType.Nature.MANDATORY,
            periodicity=ContributionType.Periodicity.ONE_OFF,
            amount="5",
            is_membership_fee=True,
        )
        # Nouveau tarif : ne s'applique qu'à partir du mois suivant (CDC 4.4.1).
        services.update_contribution_type(contribution_type=fee_type, updated_by=ctx.president.user, amount="7")
        membership, application = add_recruit(ctx)

        assert fee_dues(membership).get().amount == FEE
        pay_application(ctx, application, "5")
        assert services.has_paid_membership_fee(membership) is True
        assert balance(ctx, membership) == Decimal("0.00")

    def test_creation_atomique_avec_l_adhesion(self, ctx, fee_type, monkeypatch):
        def boom(*args, **kwargs):
            raise services.TreasuryValidationError("Erreur simulée.")

        monkeypatch.setattr(services, "ensure_membership_fee_due", boom)
        with pytest.raises(services.TreasuryValidationError):
            add_recruit(ctx)
        assert not Membership.all_objects.filter(user__email=f"recrue-{ctx.club.id}@example.com").exists()
        assert not MembershipApplication.all_objects.exists()

    def test_idempotent_jamais_deux_dus_pour_une_meme_adhesion(self, ctx, fee_type):
        membership, application = add_recruit(ctx)
        first = fee_dues(membership).get()

        again = services.ensure_membership_fee_due(membership, actor=ctx.president.user)
        assert again.pk == first.pk
        pay_application(ctx, application, "3")
        pay_application(ctx, application, "2")
        assert fee_dues(membership).count() == 1

    def test_un_nouveau_type_adhesion_ne_cree_pas_de_second_du(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)
        services.archive_contribution_type(contribution_type=fee_type, archived_by=ctx.president.user)
        MembershipFeeTypeFactory(club=ctx.club, created_by=ctx.president.user, amount=Decimal("8.00"))

        services.ensure_membership_fee_due(membership, actor=ctx.president.user)
        assert fee_dues(membership).count() == 1

    def test_registre_gele_aucun_du_a_l_ouverture_cree_au_paiement(self, ctx, fee_type):
        """10.2 n° 108 : aucune dette créée tant que les joueurs ne peuvent pas
        payer. Le dû est alors créé au premier paiement des frais."""

        from apps.accounts.tests.factories import SuperuserFactory

        services.freeze_ledger(club=ctx.club, reason="Rupture détectée (test)", actor=SuperuserFactory())
        membership, _application = add_recruit(ctx)
        assert not fee_dues(membership).exists()
        assert balance(ctx, membership) == Decimal("0.00")

    def test_paiement_d_un_ancien_dossier_sans_du_cree_le_du(self, ctx, fee_type):
        """Adhésion ouverte avant la décision (aucun dû) : le premier paiement
        des frais crée le dû et s'y alloue (jamais de crédit)."""

        assert not fee_dues(ctx.pending_member).exists()
        pay_fee(ctx, ctx.pending_member, "5")
        due = fee_dues(ctx.pending_member).get()
        assert due.amount == FEE
        assert balance(ctx, ctx.pending_member) == Decimal("0.00")


# ---------------------------------------------------------------------------
# Paiement des frais
# ---------------------------------------------------------------------------


class TestPaiementDesFrais:
    def test_paiement_de_5_solde_a_zero(self, ctx, fee_type):
        membership, application = add_recruit(ctx)
        pay_application(ctx, application, "5")

        due = fee_dues(membership).get()
        assert balance(ctx, membership) == Decimal("0.00")
        assert services.has_paid_membership_fee(membership) is True
        allocations = list(
            PaymentAllocation.all_objects.filter(membership=membership).values_list("period", "amount")
        )
        assert allocations == [(due.period, FEE)]

    def test_paiements_partiels_3_puis_2(self, ctx, fee_type):
        membership, application = add_recruit(ctx)

        pay_application(ctx, application, "3")
        assert balance(ctx, membership) == Decimal("-2.00")
        assert services.has_paid_membership_fee(membership) is False

        pay_application(ctx, application, "2")
        assert balance(ctx, membership) == Decimal("0.00")
        assert services.has_paid_membership_fee(membership) is True
        assert PaymentAllocation.all_objects.filter(membership=membership).count() == 2

    def test_paiement_de_8_surplus_de_3_en_credit(self, ctx, fee_type):
        membership, application = add_recruit(ctx)
        pay_application(ctx, application, "8")

        assert balance(ctx, membership) == Decimal("3.00")
        assert services.has_paid_membership_fee(membership) is True
        allocated = sum(PaymentAllocation.all_objects.filter(membership=membership).values_list("amount", flat=True))
        assert allocated == FEE

    def test_mensualites_intactes(self, ctx, fee_type):
        """Les frais payés couvrent le dû d'adhésion, jamais une mensualité."""

        monthly = services.create_contribution_type(
            club=ctx.club,
            created_by=ctx.president.user,
            name="Mensuelle 10",
            nature=ContributionType.Nature.MANDATORY,
            periodicity=ContributionType.Periodicity.MONTHLY,
            amount="10",
        )
        period = club_today(ctx).replace(day=1)
        services.generate_dues_for_period(club=ctx.club, period=period, actor=ctx.president.user)
        later = club_today(ctx) + datetime.timedelta(days=45)
        assert balance(ctx, ctx.player, later) == Decimal("-10.00")

        pay_fee(ctx, ctx.player, "5")

        assert balance(ctx, ctx.player, later) == Decimal("-10.00")
        assert not PaymentAllocation.all_objects.filter(membership=ctx.player, contribution_type=monthly).exists()

    def test_paiement_saisi_par_la_modale_generale_sur_le_type_adhesion(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)
        services.record_payment(
            membership=membership,
            contribution_type=fee_type,
            amount="5",
            method="cash",
            paid_on=today_utc(),
            recorded_by=ctx.treasurer.user,
        )
        assert fee_dues(membership).count() == 1
        assert balance(ctx, membership) == Decimal("0.00")

    def test_apercu_du_paiement_affiche_le_solde_a_zero(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)
        preview = services.preview_payment_allocation(
            membership=membership,
            contribution_type=fee_type,
            amount="5",
            paid_on=today_utc(),
            requested_by=ctx.treasurer.user,
        )
        assert preview.current.balance == Decimal("-5.00")
        assert preview.after.balance == Decimal("0.00")
        assert preview.unallocated_amount == Decimal("0.00")


# ---------------------------------------------------------------------------
# Joueur « En attente » : jamais présenté « En dette » (CDC 4.1, 4.3)
# ---------------------------------------------------------------------------


class TestJoueurEnAttente:
    def test_tableau_des_membres_classe_en_attente_et_non_en_dette(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)
        page = services.list_member_finances(club=ctx.club, requested_by=ctx.treasurer.user, limit=100)
        row = next(row for row in page.rows if row.membership.pk == membership.pk)

        assert row.summary.balance == Decimal("-5.00")
        assert row.financial_status == services.MEMBER_STATUS_PENDING
        assert row.statuses == [services.MEMBER_STATUS_PENDING]
        in_debt = services.list_member_finances(
            club=ctx.club, requested_by=ctx.treasurer.user, statuses=["in_debt"], limit=100
        )
        assert membership.pk not in {row.membership.pk for row in in_debt.rows}

    def test_priorite_sportive_inchangee_attente_d_abord(self, ctx, fee_type):
        from apps.sport.services import get_playability

        membership, _application = add_recruit(ctx)
        assert get_playability(membership).reason_code == "pending_membership"

    def test_tableau_de_bord_ne_compte_pas_l_adhesion_en_attente_comme_dette(self, ctx, fee_type):
        add_recruit(ctx)
        summary = services.get_treasury_dashboard_summary(ctx.club)
        assert summary.members_in_debt == 0
        assert summary.total_debts == Decimal("0.00")

    def test_aucune_notification_de_dette_pour_les_frais_d_un_joueur_en_attente(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)
        services.run_debt_due_notifications(ctx.club, now=timezone.now() + datetime.timedelta(days=3))
        assert not Notification.objects.filter(
            event_type=Notification.EventType.DEBT_DUE, recipient=membership.user
        ).exists()


# ---------------------------------------------------------------------------
# Annulation de l'adhésion (CDC 4.3, refus du parrain)
# ---------------------------------------------------------------------------


def refuse(ctx, application):
    return clubs_services.refuse_sponsor_application(
        application=application, sponsor_user=ctx.player.user, reason="Je ne connais pas ce joueur."
    )


def cancel(ctx, application, disposition):
    return clubs_services.cancel_membership_application(
        application=application,
        president_user=ctx.president.user,
        reason="Refus du parrain",
        disposition=disposition,
    )


class TestAnnulationDeLAdhesion:
    def test_remboursement_neutralise_le_du_par_une_ecriture_d_annulation(self, ctx, fee_type):
        membership, application = add_recruit(ctx)
        pay_application(ctx, application, "5")
        application = refuse(ctx, MembershipApplication.all_objects.get(pk=application.pk))
        cancel(ctx, application, MembershipApplication.FeeDisposition.REFUNDED)

        due = fee_dues(membership).get()  # jamais supprimé
        cancellation = DueCancellation.all_objects.get(due=due)
        assert cancellation.cancelled_by_id == ctx.president.user_id
        assert cancellation.reason
        assert balance(ctx, membership) == Decimal("0.00")
        assert services.has_paid_membership_fee(membership) is False
        log = AuditLog.objects.get(action_type="treasury.due.cancelled")
        assert log.actor_id == ctx.president.user_id
        assert log.object_id == str(cancellation.pk)

    def test_conservation_des_frais_payes_garde_le_du(self, ctx, fee_type):
        membership, application = add_recruit(ctx)
        pay_application(ctx, application, "5")
        application = refuse(ctx, MembershipApplication.all_objects.get(pk=application.pk))
        cancel(ctx, application, MembershipApplication.FeeDisposition.KEPT)

        assert not DueCancellation.all_objects.exists()
        assert balance(ctx, membership) == Decimal("0.00")

    def test_annulation_sans_paiement_ne_laisse_aucune_dette(self, ctx, fee_type):
        membership, application = add_recruit(ctx)
        application = refuse(ctx, application)
        cancel(ctx, application, MembershipApplication.FeeDisposition.KEPT)

        assert DueCancellation.all_objects.filter(due__membership=membership).count() == 1
        assert balance(ctx, membership) == Decimal("0.00")

    def test_annulation_de_du_reservee_au_president(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            services.cancel_membership_fee_due(
                membership=membership, reason="Test", cancelled_by=ctx.treasurer.user
            )
        assert not DueCancellation.all_objects.exists()

    def test_annulation_de_du_idempotente_et_motif_obligatoire(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)
        with pytest.raises(services.TreasuryValidationError):
            services.cancel_membership_fee_due(membership=membership, reason="  ", cancelled_by=ctx.president.user)
        first = services.cancel_membership_fee_due(
            membership=membership, reason="Adhésion annulée", cancelled_by=ctx.president.user
        )
        second = services.cancel_membership_fee_due(
            membership=membership, reason="Adhésion annulée", cancelled_by=ctx.president.user
        )
        assert first is not None and second is None
        assert DueCancellation.all_objects.count() == 1

    def test_ecriture_d_annulation_immuable_et_jamais_supprimee(self, ctx, fee_type):
        membership, _application = add_recruit(ctx)
        cancellation = services.cancel_membership_fee_due(
            membership=membership, reason="Adhésion annulée", cancelled_by=ctx.president.user
        )
        with pytest.raises(LedgerImmutableError):
            cancellation.delete()
        with pytest.raises(LedgerImmutableError):
            DueCancellation.all_objects.all().delete()
        cancellation.reason = "Autre motif"
        with pytest.raises(LedgerImmutableError):
            cancellation.save()
        with pytest.raises(LedgerImmutableError):
            fee_dues(membership).get().delete()


# ---------------------------------------------------------------------------
# Étanchéité entre clubs (CLAUDE.md règle 8)
# ---------------------------------------------------------------------------


class TestEtancheite:
    def test_ajout_dans_le_club_a_ne_touche_pas_le_club_b(self, ctx, fee_type, other_ctx, other_fee_type):
        membership, _application = add_recruit(ctx)

        assert fee_dues(membership).get().club_id == ctx.club.id
        assert not Due.all_objects.filter(club=other_ctx.club).exists()
        assert all(value == Decimal("0.00") for value in services.get_balances(other_ctx.club).values())

    def test_creation_refusee_dans_le_contexte_d_un_autre_club(self, ctx, fee_type, other_ctx):
        with active_club(other_ctx.club):
            with pytest.raises(TenantMismatchError):
                services.ensure_membership_fee_due(ctx.pending_member, actor=ctx.president.user)
        assert not Due.all_objects.exists()

    def test_annulation_refusee_par_le_president_d_un_autre_club(self, ctx, fee_type, other_ctx):
        membership, _application = add_recruit(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            services.cancel_membership_fee_due(
                membership=membership, reason="Test", cancelled_by=other_ctx.president.user
            )

    def test_ecriture_d_annulation_d_un_autre_club_refusee(self, ctx, fee_type, other_ctx):
        membership, _application = add_recruit(ctx)
        due = fee_dues(membership).get()
        cancellation = DueCancellation(
            club=other_ctx.club,
            due=due,
            reason="Test",
            cancelled_by=other_ctx.president.user,
            cancelled_at=timezone.now(),
        )
        with pytest.raises(DjangoValidationError):
            cancellation.full_clean()


# ---------------------------------------------------------------------------
# Import des joueurs historiques (CDC 4.1)
# ---------------------------------------------------------------------------


class TestImportDesJoueurs:
    def test_import_des_membres_historiques_ne_cree_pas_de_du_d_adhesion(self, ctx, fee_type):
        """CDC 4.1 : les joueurs importés sont des membres historiques qui
        passent directement « Inscrit » (adhésion réputée acquise, CDC 4.1
        diagramme « EnAttente → Inscrit : adhésion payée + parrain signé »).
        Leur créer un dû d'adhésion impayé les mettrait tous « En dette » dès
        l'import (bloqués à tort). Position prudente provisoire, signalée au
        compte rendu : aucun dû d'adhésion à l'import (question au client)."""

        csv_file = SimpleUploadedFile(
            "joueurs.csv", b"email,prenom,nom\nhisto@example.com,Ancien,Membre\n", content_type="text/csv"
        )
        clubs_services.import_players_from_csv(club=ctx.club, imported_by=ctx.president.user, csv_file=csv_file)
        imported = Membership.all_objects.get(club=ctx.club, user__email="histo@example.com")

        assert imported.status == Membership.Status.ACTIVE
        assert not fee_dues(imported).exists()
        assert balance(ctx, imported) == Decimal("0.00")


# ---------------------------------------------------------------------------
# Commande de rééquilibrage des données existantes
# ---------------------------------------------------------------------------


@pytest.fixture
def legacy_credit(ctx, fee_type, monkeypatch):
    """Adhésion dont les frais ont été payés AVANT la décision : paiement
    enregistré sans dû (crédit de 5). Reproduit l'ancien comportement en
    neutralisant la création du dû le temps du paiement."""

    monkeypatch.setattr(services, "_ensure_fee_due_for_payment", lambda **kwargs: None)
    pay_fee(ctx, ctx.pending_member, "5")
    monkeypatch.undo()
    assert not fee_dues(ctx.pending_member).exists()
    assert balance(ctx, ctx.pending_member) == Decimal("5.00")
    return ctx.pending_member


def run_command(*args):
    out = io.StringIO()
    call_command("rebalance_membership_fee_dues", *args, stdout=out)
    return out.getvalue()


def snapshot():
    return (
        Due.all_objects.count(),
        DueCancellation.all_objects.count(),
        list(PaymentAllocation.all_objects.order_by("pk").values_list("pk", "period", "amount")),
        AuditLog.objects.count(),
        Payment.all_objects.count(),
    )


class TestCommandeDeReequilibrage:
    def test_simulation_par_defaut_ne_modifie_rien(self, ctx, legacy_credit):
        before = snapshot()
        output = run_command("--club", str(ctx.club.id))
        assert snapshot() == before
        assert "[simulation]" in output
        assert "1 adhésion(s)" in output
        assert balance(ctx, legacy_credit) == Decimal("5.00")

    def test_option_dry_run_explicite_ne_modifie_rien(self, ctx, legacy_credit):
        before = snapshot()
        run_command("--club", str(ctx.club.id), "--dry-run")
        assert snapshot() == before

    def test_application_cree_le_du_manquant_et_realloue(self, ctx, legacy_credit):
        output = run_command("--club", str(ctx.club.id), "--apply")

        due = fee_dues(legacy_credit).get()
        assert due.amount == FEE
        assert due.due_date == legacy_credit.joined_on
        assert balance(ctx, legacy_credit) == Decimal("0.00")
        assert list(
            PaymentAllocation.all_objects.filter(membership=legacy_credit).values_list("period", "amount")
        ) == [(due.period, FEE)]
        assert "1 adhésion(s)" in output
        assert AuditLog.objects.filter(action_type="treasury.due.generated", object_id=str(due.pk)).exists()

    def test_application_idempotente(self, ctx, legacy_credit):
        run_command("--club", str(ctx.club.id), "--apply")
        before = snapshot()
        output = run_command("--club", str(ctx.club.id), "--apply")
        assert snapshot() == before
        assert "0 adhésion(s)" in output

    def test_ne_traite_que_le_club_demande(self, ctx, legacy_credit, other_ctx, other_fee_type, monkeypatch):
        monkeypatch.setattr(services, "_ensure_fee_due_for_payment", lambda **kwargs: None)
        pay_fee(other_ctx, other_ctx.pending_member, "5")
        monkeypatch.undo()

        run_command("--club", str(ctx.club.id), "--apply")
        assert fee_dues(legacy_credit).exists()
        assert not fee_dues(other_ctx.pending_member).exists()

    def test_club_obligatoire(self, ctx):
        with pytest.raises(CommandError):
            run_command()

    def test_rembourse_ou_annule_n_est_pas_retraite(self, ctx, legacy_credit):
        services.refund_membership_fee(membership=legacy_credit, reason="Refus du parrain", president=ctx.president.user)
        output = run_command("--club", str(ctx.club.id), "--apply")
        assert not fee_dues(legacy_credit).exists()
        assert "0 adhésion(s)" in output
