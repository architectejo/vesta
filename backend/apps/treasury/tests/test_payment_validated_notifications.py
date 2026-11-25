"""Notification « Paiement validé » (CDC 4.17 : joueur, in-app + email ;
CDC 4.4.4 ; CLAUDE.md règles 6, 20).

Un seul événement par paiement validé, quel que soit le chemin de
validation : saisie du Trésorier, Caisse Terrain Express, frais
d'adhésion, déclaration « J'ai payé » validée, passerelle de paiement.
Jamais pour l'import historique CSV (position prudente : aucune
notification ni aucun email en masse pour des paiements anciens), jamais
pour une validation refusée (rôle non autorisé, registre gelé), jamais pour une
annulation. Étanchéité entre clubs.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import set_email_preference
from apps.treasury import services
from apps.treasury.models import LedgerChainState, Payment, Transaction
from apps.treasury.tests.cash_helpers import cash_pay, monthly_type, named_member, open_session
from apps.treasury.tests.conftest import past_day

pytestmark = pytest.mark.django_db

EVENT = Notification.EventType.PAYMENT_VALIDATED


def validated_notifications(user=None, club=None):
    queryset = Notification.objects.filter(event_type=EVENT)
    if user is not None:
        queryset = queryset.filter(recipient=user)
    if club is not None:
        queryset = queryset.filter(club=club)
    return queryset


def record(ctx, membership, ctype, *, amount="40", method="mobile_money", reference="MM-42"):
    return services.record_payment(
        membership=membership,
        contribution_type=ctype,
        amount=amount,
        method=method,
        reference=reference,
        paid_on=past_day(),
        recorded_by=ctx.treasurer.user,
    )


def set_link(ctx):
    settings_obj = ctx.club.settings
    settings_obj.payment_link_url = "https://paiement.example.test/club"
    settings_obj.save()


def declare(ctx, ctype, *, reference="LAX-NOTIF-1", amount="10"):
    return services.declare_payment(
        membership=ctx.player,
        declared_by=ctx.player.user,
        contribution_type=ctype,
        amount=amount,
        reference=reference,
    )


def gateway_payment(ctx, ctype, *, amount="15.50", external_ref="FLX-001"):
    """Paiement de passerelle (FlexPaie, CDC 4.6) : aucun valideur humain."""

    payment = Payment(
        club=ctx.club,
        membership=ctx.player,
        contribution_type=ctype,
        amount=Decimal(amount),
        currency="USD",
        method=Payment.Method.PAYMENT_LINK,
        reference=external_ref,
        paid_on=past_day(),
        source=Payment.Source.GATEWAY,
        submitted_by=ctx.player.user,
        submitted_at=timezone.now(),
    )
    payment.save()
    txn = services.open_payment_transaction(
        payment=payment, provider=Transaction.Provider.FLEXPAIE, status=Transaction.Status.INITIATED
    )
    return payment, txn


@pytest.fixture
def ctype(ctx):
    return monthly_type(ctx)


@pytest.fixture
def payer(ctx):
    return named_member(ctx, first_name="Élodie", last_name="Payeur")


# ---------------------------------------------------------------------------
# Chaque chemin de validation : exactement une notification au joueur
# ---------------------------------------------------------------------------


class TestCheminsDeValidation:
    def test_saisie_du_tresorier(self, ctx, ctype, payer):
        payment = record(ctx, payer, ctype)

        (notification,) = validated_notifications()
        assert notification.recipient_id == payer.user_id
        assert notification.club_id == ctx.club.pk
        assert notification.title == "Paiement validé"
        assert notification.body == (
            "Votre paiement de 40 $ (Mensuelle 10) a été validé. Reçu n° 1."
        )
        assert (notification.link_object_type, notification.link_object_id) == ("Payment", payment.pk)

    def test_caisse_terrain_express_et_rejeu_de_synchronisation(self, ctx, ctype, payer):
        session = open_session(ctx)
        key = uuid.uuid4()
        payment, created = cash_pay(ctx, session, payer, amount="10", client_uuid=key, contribution_type=ctype)
        assert created
        # Synchronisation rejouée : même paiement, jamais une seconde notification.
        replay, created_again = cash_pay(ctx, session, payer, amount="10", client_uuid=key, contribution_type=ctype)
        assert not created_again and replay.pk == payment.pk

        (notification,) = validated_notifications(payer.user)
        assert notification.body == "Votre paiement de 10 $ (Mensuelle 10) a été validé. Reçu n° 1."

    def test_frais_d_adhesion(self, ctx, fee_type):
        payment = services.record_membership_fee_payment(
            membership=ctx.pending_member,
            amount="5",
            method="cash",
            paid_on=past_day(),
            validated_by=ctx.treasurer.user,
        )
        (notification,) = validated_notifications()
        assert notification.recipient_id == ctx.pending_member.user_id
        assert f"({fee_type.name})" in notification.body
        assert "5 $" in notification.body and f"Reçu n° {payment.receipt_number}." in notification.body

    def test_declaration_j_ai_paye_une_seule_notification_a_la_validation(self, ctx, ctype):
        set_link(ctx)
        declared = declare(ctx, ctype)
        assert not validated_notifications().exists()  # déclarée, pas encore validée

        services.validate_declared_payment(payment=declared, validated_by=ctx.treasurer.user)

        (notification,) = validated_notifications()
        assert notification.recipient_id == ctx.player.user_id
        assert notification.body == "Votre paiement de 10 $ (Mensuelle 10) a été validé. Reçu n° 1."

    def test_declaration_refusee_aucune_notification_de_validation(self, ctx, ctype):
        set_link(ctx)
        declared = declare(ctx, ctype)
        services.reject_declared_payment(payment=declared, rejected_by=ctx.treasurer.user, reason="Référence inconnue")
        assert not validated_notifications().exists()

    def test_passerelle_de_paiement(self, ctx, ctype):
        payment, txn = gateway_payment(ctx, ctype)
        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.PENDING)
        assert not validated_notifications().exists()

        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)

        (notification,) = validated_notifications()
        assert notification.recipient_id == ctx.player.user_id
        assert notification.body == "Votre paiement de 15,50 $ (Mensuelle 10) a été validé. Reçu n° 1."
        assert notification.link_object_id == payment.pk

    def test_passerelle_en_echec_aucune_notification(self, ctx, ctype):
        _payment, txn = gateway_payment(ctx, ctype)
        services.advance_transaction(transaction_obj=txn, status=Transaction.Status.FAILED)
        assert not validated_notifications().exists()


# ---------------------------------------------------------------------------
# Jamais deux, jamais à tort
# ---------------------------------------------------------------------------


class TestJamaisATort:
    def test_une_notification_par_paiement(self, ctx, ctype, payer):
        record(ctx, payer, ctype, reference="MM-1")
        record(ctx, payer, ctype, reference="MM-2", amount="1250")
        bodies = sorted(validated_notifications(payer.user).values_list("body", flat=True))
        assert bodies == [
            "Votre paiement de 1 250 $ (Mensuelle 10) a été validé. Reçu n° 2.",
            "Votre paiement de 40 $ (Mensuelle 10) a été validé. Reçu n° 1.",
        ]

    def test_role_non_autorise_aucune_notification(self, ctx, ctype, payer):
        # Remplace l'ancien cas « PIN faux » (PIN supprimé le 11/10/2026) :
        # une validation refusée ne notifie jamais le joueur.
        with pytest.raises(services.TreasuryPermissionError):
            services.record_payment(
                membership=payer, contribution_type=ctype, amount="40", method="mobile_money",
                reference="MM-42", paid_on=past_day(), recorded_by=ctx.player.user,
            )
        assert not Notification.objects.exists()

    def test_registre_gele_aucune_notification(self, ctx, ctype, payer):
        record(ctx, payer, ctype, reference="MM-AVANT")
        services.freeze_ledger(club=ctx.club, reason="Test de gel", actor=ctx.president.user)
        with pytest.raises(services.LedgerFrozenError):
            record(ctx, payer, ctype, reference="MM-APRES")
        assert validated_notifications().count() == 1
        assert LedgerChainState.all_objects.get(club=ctx.club).is_frozen

    def test_rollback_apres_le_scellement_aucune_notification(self, ctx, ctype, payer, monkeypatch):
        def boom(**kwargs):
            raise RuntimeError("journal indisponible")

        monkeypatch.setattr(services, "_recompute_allocations", boom)
        with pytest.raises(RuntimeError):
            record(ctx, payer, ctype)
        assert not Payment.all_objects.exists()
        assert not Notification.objects.exists()

    def test_annulation_aucune_nouvelle_notification_de_validation(self, ctx, ctype, payer):
        payment = record(ctx, payer, ctype)
        reversal = services.request_payment_reversal(
            payment=payment, reason="Saisie en double", requested_by=ctx.treasurer.user
        )
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)
        assert validated_notifications().count() == 1

    def test_import_historique_csv_aucune_notification(self, ctx):
        from apps.treasury.tests.grid_helpers import NOW, YEAR, attach, attached_type, csv_file, csv_line, player

        imported_type = attached_type(ctx)
        member = player(ctx, "Adolphe", "Akeba", email="adolphe.akeba@example.com")
        attach(ctx, member, imported_type)
        services.import_contributions(
            contribution_type=imported_type,
            year=YEAR,
            csv_file=csv_file([csv_line("Adolphe Akeba", "60", "", "", "", "", "", "", "10")]),
            imported_by=ctx.treasurer.user,
            now=NOW,
        )
        assert Payment.all_objects.filter(membership=member).count() == 2
        assert not validated_notifications().exists()


# ---------------------------------------------------------------------------
# Canal email (CDC 4.17 : in-app + email selon la préférence du joueur)
# ---------------------------------------------------------------------------


class TestCanal:
    def test_email_mis_en_file_par_defaut(self, ctx, ctype, payer):
        record(ctx, payer, ctype)
        notification = validated_notifications().get()
        assert notification.email_requested is True
        assert notification.email_status == Notification.EmailStatus.PENDING

    def test_email_desactive_in_app_seulement(self, ctx, ctype, payer):
        set_email_preference(user=payer.user, email_enabled=False)
        record(ctx, payer, ctype)
        notification = validated_notifications().get()
        assert notification.email_requested is False
        assert notification.email_status == Notification.EmailStatus.NOT_APPLICABLE

    def test_aucun_lien_ni_piece_jointe_du_recu_dans_le_texte(self, ctx, ctype, payer):
        record(ctx, payer, ctype)
        body = validated_notifications().get().body
        assert "http" not in body and "/recu" not in body and ".pdf" not in body


# ---------------------------------------------------------------------------
# Étanchéité entre clubs
# ---------------------------------------------------------------------------


class TestEtancheite:
    def test_chaque_club_ne_notifie_que_son_joueur(self, ctx, other_ctx, ctype, payer):
        record(ctx, payer, ctype)
        other_type = monthly_type(other_ctx, amount="25000")
        record(other_ctx, other_ctx.player, other_type, amount="25000", method="cash", reference="")

        mine = validated_notifications(club=ctx.club)
        theirs = validated_notifications(club=other_ctx.club)
        assert list(mine.values_list("recipient_id", flat=True)) == [payer.user_id]
        assert list(theirs.values_list("recipient_id", flat=True)) == [other_ctx.player.user_id]
        assert theirs.get().body == "Votre paiement de 25 000 FC (Mensuelle 10) a été validé. Reçu n° 1."
        # Aucun membre du bureau d'un club n'est notifié des paiements de l'autre.
        for member in (ctx.president, ctx.treasurer, other_ctx.president, other_ctx.treasurer):
            assert not validated_notifications(member.user).exists()

    def test_aucune_notification_hors_du_joueur_concerne(self, ctx, ctype, payer):
        record(ctx, payer, ctype)
        assert set(validated_notifications().values_list("recipient_id", flat=True)) == {payer.user_id}
        # Ni le Trésorier qui a validé, ni les autres membres du club.
        assert Notification.objects.filter(recipient=ctx.treasurer.user).count() == 0
        assert Notification.objects.filter(recipient=ctx.player.user).count() == 0
