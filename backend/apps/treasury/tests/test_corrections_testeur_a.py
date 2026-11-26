"""Corrections de la série de tests du testeur A (13/11/2026).

- D-A4 : après le REFUS d'une demande d'annulation, une nouvelle demande est
  possible (CDC 4.4.4 : une erreur se corrige par une écriture d'annulation) ;
  au plus une demande ouverte (en attente ou approuvée) par paiement, une
  seule annulation APPROUVÉE ; les demandes refusées restent conservées et
  journalisées (CDC 5.3, CLAUDE.md règle 6).
- D-A6 : une dépense ne peut pas être datée dans le futur.
- D-A7 : saisie d'un montant : virgule décimale acceptée, plus de deux
  décimales et notation scientifique refusées, message français clair.
- D-A9/A10 : aucun renvoi interne (« CDC 2.4 », « 10.2 n° 37 »...) dans les
  messages montrés à l'utilisateur.
- D-A11 : rejeu parallèle d'une même saisie (``client_uuid``) : un seul 201,
  les autres 200, jamais d'erreur 500 ni de double paiement.
"""

from __future__ import annotations

import datetime
import inspect
import threading
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, connection
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.treasury import permissions as treasury_permissions
from apps.treasury import services
from apps.treasury.models import Payment, PaymentReversal, Transaction
from apps.treasury.tests.cash_helpers import monthly_type
from apps.treasury.tests.conftest import past_day
from apps.treasury.tests.expense_helpers import club_today, make_category, make_expense, put_in_debt

pytestmark = pytest.mark.django_db


def client_for(member) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member.user).access_token}")
    return client


def record(ctx, ctype, *, amount="10", **extra):
    return services.record_payment(
        membership=extra.pop("membership", ctx.player),
        contribution_type=ctype,
        amount=amount,
        method=extra.pop("method", "cash"),
        reference=extra.pop("reference", ""),
        paid_on=extra.pop("paid_on", past_day()),
        recorded_by=ctx.treasurer.user,
        **extra,
    )


def request_reversal(ctx, payment, reason="Saisie en double"):
    return services.request_payment_reversal(payment=payment, reason=reason, requested_by=ctx.treasurer.user)


def reject(ctx, reversal, reason="Paiement bien reçu"):
    return services.reject_payment_reversal(
        reversal=reversal, rejected_by=ctx.president.user, rejection_reason=reason
    )


def approve(ctx, reversal):
    return services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)


def action_url(payment, action: str) -> str:
    name = {
        "request": "payment-reversal-request",
        "approve": "payment-reversal-approve",
        "reject": "payment-reversal-reject",
    }
    return reverse(f"treasury:{name[action]}", args=[payment.pk])


# ---------------------------------------------------------------------------
# D-A4 : nouvelle demande d'annulation après un refus
# ---------------------------------------------------------------------------


