"""Idempotence de l'enregistrement d'un paiement (correctif sécurité M4,
audit du 12/10/2026 ; CDC 4.4.4, 4.3 ; CLAUDE.md règles 4, 6, 7).

Le PIN étant supprimé (règle 7), un renvoi réseau ou un double POST de la
modale « Enregistrer un paiement » ne doit jamais créer deux paiements
validés scellés ni deux reçus. Le client envoie un ``client_uuid``
FACULTATIF (généré à l'ouverture de la modale) : unique par club, un rejeu
renvoie le paiement existant (HTTP 200), sans nouvelle écriture, reçu,
entrée de journal ni notification. Sans ``client_uuid`` : comportement
inchangé.
"""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import LedgerChainState, Payment, PaymentAllocation, Transaction
from apps.treasury.tests.cash_helpers import monthly_type, open_session, cash_pay
from apps.treasury.tests.conftest import past_day

pytestmark = pytest.mark.django_db

VALIDATED = "treasury.payment.validated"
RECEIPT = "treasury.payment.receipt_issued"


def record(ctx, ctype, *, membership=None, amount="40", by=None, **extra):
    return services.record_payment(
        membership=membership or ctx.player,
        contribution_type=ctype,
        amount=amount,
        method=extra.pop("method", "mobile_money"),
        reference=extra.pop("reference", "MM-42"),
        paid_on=extra.pop("paid_on", past_day()),
        recorded_by=(by or ctx.treasurer).user,
        **extra,
    )


def record_fee(ctx, *, amount="5", by=None, **extra):
    return services.record_membership_fee_payment(
        membership=ctx.pending_member,
        amount=amount,
        method=extra.pop("method", "cash"),
        paid_on=extra.pop("paid_on", past_day()),
        validated_by=(by or ctx.treasurer).user,
        **extra,
    )


def writes(club):
    return {
        "payments": Payment.all_objects.filter(club=club).count(),
        "transactions": Transaction.all_objects.filter(club=club).count(),
        "allocations": PaymentAllocation.all_objects.filter(club=club).count(),
        "validated_logs": AuditLog.objects.filter(club=club, action_type=VALIDATED).count(),
        "receipt_logs": AuditLog.objects.filter(club=club, action_type=RECEIPT).count(),
        "notifications": Notification.objects.filter(
            club=club, event_type=Notification.EventType.PAYMENT_VALIDATED
        ).count(),
        "last_receipt": LedgerChainState.all_objects.get(club=club).last_receipt_number,
    }


def client_for(member) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member.user).access_token}")
    return client


def body(ctx, ctype, **extra):
    data = {
        "membership_id": ctx.player.pk,
        "contribution_type_id": ctype.pk,
        "amount": "40",
        "method": "mobile_money",
        "reference": "MM-42",
        "paid_on": past_day().isoformat(),
    }
    data.update(extra)
    return data


# ---------------------------------------------------------------------------
# Service record_payment
# ---------------------------------------------------------------------------


