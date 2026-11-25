"""Fichiers privés des paiements (CDC 4.4.4, 6.7, 7.6 ; CLAUDE.md règle n° 10).

Couvre :
- le rangement de la pièce jointe et du reçu sur le stockage privé
  (``apps.core.storage.private_storage``), sans aucune URL publique ;
- le plafond de 10 Mo de la pièce jointe (``validate_upload_size``), sans
  aucune écriture si le fichier est refusé ;
- les vues de téléchargement authentifiées : rôles autorisés (ligne
  « Enregistrement des paiements » de la matrice 2.4), joueur pour ses
  propres paiements, refus (404) des autres joueurs et fonctions, étanchéité
  entre clubs (404, jamais 403), fichier absent, requête non authentifiée.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import MembershipRoleFactory
from apps.core.validators import MAX_UPLOAD_SIZE_BYTES
from apps.treasury import services
from apps.treasury.models import Payment, Transaction
from apps.treasury.tests.conftest import ClubContext, make_member, past_day

pytestmark = pytest.mark.django_db

ATTACHMENT_CONTENT = b"%PDF-1.4\n%justificatif de paiement de test\n%%EOF\n"
RECEIPT_CONTENT = b"%PDF-1.4\n%recu de test\n%%EOF\n"


def client_for(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def attachment_url(payment) -> str:
    return reverse("treasury:payment-attachment-download", args=[payment.pk])


def receipt_url(payment) -> str:
    return reverse("treasury:payment-receipt-download", args=[payment.pk])


def pay_with_attachment(ctx: ClubContext, *, membership=None, content=ATTACHMENT_CONTENT) -> Payment:
    return services.record_membership_fee_payment(
        membership=membership or ctx.player,
        amount="5",
        method="cash",
        paid_on=past_day(),
        validated_by=ctx.treasurer.user,
        attachment=SimpleUploadedFile("preuve.pdf", content, content_type="application/pdf"),
    )


def add_receipt(payment: Payment) -> Payment:
    payment.receipt_file.save("recu.pdf", ContentFile(RECEIPT_CONTENT), save=True)
    return payment


def body(response) -> bytes:
    return b"".join(response.streaming_content)


class TestPrivateStorage:
    def test_attachment_and_receipt_are_stored_outside_public_media(self, ctx, fee_type):
        payment = add_receipt(pay_with_attachment(ctx))

        private_root = Path(django_settings.PRIVATE_MEDIA_ROOT).resolve()
        public_root = Path(django_settings.MEDIA_ROOT).resolve()
        for field in (payment.attachment, payment.receipt_file):
            stored = Path(field.path).resolve()
            assert stored.is_file()
            assert private_root in stored.parents
            assert not (public_root / field.name).exists()
            with pytest.raises(ValueError):
                field.url  # noqa: B018 -- aucune URL publique, jamais

    def test_oversized_attachment_is_refused_and_nothing_is_written(self, ctx, fee_type):
        too_big = b"0" * (MAX_UPLOAD_SIZE_BYTES + 1)

        with pytest.raises(services.TreasuryValidationError, match="10 Mo"):
            pay_with_attachment(ctx, content=too_big)

        assert not Payment.all_objects.filter(club=ctx.club).exists()
        assert not Transaction.all_objects.filter(club=ctx.club).exists()
        assert not AuditLog.objects.filter(action_type="treasury.payment.validated").exists()


class TestDownloadPermissions:
    @pytest.mark.parametrize("role_name", ["president", "vice_president", "treasurer", "assistant_treasurer"])
    def test_bureau_readers_download_attachment_and_receipt(self, ctx, fee_type, role_name):
        payment = add_receipt(pay_with_attachment(ctx))
        client = client_for(getattr(ctx, role_name).user)

        response = client.get(attachment_url(payment))
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Disposition"].startswith("attachment")
        assert f"paiement-{payment.pk}-justificatif.pdf" in response["Content-Disposition"]
        assert body(response) == ATTACHMENT_CONTENT

        response = client.get(receipt_url(payment))
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Disposition"].startswith("attachment")
        assert body(response) == RECEIPT_CONTENT

    def test_player_downloads_his_own_payment_files(self, ctx, fee_type):
        payment = add_receipt(pay_with_attachment(ctx, membership=ctx.player))
        client = client_for(ctx.player.user)

        assert body(client.get(attachment_url(payment))) == ATTACHMENT_CONTENT
        assert body(client.get(receipt_url(payment))) == RECEIPT_CONTENT

    def test_other_player_of_same_club_gets_404(self, ctx, fee_type):
        payment = add_receipt(pay_with_attachment(ctx, membership=ctx.player))
        other_player = make_member(ctx.club)
        client = client_for(other_player.user)

        for url in (attachment_url(payment), receipt_url(payment)):
            response = client.get(url)
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert response.data["detail"] == "Ce paiement n'existe pas dans ce club."

    @pytest.mark.parametrize(
        "role",
        [
            MembershipRole.Role.SPORTS_DIRECTOR,
            MembershipRole.Role.STEWARD,
            MembershipRole.Role.COACH,
            MembershipRole.Role.CAPTAIN,
            MembershipRole.Role.DOCTOR,
        ],
    )
    def test_functions_without_payment_access_get_404(self, ctx, fee_type, role):
        payment = add_receipt(pay_with_attachment(ctx, membership=ctx.player))
        member = make_member(ctx.club)
        extra = {"is_qualified_professional": True} if role == MembershipRole.Role.DOCTOR else {}
        MembershipRoleFactory(membership=member, club=ctx.club, role=role, appointed_at=timezone.now(), **extra)

        assert client_for(member.user).get(attachment_url(payment)).status_code == status.HTTP_404_NOT_FOUND
        assert client_for(member.user).get(receipt_url(payment)).status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_request_is_refused(self, ctx, fee_type):
        payment = add_receipt(pay_with_attachment(ctx))

        assert APIClient().get(attachment_url(payment)).status_code == status.HTTP_401_UNAUTHORIZED
        assert APIClient().get(receipt_url(payment)).status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_files_answer_404_with_french_message(self, ctx, fee_type):
        payment = services.record_membership_fee_payment(
            membership=ctx.player,
            amount="5",
            method="cash",
            paid_on=past_day(),
            validated_by=ctx.treasurer.user,
        )
        client = client_for(ctx.treasurer.user)

        response = client.get(attachment_url(payment))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["detail"] == "Ce paiement n'a pas de pièce jointe."

        response = client.get(receipt_url(payment))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["detail"] == "Le reçu de ce paiement n'est pas encore disponible."


class TestTenantIsolation:
    @pytest.mark.parametrize("role_name", ["president", "treasurer", "player"])
    def test_other_club_never_reaches_payment_files(self, ctx, other_ctx, fee_type, role_name):
        payment = add_receipt(pay_with_attachment(ctx, membership=ctx.player))
        client = client_for(getattr(other_ctx, role_name).user)

        for url in (attachment_url(payment), receipt_url(payment)):
            response = client.get(url)
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert response.data["detail"] == "Ce paiement n'existe pas dans ce club."

    def test_unknown_payment_and_foreign_payment_answer_identically(self, ctx, other_ctx, fee_type, other_fee_type):
        foreign = add_receipt(pay_with_attachment(other_ctx, membership=other_ctx.player))
        client = client_for(ctx.president.user)

        foreign_response = client.get(attachment_url(foreign))
        missing_response = client.get(reverse("treasury:payment-attachment-download", args=[foreign.pk + 1000]))

        assert foreign_response.status_code == missing_response.status_code == status.HTTP_404_NOT_FOUND
        assert foreign_response.data == missing_response.data