class TestNouvelleDemandeApresRefus:
    def test_nouvelle_demande_possible_apres_refus_et_historique_conserve(self, ctx):
        payment = record(ctx, monthly_type(ctx))
        first = request_reversal(ctx, payment, reason="Saisie en double")
        reject(ctx, first)

        second = request_reversal(ctx, payment, reason="Montant erroné")

        assert second.pk != first.pk
        assert second.status == PaymentReversal.Status.PENDING_APPROVAL
        first.refresh_from_db()
        assert first.status == PaymentReversal.Status.REJECTED  # jamais réutilisée ni modifiée
        assert first.rejection_reason == "Paiement bien reçu"
        assert PaymentReversal.all_objects.filter(payment=payment).count() == 2
        assert AuditLog.objects.filter(club=ctx.club, action_type="treasury.payment_reversal.requested").count() == 2
        assert AuditLog.objects.filter(club=ctx.club, action_type="treasury.payment_reversal.rejected").count() == 1
        # Aucune écriture financière tant que le Président n'a pas approuvé.
        assert not Transaction.all_objects.filter(club=ctx.club, kind=Transaction.Kind.PAYMENT_REVERSAL).exists()

    def test_approbation_de_la_nouvelle_demande_annule_le_paiement_une_seule_fois(self, ctx):
        ctype = monthly_type(ctx)
        payment = record(ctx, ctype)
        reject(ctx, request_reversal(ctx, payment))
        approve(ctx, request_reversal(ctx, payment, reason="Montant erroné"))

        assert services.payment_status_key(Payment.all_objects.get(pk=payment.pk)) == "cancelled"
        assert Transaction.all_objects.filter(club=ctx.club, kind=Transaction.Kind.PAYMENT_REVERSAL).count() == 1
        assert services.verify_chain(ctx.club).ok is True
        # Une seule annulation approuvée par paiement.
        with pytest.raises(services.TreasuryValidationError, match="déjà été annulé"):
            request_reversal(ctx, payment, reason="Encore")
        assert PaymentReversal.all_objects.filter(payment=payment).count() == 2

    def test_demande_en_attente_bloque_une_seconde_demande(self, ctx):
        payment = record(ctx, monthly_type(ctx))
        request_reversal(ctx, payment)
        with pytest.raises(services.TreasuryValidationError, match="déjà en attente"):
            request_reversal(ctx, payment, reason="Autre")
        assert PaymentReversal.all_objects.filter(payment=payment).count() == 1

    def test_plusieurs_refus_successifs_restent_possibles(self, ctx):
        payment = record(ctx, monthly_type(ctx))
        for index in range(3):
            reject(ctx, request_reversal(ctx, payment, reason=f"Demande {index}"), reason=f"Refus {index}")
        assert PaymentReversal.all_objects.filter(payment=payment, status="rejected").count() == 3
        assert services.payment_status_key(Payment.all_objects.get(pk=payment.pk)) == "validated"

    def test_la_base_refuse_deux_demandes_ouvertes_sur_le_meme_paiement(self, ctx):
        """Garde-fou en base, valable sur tous les moteurs (pas d'index
        partiel) : jamais deux demandes en attente ou approuvées."""

        payment = record(ctx, monthly_type(ctx))
        request_reversal(ctx, payment)
        duplicate = PaymentReversal(
            club=ctx.club,
            payment=payment,
            reason="Doublon",
            requested_by=ctx.treasurer.user,
            requested_at=timezone.now(),
        )
        with pytest.raises((DjangoValidationError, IntegrityError)):
            duplicate.save()
        assert PaymentReversal.all_objects.filter(payment=payment).count() == 1

    def test_remboursement_des_frais_possible_apres_un_refus(self, ctx, fee_type):
        payment = services.record_membership_fee_payment(
            membership=ctx.pending_member,
            amount="5",
            method="cash",
            paid_on=past_day(),
            validated_by=ctx.treasurer.user,
        )
        reject(ctx, request_reversal(ctx, payment))
        reversals = services.refund_membership_fee(
            membership=ctx.pending_member, reason="Refus du parrain", president=ctx.president.user
        )
        assert [r.payment_id for r in reversals] == [payment.pk]
        assert services.has_paid_membership_fee(ctx.pending_member) is False

    def test_api_nouvelle_demande_puis_validation_apres_refus(self, ctx):
        payment = record(ctx, monthly_type(ctx))
        treasurer = client_for(ctx.treasurer)
        president = client_for(ctx.president)

        assert treasurer.post(action_url(payment, "request"), {"reason": "Erreur"}, format="json").status_code == 201
        rejected = president.post(action_url(payment, "reject"), {"rejection_reason": "Non"}, format="json")
        assert rejected.status_code == 200
        assert rejected.json()["reversal"]["status"] == "rejected"

        again = treasurer.post(action_url(payment, "request"), {"reason": "Montant erroné"}, format="json")
        assert again.status_code == 201, again.json()
        data = again.json()
        assert data["reversal"]["status"] == "pending_approval"
        assert data["reversal"]["reason"] == "Montant erroné"
        assert data["reversal_pending"] is True

        pending = president.get(reverse("treasury:payment-create"), {"reversal": "pending_approval"}).json()
        assert [item["id"] for item in pending["results"]] == [payment.pk]

        approved = president.post(action_url(payment, "approve"), {}, format="json")
        assert approved.status_code == 200
        assert approved.json()["status"] == "cancelled"
        assert approved.json()["reversal"]["status"] == "approved"

        third = treasurer.post(action_url(payment, "request"), {"reason": "Encore"}, format="json")
        assert third.status_code == 400
        assert "déjà été annulé" in third.json()["detail"]

    def test_liste_sans_doublon_avec_plusieurs_refus(self, ctx):
        payment = record(ctx, monthly_type(ctx))
        for index in range(2):
            reject(ctx, request_reversal(ctx, payment, reason=f"Demande {index}"))
        response = client_for(ctx.president).get(reverse("treasury:payment-create"))
        ids = [item["id"] for item in response.json()["results"]]
        assert ids.count(payment.pk) == 1