class TestRecordPaymentService:
    def test_rejeu_meme_uuid_un_seul_paiement_un_recu_une_entree_de_journal(
        self, ctx, django_capture_on_commit_callbacks
    ):
        ctype = monthly_type(ctx)
        key = uuid.uuid4()
        with django_capture_on_commit_callbacks(execute=True):
            first = record(ctx, ctype, client_uuid=key)
        assert first.idempotent_replay is False
        after_first = writes(ctx.club)

        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            again = record(ctx, ctype, client_uuid=str(key))

        assert again.pk == first.pk
        assert again.idempotent_replay is True
        assert callbacks == []  # aucun reçu programmé
        assert writes(ctx.club) == after_first
        assert after_first["payments"] == 1
        assert after_first["validated_logs"] == 1
        assert after_first["receipt_logs"] == 1
        assert after_first["notifications"] == 1
        assert after_first["last_receipt"] == 1
        first.refresh_from_db()
        assert first.receipt_file  # un seul reçu, celui du premier envoi
        assert services.verify_chain(ctx.club).ok is True

    def test_uuid_journalise(self, ctx):
        ctype = monthly_type(ctx)
        key = uuid.uuid4()
        payment = record(ctx, ctype, client_uuid=key)
        log = AuditLog.objects.get(action_type=VALIDATED, object_id=str(payment.pk))
        assert log.after["client_uuid"] == str(key)

    def test_sans_uuid_comportement_inchange(self, ctx):
        ctype = monthly_type(ctx)
        first = record(ctx, ctype)
        second = record(ctx, ctype)
        assert first.pk != second.pk
        assert first.client_uuid is None and second.client_uuid is None
        assert first.client_recorded_at is None
        assert first.idempotent_replay is False
        assert (first.receipt_number, second.receipt_number) == (1, 2)
        assert writes(ctx.club)["validated_logs"] == 2

    def test_uuid_distincts_deux_paiements(self, ctx):
        ctype = monthly_type(ctx)
        first = record(ctx, ctype, client_uuid=uuid.uuid4())
        second = record(ctx, ctype, client_uuid=uuid.uuid4())
        assert first.pk != second.pk

    @pytest.mark.parametrize(
        "change",
        [
            {"amount": "50"},
            {"method": "cash", "reference": ""},
            {"reference": "MM-43"},
            {"paid_on": past_day(5)},
        ],
    )
    def test_meme_uuid_autre_contenu_conflit_sans_ecriture(self, ctx, change):
        ctype = monthly_type(ctx)
        key = uuid.uuid4()
        record(ctx, ctype, client_uuid=key)
        before = writes(ctx.club)
        with pytest.raises(services.ClientUuidConflictError):
            record(ctx, ctype, client_uuid=key, **change)
        assert writes(ctx.club) == before

    def test_meme_uuid_autre_joueur_conflit(self, ctx):
        from apps.treasury.tests.cash_helpers import named_member

        ctype = monthly_type(ctx)
        key = uuid.uuid4()
        record(ctx, ctype, client_uuid=key)
        other = named_member(ctx, first_name="Autre", last_name="Joueur")
        with pytest.raises(services.ClientUuidConflictError):
            record(ctx, ctype, membership=other, client_uuid=key)
        assert Payment.all_objects.filter(club=ctx.club).count() == 1

    def test_meme_uuid_autre_auteur_conflit(self, ctx):
        ctype = monthly_type(ctx)
        key = uuid.uuid4()
        record(ctx, ctype, client_uuid=key)
        with pytest.raises(services.ClientUuidConflictError):
            record(ctx, ctype, client_uuid=key, by=ctx.assistant_treasurer)

    def test_uuid_deja_utilise_par_la_caisse_conflit(self, ctx):
        ctype = monthly_type(ctx)
        session = open_session(ctx)
        key = uuid.uuid4()
        cash_pay(ctx, session, ctx.player, client_uuid=key, amount="40", contribution_type=ctype)
        with pytest.raises(services.ClientUuidConflictError):
            record(ctx, ctype, client_uuid=key)
        assert Payment.all_objects.filter(club=ctx.club).count() == 1

    def test_uuid_invalide(self, ctx):
        ctype = monthly_type(ctx)
        with pytest.raises(services.TreasuryValidationError):
            record(ctx, ctype, client_uuid="pas-un-uuid")
        assert Payment.all_objects.count() == 0

    def test_rejeu_par_un_non_tresorier_refuse(self, ctx):
        ctype = monthly_type(ctx)
        key = uuid.uuid4()
        record(ctx, ctype, client_uuid=key)
        with pytest.raises(services.TreasuryPermissionError):
            record(ctx, ctype, client_uuid=key, by=ctx.president)

    def test_rejeu_registre_gele_renvoie_le_paiement_sans_ecriture(self, ctx):
        ctype = monthly_type(ctx)
        key = uuid.uuid4()
        first = record(ctx, ctype, client_uuid=key)
        services.freeze_ledger(club=ctx.club, reason="Test de gel", actor=ctx.president.user)
        before = Transaction.all_objects.filter(club=ctx.club).count()
        again = record(ctx, ctype, client_uuid=key)
        assert again.pk == first.pk and again.idempotent_replay is True
        assert Transaction.all_objects.filter(club=ctx.club).count() == before

    def test_course_concurrente_integrity_error_renvoie_l_existant(self, ctx, monkeypatch):
        """Deux requêtes simultanées : la seconde passe le contrôle préalable
        avant que la première n'ait écrit ; la contrainte unique la rattrape."""

        ctype = monthly_type(ctx)
        key = uuid.uuid4()
        first = record(ctx, ctype, client_uuid=key)
        real_lookup = services._existing_client_uuid_payment
        calls = {"n": 0}

        def miss_once(club, parsed):
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return real_lookup(club, parsed)

        monkeypatch.setattr(services, "_existing_client_uuid_payment", miss_once)
        again = record(ctx, ctype, client_uuid=key)
        assert again.pk == first.pk and again.idempotent_replay is True
        assert Payment.all_objects.filter(club=ctx.club).count() == 1
        assert services.verify_chain(ctx.club).ok is True


