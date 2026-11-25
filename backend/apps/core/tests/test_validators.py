"""Tests des validateurs de fichiers uploades ``apps.core.validators``
(CDC 6.7 : JPEG/PNG/WebP/PDF, 10 Mo maximum ; CDC 7.6 : verification du
type REEL des fichiers ; ecart bloquant B10).
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.core.validators import (
    MAX_UPLOAD_SIZE_BYTES,
    validate_csv_file,
    validate_image_format,
    validate_upload_size,
)

TEN_MEGABYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Taille (CDC 6.7)
# ---------------------------------------------------------------------------


class TestValidateUploadSize:
    def test_max_size_constant_is_exactly_ten_megabytes(self):
        assert MAX_UPLOAD_SIZE_BYTES == TEN_MEGABYTES

    def test_file_of_exactly_ten_megabytes_is_accepted(self):
        validate_upload_size(SimpleNamespace(size=TEN_MEGABYTES))

    def test_file_of_ten_megabytes_plus_one_byte_is_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_upload_size(SimpleNamespace(size=TEN_MEGABYTES + 1))

        assert exc_info.value.code == "file_too_large"
        assert "10 Mo" in exc_info.value.messages[0]

    def test_rejection_message_is_in_french(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_upload_size(SimpleNamespace(size=TEN_MEGABYTES + 1))

        message = exc_info.value.messages[0]
        assert "taille maximale" in message
        assert "maximum size" not in message.lower()

    def test_small_and_empty_files_are_accepted(self):
        validate_upload_size(SimpleNamespace(size=0))
        validate_upload_size(SimpleNamespace(size=1))

    def test_real_uploaded_file_over_the_limit_is_rejected(self):
        upload = SimpleUploadedFile("gros.csv", b"a" * (TEN_MEGABYTES + 1))

        with pytest.raises(ValidationError):
            validate_upload_size(upload)

    def test_real_uploaded_file_at_the_limit_is_accepted(self):
        upload = SimpleUploadedFile("limite.csv", b"a" * TEN_MEGABYTES)

        validate_upload_size(upload)


# ---------------------------------------------------------------------------
# Format d'image (CDC 6.7, 7.6)
# ---------------------------------------------------------------------------


def _image_bytes(image_format: str, *, mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (4, 4), color="red" if mode == "RGB" else 0).save(buffer, format=image_format)
    return buffer.getvalue()


def _cleaned_image_upload(image_format: str, name: str) -> SimpleUploadedFile:
    """Passe le fichier par ``forms.ImageField.to_python`` (exactement ce que
    fait ``rest_framework.fields.ImageField`` avant d'appeler les validateurs
    du champ) : pose l'attribut ``image`` de Pillow sur le fichier."""

    upload = SimpleUploadedFile(name, _image_bytes(image_format))
    return forms.ImageField().to_python(upload)


