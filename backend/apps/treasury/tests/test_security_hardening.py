"""Corrections de l'audit de securite de la tresorerie (A1 a A3 ; CDC 5.3,
4.4.4, 7.2 ; CLAUDE.md regles n4, n8, n12).

- A1 : un ``key_id`` inconnu sur une ligne existante, alors que des cles
  valides sont configurees, est une **rupture** (gel + alerte + code 2) ;
  seule l'absence totale de cle reste une erreur de configuration sans gel.
- A2 : contenu scelle complete (format canonique v2 versionne), les
  transactions scellees en v1 restent verifiables ; piece jointe figee ;
  concordance ``Payment.amount == Transaction.amount`` controlee.
- A3 : piece jointe controlee avant le PIN (frais d'adhesion) ; club actif
  controle en tete des services d'annulation et de remboursement.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.models import Membership
from apps.core.tenant import TenantMismatchError, active_club
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import (
    LedgerChainState,
    LedgerImmutableError,
    Payment,
    PaymentReversal,
    Transaction,
)
from apps.treasury.tests.conftest import PIN, WRONG_PIN, make_member, past_day

pytestmark = pytest.mark.django_db

TABLE = Transaction._meta.db_table
PAYMENT_TABLE = Payment._meta.db_table
PDF = b"%PDF-1.4\n%piece de test\n%%EOF\n"

V1_KEYS = {
    "club", "sequence", "kind", "payment", "reversal", "expense", "membership",
    "contribution_type", "amount", "currency", "value_date", "provider",
    "external_ref", "status", "sealed_at", "key_id",
}


def pay(ctx, *, membership=None, amount="5", pin=PIN, **extra):
    return services.record_membership_fee_payment(
        membership=membership or make_member(ctx.club, status=Membership.Status.PENDING),
        amount=amount,
        method="cash",
        paid_on=past_day(),
        validated_by=ctx.treasurer.user,
        pin=pin,
        **extra,
    )


def raw_sql(sql, params):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


def pdf(name="piece.pdf"):
    return SimpleUploadedFile(name, PDF, content_type="application/pdf")


def active_superuser_ids():
    return list(get_user_model().objects.filter(is_superuser=True, is_active=True).values_list("pk", flat=True))


def chain_alerts():
    return Notification.objects.filter(event_type=Notification.EventType.LEDGER_CHAIN_BROKEN)


# ---------------------------------------------------------------------------
# A1 : cle inconnue sur une ligne existante = rupture
# ---------------------------------------------------------------------------


class TestCleInconnue:
    def test_key_id_inconnu_alors_qu_une_cle_valide_existe_est_une_rupture(self, ctx, fee_type):
        pay(ctx)
        t2 = pay(ctx).transaction
        raw_sql(f"UPDATE {TABLE} SET key_id = %s WHERE id = %s", ["fantome", t2.pk])

        result = services.verify_chain(ctx.club)

        assert result.ok is False
        assert result.key_unavailable is False
        assert result.first_broken_sequence == 2
        assert "fantome" in result.details

    def test_key_id_inconnu_gele_le_club_et_alerte_le_superuser(self, ctx, fee_type):
        superuser = SuperuserFactory()
        member = make_member(ctx.club, status=Membership.Status.PENDING)
        t1 = pay(ctx, membership=member).transaction
        raw_sql(f"UPDATE {TABLE} SET key_id = %s WHERE id = %s", ["retiree", t1.pk])

        outcome = services.run_ledger_verification(ctx.club)

        assert outcome.status == "broken"
        assert outcome.newly_frozen is True and outcome.alerts_sent == len(active_superuser_ids())
        assert LedgerChainState.all_objects.get(club=ctx.club).is_frozen is True
        recipients = sorted(chain_alerts().values_list("recipient_id", flat=True))
        assert superuser.pk in recipients
        assert recipients == sorted(active_superuser_ids())
        # Aucun joueur n'est penalise (CDC 5.3).
        member.refresh_from_db()
        assert member.status == Membership.Status.PENDING

    def test_commande_cron_code_de_sortie_2_pour_une_cle_inconnue(self, ctx, fee_type, settings):
        SuperuserFactory()
        pay(ctx)
        # La cle d'origine a ete retiree de l'environnement mais une autre
        # cle valide existe : rupture, pas « verification impossible ».
        settings.LEDGER_HMAC_KEYS = {"test-v2": "nouvelle-cle-factice-de-test-" + "2" * 40}
        settings.LEDGER_HMAC_ACTIVE_KEY_ID = "test-v2"
        err = StringIO()
        with pytest.raises(CommandError) as excinfo:
            call_command("verify_ledger_chain", stdout=StringIO(), stderr=err)

        assert excinfo.value.returncode == 2
        assert "RUPTURE DE CHAÎNE" in err.getvalue()
        assert LedgerChainState.all_objects.get(club=ctx.club).is_frozen is True
        assert chain_alerts().count() == len(active_superuser_ids()) >= 1

    def test_cle_presente_mais_invalide_sur_une_ligne_est_une_rupture(self, ctx, fee_type, settings):
        pay(ctx)
        settings.LEDGER_HMAC_KEYS = {
            "test-v1": "changeme-" + "x" * 40,
            "test-v2": "nouvelle-cle-factice-de-test-" + "2" * 40,
        }
        settings.LEDGER_HMAC_ACTIVE_KEY_ID = "test-v2"
        result = services.verify_chain(ctx.club)
        assert result.ok is False and result.key_unavailable is False

    @pytest.mark.parametrize("keys", [{}, {"test-v1": "court"}, {"test-v1": "changeme-" + "x" * 40}])
    def test_aucune_cle_valide_configuree_reste_une_erreur_sans_gel(self, ctx, fee_type, settings, keys):
        SuperuserFactory()
        pay(ctx)
        settings.LEDGER_HMAC_KEYS = keys

        outcome = services.run_ledger_verification(ctx.club)

        assert outcome.status == "error"
        assert outcome.result.key_unavailable is True
        assert LedgerChainState.all_objects.get(club=ctx.club).is_frozen is False
        assert not chain_alerts().exists()


# ---------------------------------------------------------------------------
# A2 : contenu scelle complete, format versionne, piece jointe figee
# ---------------------------------------------------------------------------


class TestFormatVersionne:
    def test_format_v1_inchange_octet_pour_octet(self, ctx, fee_type):
        """Le format v1 (transactions deja en base) ne doit jamais changer :
        la chaine canonique d'une transaction v1 est comparee a sa valeur
        litterale d'origine."""

        txn = Transaction(
            club_id=7,
            kind=Transaction.Kind.PAYMENT,
            payment_id=11,
            membership_id=13,
            contribution_type_id=17,
            amount=Decimal("5.00"),
            currency="USD",
            value_date=datetime.date(2026, 3, 2),
            provider=Transaction.Provider.MANUAL,
            status=Transaction.Status.SUCCEEDED,
            sequence=3,
            key_id="test-v1",
            sealed_at=datetime.datetime(2026, 3, 2, 10, 0, tzinfo=datetime.timezone.utc),
            payload_version=1,
        )
        assert services.transaction_canonical_payload(txn) == (
            '{"amount":"5.00","club":7,"contribution_type":17,"currency":"USD","expense":null,'
            '"external_ref":null,"key_id":"test-v1","kind":"payment","membership":13,"payment":11,'
            '"provider":"manual","reversal":null,"sealed_at":"2026-03-02T10:00:00.000000Z","sequence":3,'
            '"status":"succeeded","value_date":"2026-03-02"}'
        )

    def test_transaction_scellee_avant_la_correction_reste_verifiable(self, ctx, fee_type, monkeypatch):
        # Simule une ligne scellee avant l'introduction du format v2.
        monkeypatch.setattr(services, "LEDGER_PAYLOAD_VERSION", 1)
        legacy = pay(ctx).transaction
        monkeypatch.undo()
        current = pay(ctx).transaction

        legacy = Transaction.all_objects.get(pk=legacy.pk)
        current = Transaction.all_objects.get(pk=current.pk)
        assert legacy.payload_version == 1
        assert set(json.loads(services.transaction_canonical_payload(legacy))) == V1_KEYS
        assert current.payload_version == 2
        assert current.previous_hash == legacy.hash
        result = services.verify_chain(ctx.club)
        assert result.ok is True and result.checked_count == 2

    @pytest.mark.parametrize(
        "column, value",
        [
            ("reference", "FRAUDE-1"),
            ("method", "mobile_money"),
            ("source", "gateway"),
            ("receipt_number", 999),
            ("attachment", "treasury/payments/attachments/autre.pdf"),
        ],
    )
    def test_champ_du_paiement_modifie_en_base_detecte(self, ctx, fee_type, column, value):
        payment = pay(ctx, attachment=pdf())
        pay(ctx)
        raw_sql(f"UPDATE {PAYMENT_TABLE} SET {column} = %s WHERE id = %s", [value, payment.pk])

        result = services.verify_chain(ctx.club)

        assert result.ok is False
        assert result.first_broken_sequence == 1

    def test_valideur_du_paiement_modifie_en_base_detecte(self, ctx, fee_type):
        payment = pay(ctx)
        raw_sql(
            f"UPDATE {PAYMENT_TABLE} SET validated_by_id = %s WHERE id = %s",
            [ctx.assistant_treasurer.user.pk, payment.pk],
        )
        assert services.verify_chain(ctx.club).ok is False

    def test_retrogradation_en_v1_detectee(self, ctx, fee_type):
        txn = pay(ctx).transaction
        raw_sql(f"UPDATE {TABLE} SET payload_version = 1 WHERE id = %s", [txn.pk])
        result = services.verify_chain(ctx.club)
        assert result.ok is False and result.first_broken_sequence == 1

    def test_version_inconnue_detectee(self, ctx, fee_type):
        txn = pay(ctx).transaction
        raw_sql(f"UPDATE {TABLE} SET payload_version = 9 WHERE id = %s", [txn.pk])
        result = services.verify_chain(ctx.club)
        assert result.ok is False and result.first_broken_sequence == 1
        assert result.key_unavailable is False

    def test_montant_du_paiement_different_de_la_transaction_detecte_meme_en_v1(self, ctx, fee_type, monkeypatch):
        monkeypatch.setattr(services, "LEDGER_PAYLOAD_VERSION", 1)
        payment = pay(ctx)
        monkeypatch.undo()
        raw_sql(f"UPDATE {PAYMENT_TABLE} SET amount = %s WHERE id = %s", ["500.00", payment.pk])

        result = services.verify_chain(ctx.club)

        assert result.ok is False
        assert result.first_broken_sequence == 1
        assert "montant" in result.details

    def test_joueur_du_paiement_modifie_en_base_detecte(self, ctx, fee_type):
        payment = pay(ctx)
        raw_sql(f"UPDATE {PAYMENT_TABLE} SET membership_id = %s WHERE id = %s", [ctx.player.pk, payment.pk])
        assert services.verify_chain(ctx.club).ok is False

    def test_transaction_ouverte_avant_la_correction_scellee_en_v2(self, ctx, fee_type):
        """Une transaction ouverte avant la correction (``payload_version=1``
        par defaut) est scellee dans le format courant."""

        payment = Payment(
            club=ctx.club,
            membership=ctx.pending_member,
            contribution_type=fee_type,
            amount=Decimal("5.00"),
            currency="USD",
            method=Payment.Method.PAYMENT_LINK,
            reference="LAX-9",
            paid_on=past_day(),
            source=Payment.Source.PLAYER_DECLARATION,
            submitted_by=ctx.pending_member.user,
            submitted_at=datetime.datetime.now(datetime.timezone.utc),
            validated_by=ctx.treasurer.user,
            validated_at=datetime.datetime.now(datetime.timezone.utc),
        )
        payment.save()
        txn = services.open_payment_transaction(payment=payment, provider=Transaction.Provider.LINK)
        assert txn.payload_version == 1
        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)
        txn.refresh_from_db()
        assert txn.payload_version == 2
        payload = json.loads(services.transaction_canonical_payload(txn))
        assert payload["payment_reference"] == "LAX-9"
        assert payload["payment_validated_by"] == ctx.treasurer.user.pk
        assert services.verify_chain(ctx.club).ok is True