# ---------------------------------------------------------------------------
# Service record_membership_fee_payment
# ---------------------------------------------------------------------------


class TestMembershipFeeService:
    def test_rejeu_meme_uuid_un_seul_paiement(self, ctx, fee_type, django_capture_on_commit_callbacks):
        key = uuid.uuid4()
        with django_capture_on_commit_callbacks(execute=True):
            first = record_fee(ctx, client_uuid=key)
        after_first = writes(ctx.club)
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            again = record_fee(ctx, client_uuid=key)
        assert again.pk == first.pk
        assert (first.idempotent_replay, again.idempotent_replay) == (False, True)
        assert callbacks == []
        assert writes(ctx.club) == after_first
        assert after_first["payments"] == 1 and after_first["validated_logs"] == 1
        assert after_first["receipt_logs"] == 1 and after_first["notifications"] == 1
        assert services.verify_chain(ctx.club).ok is True

    def test_sans_uuid_paiements_partiels_additionnes(self, ctx, fee_type):
        first = record_fee(ctx, amount="2")
        second = record_fee(ctx, amount="3")
        assert first.pk != second.pk
        assert first.idempotent_replay is False
        assert services.has_paid_membership_fee(ctx.pending_member) is True

    def test_meme_uuid_autre_montant_conflit(self, ctx, fee_type):
        key = uuid.uuid4()
        record_fee(ctx, client_uuid=key, amount="2")
        with pytest.raises(services.ClientUuidConflictError):
            record_fee(ctx, client_uuid=key, amount="3")
        assert Payment.all_objects.filter(club=ctx.club).count() == 1

    def test_uuid_d_un_paiement_de_cotisation_conflit(self, ctx, fee_type):
        ctype = monthly_type(ctx)
        key = uuid.uuid4()
        record(ctx, ctype, client_uuid=key, membership=ctx.pending_member)
        with pytest.raises(services.ClientUuidConflictError):
            record_fee(ctx, client_uuid=key)


# ---------------------------------------------------------------------------
# Étanchéité entre clubs
# ---------------------------------------------------------------------------


class TestEtancheite:
    def test_meme_uuid_dans_deux_clubs_deux_paiements_distincts(self, ctx, other_ctx):
        key = uuid.uuid4()
        mine = record(ctx, monthly_type(ctx), client_uuid=key)
        other_type = monthly_type(other_ctx, amount="25000")
        theirs = record(
            other_ctx, other_type, amount="25000", method="cash", reference="", client_uuid=key
        )
        assert mine.pk != theirs.pk
        assert (mine.idempotent_replay, theirs.idempotent_replay) == (False, False)
        assert (mine.club_id, theirs.club_id) == (ctx.club.pk, other_ctx.club.pk)
        assert (mine.receipt_number, theirs.receipt_number) == (1, 1)
        assert Payment.all_objects.filter(client_uuid=key).count() == 2

    def test_frais_d_adhesion_meme_uuid_deux_clubs(self, ctx, other_ctx, fee_type, other_fee_type):
        key = uuid.uuid4()
        mine = record_fee(ctx, client_uuid=key)
        theirs = services.record_membership_fee_payment(
            membership=other_ctx.pending_member,
            amount="5000",
            method="cash",
            paid_on=past_day(),
            validated_by=other_ctx.treasurer.user,
            client_uuid=key,
        )
        assert mine.pk != theirs.pk and theirs.idempotent_replay is False

    def test_api_meme_uuid_deux_clubs_deux_201(self, ctx, other_ctx):
        key = str(uuid.uuid4())
        mine = client_for(ctx.treasurer).post(
            reverse("treasury:payment-create"), body(ctx, monthly_type(ctx), client_uuid=key), format="json"
        )
        other_type = monthly_type(other_ctx, amount="25000")
        theirs = client_for(other_ctx.treasurer).post(
            reverse("treasury:payment-create"),
            body(other_ctx, other_type, amount="25000", method="cash", reference="", client_uuid=key),
            format="json",
        )
        assert (mine.status_code, theirs.status_code) == (201, 201)
        assert mine.data["id"] != theirs.data["id"]


