"""Reçu PDF numéroté d'un paiement validé (CDC 4.4.4, 4.6, 6.1, 6.7 ;
annexe D §1 ; CLAUDE.md règles 6, 10, 18, 19).

Couvre :
- génération déclenchée par la validation (après validation effective en
  base, ``on_commit``) pour chaque chemin qui valide un paiement
  (saisie Trésorier, frais d'adhésion, déclaration « J'ai payé ») ;
- aucun reçu tant que le paiement n'est pas validé ;
- contenu : identité du club (nom, ville, logo, devise) venue du club,
  joueur concerné seulement, aucune mention de l'Éditeur ni de « Vesta »,
  aucun solde ;
- stockage privé (``PRIVATE_MEDIA_ROOT``), jamais d'URL publique ;
- idempotence (jamais deux reçus) et immuabilité du reçu émis ;
- annulation : le reçu d'origine est conservé ;
- échec de génération : le paiement reste validé, rattrapage par la
  commande ``issue_missing_payment_receipts`` ;
- journal d'activité (règle 6) obligatoire : s'il échoue, le reçu n'est
  pas émis (fichier supprimé) et la commande de rattrapage réessaie ;
- étanchéité entre clubs (service et téléchargement).
"""

from __future__ import annotations

import io
import re
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.core.tenant import TenantMismatchError, active_club
from apps.treasury import services
from apps.treasury.models import LedgerImmutableError, Payment
from apps.treasury.tests.cash_helpers import monthly_type, named_member
from apps.treasury.tests.conftest import PIN, past_day

pytestmark = pytest.mark.django_db

RECEIPT_ACTION = "treasury.payment.receipt_issued"


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------


def client_for(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


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


def record_committed(ctx, membership, ctype, capture, **kwargs) -> Payment:
    """Enregistre un paiement en exécutant les rappels ``on_commit`` (le test
    tourne dans une transaction jamais validée : sans la capture, la
    génération post-validation ne s'exécuterait pas)."""

    with capture(execute=True):
        payment = record(ctx, membership, ctype, **kwargs)
    payment.refresh_from_db()
    return payment


def pdf_text(payment: Payment) -> str:
    with payment.receipt_file.open("rb") as handle:
        content = handle.read()
    assert content.startswith(b"%PDF")
    # Canevas non compressé (``pageCompression=0``) : flux lisible tel quel.
    return content.decode("latin-1")


def receipt_logs(payment: Payment):
    return AuditLog.objects.filter(action_type=RECEIPT_ACTION, object_id=str(payment.pk))


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 16, 46)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def ctype(ctx):
    return monthly_type(ctx)


@pytest.fixture
def payer(ctx):
    return named_member(ctx, first_name="Payeur", last_name="Recu")


# ---------------------------------------------------------------------------
# Déclencheur : la validation du paiement
# ---------------------------------------------------------------------------


