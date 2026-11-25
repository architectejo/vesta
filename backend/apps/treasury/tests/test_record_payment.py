"""Enregistrement général d'un paiement (tâche 2.4 ; CDC 4.4.3, 4.4.4).

Service ``preview_payment_allocation`` (aperçu sans écriture) et
``record_payment`` (rôle et données contrôlés par le serveur ; plus de PIN
depuis la décision client du 11/10/2026, CLAUDE.md règle 7 : l'auteur est
journalisé), puis l'API correspondante (JSON et multipart), avec
l'étanchéité entre clubs.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.treasury import services
from apps.treasury.models import Payment, PaymentAllocation, Transaction
from apps.treasury.tests.cash_helpers import club_today, free_type, monthly_type, named_member, put_in_debt
from apps.treasury.tests.conftest import PIN, WRONG_PIN, assert_logged_by, past_day

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n%piece de test\n%%EOF\n"
MARCH = datetime.date(2026, 3, 10)


def march_player(ctx):
    """Joueur arrivé le 1er mars 2026, à jour (aucun montant dû)."""

    return named_member(ctx, first_name="Mars", last_name="Quatremois", joined_on=datetime.date(2026, 3, 1))


def record(ctx, membership, ctype, *, amount="10", method="cash", paid_on=MARCH, by=None, **extra):
    return services.record_payment(
        membership=membership,
        contribution_type=ctype,
        amount=amount,
        method=method,
        paid_on=paid_on,
        recorded_by=(by or ctx.treasurer).user,
        **extra,
    )


def counts():
    return (
        Payment.all_objects.count(),
        Transaction.all_objects.count(),
        PaymentAllocation.all_objects.count(),
        AuditLog.objects.count(),
    )


class TestPreview:
    def test_exemple_du_cdc_40_dollars_en_mars_couvre_mars_a_juin(self, ctx):
        ctype = monthly_type(ctx)
        player = march_player(ctx)

        preview = services.preview_payment_allocation(
            membership=player, contribution_type=ctype, amount="40", paid_on=MARCH, requested_by=ctx.treasurer.user
        )

        assert [(line.period, line.amount, line.status) for line in preview.lines] == [
            (datetime.date(2026, 3, 1), Decimal("10.00"), "paid"),
            (datetime.date(2026, 4, 1), Decimal("10.00"), "paid"),
            (datetime.date(2026, 5, 1), Decimal("10.00"), "paid"),
            (datetime.date(2026, 6, 1), Decimal("10.00"), "paid"),
        ]
        assert preview.unallocated_amount == Decimal("0.00")
        assert preview.current.balance == Decimal("0.00")
        assert preview.after.balance == Decimal("40.00")
        assert preview.after.is_in_good_standing is True
        assert preview.currency == "USD"

    def test_aucune_ecriture(self, ctx):
        ctype = monthly_type(ctx)
        player = march_player(ctx)
        before = counts()
        services.preview_payment_allocation(
            membership=player, contribution_type=ctype, amount="40", paid_on=MARCH, requested_by=ctx.treasurer.user
        )
        assert counts() == before

    def test_paiement_partiel_et_dette_ancienne_d_abord(self, ctx):
        ctype = monthly_type(ctx)
        player = named_member(ctx, first_name="Ancien", last_name="Retard")
        put_in_debt(ctx, player, ctype, months_ago=2)
        today = club_today(ctx)

        preview = services.preview_payment_allocation(
            membership=player, contribution_type=ctype, amount="4", paid_on=today, requested_by=ctx.treasurer.user
        )

        oldest = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
        oldest = (oldest - datetime.timedelta(days=1)).replace(day=1)
        assert len(preview.lines) == 1
        line = preview.lines[0]
        assert (line.period, line.amount, line.status) == (oldest, Decimal("4.00"), "partial")
        assert line.period_amount == Decimal("10.00")
        assert preview.current.is_in_good_standing is False
        assert preview.after.balance == Decimal("-6.00")
        assert preview.after.is_in_good_standing is False
        assert "6.00 USD" in preview.after.reason

    def test_type_libre_hors_solde(self, ctx):
        ctype = free_type(ctx)
        preview = services.preview_payment_allocation(
            membership=ctx.player, contribution_type=ctype, amount="3", paid_on=past_day(), requested_by=ctx.treasurer.user
        )
        assert preview.is_free_type is True
        assert [line.status for line in preview.lines] == ["free"]
        assert preview.after.balance == preview.current.balance

    def test_apercu_identique_a_la_repartition_enregistree(self, ctx):
        ctype = monthly_type(ctx)
        player = march_player(ctx)
        record(ctx, player, ctype, amount="15")
        preview = services.preview_payment_allocation(
            membership=player, contribution_type=ctype, amount="25", paid_on=MARCH, requested_by=ctx.treasurer.user
        )
        payment = record(ctx, player, ctype, amount="25")
        recorded = list(payment.allocations.order_by("period").values_list("period", "amount"))
        assert [(line.period, line.amount) for line in preview.lines] == recorded
        assert recorded[0] == (datetime.date(2026, 4, 1), Decimal("5.00"))

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    def test_reserve_au_tresorier_et_a_l_adjoint(self, ctx, role):
        ctype = monthly_type(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            services.preview_payment_allocation(
                membership=ctx.player, contribution_type=ctype, amount="10", paid_on=past_day(),
                requested_by=getattr(ctx, role).user,
            )


class TestRecordPayment:
    def test_paiement_valide_chaine_recu_repartition_journal(self, ctx):
        ctype = monthly_type(ctx)
        player = march_player(ctx)

        payment = record(ctx, player, ctype, amount="40", method="mobile_money", reference="MM-42")

        assert payment.source == Payment.Source.TREASURER_ENTRY
        assert payment.validated_by_id == ctx.treasurer.user_id
        assert payment.receipt_number == 1
        assert payment.cash_session_id is None
        txn = payment.transaction
        assert (txn.status, txn.provider, txn.amount) == (Transaction.Status.SUCCEEDED, "manual", Decimal("40.00"))
        assert txn.sealed_at is not None
        assert list(payment.allocations.order_by("period").values_list("period", flat=True)) == [
            datetime.date(2026, month, 1) for month in (3, 4, 5, 6)
        ]
        log = AuditLog.objects.get(action_type="treasury.payment.validated", object_id=str(payment.pk))
        assert log.after["transaction_hash"] == txn.hash
        assert PIN not in str(log.after)
        assert services.verify_chain(ctx.club).ok

    def test_numero_de_recu_sequentiel_par_club(self, ctx, other_ctx):
        ctype = monthly_type(ctx)
        other_type = monthly_type(other_ctx)
        first = record(ctx, ctx.player, ctype, paid_on=past_day())
        second = record(ctx, ctx.player, ctype, paid_on=past_day())
        other = record(other_ctx, other_ctx.player, other_type, paid_on=past_day())
        assert (first.receipt_number, second.receipt_number, other.receipt_number) == (1, 2, 1)

    def test_adjoint_autorise(self, ctx):
        ctype = monthly_type(ctx)
        payment = record(ctx, ctx.player, ctype, paid_on=past_day(), by=ctx.assistant_treasurer)
        assert payment.validated_by_id == ctx.assistant_treasurer.user_id

    def test_joueur_regularise_redevient_en_ordre(self, ctx):
        ctype = monthly_type(ctx)
        put_in_debt(ctx, ctx.player, ctype)
        assert services.is_in_good_standing(ctx.player)[0] is False
        record(ctx, ctx.player, ctype, paid_on=club_today(ctx))
        assert services.is_in_good_standing(ctx.player)[0] is True

    def test_reussit_sans_pin_et_journalise_l_auteur(self, ctx):
        """Décision client du 11/10/2026 (CLAUDE.md règle 7) : plus de PIN ;
        l'auteur de la validation est écrit dans le journal."""

        ctype = monthly_type(ctx)
        payment = record(ctx, ctx.player, ctype, paid_on=past_day(), by=ctx.assistant_treasurer)
        assert payment.transaction.status == Transaction.Status.SUCCEEDED
        assert_logged_by("treasury.payment.validated", ctx.assistant_treasurer.user, club=ctx.club)

    def test_le_parametre_pin_n_existe_plus(self, ctx):
        """Le service n'accepte plus de ``pin`` (supprimé le 11/10/2026)."""

        ctype = monthly_type(ctx)
        with pytest.raises(TypeError):
            record(ctx, ctx.player, ctype, paid_on=past_day(), pin=WRONG_PIN)
        assert Payment.all_objects.count() == 0

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    def test_roles_non_autorises_refuses(self, ctx, role):
        ctype = monthly_type(ctx)
        member = getattr(ctx, role)
        before = counts()
        with pytest.raises(services.TreasuryPermissionError):
            record(ctx, ctx.player, ctype, paid_on=past_day(), by=member)
        assert counts() == before

    @pytest.mark.parametrize("amount", ["0", "-5", "abc", "", "1e30", 10.5, None])
    def test_montants_invalides(self, ctx, amount):
        ctype = monthly_type(ctx)
        with pytest.raises(services.InvalidAmountError):
            record(ctx, ctx.player, ctype, amount=amount, paid_on=past_day())
        assert Payment.all_objects.count() == 0

    def test_montant_arrondi_a_deux_decimales(self, ctx):
        ctype = monthly_type(ctx)
        # D7 : valeur Decimal arrondie ; une saisie texte à 3 décimales est refusée (D-A7).
        assert record(ctx, ctx.player, ctype, amount=Decimal("10.005"), paid_on=past_day()).amount == Decimal("10.01")
        with pytest.raises(services.InvalidAmountError, match="2 chiffres après la virgule"):
            record(ctx, ctx.player, ctype, amount="10.005", paid_on=past_day())

    @pytest.mark.parametrize("method", ["mobile_money", "payment_link"])
    def test_reference_obligatoire_hors_especes(self, ctx, method):
        ctype = monthly_type(ctx)
        with pytest.raises(services.TreasuryValidationError, match="référence"):
            record(ctx, ctx.player, ctype, method=method, paid_on=past_day())

    def test_mode_carte_refuse(self, ctx):
        ctype = monthly_type(ctx)
        with pytest.raises(services.TreasuryValidationError):
            record(ctx, ctx.player, ctype, method="card", paid_on=past_day())

    def test_date_future_refusee(self, ctx):
        ctype = monthly_type(ctx)
        with pytest.raises(services.TreasuryValidationError, match="futur"):
            record(ctx, ctx.player, ctype, paid_on=club_today(ctx) + datetime.timedelta(days=1))

    def test_type_archive_refuse(self, ctx):
        ctype = monthly_type(ctx)
        services.archive_contribution_type(contribution_type=ctype, archived_by=ctx.president.user)
        ctype.refresh_from_db()
        with pytest.raises(services.TreasuryValidationError, match="archivé"):
            record(ctx, ctx.player, ctype, paid_on=past_day())

    def test_type_d_un_autre_club_refuse(self, ctx, other_ctx):
        other_type = monthly_type(other_ctx)
        with pytest.raises(services.TreasuryValidationError):
            record(ctx, ctx.player, other_type, paid_on=past_day())

    def test_joueur_parti_refuse(self, ctx):
        ctype = monthly_type(ctx)
        ctx.player.status = Membership.Status.DEPARTED
        ctx.player.left_on = past_day()
        ctx.player.left_reason = Membership.LeftReason.OTHER
        ctx.player.left_by = ctx.president.user
        ctx.player.save()
        with pytest.raises(services.TreasuryValidationError, match="quitté"):
            record(ctx, ctx.player, ctype, paid_on=past_day())

    def test_piece_jointe_invalide_refusee(self, ctx):
        ctype = monthly_type(ctx)
        fake = SimpleUploadedFile("faux.pdf", b"pas un pdf", content_type="application/pdf")
        with pytest.raises(services.TreasuryValidationError, match="Format"):
            record(ctx, ctx.player, ctype, paid_on=past_day(), attachment=fake)
        assert Payment.all_objects.count() == 0

    def test_ecritures_gelees(self, ctx):
        ctype = monthly_type(ctx)
        services.freeze_ledger(club=ctx.club, reason="Test de gel", actor=None)
        with pytest.raises(services.LedgerFrozenError):
            record(ctx, ctx.player, ctype, paid_on=past_day())
        assert Payment.all_objects.count() == 0


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def client_for(member) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member.user).access_token}")
    return client


