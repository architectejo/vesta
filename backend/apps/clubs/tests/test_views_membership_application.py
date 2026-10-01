"""Tests HTTP de l'adhesion et du parrainage (CDC 4.3 ; matrice 2.4 ; tache 1.4b).

Complete `test_membership_application.py` (tests de service) : verifie ici
le cablage vue -> service -> reponse HTTP (permissions par role, codes de
statut, etancheite multi-tenant), pas la logique metier elle-meme.
"""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.clubs.models import Membership, MembershipApplication, MembershipRole
from apps.clubs.tests.test_membership_application import add_player, build_context, pay
from apps.treasury.models import Payment
from apps.treasury.tests.conftest import PIN, WRONG_PIN, make_member

pytestmark = pytest.mark.django_db


def _authenticated_client(user) -> APIClient:
    """Meme principe que les autres tests HTTP de ce module (jeton d'acces
    reel, club actif resolu depuis l'adhesion reelle, CLAUDE.md regle n9)."""

    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


class TestAddPlayerWithSponsorView:
    def test_le_president_ajoute_un_joueur_avec_parrain(self):
        ctx = build_context()
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:players-add"),
            {
                "email": "nouveau@example.com",
                "first_name": "Nouveau",
                "last_name": "Joueur",
                "position": Membership.Position.FORWARD,
                "sponsor_membership_id": ctx.sponsor.id,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Membership.all_objects.filter(club=ctx.club, user__email="nouveau@example.com").exists()
        membership = Membership.all_objects.get(club=ctx.club, user__email="nouveau@example.com")
        assert membership.status == Membership.Status.PENDING

    def test_un_recruteur_designe_peut_ajouter(self):
        ctx = build_context()
        recruteur = make_member(ctx.club, roles=[MembershipRole.Role.PLAYER_RECRUITER])
        client = _authenticated_client(recruteur.user)

        response = client.post(
            reverse("clubs:players-add"),
            {
                "email": "nouveau2@example.com",
                "first_name": "Nouveau",
                "last_name": "Joueur",
                "position": Membership.Position.FORWARD,
                "sponsor_membership_id": ctx.sponsor.id,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_un_simple_joueur_est_refuse(self):
        ctx = build_context()
        client = _authenticated_client(ctx.sponsor.user)

        response = client.post(
            reverse("clubs:players-add"),
            {
                "email": "nouveau3@example.com",
                "first_name": "Nouveau",
                "last_name": "Joueur",
                "position": Membership.Position.FORWARD,
                "sponsor_membership_id": ctx.sponsor.id,
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_sans_parrain_est_refuse(self):
        ctx = build_context()
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:players-add"),
            {
                "email": "nouveau4@example.com",
                "first_name": "Nouveau",
                "last_name": "Joueur",
                "position": Membership.Position.FORWARD,
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_falsifier_un_club_dans_la_requete_est_sans_effet(self):
        """CLAUDE.md regle n9 : le club actif vient de l'adhesion reelle. Le
        parrain est recherche via ``Membership.objects`` (tenant-aware,
        filtre automatiquement sur le club actif) : un parrain d'un autre
        club n'est donc meme jamais trouve -- 404, jamais utilise comme
        parrain reel malgre son identifiant transmis dans la requete."""

        ctx = build_context()
        other = build_context()
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:players-add"),
            {
                "email": "nouveau5@example.com",
                "first_name": "Nouveau",
                "last_name": "Joueur",
                "position": Membership.Position.FORWARD,
                "sponsor_membership_id": other.sponsor.id,
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not Membership.all_objects.filter(club=ctx.club, user__email="nouveau5@example.com").exists()


class TestMembershipFeePaymentView:
    def test_le_tresorier_enregistre_le_paiement_et_enchaine_la_fiche(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        client = _authenticated_client(ctx.treasurer.user)

        response = client.post(
            reverse("clubs:application-fee-payment"),
            {
                "application_id": application.id,
                "amount": "5",
                "method": "cash",
                "paid_on": "2026-09-20",
                "pin": PIN,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["generated_at"] is not None
        assert response.data["sponsor_notified_at"] is not None

    def test_tresorier_adjoint_autorise(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        client = _authenticated_client(ctx.assistant.user)

        response = client.post(
            reverse("clubs:application-fee-payment"),
            {
                "application_id": application.id,
                "amount": "5",
                "method": "cash",
                "paid_on": "2026-09-20",
                "pin": PIN,
            },
        )

        assert response.status_code == status.HTTP_200_OK

    def test_le_president_seul_est_refuse(self):
        """Matrice 2.4 : « Enregistrement des paiements » est L pour le
        President (pas E) -- confirme par `finance-engine`."""

        ctx = build_context()
        _membership, application = add_player(ctx)
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:application-fee-payment"),
            {
                "application_id": application.id,
                "amount": "5",
                "method": "cash",
                "paid_on": "2026-09-20",
                "pin": PIN,
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_pin_incorrect_renvoie_400_avec_tentatives_restantes(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        client = _authenticated_client(ctx.treasurer.user)

        response = client.post(
            reverse("clubs:application-fee-payment"),
            {
                "application_id": application.id,
                "amount": "5",
                "method": "cash",
                "paid_on": "2026-09-20",
                "pin": WRONG_PIN,
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "attempts_remaining" in response.data

    def test_dossier_dun_autre_club_introuvable(self):
        ctx = build_context()
        other = build_context()
        _membership, other_application = add_player(other)
        client = _authenticated_client(ctx.treasurer.user)

        response = client.post(
            reverse("clubs:application-fee-payment"),
            {
                "application_id": other_application.id,
                "amount": "5",
                "method": "cash",
                "paid_on": "2026-09-20",
                "pin": PIN,
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_club_gele_renvoie_409_et_non_500(self):
        """Complement demande en revue independante (tache 1.4bt), point 5 :
        un club gele (CDC 5.3, ``LedgerFrozenError`` cote tresorerie) doit
        renvoyer une reponse HTTP propre (409, deja le code choisi par
        ``_treasury_error_response``), jamais une erreur 500 non traduite."""

        from apps.treasury.services import freeze_ledger

        ctx = build_context()
        _membership, application = add_player(ctx)
        freeze_ledger(club=ctx.club, reason="Verification annuelle", actor=ctx.president.user)
        client = _authenticated_client(ctx.treasurer.user)

        response = client.post(
            reverse("clubs:application-fee-payment"),
            {
                "application_id": application.id,
                "amount": "5",
                "method": "cash",
                "paid_on": "2026-09-20",
                "pin": PIN,
            },
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.data


class TestMembershipFeePaymentAttachmentValidation:
    """CDC 6.7, 7.6 : le justificatif est vérifié sur son contenu réel
    (JPEG, PNG, WebP, PDF ; 10 Mo maximum)."""

    @staticmethod
    def _post(ctx, application, attachment):
        client = _authenticated_client(ctx.treasurer.user)
        return client.post(
            reverse("clubs:application-fee-payment"),
            {
                "application_id": application.id,
                "amount": "5",
                "method": "cash",
                "paid_on": "2026-09-20",
                "pin": PIN,
                "attachment": attachment,
            },
            format="multipart",
        )

    @staticmethod
    def _image(image_format: str) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), color="red").save(buffer, format=image_format)
        return buffer.getvalue()

    @pytest.mark.parametrize(
        ("name", "content_type", "kind"),
        [
            ("recu.jpg", "image/jpeg", "JPEG"),
            ("recu.png", "image/png", "PNG"),
            ("recu.webp", "image/webp", "WEBP"),
            ("recu.pdf", "application/pdf", "PDF"),
        ],
    )
    def test_un_vrai_justificatif_est_accepte_et_stocke(self, name, content_type, kind):
        ctx = build_context()
        _membership, application = add_player(ctx)
        content = b"%PDF-1.4\n%justificatif\n%%EOF\n" if kind == "PDF" else self._image(kind)

        response = self._post(ctx, application, SimpleUploadedFile(name, content, content_type=content_type))

        assert response.status_code == status.HTTP_200_OK
        payment = Payment.all_objects.filter(club=ctx.club).exclude(attachment="").latest("id")
        assert payment.attachment.read() == content

    def test_un_executable_renomme_en_jpg_est_refuse(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        fake = SimpleUploadedFile("photo.jpg", b"MZ\x90\x00" + b"\x00" * 64, content_type="image/jpeg")

        response = self._post(ctx, application, fake)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "accepté" in str(response.data["attachment"][0])
        assert not Payment.all_objects.filter(club=ctx.club).exists()

    def test_un_gif_renomme_en_pdf_est_refuse(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        fake = SimpleUploadedFile("recu.pdf", self._image("GIF"), content_type="application/pdf")

        response = self._post(ctx, application, fake)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "attachment" in response.data
        assert not Payment.all_objects.filter(club=ctx.club).exists()

    def test_un_fichier_de_plus_de_10_mo_est_refuse(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        big = SimpleUploadedFile(
            "gros.pdf", b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024), content_type="application/pdf"
        )

        response = self._post(ctx, application, big)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "10 Mo" in str(response.data["attachment"][0])
        assert not Payment.all_objects.filter(club=ctx.club).exists()

    def test_un_fichier_vide_est_refuse(self):
        ctx = build_context()
        _membership, application = add_player(ctx)

        response = self._post(ctx, application, SimpleUploadedFile("vide.pdf", b"", content_type="application/pdf"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "attachment" in response.data


class TestSponsorSignatureView:
    def test_le_parrain_signe(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        client = _authenticated_client(ctx.sponsor.user)

        response = client.post(
            reverse("clubs:application-sponsor-sign"),
            {"application_id": application.id, "pin": PIN},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["sponsor_decision"] == MembershipApplication.SponsorDecision.SIGNED

        membership = Membership.all_objects.get(pk=application.membership_id)
        assert membership.status == Membership.Status.ACTIVE

    def test_quelqu_un_d_autre_que_le_parrain_est_refuse(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:application-sponsor-sign"),
            {"application_id": application.id, "pin": PIN},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_pin_bloque_apres_trois_echecs_renvoie_423(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        client = _authenticated_client(ctx.sponsor.user)

        for _ in range(3):
            response = client.post(
                reverse("clubs:application-sponsor-sign"),
                {"application_id": application.id, "pin": WRONG_PIN},
            )

        assert response.status_code == status.HTTP_423_LOCKED

    def test_falsifier_un_dossier_dun_autre_club_est_sans_effet(self):
        """Complement demande en revue independante (tache 1.4bt), point 6 :
        un President (ou n'importe quel membre) du club A ne doit jamais
        pouvoir signer un dossier du club B en forgeant son identifiant
        dans la requete -- ``_get_application`` est tenant-aware
        (``MembershipApplication.objects``), donc 404, jamais le dossier
        reel de l'autre club."""

        ctx = build_context()
        other = build_context()
        _membership, other_application = add_player(other)
        other_application = pay(other, other_application)
        client = _authenticated_client(ctx.sponsor.user)

        response = client.post(
            reverse("clubs:application-sponsor-sign"),
            {"application_id": other_application.id, "pin": PIN},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        other_application.refresh_from_db()
        assert other_application.sponsor_decision == MembershipApplication.SponsorDecision.PENDING


class TestSponsorRefusalView:
    def test_le_parrain_refuse_avec_motif(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        client = _authenticated_client(ctx.sponsor.user)

        response = client.post(
            reverse("clubs:application-sponsor-refuse"),
            {"application_id": application.id, "reason": "Ne le connait pas"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["sponsor_decision"] == MembershipApplication.SponsorDecision.REFUSED

    def test_motif_vide_refuse(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        client = _authenticated_client(ctx.sponsor.user)

        response = client.post(
            reverse("clubs:application-sponsor-refuse"),
            {"application_id": application.id, "reason": ""},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_falsifier_un_dossier_dun_autre_club_est_sans_effet(self):
        """Complement demande en revue independante (tache 1.4bt), point 6."""

        ctx = build_context()
        other = build_context()
        _membership, other_application = add_player(other)
        other_application = pay(other, other_application)
        client = _authenticated_client(ctx.sponsor.user)

        response = client.post(
            reverse("clubs:application-sponsor-refuse"),
            {"application_id": other_application.id, "reason": "Motif"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        other_application.refresh_from_db()
        assert other_application.sponsor_decision == MembershipApplication.SponsorDecision.PENDING


class TestSponsorReassignmentView:
    def test_le_president_designe_un_nouveau_parrain(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        application.sponsor_refused_reason = "Motif"
        application.save()
        new_sponsor = make_member(ctx.club)
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:application-sponsor-reassign"),
            {"application_id": application.id, "new_sponsor_membership_id": new_sponsor.id},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["sponsor_decision"] == MembershipApplication.SponsorDecision.PENDING

    def test_reserve_au_president(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        application.save()
        new_sponsor = make_member(ctx.club)
        client = _authenticated_client(ctx.treasurer.user)

        response = client.post(
            reverse("clubs:application-sponsor-reassign"),
            {"application_id": application.id, "new_sponsor_membership_id": new_sponsor.id},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_falsifier_un_dossier_dun_autre_club_est_sans_effet(self):
        """Complement demande en revue independante (tache 1.4bt), point 6."""

        ctx = build_context()
        other = build_context()
        _membership, other_application = add_player(other)
        other_application = pay(other, other_application)
        other_application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        other_application.save()
        new_sponsor = make_member(ctx.club)
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:application-sponsor-reassign"),
            {"application_id": other_application.id, "new_sponsor_membership_id": new_sponsor.id},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        other_application.refresh_from_db()
        assert other_application.sponsor_decision == MembershipApplication.SponsorDecision.REFUSED

    def test_falsifier_un_nouveau_parrain_dun_autre_club_est_sans_effet(self):
        """Le President du club A ne peut pas designer un joueur du club B
        comme nouveau parrain : le parrain est recherche via
        ``Membership.objects`` (tenant-aware), donc 404 -- meme principe
        que ``TestAddPlayerWithSponsorView.test_falsifier_un_club_dans_la_requete_est_sans_effet``."""

        ctx = build_context()
        other = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        application.save()
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:application-sponsor-reassign"),
            {"application_id": application.id, "new_sponsor_membership_id": other.sponsor.id},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        application.refresh_from_db()
        assert application.sponsor_decision == MembershipApplication.SponsorDecision.REFUSED


class TestMembershipApplicationCancellationView:
    def test_le_president_annule_avec_conservation(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        application.sponsor_refused_reason = "Motif"
        application.save()
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:application-cancel"),
            {
                "application_id": application.id,
                "reason": "Aucun autre parrain",
                "disposition": MembershipApplication.FeeDisposition.KEPT,
                "pin": PIN,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["membership_fee_disposition"] == MembershipApplication.FeeDisposition.KEPT
        membership = Membership.all_objects.get(pk=application.membership_id)
        assert membership.status == Membership.Status.DEPARTED

    def test_reserve_au_president(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        application = pay(ctx, application)
        application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        application.save()
        client = _authenticated_client(ctx.treasurer.user)

        response = client.post(
            reverse("clubs:application-cancel"),
            {
                "application_id": application.id,
                "reason": "Motif",
                "disposition": MembershipApplication.FeeDisposition.KEPT,
                "pin": PIN,
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_falsifier_un_dossier_dun_autre_club_est_sans_effet(self):
        """Complement demande en revue independante (tache 1.4bt), point 6."""

        ctx = build_context()
        other = build_context()
        _membership, other_application = add_player(other)
        other_application = pay(other, other_application)
        other_application.sponsor_decision = MembershipApplication.SponsorDecision.REFUSED
        other_application.save()
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:application-cancel"),
            {
                "application_id": other_application.id,
                "reason": "Motif",
                "disposition": MembershipApplication.FeeDisposition.KEPT,
                "pin": PIN,
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        other_membership = Membership.all_objects.get(pk=other_application.membership_id)
        assert other_membership.status != Membership.Status.DEPARTED

    def test_hors_authentification_refuse(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        client = APIClient()

        response = client.post(
            reverse("clubs:application-cancel"),
            {
                "application_id": application.id,
                "reason": "Motif",
                "disposition": MembershipApplication.FeeDisposition.KEPT,
                "pin": PIN,
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestParcoursComplet:
    def test_ajout_paiement_signature_fait_passer_inscrit_de_bout_en_bout(self):
        """Critere de fin de la tache 1.4b (plan-lots.md) : « Un joueur
        ajoute avec parrain passe Inscrit apres paiement et signature »,
        verifie ici entierement par HTTP (vue -> service -> vue)."""

        ctx = build_context()
        president_client = _authenticated_client(ctx.president.user)
        treasurer_client = _authenticated_client(ctx.treasurer.user)

        add_response = president_client.post(
            reverse("clubs:players-add"),
            {
                "email": "boutenbout@example.com",
                "first_name": "Bout",
                "last_name": "EnBout",
                "position": Membership.Position.DEFENDER,
                "sponsor_membership_id": ctx.sponsor.id,
            },
        )
        assert add_response.status_code == status.HTTP_201_CREATED
        application_id = add_response.data["application"]["id"]
        membership_id = add_response.data["membership_id"]

        pay_response = treasurer_client.post(
            reverse("clubs:application-fee-payment"),
            {
                "application_id": application_id,
                "amount": "5",
                "method": "cash",
                "paid_on": "2026-09-20",
                "pin": PIN,
            },
        )
        assert pay_response.status_code == status.HTTP_200_OK

        membership_still_pending = Membership.all_objects.get(pk=membership_id)
        assert membership_still_pending.status == Membership.Status.PENDING

        sponsor_client = _authenticated_client(ctx.sponsor.user)
        sign_response = sponsor_client.post(
            reverse("clubs:application-sponsor-sign"),
            {"application_id": application_id, "pin": PIN},
        )
        assert sign_response.status_code == status.HTTP_200_OK

        membership = Membership.all_objects.get(pk=membership_id)
        assert membership.status == Membership.Status.ACTIVE
