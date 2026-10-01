"""Tests HTTP des fichiers prives (CDC 6.7, 7.6 ; CLAUDE.md section 2 regle
n10 ; ecart bloquant B10 de la revue de fin de Lot 1).

Couvre :
- les trois vues de telechargement authentifiees (CSV source et rapport d'un
  lot d'import, fiche d'adhesion PDF) : permissions, etancheite entre clubs
  (404, jamais 403), fichier absent, non authentifie, licence suspendue ;
- la permission des lots d'import SELON LEUR TYPE (correction de faille,
  audit de securite + revue manuelle) : un lot de cotisations historiques
  (CDC 4.4.8, cree par `apps.treasury`) n'est telechargeable que par le
  Tresorier/adjoint, jamais par le recruteur designe ni le President seul ;
  un lot de joueurs (CDC 4.1) reste accessible au President/recruteur ;
- l'exposition, par les serializers, de l'URL authentifiee (jamais un chemin
  ``MEDIA_URL``) ;
- le refus, a l'upload, d'un CSV trop lourd ou deguise, d'un logo de club et
  d'une photo de profil trop lourds ou au mauvais format.
"""

from __future__ import annotations

import base64
import io

import pytest
from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import ImportBatch, Membership, MembershipApplication, MembershipRole
from apps.clubs.serializers import ImportBatchSerializer, MembershipApplicationSerializer
from apps.clubs.tests.factories import (
    ClubFactory,
    ClubSettingsFactory,
    ImportBatchFactory,
    MembershipApplicationFactory,
    MembershipFactory,
    MembershipRoleFactory,
)
from apps.licences.models import Licence
from apps.licences.tests.factories import LicenceFactory

pytestmark = pytest.mark.django_db

TEN_MEGABYTES = 10 * 1024 * 1024

SOURCE_CONTENT = b"email,prenom,nom\nrecrue1@example.com,Aline,Kabila\n"
REPORT_CONTENT = b"ligne,resultat,message\n2,created,Ligne 2 : joueur cree.\n"
PDF_CONTENT = b"%PDF-1.4\n%fiche d'adhesion de test\n%%EOF\n"

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _authenticated_client(user) -> APIClient:
    """Jeton d'acces reel : le club actif est resolu depuis l'adhesion reelle
    (CLAUDE.md regle n9), comme dans les autres tests HTTP de l'app."""

    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


def _member(club, *roles):
    membership = MembershipFactory(club=club)
    for role in roles:
        MembershipRoleFactory(membership=membership, role=role)
    return membership


def _body(response) -> bytes:
    return b"".join(response.streaming_content)


def _batch_with_files(
    club, *, source=SOURCE_CONTENT, report=REPORT_CONTENT, import_type=ImportBatch.ImportType.PLAYERS
) -> ImportBatch:
    batch = ImportBatchFactory(
        club=club, import_type=import_type, source_file=ContentFile(source, name="source.csv")
    )
    if report is not None:
        batch.report_file.save("rapport.csv", ContentFile(report), save=True)
    return batch


def _application_with_pdf(club, *, sponsor=None, membership=None, pdf=PDF_CONTENT) -> MembershipApplication:
    if membership is None:
        membership = MembershipFactory(club=club, sponsor=sponsor)
    application = MembershipApplicationFactory(membership=membership, club=club)
    if pdf is not None:
        application.application_pdf_file.save("fiche.pdf", ContentFile(pdf), save=True)
    return application


def _png_bytes(*, padding: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buffer, format="PNG")
    return buffer.getvalue() + b"\x00" * padding


def _gif_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("P", (4, 4), color=0).save(buffer, format="GIF")
    return buffer.getvalue()


def _first_error_text(response) -> str:
    """Aplatit le corps d'erreur (dict de listes ou ``detail``) en texte."""

    return str(response.data)


# ---------------------------------------------------------------------------
# 3. Telechargement du CSV source et du rapport
# ---------------------------------------------------------------------------


IMPORT_DOWNLOADS = [
    pytest.param("clubs:import-source-download", SOURCE_CONTENT, "import-{pk}-source.csv", id="source"),
    pytest.param("clubs:import-report-download", REPORT_CONTENT, "import-{pk}-rapport.csv", id="report"),
]


