"""Ecritures d'annulation (CDC 4.3 cas limite « refus du parrain », 4.4.4, 7.2 ;
10.2 n° 36 ; schema-treasury.md §5.3 ; decisions D9, D10, D11 -- a confirmer).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.services import InvalidPinError
from apps.audit.models import AuditLog
from apps.treasury import services
from apps.treasury.models import LedgerImmutableError, PaymentReversal, Transaction
from apps.treasury.tests.conftest import PIN, WRONG_PIN, past_day

pytestmark = pytest.mark.django_db


def pay(ctx, amount="5", days_ago=5):
    return services.record_membership_fee_payment(
        membership=ctx.pending_member,
        amount=amount,
        method="cash",
        paid_on=past_day(days_ago),
        validated_by=ctx.treasurer.user,
        pin=PIN,
    )


def request(ctx, payment, *, kind=PaymentReversal.ReasonKind.ERROR, by=None, reason="Saisie en double"):
    return services.request_payment_reversal(
        payment=payment, reason=reason, reason_kind=kind, requested_by=(by or ctx.treasurer).user
    )


class TestDemande:
    def test_demande_en_attente_d_approbation_et_journalisee(self, ctx, fee_type):
        payment = pay(ctx)
        reversal = request(ctx, payment)
        assert reversal.status == PaymentReversal.Status.PENDING_APPROVAL
        assert reversal.club_id == ctx.club.id
        assert reversal.requested_by_id == ctx.treasurer.user_id
        # Aucune ecriture financiere tant que le President n'a pas approuve.
        assert not Transaction.all_objects.filter(kind=Transaction.Kind.PAYMENT_REVERSAL).exists()
        assert services.has_paid_membership_fee(ctx.pending_member) is True
        assert AuditLog.objects.filter(action_type="treasury.payment_reversal.requested").count() == 1

    @pytest.mark.parametrize("who", ["treasurer", "assistant_treasurer", "president"])
    def test_demandeurs_autorises(self, ctx, fee_type, who):
        assert request(ctx, pay(ctx), by=getattr(ctx, who)).pk

    @pytest.mark.parametrize("who", ["vice_president", "player"])
    def test_demandeurs_refuses(self, ctx, fee_type, who):
        with pytest.raises(services.TreasuryPermissionError):
            request(ctx, pay(ctx), by=getattr(ctx, who))

    def test_motif_obligatoire(self, ctx, fee_type):
        with pytest.raises(services.TreasuryValidationError):
            request(ctx, pay(ctx), reason="   ")

    def test_un_paiement_ne_s_annule_qu_une_fois(self, ctx, fee_type):
        payment = pay(ctx)
        request(ctx, payment)
        with pytest.raises(services.TreasuryValidationError):
            request(ctx, payment)

    def test_remboursement_reserve_aux_frais_d_adhesion(self, ctx, fee_type):
        from django.utils import timezone

        from apps.treasury.models import Payment
        from apps.treasury.tests.factories import ContributionTypeFactory

        monthly = ContributionTypeFactory(club=ctx.club)
        other = Payment(
            club=ctx.club, membership=ctx.player, contribution_type=monthly, amount=Decimal("20.00"),
            currency="USD", method=Payment.Method.CASH, paid_on=past_day(), source=Payment.Source.TREASURER_ENTRY,
            submitted_by=ctx.treasurer.user, submitted_at=timezone.now(),
            validated_by=ctx.treasurer.user, validated_at=timezone.now(),
        )
        other.save()
        txn = services.open_payment_transaction(payment=other, provider=Transaction.Provider.MANUAL)
        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)
        with pytest.raises(services.TreasuryValidationError):
            request(ctx, other, kind=PaymentReversal.ReasonKind.REFUND)


class TestApprobation:
    def test_president_approuve_avec_pin_ecriture_negative_chainee(self, ctx, fee_type):
        payment = pay(ctx, days_ago=5)
        reversal = request(ctx, payment)
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=PIN)

        reversal.refresh_from_db()
        assert reversal.status == PaymentReversal.Status.APPROVED
        assert reversal.approved_by_id == ctx.president.user_id
        assert reversal.approved_at is not None

        txn = reversal.transaction
        assert txn.kind == Transaction.Kind.PAYMENT_REVERSAL
        assert txn.status == Transaction.Status.SUCCEEDED
        # D11 : annulation totale.
        assert txn.amount == Decimal("-5.00")
        # D10 : date de valeur du paiement d'origine.
        assert txn.value_date == payment.paid_on
        assert txn.membership_id == payment.membership_id
        assert txn.contribution_type_id == payment.contribution_type_id
        assert txn.sequence == 2
        assert txn.previous_hash == payment.transaction.hash

        # Le paiement d'origine reste intact (invariant 5).
        payment.refresh_from_db()
        assert payment.amount == Decimal("5.00")
        assert payment.transaction.status == Transaction.Status.SUCCEEDED

        assert services.has_paid_membership_fee(ctx.pending_member) is False
        assert services.verify_chain(ctx.club).ok is True
        assert AuditLog.objects.filter(action_type="treasury.payment_reversal.approved").count() == 1

    @pytest.mark.parametrize("who", ["treasurer", "vice_president", "assistant_treasurer"])
    def test_seul_le_president_approuve(self, ctx, fee_type, who):
        reversal = request(ctx, pay(ctx))
        with pytest.raises(services.TreasuryPermissionError):
            services.approve_payment_reversal(reversal=reversal, approved_by=getattr(ctx, who).user, pin=PIN)
        reversal.refresh_from_db()
        assert reversal.status == PaymentReversal.Status.PENDING_APPROVAL

    def test_pin_incorrect(self, ctx, fee_type):
        reversal = request(ctx, pay(ctx))
        with pytest.raises(InvalidPinError):
            services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=WRONG_PIN)
        reversal.refresh_from_db()
        assert reversal.status == PaymentReversal.Status.PENDING_APPROVAL
        assert services.has_paid_membership_fee(ctx.pending_member) is True
        ctx.president.user.refresh_from_db()
        assert ctx.president.user.pin_failed_attempts == 1

    def test_approbation_unique(self, ctx, fee_type):
        reversal = request(ctx, pay(ctx))
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=PIN)
        with pytest.raises(services.TreasuryValidationError):
            services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=PIN)
        assert Transaction.all_objects.filter(kind=Transaction.Kind.PAYMENT_REVERSAL).count() == 1

    def test_club_gele(self, ctx, fee_type):
        from apps.accounts.tests.factories import SuperuserFactory

        reversal = request(ctx, pay(ctx))
        services.freeze_ledger(club=ctx.club, reason="Analyse", actor=SuperuserFactory())
        with pytest.raises(services.LedgerFrozenError):
            services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=PIN)
        reversal.refresh_from_db()
        assert reversal.status == PaymentReversal.Status.PENDING_APPROVAL

    def test_annulation_approuvee_immuable(self, ctx, fee_type):
        reversal = request(ctx, pay(ctx))
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=PIN)
        reversal.refresh_from_db()
        reversal.reason = "autre motif"
        with pytest.raises(LedgerImmutableError):
            reversal.save()
        with pytest.raises(LedgerImmutableError):
            reversal.delete()

    def test_correction_de_montant_par_annulation_puis_nouvelle_saisie(self, ctx, fee_type):
        wrong = pay(ctx, amount="50")
        reversal = request(ctx, wrong, reason="Montant errone")
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=PIN)
        pay(ctx, amount="5")
        assert services.has_paid_membership_fee(ctx.pending_member) is True
        assert services.verify_chain(ctx.club).ok is True


class TestRejet:
    def test_president_rejette_avec_motif(self, ctx, fee_type):
        reversal = request(ctx, pay(ctx))
        services.reject_payment_reversal(
            reversal=reversal, rejected_by=ctx.president.user, rejection_reason="Paiement bien recu"
        )
        reversal.refresh_from_db()
        assert reversal.status == PaymentReversal.Status.REJECTED
        assert reversal.rejected_by_id == ctx.president.user_id
        assert services.has_paid_membership_fee(ctx.pending_member) is True
        assert AuditLog.objects.filter(action_type="treasury.payment_reversal.rejected").count() == 1

    def test_motif_de_rejet_obligatoire(self, ctx, fee_type):
        reversal = request(ctx, pay(ctx))
        with pytest.raises(services.TreasuryValidationError):
            services.reject_payment_reversal(reversal=reversal, rejected_by=ctx.president.user, rejection_reason="")

    def test_seul_le_president_rejette(self, ctx, fee_type):
        reversal = request(ctx, pay(ctx))
        with pytest.raises(services.TreasuryPermissionError):
            services.reject_payment_reversal(
                reversal=reversal, rejected_by=ctx.treasurer.user, rejection_reason="non"
            )


class TestRemboursementApresRefusDuParrain:
    """CDC 4.3 : « Le sort du paiement (remboursement ou conservation) est
    enregistre » ; 10.2 n° 36 (PIN) ; D9 (annulation `refund` validee par le
    President) -- a confirmer par le client."""

    def test_remboursement_annule_tous_les_paiements_d_adhesion_en_une_fois(self, ctx, fee_type):
        p1 = pay(ctx, amount="3")
        p2 = pay(ctx, amount="2")
        reversals = services.refund_membership_fee(
            membership=ctx.pending_member,
            reason="Refus du parrain, adhesion annulee",
            president=ctx.president.user,
            pin=PIN,
        )
        assert {r.payment_id for r in reversals} == {p1.pk, p2.pk}
        for r in reversals:
            assert r.reason_kind == PaymentReversal.ReasonKind.REFUND
            assert r.status == PaymentReversal.Status.APPROVED
            assert r.requested_by_id == r.approved_by_id == ctx.president.user_id
        assert services.has_paid_membership_fee(ctx.pending_member) is False
        assert services.verify_chain(ctx.club).ok is True

    def test_remboursement_exige_le_president_et_son_pin(self, ctx, fee_type):
        pay(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            services.refund_membership_fee(
                membership=ctx.pending_member, reason="Refus", president=ctx.treasurer.user, pin=PIN
            )
        with pytest.raises(InvalidPinError):
            services.refund_membership_fee(
                membership=ctx.pending_member, reason="Refus", president=ctx.president.user, pin=WRONG_PIN
            )
        assert not PaymentReversal.all_objects.exists()
        assert services.has_paid_membership_fee(ctx.pending_member) is True

    def test_remboursement_sans_paiement(self, ctx, fee_type):
        with pytest.raises(services.TreasuryValidationError):
            services.refund_membership_fee(
                membership=ctx.pending_member, reason="Refus", president=ctx.president.user, pin=PIN
            )

    def test_remboursement_par_le_president_d_un_autre_club_refuse(self, ctx, fee_type, other_ctx, other_fee_type):
        """Etancheite (CLAUDE.md regle n8) : le President du club B n'a
        aucun role dans le club A et ne peut donc pas decider du sort du
        paiement d'un joueur du club A."""

        payment = pay(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            services.refund_membership_fee(
                membership=ctx.pending_member,
                reason="Refus du parrain",
                president=other_ctx.president.user,
                pin=PIN,
            )
        assert not PaymentReversal.all_objects.exists()
        assert services.has_paid_membership_fee(ctx.pending_member) is True
        payment.refresh_from_db()
        assert payment.transaction.status == Transaction.Status.SUCCEEDED

    def test_paiement_deja_rembourse_ignore(self, ctx, fee_type):
        pay(ctx)
        services.refund_membership_fee(
            membership=ctx.pending_member, reason="Refus", president=ctx.president.user, pin=PIN
        )
        with pytest.raises(services.TreasuryValidationError):
            services.refund_membership_fee(
                membership=ctx.pending_member, reason="Refus", president=ctx.president.user, pin=PIN
            )
