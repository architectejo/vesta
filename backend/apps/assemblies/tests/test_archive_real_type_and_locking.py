"""Archive des documents : type reel des fichiers (CDC 6.7, 7.6), garde-fou
contre toute suppression (CDC 4.15.1) et retraits/remplacements concurrents."""

from __future__ import annotations

import pytest
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.assemblies import services
from apps.assemblies.models import ArchivedDocument, ArchivedDocumentDeletionError
from apps.assemblies.tests.test_secretary_archive import (
    PDF_BYTES,
    R,
    _club,
    _client,
    _deposit,
    _member,
    _pdf,
    _payload,
)
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def _download(user, pk):
    return _client(user).get(reverse("assemblies:archive-file", kwargs={"pk": pk}))


class TestRealType:
    def test_pdf_sent_as_html_is_stored_with_real_extension_and_served_as_pdf(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        response = _deposit(secretary.user, file=_pdf("x.html"))
        assert response.status_code == 201, response.data
        document = ArchivedDocument.all_objects.get(pk=response.data["id"])
        assert document.file.name.endswith(".pdf")
        assert "x.html" not in document.file.name

        download = _download(secretary.user, document.pk)

        assert download.status_code == 200
        assert download["Content-Type"] == "application/pdf"
        assert download["X-Content-Type-Options"] == "nosniff"
        assert "archive-" in download["Content-Disposition"] and ".html" not in download["Content-Disposition"]

    def test_html_disguised_as_pdf_is_refused(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        fake = _pdf("x.html", b"%PDF-1.4\n<html><script>alert(1)</script></html>")
        response = _deposit(secretary.user, file=fake)
        assert response.status_code == 400
        assert ArchivedDocument.all_objects.count() == 0

    def test_legitimate_pdf_with_a_few_leading_bytes_is_accepted(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        response = _deposit(secretary.user, file=_pdf("a.pdf", b"\r\n" + PDF_BYTES))
        assert response.status_code == 201, response.data

    def test_content_that_is_not_pdf_or_image_is_never_served_as_html(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        document = ArchivedDocument.all_objects.get(pk=_deposit(secretary.user).data["id"])
        storage = document.file.storage
        storage.delete(document.file.name)
        storage.save(document.file.name, ContentFile(b"<html>x</html>"))

        download = _download(secretary.user, document.pk)

        assert download["Content-Type"] == "application/octet-stream"
        assert download["Content-Disposition"].endswith('.bin"')

    def test_other_club_cannot_download(self):
        secretary = _member(_club(), R.SECRETARY)
        pk = _deposit(secretary.user).data["id"]
        outsider = _member(_club(), R.SECRETARY)
        assert _download(outsider.user, pk).status_code == 404


class TestNeverDeleted:
    def test_bulk_delete_is_refused(self):
        club = _club()
        _deposit(_member(club, R.SECRETARY).user)
        with pytest.raises(ArchivedDocumentDeletionError), transaction.atomic():
            ArchivedDocument.all_objects.all().delete()
        assert ArchivedDocument.all_objects.count() == 1

    def test_club_cascade_is_refused(self):
        club = _club()
        _deposit(_member(club, R.SECRETARY).user)
        with pytest.raises(ArchivedDocumentDeletionError), transaction.atomic():
            club.delete()
        assert ArchivedDocument.all_objects.count() == 1


class TestConcurrentWithdrawAndReplace:
    def _document(self):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        pk = _deposit(secretary.user).data["id"]
        return secretary, ArchivedDocument.all_objects.get(pk=pk)

    def test_second_withdrawal_on_a_stale_instance_writes_no_second_journal_entry(self):
        secretary, document = self._document()
        stale = ArchivedDocument.all_objects.get(pk=document.pk)
        services.withdraw_archived_document(document=document, actor=secretary.user, reason="Erreur")
        with pytest.raises(services.AssemblyValidationError):
            services.withdraw_archived_document(document=stale, actor=secretary.user, reason="Erreur")
        assert AuditLog.objects.filter(action_type="assemblies.archived_document.withdrawn").count() == 1

    def test_second_replacement_on_a_stale_instance_is_a_clear_error_not_a_500(self):
        secretary, document = self._document()
        stale = ArchivedDocument.all_objects.get(pk=document.pk)
        kwargs = dict(actor=secretary.user, category="pv_reunion", title="Nouveau", document_date=document.document_date)
        services.replace_archived_document(document=document, file=_pdf("n1.pdf"), **kwargs)
        with pytest.raises(services.AssemblyValidationError) as excinfo:
            services.replace_archived_document(document=stale, file=_pdf("n2.pdf"), **kwargs)
        assert "déjà retiré" in str(excinfo.value)
        assert ArchivedDocument.all_objects.count() == 2


class TestArchiveAtomicWithJournal:
    def test_journal_failure_rolls_back_document_and_removes_file(self, monkeypatch):
        club = _club()
        secretary = _member(club, R.SECRETARY)
        saved_names = []
        real_create = services._create_archived_document

        def spy(**kwargs):
            document = real_create(**kwargs)
            saved_names.append(document.file.name)
            return document

        def boom(**kwargs):
            raise RuntimeError("journal indisponible")

        monkeypatch.setattr(services, "_create_archived_document", spy)
        monkeypatch.setattr(services, "log_action", boom)

        with pytest.raises(RuntimeError):
            services.archive_document(
                club=club,
                actor=secretary.user,
                category="pv_reunion",
                title="PV",
                document_date=timezone.localdate(),
                file=_pdf(),
            )

        assert ArchivedDocument.all_objects.count() == 0
        assert len(saved_names) == 1
        assert not ArchivedDocument._meta.get_field("file").storage.exists(saved_names[0])