# ---------------------------------------------------------------------------
# API POST /treasury/payments/
# ---------------------------------------------------------------------------


class TestPaymentCreateApi:
    def test_201_puis_rejeu_200_meme_paiement(self, ctx, django_capture_on_commit_callbacks):
        ctype = monthly_type(ctx)
        client = client_for(ctx.treasurer)
        data = body(ctx, ctype, client_uuid=str(uuid.uuid4()))
        with django_capture_on_commit_callbacks(execute=True):
            created = client.post(reverse("treasury:payment-create"), data, format="json")
        assert created.status_code == 201, created.data
        after_first = writes(ctx.club)

        with django_capture_on_commit_callbacks(execute=True):
            replay = client.post(reverse("treasury:payment-create"), data, format="json")
        assert replay.status_code == 200, replay.data
        assert replay.data["id"] == created.data["id"]
        assert replay.data["receipt_number"] == created.data["receipt_number"] == 1
        assert replay.data["client_uuid"] == data["client_uuid"]
        assert writes(ctx.club) == after_first
        assert after_first["payments"] == 1 and after_first["validated_logs"] == 1
        assert after_first["receipt_logs"] == 1 and after_first["notifications"] == 1

    def test_rejeu_multipart(self, ctx):
        ctype = monthly_type(ctx)
        client = client_for(ctx.treasurer)
        data = body(ctx, ctype, client_uuid=str(uuid.uuid4()))
        first = client.post(reverse("treasury:payment-create"), data, format="multipart")
        again = client.post(reverse("treasury:payment-create"), data, format="multipart")
        assert (first.status_code, again.status_code) == (201, 200)
        assert Payment.all_objects.filter(club=ctx.club).count() == 1

    def test_meme_uuid_autre_contenu_409(self, ctx):
        ctype = monthly_type(ctx)
        client = client_for(ctx.treasurer)
        data = body(ctx, ctype, client_uuid=str(uuid.uuid4()))
        client.post(reverse("treasury:payment-create"), data, format="json")
        conflict = client.post(reverse("treasury:payment-create"), {**data, "amount": "50"}, format="json")
        assert conflict.status_code == 409
        assert conflict.data["code"] == "client_uuid_conflict"
        assert Payment.all_objects.filter(club=ctx.club).count() == 1

    def test_sans_uuid_deux_post_deux_paiements(self, ctx):
        ctype = monthly_type(ctx)
        client = client_for(ctx.treasurer)
        data = body(ctx, ctype)
        first = client.post(reverse("treasury:payment-create"), data, format="json")
        second = client.post(reverse("treasury:payment-create"), data, format="json")
        assert (first.status_code, second.status_code) == (201, 201)
        assert first.data["id"] != second.data["id"]
        assert first.data["client_uuid"] is None

    def test_uuid_null_accepte(self, ctx):
        ctype = monthly_type(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-create"), body(ctx, ctype, client_uuid=None), format="json"
        )
        assert response.status_code == 201, response.data

    def test_uuid_mal_forme_400(self, ctx):
        ctype = monthly_type(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-create"), body(ctx, ctype, client_uuid="pas-un-uuid"), format="json"
        )
        assert response.status_code == 400
        assert "client_uuid" in response.data
        assert Payment.all_objects.count() == 0