class TestPieceJointeFigee:
    def test_piece_jointe_d_un_paiement_valide_non_remplacable(self, ctx, fee_type):
        payment = pay(ctx, attachment=pdf("origine.pdf"))
        original_name = payment.attachment.name
        payment.attachment = pdf("remplacement.pdf")
        with pytest.raises(LedgerImmutableError):
            payment.save()
        assert Payment.all_objects.get(pk=payment.pk).attachment.name == original_name

    def test_piece_jointe_d_un_paiement_valide_non_supprimable(self, ctx, fee_type):
        payment = pay(ctx, attachment=pdf())
        payment.attachment = None
        with pytest.raises(LedgerImmutableError):
            payment.save()

    def test_piece_jointe_non_ajoutable_apres_validation(self, ctx, fee_type):
        payment = pay(ctx)
        payment.attachment = pdf("ajout.pdf")
        with pytest.raises(LedgerImmutableError):
            payment.save()

    def test_champs_du_recu_restent_completables(self, ctx, fee_type):
        payment = pay(ctx, attachment=pdf())
        payment.receipt_issued_at = datetime.datetime.now(datetime.timezone.utc)
        payment.save()


# ---------------------------------------------------------------------------
# A3 : ordre des controles avant le PIN, club actif
# ---------------------------------------------------------------------------


