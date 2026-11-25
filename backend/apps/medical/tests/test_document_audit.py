"""Journalisation des documents medicaux (CLAUDE.md regles n6/n11 ; CDC
6.7, 5.2 « Medical », 7.5, 4.12).

Deux ecarts combles ici (audit independant, voir compte rendu) :
- ``apps.medical.services.attach_document`` ne journalisait aucune
  entree a la creation d'un document (regle n6 : « toute creation [...]
  ecrit une entree dans le journal d'activite »).
- ``apps.medical.views.MedicalDocumentDownloadView`` ne journalisait pas
  la consultation d'un document, alors que la regle n11 exige de
  journaliser chaque consultation d'un dossier medical (etendue ici, par
  coherence avec le reste du module -- ``medical.record.viewed`` etc. --
  a toute consultation d'un document medical, quel que soit le role du
  lecteur).

Dans les deux cas : jamais le contenu du document ni son nom de fichier
original (qui peut lui-meme reveler un element clinique, ex.
« entorse_genou.pdf ») -- seule la reference (type/id de l'objet
``MedicalDocument``, deja portee par ``AuditLog.object_id``) et, pour la
creation, le parent (blessure ou fiche de sante par identifiant) sont
journalises.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.medical import services
from apps.medical.tests.conftest import client_for

pytestmark = pytest.mark.django_db


def _fake_pdf(name: str = "piece.pdf") -> SimpleUploadedFile:
    # Signature minimale reconnue par `apps.core.validators.validate_image_or_pdf`
    # (controle du type reel, pas seulement de l'extension -- CDC 7.6).
    return SimpleUploadedFile(name, b"%PDF-1.4 contenu de test", content_type="application/pdf")


class TestAttachDocumentIsLogged:
    def test_attach_document_on_injury_writes_an_audit_entry(self, ctx):
        injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")

        document = services.attach_document(
            actor=ctx.doctor.user,
            file=_fake_pdf("genou-fracture.pdf"),
            original_filename="genou-fracture.pdf",
            injury=injury,
        )

        entry = AuditLog.objects.get(action_type="medical.document.attached", object_id=str(document.pk))
        assert entry.actor_id == ctx.doctor.user.id
        assert entry.club_id == ctx.club.id
        assert entry.object_type == "MedicalDocument"
        assert entry.after == {"injury_id": injury.pk, "health_record_id": None}

    def test_attach_document_log_never_contains_the_original_filename(self, ctx):
        """Le nom de fichier original peut lui-meme reveler un contenu
        clinique (ex. un diagnostic) : il ne doit jamais apparaitre dans
        le journal, ni dans ``before``/``after`` ni ailleurs (CLAUDE.md
        regle n11)."""

        injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")

        services.attach_document(
            actor=ctx.doctor.user,
            file=_fake_pdf("diagnostic-confidentiel-rupture-ligament.pdf"),
            original_filename="diagnostic-confidentiel-rupture-ligament.pdf",
            injury=injury,
        )

        entry = AuditLog.objects.get(action_type="medical.document.attached")
        assert "diagnostic-confidentiel-rupture-ligament" not in str(entry.before) + str(entry.after)

    def test_attach_document_on_health_record_writes_an_audit_entry(self, ctx):
        record = services.get_or_create_health_record(ctx.player)

        document = services.attach_document(
            actor=ctx.doctor.user,
            file=_fake_pdf(),
            original_filename="piece.pdf",
            health_record=record,
        )

        entry = AuditLog.objects.get(action_type="medical.document.attached", object_id=str(document.pk))
        assert entry.after == {"injury_id": None, "health_record_id": record.pk}


class TestDocumentViewIsLogged:
    def test_log_document_viewed_writes_an_audit_entry(self, ctx):
        injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
        document = services.attach_document(
            actor=ctx.doctor.user, file=_fake_pdf(), original_filename="piece.pdf", injury=injury
        )

        services.log_document_viewed(actor=ctx.doctor.user, document=document)

        entry = AuditLog.objects.get(action_type="medical.document.viewed", object_id=str(document.pk))
        assert entry.actor_id == ctx.doctor.user.id
        assert entry.club_id == ctx.club.id

    def test_president_reading_another_players_document_is_logged_as_president_view(self, ctx):
        injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
        document = services.attach_document(
            actor=ctx.doctor.user, file=_fake_pdf(), original_filename="piece.pdf", injury=injury
        )

        services.log_document_viewed(actor=ctx.president.user, document=document)

        entry = AuditLog.objects.get(object_id=str(document.pk), actor=ctx.president.user, object_type="MedicalDocument")
        assert entry.action_type == "medical.record.viewed_by_president"
        assert entry.before is None and entry.after is None
        assert not AuditLog.objects.filter(action_type="medical.document.viewed", object_id=str(document.pk)).exists()

    def test_download_view_logs_a_consultation(self, ctx):
        """Vue authentifiee (CLAUDE.md regle n10) : chaque telechargement
        reussi journalise une consultation (regle n11 ; CDC 4.12, 5.2)."""

        injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
        document = services.attach_document(
            actor=ctx.doctor.user, file=_fake_pdf(), original_filename="piece.pdf", injury=injury
        )

        client = client_for(ctx.doctor.user)
        url = reverse("medical:document-download", args=[document.pk])
        response = client.get(url)

        assert response.status_code == 200
        assert AuditLog.objects.filter(
            action_type="medical.document.viewed", object_id=str(document.pk), actor=ctx.doctor.user
        ).exists()

    def test_download_view_does_not_log_on_forbidden_access(self, ctx):
        """Un acces refuse (403) ne doit ecrire aucune entree de
        consultation : rien n'a ete consulte."""

        injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
        document = services.attach_document(
            actor=ctx.doctor.user, file=_fake_pdf(), original_filename="piece.pdf", injury=injury
        )

        client = client_for(ctx.captain.user)
        url = reverse("medical:document-download", args=[document.pk])
        response = client.get(url)

        assert response.status_code == 403
        assert not AuditLog.objects.filter(action_type="medical.document.viewed", object_id=str(document.pk)).exists()

    def test_download_view_log_never_contains_the_original_filename(self, ctx):
        injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
        document = services.attach_document(
            actor=ctx.doctor.user,
            file=_fake_pdf("diagnostic-prive.pdf"),
            original_filename="diagnostic-prive.pdf",
            injury=injury,
        )

        client = client_for(ctx.doctor.user)
        url = reverse("medical:document-download", args=[document.pk])
        client.get(url)

        entry = AuditLog.objects.get(action_type="medical.document.viewed", object_id=str(document.pk))
        assert entry.before is None and entry.after is None