@pytest.mark.django_db(transaction=True)
def test_migration_0015_reversible_sur_la_base_de_test():
    """Aller-retour sur la base de test uniquement (jamais sur db.sqlite3)."""

    from django.db.migrations.executor import MigrationExecutor

    previous = [("treasury", "0014_remove_cashsession_pin_verified_at")]
    latest = [("treasury", "0015_paymentreversal_multiple_requests")]
    # Retour a TOUTES les feuilles du graphe : revenir a 0014 deroule aussi
    # les migrations posterieures (treasury 0016, logistics 0003...) ; ne
    # reappliquer que 0015 laisserait la base de test sans leurs tables
    # (« no such table: treasury_duecancellation » dans les tests suivants).
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        executor = MigrationExecutor(connection)
        assert latest[0] not in executor.loader.applied_migrations
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(leaves)
    assert latest[0] in MigrationExecutor(connection).loader.applied_migrations


# ---------------------------------------------------------------------------
# D-A6 : date de dépense future refusée
# ---------------------------------------------------------------------------


class TestDateDeDepenseFuture:
    def test_service_refuse_une_date_future(self, ctx):
        category = make_category(ctx)
        tomorrow = club_today(ctx) + datetime.timedelta(days=1)
        with pytest.raises(services.TreasuryValidationError, match="ne peut pas être dans le futur"):
            make_expense(ctx, category, expense_date=tomorrow)

    def test_service_accepte_aujourd_hui(self, ctx):
        assert make_expense(ctx, make_category(ctx), expense_date=club_today(ctx)).pk

    def test_api_refuse_une_date_future_en_francais(self, ctx):
        category = make_category(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:expense-list"),
            {
                "category_id": category.pk,
                "amount": "25.00",
                "beneficiary_name": "Pharmacie du Centre",
                "reason": "Soins",
                "expense_date": (club_today(ctx) + datetime.timedelta(days=3)).isoformat(),
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "La date de la dépense ne peut pas être dans le futur."


# ---------------------------------------------------------------------------
# D-A7 : saisie des montants
# ---------------------------------------------------------------------------


class TestSaisieDesMontants:
    @pytest.mark.parametrize(
        "raw, expected",
        [("10,50", Decimal("10.50")), ("10,5", Decimal("10.50")), (" 7,25 ", Decimal("7.25")), ("10.50", Decimal("10.50"))],
    )
    def test_virgule_et_point_decimaux_acceptes(self, raw, expected):
        assert services.to_money(raw) == expected

    @pytest.mark.parametrize("raw", ["10.555", "10,555", "0.001"])
    def test_plus_de_deux_decimales_refuse(self, raw):
        with pytest.raises(services.InvalidAmountError) as exc:
            services.to_money(raw)
        assert "2 chiffres après la virgule" in str(exc.value)

    @pytest.mark.parametrize("raw", ["1e3", "1E3", "2.5e1", "1 000", "10,50,1", "1.000,50"])
    def test_notation_scientifique_et_formats_ambigus_refuses(self, raw):
        with pytest.raises(services.InvalidAmountError) as exc:
            services.to_money(raw)
        assert "5, 5,50 ou 5.50" in str(exc.value)

    def test_le_message_ne_dit_plus_5_ou_5_50(self):
        with pytest.raises(services.InvalidAmountError) as exc:
            services.to_money("abc")
        assert "5 ou 5.50" not in str(exc.value)
        assert "5,50" in str(exc.value)

    def test_record_payment_accepte_la_virgule(self, ctx):
        payment = record(ctx, monthly_type(ctx), amount="10,50")
        assert payment.amount == Decimal("10.50")

    def test_record_payment_refuse_trois_decimales_sans_rien_ecrire(self, ctx):
        with pytest.raises(services.InvalidAmountError):
            record(ctx, monthly_type(ctx), amount="10.555")
        assert not Payment.all_objects.filter(club=ctx.club).exists()

    def test_api_virgule_acceptee_et_erreurs_en_francais(self, ctx):
        ctype = monthly_type(ctx)
        client = client_for(ctx.treasurer)
        data = {
            "membership_id": ctx.player.pk,
            "contribution_type_id": ctype.pk,
            "method": "cash",
            "reference": "",
            "paid_on": past_day().isoformat(),
        }
        created = client.post(reverse("treasury:payment-create"), {**data, "amount": "10,50"}, format="json")
        assert created.status_code == 201, created.json()
        assert created.json()["amount"] == "10.50"
        for raw in ("10.555", "1e3"):
            refused = client.post(reverse("treasury:payment-create"), {**data, "amount": raw}, format="json")
            assert refused.status_code == 400
            assert refused.json()["detail"].startswith("Montant invalide")


# ---------------------------------------------------------------------------
# D-A9/A10 : aucun renvoi interne dans les messages
# ---------------------------------------------------------------------------

INTERNAL_MARKERS = ("CDC", "10.2 n°", "CLAUDE", "schema", "schéma")


def _assert_no_internal_reference(text: str):
    for marker in INTERNAL_MARKERS:
        assert marker not in text, f"Référence interne « {marker} » dans : {text}"


class TestMessagesSansReferenceInterne:
    def test_messages_403_des_permissions(self):
        classes = [
            obj
            for _, obj in inspect.getmembers(treasury_permissions, inspect.isclass)
            if obj.__module__ == treasury_permissions.__name__ and isinstance(getattr(obj, "message", None), str)
        ]
        assert classes
        for permission in classes:
            _assert_no_internal_reference(permission.message)

    def test_403_api_sans_reference(self, ctx):
        response = client_for(ctx.player).get(reverse("treasury:expense-list"))
        assert response.status_code == 403
        _assert_no_internal_reference(response.json()["detail"])

    def test_refus_de_role_du_service_sans_reference(self, ctx):
        with pytest.raises(services.TreasuryPermissionError) as exc:
            services.create_expense_category(club=ctx.club, created_by=ctx.player.user, name="Transport")
        _assert_no_internal_reference(str(exc.value))

    def test_raison_d_eligibilite_de_l_assistance_sans_reference(self, ctx):
        today = club_today(ctx)
        ctype = put_in_debt(ctx, ctx.player, due_date=today - datetime.timedelta(days=20))
        # En ordre à la date de l'événement (avant l'échéance), en dette aujourd'hui.
        event_date = today - datetime.timedelta(days=60)
        eligibility = services.get_social_assistance_eligibility(ctx.player, event_date)
        assert eligibility.eligible is True and eligibility.can_be_approved is False
        _assert_no_internal_reference(eligibility.reason)
        assert "à régulariser avant toute approbation" in eligibility.reason
        assert ctype is not None

    def test_message_d_immuabilite_sans_reference(self, ctx):
        payment = record(ctx, monthly_type(ctx))
        from apps.treasury.models import LedgerImmutableError

        with pytest.raises(LedgerImmutableError) as exc:
            payment.delete()
        _assert_no_internal_reference(str(exc.value))


# ---------------------------------------------------------------------------
# D-A11 : rejeu parallèle d'une même saisie
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestRejeuParallele:
    def test_quatre_envois_simultanes_un_seul_201(self, ctx):
        ctype = monthly_type(ctx)
        payload = {
            "membership_id": ctx.player.pk,
            "contribution_type_id": ctype.pk,
            "amount": "10",
            "method": "cash",
            "reference": "",
            "paid_on": past_day().isoformat(),
            "client_uuid": str(uuid.uuid4()),
        }
        token = str(RefreshToken.for_user(ctx.treasurer.user).access_token)
        barrier = threading.Barrier(4)
        results: list = []
        errors: list = []

        def send():
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            try:
                barrier.wait(timeout=10)
                response = client.post(reverse("treasury:payment-create"), payload, format="json")
                results.append((response.status_code, response.json().get("id")))
            except Exception as exc:  # pragma: no cover - rendu visible par l'assertion
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=send) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert not errors, errors
        codes = sorted(code for code, _ in results)
        assert codes == [200, 200, 200, 201], results
        assert len({payment_id for _, payment_id in results}) == 1
        assert Payment.all_objects.filter(club=ctx.club).count() == 1
        assert Transaction.all_objects.filter(club=ctx.club).count() == 1
        assert services.verify_chain(ctx.club).ok is True
