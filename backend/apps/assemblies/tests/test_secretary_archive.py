"""Role Secretaire et archive des documents (CDC 2.4, 4.15, 4.15.1, 4.16 ;
decision client du 11/10/2026, 10.3 n 169 et suivants).

Couvre : droits par role, etancheite entre clubs, depot/consultation/
telechargement/retrait/remplacement journalises, fichier prive, jamais de
suppression en dur, communiques et canal Bureau ouverts au Secretaire, AG
(convocation oui ; vote, pointage, signature du PV non).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.assemblies.models import ArchivedDocument, ArchivedDocumentDeletionError
from apps.assemblies.tests.factories import AgendaItemFactory, AssemblyFactory
from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory, MembershipRoleFactory

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _client(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _club():
    return ClubSettingsFactory(timezone="Africa/Kinshasa").club


def _member(club, role=None):
    membership = MembershipFactory(club=club)
    if role:
        extra = {"is_qualified_professional": True} if role == MembershipRole.Role.DOCTOR else {}
        MembershipRoleFactory(membership=membership, role=role, **extra)
    return membership


def _pdf(name="pv.pdf", content=PDF_BYTES):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def _payload(**overrides):
    data = {"category": "pv_reunion", "title": "PV du bureau de septembre", "document_date": "2026-09-30", "file": _pdf()}
    data.update(overrides)
    return data


def _deposit(user, **overrides):
    return _client(user).post(reverse("assemblies:archive-list"), _payload(**overrides), format="multipart")


R = MembershipRole.Role


class TestArchiveWritePermissions:
    @pytest.mark.parametrize("role", [R.SECRETARY, R.PRESIDENT, R.VICE_PRESIDENT])
    def test_writers_can_deposit(self, role):
        club = _club()
        member = _member(club, role)
        response = _deposit(member.user)
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert set(response.data) == {
            "id", "category", "category_label", "title", "document_date", "status", "status_label",
            "uploaded_by_name", "uploaded_at", "withdrawn_by_name", "withdrawn_at", "withdrawn_reason",
            "replaces_id", "replaced_by_id", "file_name", "file_size", "download_url",
        }
        assert response.data["status"] == "active"
        assert response.data["category_label"] == "PV de réunion"

    @pytest.mark.parametrize(
        "role", [None, R.TREASURER, R.SPORTS_DIRECTOR, R.STEWARD, R.ASSISTANT_TREASURER, R.COACH, R.DOCTOR, R.CAPTAIN]
    )
    def test_others_cannot_deposit(self, role):
        club = _club()
        member = _member(club, role)
        assert _deposit(member.user).status_code == status.HTTP_403_FORBIDDEN
        assert ArchivedDocument.all_objects.count() == 0

    def test_a_board_reader_who_is_not_a_writer_cannot_withdraw_or_replace(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        treasurer = _member(club, R.TREASURER)
        pk = _deposit(secretary.user).data["id"]
        client = _client(treasurer.user)
        assert client.post(reverse("assemblies:archive-withdraw", kwargs={"pk": pk}), {"reason": "x"}).status_code == 403
        assert (
            client.post(reverse("assemblies:archive-replace", kwargs={"pk": pk}), _payload(), format="multipart").status_code
            == 403
        )


class TestArchiveReadPermissionsAndFilters:
    @pytest.mark.parametrize(
        "role",
        [R.PRESIDENT, R.VICE_PRESIDENT, R.SPORTS_DIRECTOR, R.TREASURER, R.ASSISTANT_TREASURER, R.STEWARD, R.SECRETARY],
    )
    def test_board_can_read(self, role):
        club = _club()
        reader = _member(club, role)
        # Un seul titulaire par role : le lecteur depose lui-meme s'il peut,
        # sinon le Secretaire du club depose.
        depositor = reader if role in (R.PRESIDENT, R.VICE_PRESIDENT, R.SECRETARY) else _member(club, R.SECRETARY)
        _deposit(depositor.user)
        response = _client(reader.user).get(reverse("assemblies:archive-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert set(response.data) == {"results", "count", "next_offset"}

    @pytest.mark.parametrize("role", [None, R.COACH, R.DOCTOR, R.CAPTAIN, R.PLAYER_RECRUITER])
    def test_non_board_cannot_read_list_detail_or_file(self, role):
        club = _club()
        pk = _deposit(_member(club, R.SECRETARY).user).data["id"]
        client = _client(_member(club, role).user)
        assert client.get(reverse("assemblies:archive-list")).status_code == 403
        assert client.get(reverse("assemblies:archive-detail", kwargs={"pk": pk})).status_code == 403
        assert client.get(reverse("assemblies:archive-file", kwargs={"pk": pk})).status_code == 403

    def test_anonymous_is_refused(self):
        assert APIClient().get(reverse("assemblies:archive-list")).status_code == 401

    def test_filters_by_category_year_and_pagination(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        _deposit(secretary.user, category="pv_reunion", document_date="2025-03-01", title="A")
        _deposit(secretary.user, category="convocation", document_date="2026-03-01", title="B")
        _deposit(secretary.user, category="convocation", document_date="2026-04-01", title="C")
        client = _client(secretary.user)
        url = reverse("assemblies:archive-list")

        assert client.get(url, {"category": "convocation"}).data["count"] == 2
        assert client.get(url, {"year": "2025"}).data["count"] == 1
        assert client.get(url, {"category": "convocation", "year": "2026"}).data["count"] == 2
        page = client.get(url, {"limit": 2}).data
        assert [row["title"] for row in page["results"]] == ["C", "B"]
        assert page["next_offset"] == 2
        assert client.get(url, {"category": "inconnue"}).status_code == 400
        assert client.get(url, {"year": "20x6"}).status_code == 400


class TestArchiveIsolationBetweenClubs:
    def test_secretary_of_another_club_sees_and_downloads_nothing(self):
        club_a, club_b = _club(), _club()
        pk = _deposit(_member(club_a, R.SECRETARY).user).data["id"]
        other = _client(_member(club_b, R.SECRETARY).user)

        assert other.get(reverse("assemblies:archive-list")).data["count"] == 0
        assert other.get(reverse("assemblies:archive-detail", kwargs={"pk": pk})).status_code == 404
        assert other.get(reverse("assemblies:archive-file", kwargs={"pk": pk})).status_code == 404
        assert other.post(reverse("assemblies:archive-withdraw", kwargs={"pk": pk}), {"reason": "x"}).status_code == 404
        assert (
            other.post(reverse("assemblies:archive-replace", kwargs={"pk": pk}), _payload(), format="multipart").status_code
            == 404
        )
        assert ArchivedDocument.all_objects.get(pk=pk).status == "active"

    def test_deposit_is_attached_to_the_actors_club(self):
        club_a, club_b = _club(), _club()
        _deposit(_member(club_a, R.SECRETARY).user)
        assert ArchivedDocument.all_objects.filter(club=club_a).count() == 1
        assert ArchivedDocument.all_objects.filter(club=club_b).count() == 0


class TestArchiveFilesAndAudit:
    def test_download_is_authenticated_private_and_audited(self, settings):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        data = _deposit(secretary.user).data
        assert data["download_url"].endswith(f"/documents/{data['id']}/file/")

        response = _client(secretary.user).get(data["download_url"])

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == PDF_BYTES
        assert "attachment" in response["Content-Disposition"]
        assert "Content-Disposition" in response and ".pdf" in response["Content-Disposition"]
        document = ArchivedDocument.all_objects.get(pk=data["id"])
        assert document.file.path.startswith(str(settings.PRIVATE_MEDIA_ROOT))  # stockage prive
        actions = set(AuditLog.objects.filter(object_type="ArchivedDocument").values_list("action_type", flat=True))
        assert {"assemblies.archived_document.created", "assemblies.archived_document.downloaded"} <= actions

    def test_detail_is_audited(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        pk = _deposit(secretary.user).data["id"]
        _client(secretary.user).get(reverse("assemblies:archive-detail", kwargs={"pk": pk}))
        assert AuditLog.objects.filter(action_type="assemblies.archived_document.viewed", object_id=str(pk)).exists()

    def test_executable_disguised_as_pdf_is_refused(self):
        club = _club()
        response = _deposit(_member(club, R.SECRETARY).user, file=_pdf("faux.pdf", b"MZ\x90\x00 not a pdf"))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ArchivedDocument.all_objects.count() == 0

    def test_oversized_file_is_refused(self):
        club = _club()
        big = _pdf("gros.pdf", PDF_BYTES + b"0" * (10 * 1024 * 1024 + 1))
        assert _deposit(_member(club, R.SECRETARY).user, file=big).status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_title_or_invalid_category_is_refused(self):
        secretary = _member(_club(), R.SECRETARY)
        assert _deposit(secretary.user, title="").status_code == 400
        assert _deposit(secretary.user, category="secret").status_code == 400


class TestWithdrawAndReplace:
    def test_withdraw_requires_a_reason_keeps_the_file_and_is_audited(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        pk = _deposit(secretary.user).data["id"]
        client = _client(secretary.user)
        url = reverse("assemblies:archive-withdraw", kwargs={"pk": pk})

        assert client.post(url, {}).status_code == 400
        response = client.post(url, {"reason": "Document erroné"})

        assert response.status_code == 200
        assert response.data["status"] == "withdrawn"
        assert response.data["withdrawn_reason"] == "Document erroné"
        document = ArchivedDocument.all_objects.get(pk=pk)
        assert document.file.storage.exists(document.file.name)
        assert AuditLog.objects.filter(action_type="assemblies.archived_document.withdrawn", object_id=str(pk)).exists()
        assert client.post(url, {"reason": "encore"}).status_code == 400
        # Masque par defaut de la liste, visible avec include_withdrawn.
        assert client.get(reverse("assemblies:archive-list")).data["count"] == 0
        assert client.get(reverse("assemblies:archive-list"), {"include_withdrawn": "1"}).data["count"] == 1

    def test_replace_keeps_the_old_document_as_withdrawn_and_links_both(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        old_id = _deposit(secretary.user).data["id"]
        client = _client(secretary.user)

        response = client.post(
            reverse("assemblies:archive-replace", kwargs={"pk": old_id}),
            _payload(title="PV corrigé", file=_pdf("v2.pdf")),
            format="multipart",
        )

        assert response.status_code == 201, response.data
        assert response.data["replaces_id"] == old_id
        old = ArchivedDocument.all_objects.get(pk=old_id)
        assert old.status == "withdrawn"
        assert old.file.storage.exists(old.file.name)
        detail = client.get(reverse("assemblies:archive-detail", kwargs={"pk": old_id})).data
        assert detail["replaced_by_id"] == response.data["id"]
        assert AuditLog.objects.filter(action_type="assemblies.archived_document.replaced", object_id=str(old_id)).exists()
        # Un document retire ne peut plus etre remplace.
        again = client.post(
            reverse("assemblies:archive-replace", kwargs={"pk": old_id}), _payload(), format="multipart"
        )
        assert again.status_code == 400

    def test_a_document_is_never_deleted_in_hard(self):
        club = _club()
        pk = _deposit(_member(club, R.SECRETARY).user).data["id"]
        with pytest.raises(ArchivedDocumentDeletionError):
            ArchivedDocument.all_objects.get(pk=pk).delete()
        assert _client(_member(club, R.PRESIDENT).user).delete(
            reverse("assemblies:archive-detail", kwargs={"pk": pk})
        ).status_code == 405


class TestSecretaryAssemblyRights:
    def _convene_payload(self):
        return {
            "assembly_type": "ordinary",
            "scheduled_date": str((timezone.now() + timedelta(days=5)).date()),
            "scheduled_time": "18:00:00",
            "location": "Terrain",
            "agenda_items": [{"title": "Bilan"}],
        }

    def test_secretary_convenes_and_all_players_are_notified(self):
        from apps.notifications.models import Notification

        club = _club()
        secretary = _member(club, R.SECRETARY)
        player = _member(club)

        response = _client(secretary.user).post(
            reverse("assemblies:assembly-list"), self._convene_payload(), format="json"
        )

        assert response.status_code == 201, response.data
        assert response.data["can_convene"] is True
        assert response.data["can_manage"] is False
        assert Notification.objects.filter(recipient=player.user, event_type="assembly_convened").exists()

    def test_plain_player_cannot_convene_and_has_no_convene_right(self):
        club = _club()
        player = _member(club)
        assert (
            _client(player.user).post(reverse("assemblies:assembly-list"), self._convene_payload(), format="json").status_code
            == 403
        )

    def test_secretary_cannot_attend_vote_draft_sign_or_set_quorum(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        member = _member(club)
        assembly = AssemblyFactory(club=club, scheduled_date=timezone.now().date())
        item = AgendaItemFactory(assembly=assembly)
        client = _client(secretary.user)

        assert (
            client.post(
                reverse("assemblies:assembly-attendance", kwargs={"pk": assembly.pk}),
                {"membership_id": member.id},
                format="json",
            ).status_code
            == 403
        )
        assert (
            client.put(
                reverse("assemblies:assembly-decision", kwargs={"pk": assembly.pk, "agenda_item_id": item.pk}),
                {"votes_for": 1, "votes_against": 0, "votes_abstain": 0, "outcome": "ok"},
                format="json",
            ).status_code
            == 403
        )
        assert (
            client.put(
                reverse("assemblies:assembly-minutes", kwargs={"pk": assembly.pk}), {"content": "x"}, format="json"
            ).status_code
            == 403
        )
        sign = client.post(
            reverse("assemblies:assembly-minutes-sign", kwargs={"pk": assembly.pk}), {}, format="json"
        )
        assert sign.status_code == 403
        assert (
            client.put(reverse("assemblies:quorum-threshold"), {"percentage": "60"}, format="json").status_code == 403
        )

    def test_detail_exposes_no_signature_right_to_the_secretary(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        assembly = AssemblyFactory(club=club)
        data = _client(secretary.user).get(reverse("assemblies:assembly-detail", kwargs={"pk": assembly.pk})).data
        assert data["can_sign_president"] is False
        assert data["can_sign_vice_president"] is False
        assert data["can_manage"] is False
        assert data["can_convene"] is True

    def test_another_clubs_secretary_cannot_see_the_assembly(self):
        club_a, club_b = _club(), _club()
        secretary_a = _member(club_a, R.SECRETARY)
        assembly_b = AssemblyFactory(club=club_b)
        response = _client(secretary_a.user).get(reverse("assemblies:assembly-detail", kwargs={"pk": assembly_b.pk}))
        assert response.status_code == 404


class TestSecretaryAnnouncementsAndBoardChat:
    def test_secretary_publishes_an_announcement_and_reads_receipts(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        client = _client(secretary.user)

        publish = client.post(
            reverse("social:announcement-list"), {"title": "Titre", "body": "Corps"}, format="multipart"
        )
        assert publish.status_code == 201, publish.data
        receipts = client.get(reverse("social:announcement-read-receipts", kwargs={"pk": publish.data["id"]}))
        assert receipts.status_code == 200

    def test_announcement_publication_still_open_to_president_and_vp_and_closed_to_players(self):
        club = _club()
        for role, expected in ((R.PRESIDENT, 201), (R.VICE_PRESIDENT, 201), (None, 403), (R.TREASURER, 403)):
            member = _member(club, role)
            response = _client(member.user).post(
                reverse("social:announcement-list"), {"title": "T", "body": "C"}, format="multipart"
            )
            assert response.status_code == expected, role

    def test_another_clubs_secretary_cannot_read_receipts(self):
        from apps.social.tests.factories import AnnouncementFactory

        club_a, club_b = _club(), _club()
        announcement = AnnouncementFactory(club=club_a)
        secretary_b = _member(club_b, R.SECRETARY)
        response = _client(secretary_b.user).get(
            reverse("social:announcement-read-receipts", kwargs={"pk": announcement.pk})
        )
        assert response.status_code in (403, 404)

    def test_secretary_is_in_the_board_channel(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        client = _client(secretary.user)
        channels = client.get(reverse("social:chat-channel-list")).data["results"]
        assert {c["channel_type"] for c in channels} == {"general", "board"}
        board_id = next(c["id"] for c in channels if c["channel_type"] == "board")
        send = client.post(reverse("social:chat-message-list", kwargs={"pk": board_id}), {"body": "Salut"}, format="json")
        assert send.status_code == 201

    def test_a_secretary_of_club_a_cannot_post_in_club_b_board_channel(self):
        club_a, club_b = _club(), _club()
        president_b = _member(club_b, R.PRESIDENT)
        channels = _client(president_b.user).get(reverse("social:chat-channel-list")).data["results"]
        board_b = next(c["id"] for c in channels if c["channel_type"] == "board")
        secretary_a = _member(club_a, R.SECRETARY)
        response = _client(secretary_a.user).post(
            reverse("social:chat-message-list", kwargs={"pk": board_b}), {"body": "Intrus"}, format="json"
        )
        assert response.status_code == 404