class TestControlesAvantLePin:
    def test_piece_jointe_invalide_refusee_avant_le_pin_frais_d_adhesion(self, ctx, fee_type):
        bogus = SimpleUploadedFile("x.pdf", b"pas un pdf", content_type="application/pdf")
        with pytest.raises(services.TreasuryValidationError):
            pay(ctx, pin=WRONG_PIN, attachment=bogus)
        ctx.treasurer.user.refresh_from_db()
        assert ctx.treasurer.user.pin_failed_attempts == 0
        assert not Payment.all_objects.exists()

    def test_frais_d_adhesion_refuses_dans_le_contexte_d_un_autre_club(self, ctx, fee_type, other_ctx):
        with active_club(other_ctx.club):
            with pytest.raises(TenantMismatchError):
                pay(ctx, membership=ctx.pending_member, pin=WRONG_PIN)
        ctx.treasurer.user.refresh_from_db()
        assert ctx.treasurer.user.pin_failed_attempts == 0

    def test_remboursement_refuse_dans_le_contexte_d_un_autre_club(self, ctx, fee_type, other_ctx):
        pay(ctx, membership=ctx.pending_member)
        with active_club(other_ctx.club):
            with pytest.raises(TenantMismatchError):
                services.refund_membership_fee(
                    membership=ctx.pending_member, reason="Refus du parrain", president=ctx.president.user, pin=WRONG_PIN
                )
        ctx.president.user.refresh_from_db()
        assert ctx.president.user.pin_failed_attempts == 0
        assert not PaymentReversal.all_objects.exists()

    def test_demande_d_annulation_refusee_dans_le_contexte_d_un_autre_club(self, ctx, fee_type, other_ctx):
        payment = pay(ctx)
        with active_club(other_ctx.club):
            with pytest.raises(TenantMismatchError):
                services.request_payment_reversal(payment=payment, reason="Erreur", requested_by=ctx.treasurer.user)
        assert not PaymentReversal.all_objects.exists()

    def test_approbation_et_rejet_refuses_dans_le_contexte_d_un_autre_club(self, ctx, fee_type, other_ctx):
        payment = pay(ctx)
        reversal = services.request_payment_reversal(payment=payment, reason="Erreur", requested_by=ctx.treasurer.user)
        with active_club(other_ctx.club):
            with pytest.raises(TenantMismatchError):
                services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=WRONG_PIN)
            with pytest.raises(TenantMismatchError):
                services.reject_payment_reversal(
                    reversal=reversal, rejected_by=ctx.president.user, rejection_reason="Non"
                )
        ctx.president.user.refresh_from_db()
        assert ctx.president.user.pin_failed_attempts == 0
        assert PaymentReversal.all_objects.get(pk=reversal.pk).status == PaymentReversal.Status.PENDING_APPROVAL
