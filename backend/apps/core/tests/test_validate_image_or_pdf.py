"""Tests de ``apps.core.validators.validate_image_or_pdf`` (CDC 6.7 :
« Formats acceptés : JPEG, PNG, WebP, PDF ; taille maximale 10 Mo » ;
CDC 7.6 : vérification du type RÉEL des fichiers envoyés).

Le contrôle porte sur le contenu (signatures), jamais sur le nom ni sur le
content-type déclarés.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.core.validators import validate_image_or_pdf, validate_upload_size

TEN_MEGABYTES = 10 * 1024 * 1024
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def image_bytes(image_format: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buffer, format=image_format)
    return buffer.getvalue()


class TestAcceptedFiles:
    @pytest.mark.parametrize(
        ("image_format", "name", "content_type"),
        [
            ("JPEG", "recu.jpg", "image/jpeg"),
            ("PNG", "recu.png", "image/png"),
            ("WEBP", "recu.webp", "image/webp"),
        ],
    )
    def test_real_jpeg_png_and_webp_are_accepted(self, image_format, name, content_type):
        validate_image_or_pdf(SimpleUploadedFile(name, image_bytes(image_format), content_type=content_type))

    def test_real_pdf_is_accepted(self):
        validate_image_or_pdf(SimpleUploadedFile("recu.pdf", PDF_BYTES, content_type="application/pdf"))

    def test_stream_is_rewound_after_validation(self):
        data = image_bytes("PNG")
        upload = SimpleUploadedFile("recu.png", data)

        validate_image_or_pdf(upload)

        assert upload.read() == data

    def test_name_and_content_type_are_never_trusted_in_either_direction(self):
        """Un vrai PNG nommé .pdf est accepté (son type réel est autorisé) ;
        c'est le contenu qui décide, jamais l'extension."""

        validate_image_or_pdf(SimpleUploadedFile("recu.pdf", image_bytes("PNG"), content_type="application/pdf"))
        validate_image_or_pdf(SimpleUploadedFile("recu.png", PDF_BYTES, content_type="image/png"))

    def test_already_stored_file_is_not_revalidated(self):
        validate_image_or_pdf(SimpleNamespace(_committed=True))


class TestRejectedFiles:
    def test_gif_renamed_pdf_is_rejected(self):
        upload = SimpleUploadedFile("recu.pdf", image_bytes("GIF"), content_type="application/pdf")

        with pytest.raises(ValidationError) as exc_info:
            validate_image_or_pdf(upload)

        assert exc_info.value.code == "unsupported_file_type"

    def test_bmp_renamed_jpg_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_image_or_pdf(SimpleUploadedFile("recu.jpg", image_bytes("BMP"), content_type="image/jpeg"))

    @pytest.mark.parametrize(
        "content",
        [
            b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 64,
            b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64,
            b"#!/bin/sh\nrm -rf /\n",
            b"<?php system($_GET['c']); ?>",
            b"<html><script>alert(1)</script></html>",
            b"PK\x03\x04" + b"\x00" * 32,
        ],
    )
    def test_executable_or_script_renamed_jpg_is_rejected(self, content):
        upload = SimpleUploadedFile("photo.jpg", content, content_type="image/jpeg")

        with pytest.raises(ValidationError) as exc_info:
            validate_image_or_pdf(upload)

        assert exc_info.value.code == "unsupported_file_type"
        assert "JPEG, PNG, WebP ou PDF" in exc_info.value.messages[0]

    def test_riff_container_that_is_not_webp_is_rejected(self):
        wav = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32

        with pytest.raises(ValidationError):
            validate_image_or_pdf(SimpleUploadedFile("son.webp", wav, content_type="image/webp"))

    def test_truncated_image_with_valid_header_is_rejected(self):
        truncated = image_bytes("PNG")[:20]

        with pytest.raises(ValidationError) as exc_info:
            validate_image_or_pdf(SimpleUploadedFile("cassee.png", truncated, content_type="image/png"))

        assert exc_info.value.code == "corrupted_image"

    def test_jpeg_header_followed_by_garbage_is_rejected(self):
        fake = b"\xff\xd8\xff\xe0" + b"pas une image" * 10

        with pytest.raises(ValidationError):
            validate_image_or_pdf(SimpleUploadedFile("fausse.jpg", fake, content_type="image/jpeg"))

    def test_empty_file_is_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_image_or_pdf(SimpleUploadedFile("vide.pdf", b"", content_type="application/pdf"))

        assert exc_info.value.code == "empty_file"
        assert "vide" in exc_info.value.messages[0]

    def test_error_message_is_in_french_with_accents(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_image_or_pdf(SimpleUploadedFile("x.jpg", b"texte simple", content_type="image/jpeg"))

        assert "accepté" in exc_info.value.messages[0]

    def test_file_over_ten_megabytes_is_refused_by_the_size_validator(self):
        """Le plafond de 10 Mo reste porté par ``validate_upload_size``,
        toujours associé à ce validateur sur les champs concernés."""

        upload = SimpleUploadedFile("gros.pdf", PDF_BYTES + b"0" * TEN_MEGABYTES, content_type="application/pdf")

        validate_image_or_pdf(upload)  # le type est bon
        with pytest.raises(ValidationError) as exc_info:
            validate_upload_size(upload)

        assert exc_info.value.code == "file_too_large"


class TestPdfDisguise:
    def test_html_after_pdf_header_is_refused(self):
        with pytest.raises(ValidationError):
            validate_image_or_pdf(
                SimpleUploadedFile("x.html", b"%PDF-1.4\n<html><script>1</script></html>", content_type="application/pdf")
            )

    def test_pdf_with_a_few_leading_bytes_is_accepted(self):
        validate_image_or_pdf(SimpleUploadedFile("a.pdf", b"\xef\xbb\xbf\n" + PDF_BYTES, content_type="application/pdf"))

    def test_pdf_header_far_from_the_start_is_refused(self):
        with pytest.raises(ValidationError):
            validate_image_or_pdf(SimpleUploadedFile("a.pdf", b"x" * 50 + PDF_BYTES, content_type="application/pdf"))