def payload(membership, ctype, **extra):
    data = {
        "membership_id": membership.pk,
        "contribution_type_id": ctype.pk,
        "amount": "10",
        "paid_on": past_day().isoformat(),
    }
    data.update(extra)
    return data


class TestPaymentApi:
    def test_apercu(self, ctx):
        ctype = monthly_type(ctx)
        player = march_player(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-preview"),
            payload(player, ctype, amount="40", paid_on=MARCH.isoformat()),
            format="json",
        )
        assert response.status_code == 200, response.data
        assert [line["period"] for line in response.data["allocations"]] == [
            datetime.date(2026, month, 1) for month in (3, 4, 5, 6)
        ]
        assert response.data["after"]["balance"] == "40.00"
        assert response.data["after"]["is_in_good_standing"] is True
        assert Payment.all_objects.count() == 0

    def test_enregistrement_multipart_avec_piece_jointe(self, ctx):
        ctype = monthly_type(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-create"),
            payload(
                ctx.player, ctype, method="mobile_money", reference="MM-1",
                attachment=SimpleUploadedFile("recu.pdf", PDF, content_type="application/pdf"),
            ),
            format="multipart",
        )
        assert response.status_code == 201, response.data
        assert response.data["receipt_number"] == 1
        assert response.data["attachment_url"] == reverse("treasury:payment-attachment-download", args=[response.data["id"]])
        assert response.data["player_status"]["currency"] == "USD"
        assert "pin" not in response.data

    def test_piece_jointe_invalide_400(self, ctx):
        ctype = monthly_type(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-create"),
            payload(ctx.player, ctype, attachment=SimpleUploadedFile("x.pdf", b"texte")),
            format="multipart",
        )
        assert response.status_code == 400
        assert Payment.all_objects.count() == 0

    def test_sans_pin_201_et_auteur_journalise(self, ctx):
        ctype = monthly_type(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-create"), payload(ctx.player, ctype, method="cash"), format="json"
        )
        assert response.status_code == 201, response.data
        assert_logged_by("treasury.payment.validated", ctx.treasurer.user, club=ctx.club)

    def test_pin_envoye_par_un_ancien_client_ignore(self, ctx):
        ctype = monthly_type(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-create"), payload(ctx.player, ctype, pin=WRONG_PIN, method="cash"), format="json"
        )
        assert response.status_code == 201, response.data
        assert "attempts_remaining" not in response.data
        ctx.treasurer.user.refresh_from_db()

    def test_montant_illisible_400(self, ctx):
        ctype = monthly_type(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-create"),
            payload(ctx.player, ctype, method="cash", amount="dix"),
            format="json",
        )
        assert response.status_code == 400
        assert "Montant invalide" in response.data["detail"]

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    @pytest.mark.parametrize("name", ["payment-preview", "payment-create"])
    def test_403_hors_tresorier_et_adjoint(self, ctx, role, name):
        ctype = monthly_type(ctx)
        response = client_for(getattr(ctx, role)).post(
            reverse(f"treasury:{name}"), payload(ctx.player, ctype, method="cash"), format="json"
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("name", ["payment-preview", "payment-create"])
    def test_401_sans_authentification(self, ctx, name):
        assert APIClient().post(reverse(f"treasury:{name}"), {}, format="json").status_code == 401

    def test_joueur_d_un_autre_club_404(self, ctx, other_ctx):
        ctype = monthly_type(ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-create"),
            payload(other_ctx.player, ctype, method="cash"),
            format="json",
        )
        assert response.status_code == 404
        assert Payment.all_objects.count() == 0

    def test_type_d_un_autre_club_404(self, ctx, other_ctx):
        other_type = monthly_type(other_ctx)
        response = client_for(ctx.treasurer).post(
            reverse("treasury:payment-preview"), payload(ctx.player, other_type), format="json"
        )
        assert response.status_code == 404
        assert response.data["detail"] == "Type de cotisation introuvable dans ce club."
