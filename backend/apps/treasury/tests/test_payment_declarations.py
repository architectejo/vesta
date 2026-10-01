"""Paiement en ligne, phase 1 : lien externe et déclaration « J'ai payé »
(tâche 2.5 ; CDC 4.6, 4.4.3, 4.4.4, 4.17, 5.3, 7.2 ; matrice 2.4).

- Le lien de paiement vient des paramètres du club (jamais en dur).
- Le joueur déclare pour lui-même : `Payment` source ``player_declaration``
  + `Transaction` NON scellée ``pending`` (fournisseur ``link``) ; aucun
  effet sur le solde, la caisse, la chaîne ni les reçus.
- Validation par le Trésorier ou l'adjoint avec PIN : paiement normal
  (scellement, reçu, répartition 4.4.3, journal).
- Refus motivé (sans PIN) : transaction ``failed`` scellée, joueur prévenu.
- Étanchéité entre clubs : 404 sur la déclaration d'un autre club.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services import InvalidPinError, PinError, PinLockedError
from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import (
    ContributionType,
    LedgerChainState,
    LedgerImmutableError,
    Payment,
    PaymentAllocation,
    Transaction,
)
from apps.treasury.tests.cash_helpers import club_today, free_type, monthly_type, named_member, put_in_debt
from apps.treasury.tests.conftest import PIN, WRONG_PIN, past_day

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n%capture de test\n%%EOF\n"
LINK = "https://paiement.example.test/club-de-test"


def set_link(ctx, url=LINK):
    club_settings = ctx.club.settings
    club_settings.payment_link_url = url
    club_settings.save()


def add_months(day: datetime.date, months: int) -> datetime.date:
    index = day.year * 12 + day.month - 1 + months
    return datetime.date(index // 12, index % 12 + 1, 1)


def declare(ctx, ctype, *, member=None, by=None, amount="10", reference="LAX-001", **extra):
    member = member or ctx.player
    return services.declare_payment(
        membership=member,
        declared_by=(by or member).user,
        contribution_type=ctype,
        amount=amount,
        reference=reference,
        **extra,
    )


def validate(ctx, payment, *, by=None, pin=PIN):
    return services.validate_declared_payment(payment=payment, validated_by=(by or ctx.treasurer).user, pin=pin)


def reject(ctx, payment, *, by=None, reason="Référence introuvable chez le fournisseur."):
    return services.reject_declared_payment(payment=payment, rejected_by=(by or ctx.treasurer).user, reason=reason)


def txn_of(payment) -> Transaction:
    return Transaction.all_objects.get(payment=payment)


def written():
    return (Payment.all_objects.count(), Transaction.all_objects.count(), PaymentAllocation.all_objects.count())


def notifications(user, event_type):
    return list(Notification.objects.filter(recipient=user, event_type=event_type))


# ---------------------------------------------------------------------------
# Lien de paiement (CDC 4.6 : configuré par le club, jamais en dur)
# ---------------------------------------------------------------------------


class TestPaymentLinkAndTypes:
    def test_lien_absent_par_defaut(self, ctx):
        info = services.get_contribute_info(ctx.player)
        assert info.payment_link_url == ""

    def test_lien_du_club_et_types_du_joueur(self, ctx, other_ctx):
        set_link(ctx)
        set_link(other_ctx, "https://paiement.example.test/autre-club")
        monthly = monthly_type(ctx)
        libre = free_type(ctx)
        monthly_type(ctx, name="Réservée", scope=ContributionType.Scope.SELECTED)
        archived = monthly_type(ctx, name="Ancienne")
        services.archive_contribution_type(contribution_type=archived, archived_by=ctx.president.user)

        info = services.get_contribute_info(ctx.player)

        assert info.payment_link_url == LINK
        assert info.currency == "USD"
        assert {ctype.pk for ctype in info.contribution_types} == {monthly.pk, libre.pk}
        assert info.default_contribution_type_id == monthly.pk

    def test_type_rattache_propose(self, ctx):
        set_link(ctx)
        reserved = monthly_type(ctx, name="Réservée", scope=ContributionType.Scope.SELECTED)
        services.create_contribution_assignment(
            membership=ctx.player,
            contribution_type=reserved,
            starts_on=club_today(ctx).replace(day=1),
            created_by=ctx.president.user,
        )
        info = services.get_contribute_info(ctx.player)
        assert reserved.pk in {ctype.pk for ctype in info.contribution_types}


# ---------------------------------------------------------------------------
# Déclaration « J'ai payé » (service)
# ---------------------------------------------------------------------------


class TestDeclare:
    def test_declaration_a_valider_sans_effet_financier(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        put_in_debt(ctx, ctx.player, ctype)
        balance_before = services.get_balance(ctx.player)

        payment = declare(ctx, ctype, amount="40", reference="  LAX-40  ")

        assert payment.source == Payment.Source.PLAYER_DECLARATION
        assert payment.method == Payment.Method.PAYMENT_LINK
        assert payment.reference == "LAX-40"
        assert payment.amount == Decimal("40.00")
        assert payment.currency == "USD"
        assert payment.paid_on == club_today(ctx)
        assert payment.submitted_by == ctx.player.user
        assert payment.validated_by is None and payment.receipt_number is None
        txn = txn_of(payment)
        assert txn.provider == Transaction.Provider.LINK
        assert txn.status == Transaction.Status.PENDING
        assert txn.external_ref is None
        assert txn.sealed_at is None and txn.sequence is None and txn.hash is None
        # Aucun effet : solde, statut, répartition, caisse, chaîne.
        assert services.get_balance(ctx.player) == balance_before
        assert services.is_in_good_standing(ctx.player)[0] is False
        assert PaymentAllocation.all_objects.count() == 0
        assert services.get_available_cash(ctx.club) == Decimal("0.00")
        assert not LedgerChainState.all_objects.filter(club=ctx.club, last_sequence__gt=0).exists()
        assert services.verify_chain(ctx.club).ok is True
        assert services.payment_status_key(payment) == "to_validate"

    def test_journal_et_notification_du_tresorier_et_de_l_adjoint(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)

        entry = AuditLog.objects.get(action_type="treasury.payment.declared")
        assert entry.actor_id == ctx.player.user.pk
        assert "pin" not in str(entry.after).lower()
        event = Notification.EventType.I_PAID_DECLARED
        for recipient in (ctx.treasurer, ctx.assistant_treasurer):
            (notification,) = notifications(recipient.user, event)
            assert notification.link_object_id == payment.pk
            assert "à valider" in notification.body
        for other in (ctx.president, ctx.vice_president, ctx.player):
            assert notifications(other.user, event) == []

    def test_lien_absent_declaration_refusee(self, ctx):
        ctype = monthly_type(ctx)
        before = written()
        with pytest.raises(services.PaymentLinkNotConfiguredError, match="lien de paiement"):
            declare(ctx, ctype)
        assert written() == before

    def test_seulement_pour_soi_meme(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            declare(ctx, ctype, member=ctx.player, by=ctx.treasurer)
        assert Payment.all_objects.count() == 0

    def test_joueur_d_un_autre_club_refuse(self, ctx, other_ctx):
        set_link(ctx)
        set_link(other_ctx)
        ctype = monthly_type(ctx)
        # Un joueur du club B ne peut pas déclarer sur une adhésion du club A...
        with pytest.raises(services.TreasuryPermissionError):
            declare(ctx, ctype, member=ctx.player, by=other_ctx.player)
        # ... ni sur un type de cotisation du club A pour sa propre adhésion.
        with pytest.raises(services.TreasuryValidationError):
            declare(other_ctx, ctype, member=other_ctx.player)
        assert Payment.all_objects.count() == 0

    @pytest.mark.parametrize("amount", ["0", "-5", "abc", "", "1e30", 10.5, None])
    def test_montants_invalides(self, ctx, amount):
        set_link(ctx)
        ctype = monthly_type(ctx)
        with pytest.raises(services.InvalidAmountError):
            declare(ctx, ctype, amount=amount)
        assert Payment.all_objects.count() == 0

    def test_montant_arrondi_a_deux_decimales(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        assert declare(ctx, ctype, amount="12.345").amount == Decimal("12.35")

    @pytest.mark.parametrize("reference", ["", "   ", None])
    def test_reference_obligatoire(self, ctx, reference):
        set_link(ctx)
        ctype = monthly_type(ctx)
        with pytest.raises(services.TreasuryValidationError, match="référence"):
            declare(ctx, ctype, reference=reference)

    def test_reference_trop_longue(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        with pytest.raises(services.TreasuryValidationError, match="120"):
            declare(ctx, ctype, reference="R" * 121)

    def test_capture_mauvais_format_refusee(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        fake = SimpleUploadedFile("capture.pdf", b"pas un pdf", content_type="application/pdf")
        with pytest.raises(services.TreasuryValidationError, match="Format"):
            declare(ctx, ctype, attachment=fake)
        assert Payment.all_objects.count() == 0

    def test_capture_valide_conservee(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype, attachment=SimpleUploadedFile("capture.pdf", PDF, content_type="application/pdf"))
        assert payment.attachment

    def test_type_archive_refuse(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        services.archive_contribution_type(contribution_type=ctype, archived_by=ctx.president.user)
        ctype.refresh_from_db()
        with pytest.raises(services.TreasuryValidationError, match="archivé"):
            declare(ctx, ctype)

    def test_type_qui_ne_concerne_pas_le_joueur_refuse(self, ctx):
        set_link(ctx)
        reserved = monthly_type(ctx, name="Réservée", scope=ContributionType.Scope.SELECTED)
        with pytest.raises(services.TreasuryValidationError, match="ne vous concerne pas"):
            declare(ctx, reserved)

    def test_joueur_parti_refuse(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        ctx.player.status = Membership.Status.DEPARTED
        ctx.player.left_on = past_day()
        ctx.player.left_reason = Membership.LeftReason.OTHER
        ctx.player.left_by = ctx.president.user
        ctx.player.save()
        with pytest.raises(services.TreasuryValidationError, match="quitté"):
            declare(ctx, ctype)

    def test_meme_reference_deja_declaree_par_soi_meme_refusee(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        declare(ctx, ctype, reference="LAX-77")
        with pytest.raises(services.TreasuryValidationError, match="déjà été déclarée"):
            declare(ctx, ctype, reference="lax-77")

    def test_reference_d_un_autre_joueur_non_revelee_mais_signalee_et_bloquee_a_la_validation(self, ctx):
        """Audit sécurité A6 : auparavant, la déclaration d'un autre joueur
        était refusée avec « déjà été déclarée », ce qui permettait à un
        joueur de sonder les références des autres. Désormais la déclaration
        est acceptée (rien n'est révélé au déclarant), le Trésorier est
        averti du doublon, et la validation reste bloquée : le doublon ne
        peut jamais compter deux fois."""

        set_link(ctx)
        ctype = monthly_type(ctx)
        first = declare(ctx, ctype, reference="LAX-77")

        second = declare(ctx, ctype, member=ctx.vice_president, reference="lax-77")

        assert txn_of(second).status == Transaction.Status.PENDING
        event = Notification.EventType.I_PAID_DECLARED
        flagged = [n for n in notifications(ctx.treasurer.user, event) if n.link_object_id == second.pk]
        assert len(flagged) == 1 and "figure déjà sur un autre paiement" in flagged[0].body
        clean = [n for n in notifications(ctx.treasurer.user, event) if n.link_object_id == first.pk]
        assert "figure déjà" not in clean[0].body
        # Aucune des deux déclarations ne peut compter tant que le doublon existe.
        with pytest.raises(services.TreasuryValidationError, match="déjà été déclarée"):
            validate(ctx, second)
        reject(ctx, second, reason="Référence d'un autre joueur.")
        validate(ctx, first)
        assert txn_of(first).status == Transaction.Status.SUCCEEDED

    def test_reference_validee_d_un_autre_joueur_bloque_la_validation(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        services.record_payment(
            membership=ctx.vice_president, contribution_type=ctype, amount="10", method="payment_link",
            paid_on=past_day(), recorded_by=ctx.treasurer.user, pin=PIN, reference="LAX-6",
        )
        declared = declare(ctx, ctype, reference="LAX-6")
        with pytest.raises(services.TreasuryValidationError, match="déjà été déclarée"):
            validate(ctx, declared)
        assert txn_of(declared).status == Transaction.Status.PENDING

    def test_reference_d_un_paiement_lien_deja_enregistre_refusee(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        services.record_payment(
            membership=ctx.player, contribution_type=ctype, amount="10", method="payment_link",
            paid_on=past_day(), recorded_by=ctx.treasurer.user, pin=PIN, reference="LAX-5",
        )
        with pytest.raises(services.TreasuryValidationError, match="déjà été déclarée"):
            declare(ctx, ctype, reference="LAX-5")

    def test_reference_reutilisable_apres_refus(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        first = declare(ctx, ctype, reference="LAX-8", amount="15")
        reject(ctx, first, reason="Montant erroné : 10 $ reçus.")
        second = declare(ctx, ctype, reference="LAX-8", amount="10")
        validate(ctx, second)
        assert txn_of(second).external_ref == "LAX-8"

    def test_ecritures_gelees(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        services.freeze_ledger(club=ctx.club, reason="Rupture simulée", actor=None)
        with pytest.raises(services.LedgerFrozenError):
            declare(ctx, ctype)
        assert Payment.all_objects.count() == 0


# ---------------------------------------------------------------------------
# Validation par le Trésorier ou l'adjoint (PIN)
# ---------------------------------------------------------------------------


class TestValidate:
    def test_exemple_du_cdc_40_dollars_repartis_sur_quatre_mois(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype, amount="40", reference="LAX-40")

        validated = validate(ctx, payment)

        month = club_today(ctx).replace(day=1)
        assert list(
            PaymentAllocation.all_objects.filter(payment=validated).order_by("period").values_list("period", "amount")
        ) == [(add_months(month, i), Decimal("10.00")) for i in range(4)]
        assert validated.validated_by == ctx.treasurer.user
        assert validated.validated_at is not None
        assert validated.receipt_number == 1
        txn = txn_of(validated)
        assert txn.status == Transaction.Status.SUCCEEDED
        assert txn.provider == Transaction.Provider.LINK
        assert txn.external_ref == "LAX-40"
        assert txn.sequence == 1 and txn.hash
        assert services.verify_chain(ctx.club).ok is True
        assert services.get_balance(ctx.player) == Decimal("40.00")
        assert services.payment_status_key(validated) == "validated"

    def test_joueur_en_dette_devient_en_ordre_mois_ancien_d_abord(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        put_in_debt(ctx, ctx.player, ctype, months_ago=2)
        payment = declare(ctx, ctype, amount="10")
        assert services.is_in_good_standing(ctx.player)[0] is False

        validate(ctx, payment, by=ctx.assistant_treasurer)

        assert services.is_in_good_standing(ctx.player)[0] is True
        (allocation,) = PaymentAllocation.all_objects.filter(payment=payment)
        assert allocation.period == add_months(club_today(ctx).replace(day=1), -2)

    def test_paiement_partiel(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        put_in_debt(ctx, ctx.player, ctype, months_ago=1)
        validate(ctx, declare(ctx, ctype, amount="4"))
        assert services.get_balance(ctx.player) == Decimal("-6.00")

    def test_type_libre_hors_solde(self, ctx):
        set_link(ctx)
        ctype = free_type(ctx)
        validate(ctx, declare(ctx, ctype, amount="3"))
        assert services.get_balance(ctx.player) == Decimal("0.00")
        assert services.get_available_cash(ctx.club) == Decimal("3.00")

    def test_journal_et_notification_du_joueur(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = validate(ctx, declare(ctx, ctype))
        entry = AuditLog.objects.get(action_type="treasury.payment.validated")
        assert entry.actor_id == ctx.treasurer.user.pk
        assert (entry.object_type, entry.object_id) == ("Payment", str(payment.pk))
        assert PIN not in str(entry.after)
        (notification,) = notifications(ctx.player.user, Notification.EventType.PAYMENT_VALIDATED)
        assert "n° 1" in notification.body
        status_entries = AuditLog.objects.filter(action_type="treasury.transaction.status_changed")
        assert status_entries.get().actor_id == ctx.treasurer.user.pk

    def test_pin_faux_rien_ne_change(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        with pytest.raises(InvalidPinError):
            validate(ctx, payment, pin=WRONG_PIN)
        txn = txn_of(payment)
        assert txn.status == Transaction.Status.PENDING and txn.sealed_at is None
        payment.refresh_from_db()
        assert payment.validated_by is None
        ctx.treasurer.user.refresh_from_db()
        assert ctx.treasurer.user.pin_failed_attempts == 1

    @pytest.mark.parametrize("pin", ["", None])
    def test_pin_absent_refuse(self, ctx, pin):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        with pytest.raises(PinError):
            validate(ctx, payment, pin=pin)
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_pin_verrouille(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        for _ in range(3):
            with pytest.raises((InvalidPinError, PinLockedError)):
                validate(ctx, payment, pin=WRONG_PIN)
        with pytest.raises(PinLockedError):
            validate(ctx, payment)
        assert txn_of(payment).status == Transaction.Status.PENDING

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    def test_role_non_autorise_verifie_avant_le_pin(self, ctx, role):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype, member=ctx.pending_member if role == "player" else ctx.player)
        member = getattr(ctx, role)
        with pytest.raises(services.TreasuryPermissionError):
            validate(ctx, payment, by=member, pin=WRONG_PIN)
        member.user.refresh_from_db()
        assert member.user.pin_failed_attempts == 0
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_tresorier_d_un_autre_club_refuse(self, ctx, other_ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        with pytest.raises(services.TreasuryPermissionError):
            services.validate_declared_payment(payment=payment, validated_by=other_ctx.treasurer.user, pin=PIN)
        with pytest.raises(services.TreasuryPermissionError):
            services.reject_declared_payment(payment=payment, rejected_by=other_ctx.treasurer.user, reason="Non")
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_deja_traitee(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = validate(ctx, declare(ctx, ctype))
        with pytest.raises(services.DeclarationAlreadyProcessedError):
            validate(ctx, payment, pin=WRONG_PIN)
        with pytest.raises(services.DeclarationAlreadyProcessedError):
            reject(ctx, payment)
        ctx.treasurer.user.refresh_from_db()
        assert ctx.treasurer.user.pin_failed_attempts == 0

    def test_un_paiement_saisi_par_le_tresorier_n_est_pas_une_declaration(self, ctx):
        ctype = monthly_type(ctx)
        payment = services.record_payment(
            membership=ctx.player, contribution_type=ctype, amount="10", method="cash",
            paid_on=past_day(), recorded_by=ctx.treasurer.user, pin=PIN,
        )
        with pytest.raises(services.TreasuryValidationError, match="n'est pas une déclaration"):
            validate(ctx, payment)
        assert txn_of(payment).provider == Transaction.Provider.MANUAL

    def test_gel_verifie_avant_le_pin(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        services.freeze_ledger(club=ctx.club, reason="Rupture simulée", actor=None)
        with pytest.raises(services.LedgerFrozenError):
            validate(ctx, payment, pin=WRONG_PIN)
        ctx.treasurer.user.refresh_from_db()
        assert ctx.treasurer.user.pin_failed_attempts == 0
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_type_archive_entre_temps_refuse(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        services.archive_contribution_type(contribution_type=ctype, archived_by=ctx.president.user)
        with pytest.raises(services.TreasuryValidationError, match="archivé"):
            validate(ctx, payment)

    def test_annulation_apres_validation_ecriture_negative(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = validate(ctx, declare(ctx, ctype, amount="10", reference="LAX-R"))
        reversal = services.request_payment_reversal(payment=payment, reason="Doublon", requested_by=ctx.treasurer.user)
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=PIN)
        assert services.get_balance(ctx.player) == Decimal("0.00")
        payment.refresh_from_db()
        assert services.payment_status_key(payment) == "cancelled"
        assert services.verify_chain(ctx.club).ok is True


# ---------------------------------------------------------------------------
# Refus motivé
# ---------------------------------------------------------------------------


class TestReject:
    def test_refus_motive_trace_et_joueur_prevenu(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype, amount="20")

        rejected = reject(ctx, payment, reason="  Aucun paiement reçu avec cette référence.  ")

        assert rejected.rejected_by == ctx.treasurer.user
        assert rejected.rejected_at is not None
        assert rejected.rejection_reason == "Aucun paiement reçu avec cette référence."
        assert rejected.validated_by is None and rejected.receipt_number is None
        txn = txn_of(rejected)
        assert txn.status == Transaction.Status.FAILED
        assert txn.sealed_at is not None and txn.hash
        assert services.verify_chain(ctx.club).ok is True
        assert services.get_balance(ctx.player) == Decimal("0.00")
        assert services.get_available_cash(ctx.club) == Decimal("0.00")
        assert PaymentAllocation.all_objects.count() == 0
        assert services.payment_status_key(rejected) == "refused"
        entry = AuditLog.objects.get(action_type="treasury.payment.rejected")
        assert entry.actor_id == ctx.treasurer.user.pk
        (notification,) = notifications(ctx.player.user, Notification.EventType.I_PAID_DECLARED)
        assert "refusée" in notification.title
        assert "Aucun paiement reçu avec cette référence." in notification.body

    def test_declaration_refusee_jamais_supprimee_ni_modifiee(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        rejected = reject(ctx, declare(ctx, ctype))
        rejected.amount = Decimal("99.00")
        with pytest.raises(LedgerImmutableError):
            rejected.save()
        with pytest.raises(LedgerImmutableError):
            rejected.delete()
        with pytest.raises(services.DeclarationAlreadyProcessedError):
            validate(ctx, Payment.all_objects.get(pk=rejected.pk))

    @pytest.mark.parametrize("reason", ["", "   ", None])
    def test_motif_obligatoire(self, ctx, reason):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        with pytest.raises(services.TreasuryValidationError, match="motif"):
            reject(ctx, payment, reason=reason)
        assert txn_of(payment).status == Transaction.Status.PENDING

    @pytest.mark.parametrize("role", ["president", "vice_president"])
    def test_role_non_autorise(self, ctx, role):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        with pytest.raises(services.TreasuryPermissionError):
            reject(ctx, payment, by=getattr(ctx, role))
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_le_joueur_ne_refuse_pas_sa_propre_declaration(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        with pytest.raises(services.TreasuryPermissionError):
            reject(ctx, payment, by=ctx.player)


# ---------------------------------------------------------------------------
# Aperçu avant validation (CDC 4.4.3 : répartition affichée avant validation)
# ---------------------------------------------------------------------------


class TestPreview:
    def test_apercu_sans_ecriture(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype, amount="40")
        before = written() + (AuditLog.objects.count(),)
        preview = services.preview_declared_payment(payment=payment, requested_by=ctx.treasurer.user)
        assert written() + (AuditLog.objects.count(),) == before
        month = club_today(ctx).replace(day=1)
        assert [line.period for line in preview.lines] == [add_months(month, i) for i in range(4)]
        assert preview.after.balance == Decimal("40.00")

    def test_apercu_reserve_au_tresorier_et_a_l_adjoint(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        payment = declare(ctx, ctype)
        with pytest.raises(services.TreasuryPermissionError):
            services.preview_declared_payment(payment=payment, requested_by=ctx.president.user)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def client_for(member) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member.user).access_token}")
    return client


def url(name, *args):
    return reverse(f"treasury:{name}", args=args)


def body(ctype, **extra):
    data = {"contribution_type_id": ctype.pk, "amount": "10", "reference": "LAX-API"}
    data.update(extra)
    return data


class TestContributeApi:
    def test_lien_absent_bouton_masque(self, ctx):
        monthly_type(ctx)
        response = client_for(ctx.player).get(url("contribute"))
        assert response.status_code == 200, response.data
        assert response.data["payment_link_configured"] is False
        assert response.data["payment_link_url"] is None
        assert response.data["currency"] == "USD"

    def test_lien_configure_visible_par_tout_membre(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        for member in (ctx.player, ctx.treasurer, ctx.president):
            response = client_for(member).get(url("contribute"))
            assert response.status_code == 200
            assert response.data["payment_link_configured"] is True
            assert response.data["payment_link_url"] == LINK
        assert response.data["default_contribution_type_id"] == ctype.pk
        assert response.data["contribution_types"] == [
            {"id": ctype.pk, "name": ctype.name, "nature": "mandatory", "periodicity": "monthly", "amount": "10.00"}
        ]

    def test_lien_du_club_actif_uniquement(self, ctx, other_ctx):
        set_link(other_ctx, "https://paiement.example.test/autre-club")
        response = client_for(ctx.player).get(url("contribute"))
        assert response.data["payment_link_url"] is None

    def test_401(self, ctx):
        assert APIClient().get(url("contribute")).status_code == 401


class TestDeclarationApi:
    def test_declaration_multipart_avec_capture(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        response = client_for(ctx.player).post(
            url("payment-declaration-list"),
            body(ctype, attachment=SimpleUploadedFile("capture.pdf", PDF, content_type="application/pdf")),
            format="multipart",
        )
        assert response.status_code == 201, response.data
        data = response.data
        assert data["status"] == "to_validate" and data["status_label"] == "À valider"
        assert data["source"] == "player_declaration" and data["method"] == "payment_link"
        assert data["receipt_number"] is None and data["validated_at"] is None
        assert data["transaction"] == {"provider": "link", "status": "pending", "external_ref": None}
        assert data["attachment_url"] == url("payment-attachment-download", data["id"])
        assert data["player"]["membership_id"] == ctx.player.pk
        # La capture est servie au joueur par la vue authentifiée, à personne d'autre hors bureau.
        assert client_for(ctx.player).get(data["attachment_url"]).status_code == 200
        assert client_for(ctx.pending_member).get(data["attachment_url"]).status_code in (403, 404)

    def test_lien_absent_400_avec_code(self, ctx):
        ctype = monthly_type(ctx)
        response = client_for(ctx.player).post(url("payment-declaration-list"), body(ctype), format="json")
        assert response.status_code == 400
        assert response.data["code"] == "payment_link_not_configured"
        assert Payment.all_objects.count() == 0

    def test_capture_mauvais_format_400(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        response = client_for(ctx.player).post(
            url("payment-declaration-list"),
            body(ctype, attachment=SimpleUploadedFile("x.pdf", b"texte")),
            format="multipart",
        )
        assert response.status_code == 400
        assert Payment.all_objects.count() == 0

    @pytest.mark.parametrize("amount", ["0", "-1", "dix", "1e30"])
    def test_montant_invalide_400(self, ctx, amount):
        set_link(ctx)
        ctype = monthly_type(ctx)
        response = client_for(ctx.player).post(url("payment-declaration-list"), body(ctype, amount=amount), format="json")
        assert response.status_code == 400
        assert Payment.all_objects.count() == 0

    def test_reference_manquante_400(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        response = client_for(ctx.player).post(url("payment-declaration-list"), body(ctype, reference=""), format="json")
        assert response.status_code == 400
        assert "référence" in response.data["detail"]

    def test_type_d_un_autre_club_404(self, ctx, other_ctx):
        set_link(ctx)
        other_type = monthly_type(other_ctx)
        response = client_for(ctx.player).post(url("payment-declaration-list"), body(other_type), format="json")
        assert response.status_code == 404
        assert response.data["detail"] == "Type de cotisation introuvable dans ce club."

    def test_joueur_d_un_autre_club_declare_dans_son_propre_club(self, ctx, other_ctx):
        set_link(ctx)
        set_link(other_ctx)
        monthly_type(ctx)
        other_type = monthly_type(other_ctx)
        response = client_for(other_ctx.player).post(url("payment-declaration-list"), body(other_type), format="json")
        assert response.status_code == 201
        payment = Payment.all_objects.get()
        assert payment.club_id == other_ctx.club.pk and payment.membership_id == other_ctx.player.pk
        # Invisible et intraitable depuis l'autre club.
        assert client_for(ctx.treasurer).get(url("payment-declaration-list")).data["count"] == 0
        for name in ("payment-declaration-validate", "payment-declaration-reject", "payment-declaration-preview"):
            response = client_for(ctx.treasurer).post(url(name, payment.pk), {"pin": PIN, "reason": "x"}, format="json")
            assert response.status_code == 404, name
        assert client_for(ctx.treasurer).get(url("payment-declaration-detail", payment.pk)).status_code == 404
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_liste_tresorier_voit_le_club_joueur_voit_les_siennes(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        mine = declare(ctx, ctype, reference="A-1")
        other = declare(ctx, ctype, member=ctx.vice_president, reference="A-2")
        validate(ctx, other)
        treasurer = client_for(ctx.treasurer)

        all_items = treasurer.get(url("payment-declaration-list")).data
        assert all_items["count"] == 2
        pending = treasurer.get(url("payment-declaration-list") + "?status=to_validate").data
        assert [item["id"] for item in pending["results"]] == [mine.pk]
        assert pending["results"][0]["player"]["name"]

        own = client_for(ctx.player).get(url("payment-declaration-list")).data
        assert [item["id"] for item in own["results"]] == [mine.pk]
        assert client_for(ctx.player).get(url("payment-declaration-detail", other.pk)).status_code == 404
        assert client_for(ctx.player).get(url("payment-declaration-detail", mine.pk)).status_code == 200

    def test_liste_sans_requete_par_ligne(self, ctx):
        set_link(ctx)
        ctype = monthly_type(ctx)
        client = client_for(ctx.treasurer)

        def query_count():
            with CaptureQueriesContext(connection) as queries:
                assert client.get(url("payment-declaration-list")).status_code == 200
            return len(queries)

        validate(ctx, declare(ctx, ctype, reference="N-0"))
        baseline = query_count()
        for index, member in enumerate((ctx.vice_president, ctx.assistant_treasurer, ctx.president), start=1):
            payment = declare(ctx, ctype, member=member, reference=f"N-{index}")
            if index == 1:
                reject(ctx, payment)
        assert query_count() == baseline

    def test_filtre_de_statut_inconnu_400(self, ctx):
        response = client_for(ctx.treasurer).get(url("payment-declaration-list") + "?status=nimporte")
        assert response.status_code == 400

    def test_un_paiement_saisi_n_est_pas_une_declaration_404(self, ctx):
        ctype = monthly_type(ctx)
        payment = services.record_payment(
            membership=ctx.player, contribution_type=ctype, amount="10", method="cash",
            paid_on=past_day(), recorded_by=ctx.treasurer.user, pin=PIN,
        )
        assert client_for(ctx.treasurer).get(url("payment-declaration-detail", payment.pk)).status_code == 404
        response = client_for(ctx.treasurer).post(url("payment-declaration-validate", payment.pk), {"pin": PIN}, format="json")
        assert response.status_code == 404


class TestDecisionApi:
    def _declared(self, ctx, **extra):
        set_link(ctx)
        ctype = monthly_type(ctx)
        return declare(ctx, ctype, **extra)

    def test_validation_200_recu_repartition_statut(self, ctx):
        payment = self._declared(ctx, amount="40", reference="LAX-V")
        response = client_for(ctx.treasurer).post(
            url("payment-declaration-validate", payment.pk), {"pin": PIN}, format="json"
        )
        assert response.status_code == 200, response.data
        data = response.data
        assert data["status"] == "validated"
        assert data["receipt_number"] == 1
        assert len(data["allocations"]) == 4
        assert data["transaction"] == {"provider": "link", "status": "succeeded", "external_ref": "LAX-V"}
        assert data["player_status"]["balance"] == "40.00"
        assert PIN not in str(response.content)

    def test_apercu_200_sans_ecriture(self, ctx):
        payment = self._declared(ctx, amount="40")
        response = client_for(ctx.assistant_treasurer).post(url("payment-declaration-preview", payment.pk), {}, format="json")
        assert response.status_code == 200, response.data
        assert len(response.data["allocations"]) == 4
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_pin_faux_400_puis_verrouille_423(self, ctx):
        payment = self._declared(ctx)
        client = client_for(ctx.treasurer)
        path = url("payment-declaration-validate", payment.pk)
        first = client.post(path, {"pin": WRONG_PIN}, format="json")
        assert first.status_code == 400 and first.data["attempts_remaining"] == 2
        client.post(path, {"pin": WRONG_PIN}, format="json")
        assert client.post(path, {"pin": WRONG_PIN}, format="json").status_code == 423
        assert client.post(path, {"pin": PIN}, format="json").status_code == 423
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_pin_absent_400(self, ctx):
        payment = self._declared(ctx)
        response = client_for(ctx.treasurer).post(url("payment-declaration-validate", payment.pk), {}, format="json")
        assert response.status_code == 400
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_deja_traitee_409(self, ctx):
        payment = self._declared(ctx)
        client = client_for(ctx.treasurer)
        assert client.post(url("payment-declaration-validate", payment.pk), {"pin": PIN}, format="json").status_code == 200
        again = client.post(url("payment-declaration-reject", payment.pk), {"reason": "Trop tard"}, format="json")
        assert again.status_code == 409
        assert again.data["code"] == "declaration_already_processed"

    def test_refus_200_motif_obligatoire(self, ctx):
        payment = self._declared(ctx)
        client = client_for(ctx.assistant_treasurer)
        path = url("payment-declaration-reject", payment.pk)
        assert client.post(path, {}, format="json").status_code == 400
        response = client.post(path, {"reason": "Capture illisible."}, format="json")
        assert response.status_code == 200, response.data
        assert response.data["status"] == "refused" and response.data["status_label"] == "Refusé"
        assert response.data["rejection_reason"] == "Capture illisible."
        assert response.data["transaction"]["status"] == "failed"

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    @pytest.mark.parametrize("name", ["payment-declaration-validate", "payment-declaration-reject", "payment-declaration-preview"])
    def test_403_hors_tresorier_et_adjoint(self, ctx, role, name):
        payment = self._declared(ctx, member=ctx.vice_president if role == "player" else ctx.player)
        response = client_for(getattr(ctx, role)).post(url(name, payment.pk), {"pin": PIN, "reason": "x"}, format="json")
        assert response.status_code == 403
        assert txn_of(payment).status == Transaction.Status.PENDING

    def test_401_sans_authentification(self, ctx):
        for method, path in (
            ("get", url("payment-declaration-list")),
            ("post", url("payment-declaration-list")),
            ("get", url("payment-declaration-detail", 1)),
            ("post", url("payment-declaration-validate", 1)),
            ("post", url("payment-declaration-reject", 1)),
            ("post", url("payment-declaration-preview", 1)),
        ):
            assert getattr(APIClient(), method)(path).status_code == 401, path