@pytest.mark.parametrize(("url_name", "expected_content", "expected_filename"), IMPORT_DOWNLOADS)
class TestImportBatchFileDownload:
    def test_president_downloads_the_exact_content_as_an_attachment(
        self, url_name, expected_content, expected_filename
    ):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        batch = _batch_with_files(club)

        response = _authenticated_client(president.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_200_OK
        assert _body(response) == expected_content
        disposition = response["Content-Disposition"]
        assert disposition.startswith("attachment")
        assert expected_filename.format(pk=batch.pk) in disposition

    def test_designated_recruiter_can_download(self, url_name, expected_content, expected_filename):
        club = ClubFactory()
        recruiter = _member(club, MembershipRole.Role.PLAYER_RECRUITER)
        batch = _batch_with_files(club)

        response = _authenticated_client(recruiter.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_200_OK
        assert _body(response) == expected_content

    def test_cumul_coach_and_recruiter_can_download(self, url_name, expected_content, expected_filename):
        club = ClubFactory()
        coach_recruiter = _member(club, MembershipRole.Role.COACH, MembershipRole.Role.PLAYER_RECRUITER)
        batch = _batch_with_files(club)

        response = _authenticated_client(coach_recruiter.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_200_OK

    def test_plain_active_member_is_forbidden(self, url_name, expected_content, expected_filename):
        club = ClubFactory()
        player = _member(club)
        batch = _batch_with_files(club)

        response = _authenticated_client(player.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize(
        "role",
        [MembershipRole.Role.COACH, MembershipRole.Role.TREASURER, MembershipRole.Role.VICE_PRESIDENT],
    )
    def test_board_and_staff_roles_without_recruiter_designation_are_forbidden(
        self, url_name, expected_content, expected_filename, role
    ):
        club = ClubFactory()
        holder = _member(club, role)
        batch = _batch_with_files(club)

        response = _authenticated_client(holder.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_batch_of_another_club_is_not_found_never_forbidden(
        self, url_name, expected_content, expected_filename
    ):
        club_a = ClubFactory()
        club_b = ClubFactory()
        president_a = _member(club_a, MembershipRole.Role.PRESIDENT)
        batch_b = _batch_with_files(club_b)

        response = _authenticated_client(president_a.user).get(reverse(url_name, kwargs={"pk": batch_b.pk}))

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert b"Kabila" not in response.content
        assert b"recrue1@example.com" not in response.content

    def test_recruiter_of_club_a_cannot_download_a_batch_of_club_b(
        self, url_name, expected_content, expected_filename
    ):
        club_a = ClubFactory()
        club_b = ClubFactory()
        recruiter_a = _member(club_a, MembershipRole.Role.PLAYER_RECRUITER)
        batch_b = _batch_with_files(club_b)

        response = _authenticated_client(recruiter_a.user).get(reverse(url_name, kwargs={"pk": batch_b.pk}))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_president_of_club_b_still_downloads_his_own_batch_while_club_a_has_one_too(
        self, url_name, expected_content, expected_filename
    ):
        """Etancheite dans les deux sens : chaque club ne voit que son lot."""

        club_a = ClubFactory()
        club_b = ClubFactory()
        president_a = _member(club_a, MembershipRole.Role.PRESIDENT)
        president_b = _member(club_b, MembershipRole.Role.PRESIDENT)
        batch_a = _batch_with_files(club_a, source=b"email,prenom,nom\na@a.com,A,A\n", report=b"ligne,resultat,message\nA\n")
        batch_b = _batch_with_files(club_b, source=b"email,prenom,nom\nb@b.com,B,B\n", report=b"ligne,resultat,message\nB\n")

        response_a = _authenticated_client(president_a.user).get(reverse(url_name, kwargs={"pk": batch_a.pk}))
        response_b = _authenticated_client(president_b.user).get(reverse(url_name, kwargs={"pk": batch_b.pk}))
        cross_a = _authenticated_client(president_a.user).get(reverse(url_name, kwargs={"pk": batch_b.pk}))
        cross_b = _authenticated_client(president_b.user).get(reverse(url_name, kwargs={"pk": batch_a.pk}))

        assert response_a.status_code == status.HTTP_200_OK
        assert response_b.status_code == status.HTTP_200_OK
        assert cross_a.status_code == status.HTTP_404_NOT_FOUND
        assert cross_b.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_batch_is_not_found(self, url_name, expected_content, expected_filename):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)

        response = _authenticated_client(president.user).get(reverse(url_name, kwargs={"pk": 999999}))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_request_is_rejected_with_401(self, url_name, expected_content, expected_filename):
        club = ClubFactory()
        batch = _batch_with_files(club)

        response = APIClient().get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_suspended_licence_blocks_the_download_even_for_the_president(
        self, url_name, expected_content, expected_filename
    ):
        club = ClubFactory()
        LicenceFactory(club=club, status=Licence.Status.SUSPENDED)
        president = _member(club, MembershipRole.Role.PRESIDENT)
        batch = _batch_with_files(club)

        response = _authenticated_client(president.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_who_must_still_change_password_is_forbidden(
        self, url_name, expected_content, expected_filename
    ):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        president.user.must_change_password = True
        president.user.save()
        batch = _batch_with_files(club)

        response = _authenticated_client(president.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_post_and_delete_are_not_allowed(self, url_name, expected_content, expected_filename):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        batch = _batch_with_files(club)
        client = _authenticated_client(president.user)
        url = reverse(url_name, kwargs={"pk": batch.pk})

        assert client.post(url, {}).status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert client.delete(url).status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert ImportBatch.all_objects.filter(pk=batch.pk).exists()


class TestImportBatchMissingFile:
    def test_batch_without_report_file_returns_404_on_report_download(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        batch = _batch_with_files(club, report=None)
        assert not batch.report_file

        response = _authenticated_client(president.user).get(
            reverse("clubs:import-report-download", kwargs={"pk": batch.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.data

    def test_batch_without_source_file_returns_404_on_source_download(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        batch = _batch_with_files(club, report=None)
        # `source_file` est obligatoire a la creation : on vide la colonne en
        # base sans passer par `save()` (cas d'un lot dont le fichier a ete
        # retire), pour exercer la branche « fichier absent » de la vue.
        ImportBatch.all_objects.filter(pk=batch.pk).update(source_file="")

        response = _authenticated_client(president.user).get(
            reverse("clubs:import-source-download", kwargs={"pk": batch.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.data

    def test_source_download_still_works_when_only_the_report_is_missing(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        batch = _batch_with_files(club, report=None)

        response = _authenticated_client(president.user).get(
            reverse("clubs:import-source-download", kwargs={"pk": batch.pk})
        )

        assert response.status_code == status.HTTP_200_OK
        assert _body(response) == SOURCE_CONTENT


# ---------------------------------------------------------------------------
# 3b. Lot d'import de cotisations historiques (CDC 4.4.8) : permission
# distincte du lot de joueurs -- correction de faille (audit de securite +
# revue manuelle). Un lot ``HISTORICAL_CONTRIBUTIONS`` contient les
# versements mensuels de TOUS les joueurs (cree par `apps.treasury`, jamais
# par `apps.clubs`) : il ne doit etre telechargeable que par le Tresorier ou
# son adjoint (matrice 2.4, ligne « Enregistrement des paiements »), jamais
# par le recruteur designe ni par le President seul (« L » sur cette ligne).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_name", "expected_content", "expected_filename"), IMPORT_DOWNLOADS)
class TestHistoricalContributionsImportBatchDownload:
    def test_treasurer_can_download(self, url_name, expected_content, expected_filename):
        club = ClubFactory()
        treasurer = _member(club, MembershipRole.Role.TREASURER)
        batch = _batch_with_files(club, import_type=ImportBatch.ImportType.HISTORICAL_CONTRIBUTIONS)

        response = _authenticated_client(treasurer.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_200_OK
        assert _body(response) == expected_content

    def test_assistant_treasurer_can_download(self, url_name, expected_content, expected_filename):
        club = ClubFactory()
        assistant = _member(club, MembershipRole.Role.ASSISTANT_TREASURER)
        batch = _batch_with_files(club, import_type=ImportBatch.ImportType.HISTORICAL_CONTRIBUTIONS)

        response = _authenticated_client(assistant.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_200_OK

    def test_designated_recruiter_cannot_download_a_contributions_batch(
        self, url_name, expected_content, expected_filename
    ):
        """La faille corrigee : un recruteur designe (« Ajout et import de
        joueurs ») n'a aucun acces a la tresorerie (matrice 2.4)."""

        club = ClubFactory()
        recruiter = _member(club, MembershipRole.Role.PLAYER_RECRUITER)
        batch = _batch_with_files(club, import_type=ImportBatch.ImportType.HISTORICAL_CONTRIBUTIONS)

        response = _authenticated_client(recruiter.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert b"Kabila" not in response.content
        assert b"created" not in response.content

    def test_president_alone_cannot_download_a_contributions_batch(
        self, url_name, expected_content, expected_filename
    ):
        """Le President n'a que « L » (lecture) sur la ligne « Enregistrement
        des paiements » de la matrice 2.4 -- pas d'ecriture ni de
        telechargement du lot source."""

        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        batch = _batch_with_files(club, import_type=ImportBatch.ImportType.HISTORICAL_CONTRIBUTIONS)

        response = _authenticated_client(president.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_plain_active_member_is_forbidden(self, url_name, expected_content, expected_filename):
        club = ClubFactory()
        player = _member(club)
        batch = _batch_with_files(club, import_type=ImportBatch.ImportType.HISTORICAL_CONTRIBUTIONS)

        response = _authenticated_client(player.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_batch_of_another_club_is_not_found_never_forbidden(
        self, url_name, expected_content, expected_filename
    ):
        club_a = ClubFactory()
        club_b = ClubFactory()
        treasurer_a = _member(club_a, MembershipRole.Role.TREASURER)
        batch_b = _batch_with_files(club_b, import_type=ImportBatch.ImportType.HISTORICAL_CONTRIBUTIONS)

        response = _authenticated_client(treasurer_a.user).get(reverse(url_name, kwargs={"pk": batch_b.pk}))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_recruiter_still_downloads_a_players_batch_non_regression(
        self, url_name, expected_content, expected_filename
    ):
        """Non-regression : un lot d'import de JOUEURS reste accessible au
        recruteur designe comme avant la correction."""

        club = ClubFactory()
        recruiter = _member(club, MembershipRole.Role.PLAYER_RECRUITER)
        batch = _batch_with_files(club, import_type=ImportBatch.ImportType.PLAYERS)

        response = _authenticated_client(recruiter.user).get(reverse(url_name, kwargs={"pk": batch.pk}))

        assert response.status_code == status.HTTP_200_OK
        assert _body(response) == expected_content


# ---------------------------------------------------------------------------
# 4. Telechargement de la fiche d'adhesion PDF
# ---------------------------------------------------------------------------


class TestMembershipApplicationPdfDownload:
    def _url(self, application) -> str:
        return reverse("clubs:application-pdf-download", kwargs={"pk": application.pk})

    def test_president_downloads_the_pdf(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        application = _application_with_pdf(club)

        response = _authenticated_client(president.user).get(self._url(application))

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"].startswith("attachment")
        assert _body(response) == PDF_CONTENT

    def test_concerned_member_downloads_his_own_pdf(self):
        club = ClubFactory()
        application = _application_with_pdf(club)

        response = _authenticated_client(application.membership.user).get(self._url(application))

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert _body(response) == PDF_CONTENT

    def test_sponsor_of_the_application_downloads_the_pdf(self):
        club = ClubFactory()
        sponsor = _member(club)
        application = _application_with_pdf(club, sponsor=sponsor)

        response = _authenticated_client(sponsor.user).get(self._url(application))

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert _body(response) == PDF_CONTENT

    def test_other_member_of_the_same_club_is_forbidden(self):
        club = ClubFactory()
        other_member = _member(club)
        application = _application_with_pdf(club)

        response = _authenticated_client(other_member.user).get(self._url(application))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert b"%PDF" not in response.content

    def test_sponsor_of_another_application_is_forbidden(self):
        club = ClubFactory()
        sponsor_of_other = _member(club)
        _application_with_pdf(club, sponsor=sponsor_of_other)
        application = _application_with_pdf(club, sponsor=_member(club))

        response = _authenticated_client(sponsor_of_other.user).get(self._url(application))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize(
        "role",
        [
            MembershipRole.Role.VICE_PRESIDENT,
            MembershipRole.Role.TREASURER,
            MembershipRole.Role.COACH,
            MembershipRole.Role.PLAYER_RECRUITER,
        ],
    )
    def test_other_functions_of_the_club_are_forbidden(self, role):
        """Seuls President, adherent concerne et parrain (aucune nouvelle
        matrice de permission) : ni le bureau, ni le Coach, ni le recruteur."""

        club = ClubFactory()
        holder = _member(club, role)
        application = _application_with_pdf(club)

        response = _authenticated_client(holder.user).get(self._url(application))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_application_of_another_club_is_not_found_never_forbidden(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        president_a = _member(club_a, MembershipRole.Role.PRESIDENT)
        application_b = _application_with_pdf(club_b)

        response = _authenticated_client(president_a.user).get(self._url(application_b))

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert b"%PDF" not in response.content

    def test_concerned_member_of_club_b_cannot_be_read_through_club_a_president(self):
        """Le President du club B n'a aucun droit sur un dossier du club A,
        meme si l'identifiant est devine."""

        club_a = ClubFactory()
        club_b = ClubFactory()
        president_b = _member(club_b, MembershipRole.Role.PRESIDENT)
        application_a = _application_with_pdf(club_a)

        response = _authenticated_client(president_b.user).get(self._url(application_a))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_sponsor_of_club_a_cannot_read_an_application_of_club_b(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        sponsor_a = _member(club_a)
        application_b = _application_with_pdf(club_b)

        response = _authenticated_client(sponsor_a.user).get(self._url(application_b))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_application_whose_pdf_is_not_generated_yet_is_not_found(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        application = _application_with_pdf(club, pdf=None)
        assert not application.application_pdf_file

        response = _authenticated_client(president.user).get(self._url(application))

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.data

    def test_forbidden_user_gets_403_before_learning_whether_the_pdf_exists(self):
        """Un membre non autorise recoit 403 que la fiche soit generee ou non :
        l'etat de generation n'est jamais revele a un tiers."""

        club = ClubFactory()
        other_member = _member(club)
        generated = _application_with_pdf(club)
        not_generated = _application_with_pdf(club, pdf=None)
        client = _authenticated_client(other_member.user)

        assert client.get(self._url(generated)).status_code == status.HTTP_403_FORBIDDEN
        assert client.get(self._url(not_generated)).status_code == status.HTTP_403_FORBIDDEN

    def test_unknown_application_is_not_found(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)

        response = _authenticated_client(president.user).get(
            reverse("clubs:application-pdf-download", kwargs={"pk": 999999})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_request_is_rejected_with_401(self):
        club = ClubFactory()
        application = _application_with_pdf(club)

        response = APIClient().get(self._url(application))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_suspended_licence_blocks_the_download(self):
        club = ClubFactory()
        LicenceFactory(club=club, status=Licence.Status.SUSPENDED)
        president = _member(club, MembershipRole.Role.PRESIDENT)
        application = _application_with_pdf(club)

        response = _authenticated_client(president.user).get(self._url(application))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_without_any_membership_is_forbidden(self):
        club = ClubFactory()
        application = _application_with_pdf(club)

        response = _authenticated_client(UserFactory()).get(self._url(application))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_still_pending_cannot_download_his_own_pdf_current_behaviour(self):
        """Comportement observe (pas une regle du CDC) : un adherent dont
        l'adhesion est encore « En attente » n'a pas d'adhesion ACTIVE, donc
        aucun club actif (``resolve_active_membership``) : la garde
        ``IsActiveClubMember`` le refuse avant meme le controle du dossier.
        Il ne peut telecharger sa fiche qu'une fois « Inscrit ». Point a
        confirmer avec le client (CDC 4.3)."""

        club = ClubFactory()
        pending = MembershipFactory(club=club, status=Membership.Status.PENDING, sponsor=_member(club))
        application = _application_with_pdf(club, membership=pending)

        response = _authenticated_client(pending.user).get(self._url(application))

        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# 5. Serializers : URL authentifiee, jamais MEDIA_URL
# ---------------------------------------------------------------------------


class TestSerializersExposeAuthenticatedUrls:
    def test_import_batch_serializer_exposes_authenticated_urls(self):
        club = ClubFactory()
        batch = _batch_with_files(club)

        data = ImportBatchSerializer(batch).data

        assert data["source_file_url"].endswith(f"/clubs/imports/{batch.pk}/source/")
        assert data["source_file_url"] == reverse("clubs:import-source-download", kwargs={"pk": batch.pk})
        assert data["report_file_url"].endswith(f"/clubs/imports/{batch.pk}/report/")
        assert data["report_file_url"] == reverse("clubs:import-report-download", kwargs={"pk": batch.pk})

    def test_import_batch_serializer_never_exposes_a_media_url_or_a_storage_path(self):
        club = ClubFactory()
        batch = _batch_with_files(club)

        data = ImportBatchSerializer(batch).data

        for key in ("source_file_url", "report_file_url"):
            assert not data[key].startswith(django_settings.MEDIA_URL)
            assert ".csv" not in data[key]
            assert str(django_settings.PRIVATE_MEDIA_ROOT) not in data[key]
        assert "source_file" not in data
        assert "report_file" not in data

    def test_import_batch_serializer_returns_none_when_a_file_is_missing(self):
        club = ClubFactory()
        batch = _batch_with_files(club, report=None)

        data = ImportBatchSerializer(batch).data

        assert data["source_file_url"] is not None
        assert data["report_file_url"] is None

    def test_membership_application_serializer_exposes_the_authenticated_url(self):
        club = ClubFactory()
        application = _application_with_pdf(club)

        data = MembershipApplicationSerializer(application).data

        assert data["application_pdf_url"] == reverse("clubs:application-pdf-download", kwargs={"pk": application.pk})
        assert data["application_pdf_url"].endswith(f"/clubs/applications/{application.pk}/fiche-pdf/")
        assert not data["application_pdf_url"].startswith(django_settings.MEDIA_URL)
        assert ".pdf" not in data["application_pdf_url"].replace("/fiche-pdf/", "")
        assert "application_pdf_file" not in data

    def test_membership_application_serializer_returns_none_when_pdf_not_generated(self):
        club = ClubFactory()
        application = _application_with_pdf(club, pdf=None)

        assert MembershipApplicationSerializer(application).data["application_pdf_url"] is None

    def test_import_endpoint_returns_urls_that_the_president_can_then_download(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)
        upload = SimpleUploadedFile("import.csv", SOURCE_CONTENT, content_type="text/csv")

        response = client.post(reverse("clubs:players-import"), {"file": upload}, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED
        batch_id = response.data["id"]
        assert response.data["source_file_url"] == reverse("clubs:import-source-download", kwargs={"pk": batch_id})
        assert response.data["report_file_url"] == reverse("clubs:import-report-download", kwargs={"pk": batch_id})
        assert not response.data["source_file_url"].startswith(django_settings.MEDIA_URL)
        assert not response.data["report_file_url"].startswith(django_settings.MEDIA_URL)

        downloaded = client.get(response.data["source_file_url"])
        assert downloaded.status_code == status.HTTP_200_OK
        assert _body(downloaded) == SOURCE_CONTENT

    def test_serializing_a_private_file_never_calls_the_url_property(self):
        """Filet de securite : si un serializer appelait ``.url`` sur un champ
        prive, ``private_storage`` leverait ``ValueError`` -- les serializers
        livres n'y touchent donc jamais."""

        club = ClubFactory()
        batch = _batch_with_files(club)
        application = _application_with_pdf(club)

        ImportBatchSerializer(batch).data
        MembershipApplicationSerializer(application).data

        with pytest.raises(ValueError):
            _ = batch.source_file.url
        with pytest.raises(ValueError):
            _ = application.application_pdf_file.url


# ---------------------------------------------------------------------------
# 6. Uploads refuses : CSV d'import, logo de club, photo de profil
# ---------------------------------------------------------------------------


class TestImportUploadRejections:
    def _post(self, client, upload):
        return client.post(reverse("clubs:players-import"), {"file": upload}, format="multipart")

    def test_csv_over_ten_megabytes_is_rejected_with_a_french_400_and_no_batch(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        header = b"email,prenom,nom\n"
        content = header + b"a" * (TEN_MEGABYTES + 1 - len(header))
        assert len(content) == TEN_MEGABYTES + 1
        upload = SimpleUploadedFile("gros.csv", content, content_type="text/csv")

        response = self._post(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "10 Mo" in _first_error_text(response)
        assert not ImportBatch.all_objects.filter(club=club).exists()

    def test_csv_of_exactly_ten_megabytes_is_not_rejected_for_its_size(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        content = b"email,prenom,nom\nrecrue@example.com,Aline,Kabila\n"
        content += b"\n" * (TEN_MEGABYTES - len(content))  # lignes vides : ignorees par l'import
        assert len(content) == TEN_MEGABYTES
        upload = SimpleUploadedFile("limite.csv", content, content_type="text/csv")

        response = self._post(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_201_CREATED

    def test_png_disguised_as_csv_is_rejected_with_a_french_400_and_no_batch(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        upload = SimpleUploadedFile("joueurs.csv", _png_bytes(), content_type="text/csv")

        response = self._post(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "CSV" in _first_error_text(response)
        assert "type reel incorrect" in _first_error_text(response)
        assert not ImportBatch.all_objects.filter(club=club).exists()

    @pytest.mark.parametrize(
        "content",
        [
            b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n",
            b"PK\x03\x04\x14\x00\x00\x00email,prenom,nom",
            b"MZ\x90\x00\x03\x00\x00\x00",
            b"\x7fELF\x02\x01\x01\x00",
            b"email,prenom,nom\nrecrue@example.com,Ali\x00ne,Kabila\n",
        ],
        ids=["pdf", "zip", "exe", "elf", "null_byte"],
    )
    def test_other_disguised_files_are_rejected_and_create_no_batch_and_no_player(self, content):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        upload = SimpleUploadedFile("joueurs.csv", content, content_type="text/csv")

        response = self._post(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not ImportBatch.all_objects.filter(club=club).exists()
        assert not Membership.all_objects.filter(club=club).exclude(pk=president.pk).exists()

    def test_empty_csv_is_rejected_with_a_french_400_and_no_batch(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        upload = SimpleUploadedFile("vide.csv", b"", content_type="text/csv")

        response = self._post(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not ImportBatch.all_objects.filter(club=club).exists()

    def test_text_without_csv_structure_is_rejected_and_no_batch_is_created(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        upload = SimpleUploadedFile(
            "notes.csv", b"Bonjour ceci est un texte sans delimiteur\nUne autre ligne\n", content_type="text/csv"
        )

        response = self._post(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "structure incorrecte" in _first_error_text(response)
        assert not ImportBatch.all_objects.filter(club=club).exists()

    def test_semicolon_csv_passes_the_upload_type_check(self):
        club = ClubFactory()
        president = _member(club, MembershipRole.Role.PRESIDENT)
        client = _authenticated_client(president.user)

        semicolon = SimpleUploadedFile("pv.csv", b"email;prenom;nom\nrecrue1@example.com;Aline;Kabila\n")
        response = self._post(client, semicolon)

        # Le controle de type accepte le point-virgule ; l'import lui-meme
        # (csv.DictReader, delimiteur virgule) est un autre sujet -- ici on
        # verifie seulement que le validateur d'upload ne refuse pas le fichier.
        assert response.status_code == status.HTTP_201_CREATED

    def test_unauthorised_member_gets_403_before_any_file_inspection(self):
        club = ClubFactory()
        player = _member(club)
        upload = SimpleUploadedFile("joueurs.csv", _png_bytes(), content_type="text/csv")

        response = self._post(_authenticated_client(player.user), upload)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not ImportBatch.all_objects.filter(club=club).exists()


class TestClubLogoUploadRejections:
    def _patch(self, client, upload):
        return client.patch(reverse("clubs:identity"), {"logo": upload}, format="multipart")

    def test_president_can_upload_a_valid_png_logo(self):
        club = ClubSettingsFactory().club
        president = _member(club, MembershipRole.Role.PRESIDENT)
        upload = SimpleUploadedFile("logo.png", _png_bytes(), content_type="image/png")

        response = self._patch(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_200_OK, response.data
        club.refresh_from_db()
        assert bool(club.logo)

    def test_logo_over_ten_megabytes_is_rejected_with_a_french_400(self):
        club = ClubSettingsFactory().club
        president = _member(club, MembershipRole.Role.PRESIDENT)
        upload = SimpleUploadedFile(
            "logo.png", _png_bytes(padding=TEN_MEGABYTES), content_type="image/png"
        )

        response = self._patch(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "10 Mo" in _first_error_text(response)
        club.refresh_from_db()
        assert not club.logo

    def test_gif_logo_is_rejected_with_a_french_400(self):
        club = ClubSettingsFactory().club
        president = _member(club, MembershipRole.Role.PRESIDENT)
        upload = SimpleUploadedFile("logo.gif", _gif_bytes(), content_type="image/gif")

        response = self._patch(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "JPEG, PNG ou WebP" in _first_error_text(response)
        club.refresh_from_db()
        assert not club.logo

    def test_gif_renamed_png_is_rejected_because_the_real_format_is_checked(self):
        club = ClubSettingsFactory().club
        president = _member(club, MembershipRole.Role.PRESIDENT)
        upload = SimpleUploadedFile("logo.png", _gif_bytes(), content_type="image/png")

        response = self._patch(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        club.refresh_from_db()
        assert not club.logo

    def test_non_image_content_is_rejected(self):
        club = ClubSettingsFactory().club
        president = _member(club, MembershipRole.Role.PRESIDENT)
        upload = SimpleUploadedFile("logo.png", b"ceci n'est pas une image", content_type="image/png")

        response = self._patch(_authenticated_client(president.user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        club.refresh_from_db()
        assert not club.logo

    def test_club_creation_wizard_accepts_a_valid_png_logo(self):
        """Meme chemin que le logo de l'assistant de creation (CDC 3.5, 6.7)."""

        from apps.accounts.tests.factories import TermsVersionFactory
        from apps.clubs.models import Club, ClubSettings

        terms_version = TermsVersionFactory()
        payload = {
            "idempotency_key": "logo-key-1",
            "name": "Club Logo",
            "city": "Kinshasa",
            "country": "RD Congo",
            "currency": ClubSettings.Currency.USD,
            "timezone_name": "Africa/Kinshasa",
            "email": "logo-fondateur@example.com",
            "first_name": "Jean",
            "last_name": "Fondateur",
            "position": Membership.Position.MIDFIELDER,
            "terms_version_id": terms_version.id,
            "accept_terms": True,
            "logo": SimpleUploadedFile("logo.png", _png_bytes(), content_type="image/png"),
        }

        response = APIClient().post(reverse("clubs:create"), payload, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED, getattr(response, "data", response.content)
        assert bool(Club.objects.get(name="Club Logo").logo)
        # URL absolue (bug remarques.md) : voir docstring
        # apps.accounts.views._serialize_club.
        assert response.data["club"]["logo"].startswith("http://testserver/media/")

    def test_model_full_clean_accepts_a_stored_png_logo(self):
        """``Club.save()`` appelle ``full_clean()`` : le validateur de modele
        doit accepter un logo PNG deja range dans le champ."""

        club = ClubSettingsFactory().club
        club.logo.save("logo.png", ContentFile(_png_bytes()), save=False)

        club.full_clean()  # ne doit pas lever


class TestUserPhotoModelValidation:
    def test_model_full_clean_accepts_a_stored_png_photo(self):
        user = UserFactory()
        user.photo.save("photo.png", ContentFile(_png_bytes()), save=False)

        user.full_clean()  # ne doit pas lever


class TestProfilePhotoUploadRejections:
    def _patch(self, client, upload):
        return client.patch(reverse("accounts:profile-photo"), {"photo": upload}, format="multipart")

    def test_valid_png_photo_is_accepted(self):
        user = UserFactory()
        upload = SimpleUploadedFile("photo.png", _TINY_PNG, content_type="image/png")

        response = self._patch(_authenticated_client(user), upload)

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert bool(user.photo)

    def test_photo_over_ten_megabytes_is_rejected_with_a_french_400(self):
        user = UserFactory()
        upload = SimpleUploadedFile(
            "photo.png", _png_bytes(padding=TEN_MEGABYTES), content_type="image/png"
        )

        response = self._patch(_authenticated_client(user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "10 Mo" in _first_error_text(response)
        user.refresh_from_db()
        assert not user.photo

    def test_gif_photo_is_rejected_with_a_french_400(self):
        user = UserFactory()
        upload = SimpleUploadedFile("photo.gif", _gif_bytes(), content_type="image/gif")

        response = self._patch(_authenticated_client(user), upload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "JPEG, PNG ou WebP" in _first_error_text(response)
        user.refresh_from_db()
        assert not user.photo

    def test_rejected_photo_keeps_the_previous_photo(self):
        user = UserFactory()
        client = _authenticated_client(user)
        assert self._patch(client, SimpleUploadedFile("ok.png", _TINY_PNG, content_type="image/png")).status_code == 200
        user.refresh_from_db()
        previous_name = user.photo.name

        response = self._patch(client, SimpleUploadedFile("mauvaise.gif", _gif_bytes(), content_type="image/gif"))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.photo.name == previous_name
