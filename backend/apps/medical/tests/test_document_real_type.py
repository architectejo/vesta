"""Type reel des documents medicaux : nom de stockage et telechargement
fondes sur le contenu, jamais sur le nom saisi par le client (CDC 6.7, 7.6)."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.medical import services
from apps.medical.models import MedicalDocument
from apps.medical.tests.conftest import client_for

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def _attach(ctx, name, content):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
    return services.attach_document(
        actor=ctx.doctor.user,
        file=SimpleUploadedFile(name, content, content_type="text/html"),
        original_filename=name,
        injury=injury,
    )


def test_real_pdf_named_html_is_stored_as_pdf_and_served_as_pdf(ctx):
    document = _attach(ctx, "x.html", PDF)
    assert document.file.name.endswith(".pdf")
    assert "x.html" not in document.file.name

    response = client_for(ctx.doctor.user).get(reverse("medical:document-download", args=[document.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Disposition"].startswith("attachment")
    assert ".html" not in response["Content-Disposition"]


def test_html_disguised_as_pdf_is_refused_at_upload(ctx):
    with pytest.raises(Exception):
        _attach(ctx, "x.html", b"%PDF-1.4\n<html><script>alert(1)</script></html>")
    assert MedicalDocument.all_objects.count() == 0


def test_stored_html_is_never_served_as_html(ctx):
    document = _attach(ctx, "ok.pdf", PDF)
    storage = document.file.storage
    storage.delete(document.file.name)
    storage.save(document.file.name, __import__("django.core.files.base", fromlist=["ContentFile"]).ContentFile(b"<html>x</html>"))

    response = client_for(ctx.doctor.user).get(reverse("medical:document-download", args=[document.pk]))

    assert response["Content-Type"] == "application/octet-stream"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert ".html" not in response["Content-Disposition"]
    entry = AuditLog.objects.get(action_type="medical.document.viewed", object_id=str(document.pk))
    assert entry.before is None and entry.after is None


def test_other_club_still_gets_404(ctx, other_ctx):
    document = _attach(ctx, "a.pdf", PDF)
    response = client_for(other_ctx.doctor.user).get(reverse("medical:document-download", args=[document.pk]))
    assert response.status_code == 404
