"""Fichiers prives : nom de stockage et reponse de telechargement fondes sur
le TYPE REEL du contenu, jamais sur le nom ou le type declares par le client
(CDC 6.7, 7.6 ; CLAUDE.md regle n 10).

- ``rename_upload_to_real_type`` : a l'enregistrement, remplace le nom envoye
  par ``<aleatoire>.<extension reelle>`` (jpg, png, webp, pdf).
- ``private_file_response`` : au telechargement, relit l'en-tete du fichier
  stocke (couvre aussi les fichiers deja enregistres sous une mauvaise
  extension) et force ``Content-Type``, ``Content-Disposition: attachment`` et
  ``X-Content-Type-Options: nosniff``. Un contenu non reconnu est servi en
  ``application/octet-stream`` (extension ``bin``), jamais en ``text/html``.
"""

from __future__ import annotations

import re
import uuid

from django.http import FileResponse

from apps.core.validators import HEAD_SIZE, detect_image_or_pdf_kind

KIND_TO_EXTENSION_AND_MIME = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
    "PDF": ("pdf", "application/pdf"),
}
_FALLBACK = ("bin", "application/octet-stream")


def extension_and_mime_for_head(head: bytes) -> tuple[str, str]:
    kind = detect_image_or_pdf_kind(head)
    return KIND_TO_EXTENSION_AND_MIME.get(kind, _FALLBACK)


def rename_upload_to_real_type(file) -> None:
    """Pose sur le fichier televerse un nom aleatoire a extension reelle.

    N'interprete jamais l'extension d'origine. Un fichier illisible ou non
    reconnu recoit ``.bin`` (il sera de toute facon refuse par la validation
    du type reel a l'enregistrement du modele).
    """

    try:
        file.seek(0)
        head = file.read(HEAD_SIZE)
        file.seek(0)
    except (AttributeError, OSError, ValueError):
        head = b""
    extension, _mime = extension_and_mime_for_head(head)
    file.name = f"{uuid.uuid4().hex}.{extension}"


def safe_download_stem(value: str, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", (value or "").rsplit(".", 1)[0]).strip("-")[:60]
    return stem or fallback


def private_file_response(stored_file, *, download_stem: str, as_attachment: bool = True) -> FileResponse:
    """Reponse de telechargement sure pour un fichier prive stocke."""

    handle = stored_file.open("rb")
    try:
        head = handle.read(HEAD_SIZE)
        handle.seek(0)
    except (OSError, ValueError):
        head = b""
    extension, mime = extension_and_mime_for_head(head)
    response = FileResponse(
        handle,
        as_attachment=as_attachment,
        filename=f"{safe_download_stem(download_stem, 'document')}.{extension}",
        content_type=mime,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