class TestDeclencheur:
    def test_paiement_valide_genere_son_recu(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)

        assert payment.receipt_number == 1
        assert payment.receipt_file
        assert payment.receipt_issued_at is not None
        assert pdf_text(payment)

    def test_aucun_recu_avant_la_validation_effective_en_base(self, ctx, ctype, payer):
        # Rappels on_commit non exécutés = transaction pas encore validée.
        payment = record(ctx, payer, ctype)
        payment.refresh_from_db()
        assert payment.receipt_number == 1
        assert not payment.receipt_file
        assert payment.receipt_issued_at is None

    def test_frais_d_adhesion(self, ctx, fee_type, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            payment = services.record_membership_fee_payment(
                membership=ctx.pending_member,
                amount="5",
                method="cash",
                paid_on=past_day(),
                validated_by=ctx.treasurer.user,
            )
        payment.refresh_from_db()
        assert payment.receipt_file

    def test_declaration_j_ai_paye_recu_a_la_validation_seulement(self, ctx, ctype, django_capture_on_commit_callbacks):
        settings_obj = ctx.club.settings
        settings_obj.payment_link_url = "https://paiement.example.test/club"
        settings_obj.save()

        with django_capture_on_commit_callbacks(execute=True):
            declared = services.declare_payment(
                membership=ctx.player,
                declared_by=ctx.player.user,
                contribution_type=ctype,
                amount="10",
                reference="LAX-RECU-1",
            )
        declared.refresh_from_db()
        assert not declared.receipt_file
        with pytest.raises(services.TreasuryValidationError):
            services.issue_payment_receipt(payment=declared)

        with django_capture_on_commit_callbacks(execute=True):
            services.validate_declared_payment(payment=declared, validated_by=ctx.treasurer.user)
        declared.refresh_from_db()
        assert declared.receipt_file
        assert receipt_logs(declared).count() == 1


# ---------------------------------------------------------------------------
# Contenu (marque blanche, minimisation)
# ---------------------------------------------------------------------------


class TestContenu:
    def test_identite_du_club_et_objet_du_paiement(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        text = pdf_text(payment)

        assert ctx.club.name in text
        assert ctx.club.city in text
        assert "R-1" in text  # référence du reçu
        assert "Payeur Recu" in text
        assert "Mensuelle 10" in text
        assert "40 $" in text  # devise du club (USD)
        assert "Mobile money" in text
        assert "MM-42" in text
        # Métadonnées (annexe D §1.9) : jamais « anonymous ».
        assert f"/Author ({ctx.club.name})" in text
        assert "anonymous" not in text

    def test_devise_du_club_cdf(self, other_ctx, django_capture_on_commit_callbacks):
        ctype = monthly_type(other_ctx, amount="25000")
        payment = record_committed(
            other_ctx, other_ctx.player, ctype, django_capture_on_commit_callbacks, amount="25000", method="cash", reference=""
        )
        text = pdf_text(payment)
        assert "25 000 FC" in text
        assert "$" not in text.split("stream", 1)[1]

    def test_logo_du_club_present(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        ctx.club.logo.save("logo.png", ContentFile(png_bytes()), save=True)
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        assert "/Subtype /Image" in pdf_text(payment)

    def test_logo_illisible_ne_bloque_jamais(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        ctx.club.logo.save("logo.png", ContentFile(b"pas une image"), save=True)
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        assert payment.receipt_file

    def test_aucune_mention_editeur_vesta_cdc_ni_solde(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        text = pdf_text(payment)
        for forbidden in ("IMARA", "Vesta", "VESTA", "CDC", "Solde", "solde", "En ordre", "dette"):
            assert forbidden not in text, forbidden

    def test_aucune_donnee_d_un_autre_joueur(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        other = named_member(ctx, first_name="Autre", last_name="Voisin")
        record_committed(ctx, other, ctype, django_capture_on_commit_callbacks, reference="MM-VOISIN")
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks, reference="MM-PAYEUR")
        text = pdf_text(payment)
        assert "Voisin" not in text and "MM-VOISIN" not in text
        # Ni le Trésorier qui a validé (aucun nom de tiers sur le reçu).
        assert ctx.treasurer.user.last_name not in text
        assert payer.user.email not in text


# ---------------------------------------------------------------------------
# Stockage privé
# ---------------------------------------------------------------------------


class TestStockagePrive:
    def test_recu_dans_private_media_root_sans_url_publique(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)

        stored = Path(payment.receipt_file.path).resolve()
        private_root = Path(django_settings.PRIVATE_MEDIA_ROOT).resolve()
        public_root = Path(django_settings.MEDIA_ROOT).resolve()
        assert stored.is_file()
        assert private_root in stored.parents
        assert not (public_root / payment.receipt_file.name).exists()
        with pytest.raises(ValueError):
            payment.receipt_file.url  # noqa: B018 -- jamais d'URL publique

    def test_nom_de_fichier_sans_donnee_personnelle(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        name = Path(payment.receipt_file.name).name.lower()
        assert "payeur" not in name and "recu-" in name and name.endswith(".pdf")


# ---------------------------------------------------------------------------
# Idempotence, immuabilité, annulation
# ---------------------------------------------------------------------------


class TestIdempotenceEtImmuabilite:
    def test_jamais_deux_recus(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        first_name = payment.receipt_file.name
        first_issued = payment.receipt_issued_at

        again = services.issue_payment_receipt(payment=payment)
        again.refresh_from_db()

        assert again.receipt_file.name == first_name
        assert again.receipt_issued_at == first_issued
        assert receipt_logs(payment).count() == 1
        receipts_dir = Path(payment.receipt_file.path).parent
        assert len(list(receipts_dir.glob("*.pdf"))) == 1

    def test_recu_emis_ni_remplacable_ni_supprimable(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        original = payment.receipt_file.name

        payment.receipt_file = "treasury/payments/receipts/autre.pdf"
        with pytest.raises(LedgerImmutableError):
            payment.save()
        payment.refresh_from_db()
        payment.receipt_file = None
        with pytest.raises(LedgerImmutableError):
            payment.save()
        payment.refresh_from_db()
        payment.receipt_issued_at = None
        with pytest.raises(LedgerImmutableError):
            payment.save()
        assert Payment.all_objects.get(pk=payment.pk).receipt_file.name == original

    def test_annulation_conserve_le_recu_d_origine(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        original = payment.receipt_file.name
        content = Path(payment.receipt_file.path).read_bytes()

        with django_capture_on_commit_callbacks(execute=True):
            reversal = services.request_payment_reversal(
                payment=payment, reason="Saisie en double", requested_by=ctx.treasurer.user
            )
            services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)

        payment.refresh_from_db()
        assert payment.receipt_file.name == original
        assert Path(payment.receipt_file.path).read_bytes() == content
        assert receipt_logs(payment).count() == 1
        assert services.issue_payment_receipt(payment=payment).receipt_file.name == original


# ---------------------------------------------------------------------------
# Journal d'activité
# ---------------------------------------------------------------------------


class TestJournal:
    def test_emission_journalisee_sans_contenu_du_document(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)

        log = receipt_logs(payment).get()
        assert log.club_id == ctx.club.pk
        assert log.actor_id == ctx.treasurer.user_id
        assert log.before == {"receipt_available": False}
        assert log.after["receipt_number"] == 1
        assert log.after["receipt_available"] is True
        assert PIN not in str(log.after)

    def test_cron_sans_acteur_utilise_l_acteur_systeme(self, ctx, ctype, payer):
        payment = record(ctx, payer, ctype)
        payment.validated_by = None
        payment.submitted_by = None  # en mémoire seulement : aucun auteur ni valideur

        services._log_receipt_issued(payment, club=ctx.club, actor=None, issued_at=payment.submitted_at)

        log = receipt_logs(payment).get()
        assert log.actor.email == services.SYSTEM_ACTOR_EMAIL
        assert log.actor.is_active is False and log.actor.is_superuser is False
        assert not log.actor.has_usable_password()
        # Réutilisé, jamais dupliqué.
        assert services.get_system_actor().pk == log.actor_id

    def test_acteur_systeme_detourne_est_refuse(self, ctx):
        from apps.accounts.tests.factories import UserFactory
        from apps.clubs.tests.factories import MembershipFactory

        # Compte actif avec mot de passe utilisable : refusé.
        taken = UserFactory(email=services.SYSTEM_ACTOR_EMAIL)
        with pytest.raises(services.SystemActorCompromisedError):
            services.get_system_actor()
        taken.delete()

        # Compte inerte mais avec une adhésion : refusé.
        inert = services.get_system_actor()
        MembershipFactory(user=inert)
        with pytest.raises(services.SystemActorCompromisedError):
            services.get_system_actor()

    def test_acteur_systeme_libelle_distinct_du_ghost_mode(self):
        actor = services.get_system_actor()
        assert f"{actor.first_name} {actor.last_name}".strip() == "Système"

    def test_recu_non_emis_et_fichier_supprime_quand_le_journal_echoue(self, ctx, ctype, payer):
        payment = record(ctx, payer, ctype)  # sans reçu

        with patch("apps.treasury.services.log_action", side_effect=RuntimeError("journal indisponible")):
            with pytest.raises(services.ReceiptJournalError):
                services.issue_payment_receipt(payment=payment)

        payment.refresh_from_db()
        assert not payment.receipt_file
        assert payment.receipt_issued_at is None
        assert not receipt_logs(payment).exists()
        assert not list(Path(django_settings.PRIVATE_MEDIA_ROOT).rglob("recu-*.pdf"))
        # Le paiement reste validé et figure parmi les reçus à rattraper.
        assert payment.transaction.status == "succeeded"
        assert list(services.payments_missing_receipt(ctx.club)) == [payment]

    def test_journal_en_echec_puis_rattrapage_par_la_commande(self, ctx, ctype, payer):
        payment = record(ctx, payer, ctype)

        with patch("apps.treasury.services.log_action", side_effect=RuntimeError("journal indisponible")):
            err = io.StringIO()
            with pytest.raises(CommandError):
                call_command("issue_missing_payment_receipts", stdout=io.StringIO(), stderr=err)
        assert "non émis" in err.getvalue()
        payment.refresh_from_db()
        assert not payment.receipt_file

        call_command("issue_missing_payment_receipts", stdout=io.StringIO())
        payment.refresh_from_db()
        assert payment.receipt_file
        assert receipt_logs(payment).count() == 1
        assert len(list(Path(django_settings.PRIVATE_MEDIA_ROOT).rglob("recu-*.pdf"))) == 1

    def test_journal_en_echec_apres_validation_le_paiement_reste_valide(
        self, ctx, ctype, payer, django_capture_on_commit_callbacks
    ):
        # Émission post-validation (on_commit) : l'échec du journal du reçu ne
        # remonte jamais vers la validation, déjà enregistrée.
        real_log_action = services.log_action

        def failing_for_receipts(**kwargs):
            if kwargs.get("action_type") == RECEIPT_ACTION:
                raise RuntimeError("journal indisponible")
            return real_log_action(**kwargs)

        with patch("apps.treasury.services.log_action", side_effect=failing_for_receipts):
            payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)

        assert payment.transaction.status == "succeeded"
        assert not payment.receipt_file
        assert not list(Path(django_settings.PRIVATE_MEDIA_ROOT).rglob("recu-*.pdf"))


# ---------------------------------------------------------------------------
# Échec de génération et rattrapage
# ---------------------------------------------------------------------------


class TestEchecEtRattrapage:
    def test_echec_de_generation_ne_bloque_pas_la_validation(self, ctx, ctype, payer, django_capture_on_commit_callbacks):
        with patch("apps.treasury.services._build_payment_receipt_pdf", side_effect=OSError("disque plein")):
            payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)

        assert payment.transaction.status == "succeeded"
        assert payment.receipt_number == 1
        assert not payment.receipt_file
        assert not receipt_logs(payment).exists()
        assert not list(Path(django_settings.PRIVATE_MEDIA_ROOT).rglob("recu-*.pdf"))

    def test_commande_de_rattrapage(self, ctx, other_ctx, ctype, payer):
        missing = record(ctx, payer, ctype)  # on_commit non exécuté : pas de reçu
        other_missing = record(other_ctx, other_ctx.player, monthly_type(other_ctx), method="cash", reference="")

        out = io.StringIO()
        call_command("issue_missing_payment_receipts", "--club", str(ctx.club.pk), stdout=out)

        missing.refresh_from_db()
        other_missing.refresh_from_db()
        assert missing.receipt_file
        assert not other_missing.receipt_file  # --club limite au club demandé
        assert "1 reçu(s) émis" in out.getvalue()

        out = io.StringIO()
        call_command("issue_missing_payment_receipts", stdout=out)
        other_missing.refresh_from_db()
        assert other_missing.receipt_file
        assert receipt_logs(missing).count() == 1  # pas de second reçu

    def test_rattrapage_dry_run_n_ecrit_rien(self, ctx, ctype, payer):
        missing = record(ctx, payer, ctype)
        out = io.StringIO()
        call_command("issue_missing_payment_receipts", "--dry-run", stdout=out)
        missing.refresh_from_db()
        assert not missing.receipt_file
        assert not list(Path(django_settings.PRIVATE_MEDIA_ROOT).rglob("recu-*.pdf"))
        assert "1 reçu(s)" in out.getvalue()

    def test_rattrapage_ignore_un_paiement_annule_sans_recu(self, ctx, ctype, payer):
        payment = record(ctx, payer, ctype)  # sans reçu
        reversal = services.request_payment_reversal(
            payment=payment, reason="Saisie en double", requested_by=ctx.treasurer.user
        )
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)

        with pytest.raises(services.TreasuryValidationError, match="annulé"):
            services.issue_payment_receipt(payment=payment)
        call_command("issue_missing_payment_receipts", stdout=io.StringIO())
        payment.refresh_from_db()
        assert not payment.receipt_file

    def test_import_csv_recus_emis_par_la_commande_pas_pendant_l_import(self, ctx, django_capture_on_commit_callbacks):
        from apps.treasury.tests.grid_helpers import NOW, YEAR, attach, attached_type, csv_file, csv_line, player

        imported_type = attached_type(ctx)
        member = player(ctx, "Adolphe", "Akeba", email="adolphe.akeba@example.com")
        attach(ctx, member, imported_type)
        with django_capture_on_commit_callbacks(execute=True):
            services.import_contributions(
                contribution_type=imported_type,
                year=YEAR,
                csv_file=csv_file([csv_line("Adolphe Akeba", "60", "", "", "", "", "", "", "10")]),
                imported_by=ctx.treasurer.user,
                now=NOW,
            )
        imported = list(Payment.all_objects.filter(membership=member))
        assert len(imported) == 2
        assert all(p.receipt_number and not p.receipt_file for p in imported)

        call_command("issue_missing_payment_receipts", stdout=io.StringIO())
        for payment in imported:
            payment.refresh_from_db()
            assert payment.receipt_file
            assert "Import historique" in pdf_text(payment)

    def test_rattrapage_club_inconnu(self, ctx):
        with pytest.raises(CommandError):
            call_command("issue_missing_payment_receipts", "--club", "999999", stdout=io.StringIO())


# ---------------------------------------------------------------------------
# Étanchéité entre clubs
# ---------------------------------------------------------------------------


class TestEtancheite:
    def test_service_refuse_un_paiement_d_un_autre_club_actif(self, ctx, other_ctx, ctype, payer):
        payment = record(ctx, payer, ctype)
        with active_club(other_ctx.club), pytest.raises(TenantMismatchError):
            services.issue_payment_receipt(payment=payment)
        payment.refresh_from_db()
        assert not payment.receipt_file

    def test_telechargement_reel_reserve_au_club_et_au_joueur(
        self, ctx, other_ctx, ctype, payer, django_capture_on_commit_callbacks
    ):
        payment = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        url = reverse("treasury:payment-receipt-download", args=[payment.pk])

        response = client_for(payer.user).get(url)
        assert response.status_code == status.HTTP_200_OK
        assert b"".join(response.streaming_content).startswith(b"%PDF")

        assert client_for(ctx.player.user).get(url).status_code == status.HTTP_404_NOT_FOUND
        assert client_for(other_ctx.president.user).get(url).status_code == status.HTTP_404_NOT_FOUND
        assert client_for(other_ctx.treasurer.user).get(url).status_code == status.HTTP_404_NOT_FOUND
        assert APIClient().get(url).status_code == status.HTTP_401_UNAUTHORIZED

    def test_numerotation_et_identite_propres_a_chaque_club(
        self, ctx, other_ctx, ctype, payer, django_capture_on_commit_callbacks
    ):
        mine = record_committed(ctx, payer, ctype, django_capture_on_commit_callbacks)
        theirs = record_committed(
            other_ctx, other_ctx.player, monthly_type(other_ctx), django_capture_on_commit_callbacks,
            method="cash", reference="",
        )
        assert (mine.receipt_number, theirs.receipt_number) == (1, 1)
        assert mine.receipt_file.name != theirs.receipt_file.name
        their_text = pdf_text(theirs)
        # Borne de fin de nom : « Club de test 1 » ne doit pas matcher « Club de test 13 ».
        assert re.search(re.escape(other_ctx.club.name) + r"(?!\d)", their_text)
        assert not re.search(re.escape(ctx.club.name) + r"(?!\d)", their_text)
        assert Decimal(theirs.amount) == Decimal("40.00")