class TestValidateImageFormat:
    @pytest.mark.parametrize(
        ("image_format", "name"),
        [("JPEG", "photo.jpg"), ("PNG", "photo.png"), ("WEBP", "photo.webp")],
    )
    def test_real_jpeg_png_and_webp_images_are_accepted(self, image_format, name):
        validate_image_format(_cleaned_image_upload(image_format, name))

    def test_gif_image_is_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_image_format(_cleaned_image_upload("GIF", "anime.gif"))

        assert exc_info.value.code == "unsupported_image_format"
        assert "JPEG, PNG ou WebP" in exc_info.value.messages[0]

    def test_bmp_image_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_image_format(_cleaned_image_upload("BMP", "image.bmp"))

    def test_extension_is_never_trusted_a_gif_named_png_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_image_format(_cleaned_image_upload("GIF", "fausse-extension.png"))

    def test_a_png_named_gif_is_accepted_because_only_the_real_format_counts(self):
        validate_image_format(_cleaned_image_upload("PNG", "vrai-png.gif"))

    def test_file_without_image_attribute_is_rejected(self):
        upload = SimpleUploadedFile("photo.png", _image_bytes("PNG"))
        assert not hasattr(upload, "image")

        with pytest.raises(ValidationError) as exc_info:
            validate_image_format(upload)

        assert exc_info.value.code == "unsupported_image_format"

    def test_file_whose_image_has_no_format_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_image_format(SimpleNamespace(image=SimpleNamespace(format=None)))

    def test_file_with_image_attribute_none_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_image_format(SimpleNamespace(image=None))

    def test_rejection_message_is_in_french(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_image_format(_cleaned_image_upload("GIF", "anime.gif"))

        assert "acceptées" in exc_info.value.messages[0]


# ---------------------------------------------------------------------------
# CSV (CDC 7.6)
# ---------------------------------------------------------------------------


def _csv_file(content: bytes, name: str = "import.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="text/csv")


class TestValidateCsvFile:
    @pytest.mark.parametrize(
        "content",
        [
            b"email,prenom,nom\na@example.com,Aline,Kabila\nb@example.com,Bob,Tshi\n",
            b"email;prenom;nom\na@example.com;Aline;Kabila\nb@example.com;Bob;Tshi\n",
            b"email\tprenom\tnom\na@example.com\tAline\tKabila\nb@example.com\tBob\tTshi\n",
        ],
        ids=["comma", "semicolon", "tab"],
    )
    def test_valid_csv_with_each_supported_delimiter_is_accepted(self, content):
        validate_csv_file(_csv_file(content))

    def test_cursor_is_reset_to_zero_after_validation(self):
        upload = _csv_file(b"email,prenom,nom\na@example.com,Aline,Kabila\n")

        validate_csv_file(upload)

        assert upload.tell() == 0
        assert upload.read().startswith(b"email,prenom,nom")

    def test_cursor_is_reset_to_zero_even_if_it_was_moved_before_validation(self):
        upload = _csv_file(b"email,prenom,nom\na@example.com,Aline,Kabila\n")
        upload.read(5)

        validate_csv_file(upload)

        assert upload.tell() == 0

    def test_cursor_is_reset_to_zero_even_when_validation_fails(self):
        upload = _csv_file(b"%PDF-1.4 fake pdf")

        with pytest.raises(ValidationError):
            validate_csv_file(upload)

        assert upload.tell() == 0

    def test_utf8_bom_csv_is_accepted(self):
        validate_csv_file(_csv_file("﻿email,prenom,nom\na@example.com,Aline,Kabila\n".encode("utf-8")))

    def test_utf8_accented_csv_is_accepted(self):
        validate_csv_file(_csv_file("email,prenom,nom\na@example.com,Honoré,Kabasélé\n".encode("utf-8")))

    @pytest.mark.parametrize(
        ("label", "content"),
        [
            ("png", _image_bytes("PNG")),
            ("jpeg", _image_bytes("JPEG")),
            ("gif", b"GIF89a" + b"\x01\x00\x01\x00,email,prenom,nom\n"),
            ("webp", _image_bytes("WEBP")),
            ("pdf", b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"),
            ("zip", b"PK\x03\x04email,prenom,nom\na,b,c\n"),
            ("windows_executable", b"MZ\x90\x00email,prenom,nom\na,b,c\n"),
            ("linux_executable", b"\x7fELFemail,prenom,nom\na,b,c\n"),
        ],
    )
    def test_binary_file_disguised_as_csv_is_rejected(self, label, content):
        with pytest.raises(ValidationError) as exc_info:
            validate_csv_file(_csv_file(content, name=f"deguise-{label}.csv"))

        assert exc_info.value.code == "invalid_csv_type"
        assert "type réel incorrect" in exc_info.value.messages[0]

    def test_file_containing_a_null_byte_is_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_csv_file(_csv_file(b"email,prenom,nom\na@example.com,Ali\x00ne,Kabila\n"))

        assert exc_info.value.code == "invalid_csv_type"

    def test_empty_file_is_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_csv_file(_csv_file(b""))

        assert exc_info.value.code == "invalid_csv_type"
        assert "vide" in exc_info.value.messages[0]

    @pytest.mark.parametrize("content", [b"   ", b"\n\n\n", b" \t \r\n "], ids=["spaces", "newlines", "mixed"])
    def test_blank_file_is_rejected(self, content):
        with pytest.raises(ValidationError) as exc_info:
            validate_csv_file(_csv_file(content))

        assert "vide" in exc_info.value.messages[0]

    def test_text_without_any_csv_structure_is_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_csv_file(_csv_file(b"Bonjour ceci est un simple texte sans delimiteur\nUne autre ligne de texte\n"))

        assert exc_info.value.code == "invalid_csv_type"
        assert "structure incorrecte" in exc_info.value.messages[0]

    def test_single_line_of_text_without_delimiter_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_csv_file(_csv_file(b"Juste une ligne sans rien"))

    def test_rejection_messages_are_in_french(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_csv_file(_csv_file(b"%PDF-1.4"))

        message = exc_info.value.messages[0]
        assert "fichier CSV valide" in message
        assert "not a" not in message.lower()

    def test_binary_signature_is_detected_regardless_of_the_file_name(self):
        with pytest.raises(ValidationError):
            validate_csv_file(_csv_file(_image_bytes("PNG"), name="joueurs.CSV"))
