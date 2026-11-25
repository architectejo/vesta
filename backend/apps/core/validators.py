"""Validateurs reutilisables pour les fichiers uploades (CDC 6.7, 7.6).

CDC 6.7 : « Formats acceptes : JPEG, PNG, WebP, PDF ; taille maximale
10 Mo avant compression. » CDC 7.6 : « Verification du type reel des
fichiers envoyes. »

Corrige une partie de l'ecart bloquant B10 (revue de conformite de fin de
Lot 1, tache 1.14, `cdc-reviewer`) : les champs ``ImageField``/``FileField``
existants n'avaient ni plafond de taille explicite, ni controle du type
reel au-dela de la validation Pillow implicite de
``rest_framework.fields.ImageField``.

Le type reel est verifie -- jamais seulement l'extension du nom de
fichier -- via Pillow pour les images (deja utilise par
``django.forms.ImageField.to_python``, dont
``rest_framework.fields.ImageField`` differe entierement la validation ;
ces validateurs COMPLETENT ce controle deja fait, ils ne le
reimplementent pas, CLAUDE.md section 5) et via la lecture des premiers
octets pour le CSV importe, ou Pillow n'a rien a verifier.
"""

from __future__ import annotations

import csv
import re

from django.core.exceptions import ValidationError

# CDC 6.7 : « taille maximale 10 Mo avant compression » -- applique ici a
# toute image comme a tout document (fiches, CSV importe).
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024

# CDC 6.7 : « Formats acceptes : JPEG, PNG, WebP [...] » (le PDF, genere
# cote serveur pour la fiche d'adhesion, n'est jamais uploade directement
# par un utilisateur -- ce validateur ne concerne que les `ImageField`).
_ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

# Signatures binaires connues (images, PDF, archives, executables) : un
# fichier envoye comme CSV ne doit jamais commencer par l'une d'elles,
# quelle que soit son extension (CDC 7.6).
_BINARY_MAGIC_PREFIXES = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",  # JPEG
    b"GIF87a",
    b"GIF89a",
    b"RIFF",  # WebP (conteneur RIFF)
    b"%PDF-",
    b"PK\x03\x04",  # ZIP / XLSX / DOCX...
    b"MZ",  # executable Windows
    b"\x7fELF",  # executable Linux
)


def _is_already_stored(file) -> bool:
    """Vrai pour un ``FieldFile`` deja enregistre dans le stockage.

    Ces validateurs sont aussi branches sur des champs de modele, donc
    rejoues par ``full_clean()`` (ex. ``Club.save()`` a chaque modification
    du club). Un fichier deja range a ete controle a son entree ; le
    relire depuis le stockage (taille, Pillow) serait couteux et echouerait
    si le fichier est absent du disque. Un fichier televerse mais pas
    encore enregistre (``_committed`` faux) reste, lui, entierement
    controle.
    """

    return getattr(file, "_committed", False) is True


def validate_upload_size(file) -> None:
    """Rejette tout fichier de plus de 10 Mo (CDC 6.7)."""

    if _is_already_stored(file):
        return

    size = getattr(file, "size", None)
    if size is not None and size > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError(
            "Ce fichier dépasse la taille maximale autorisée de 10 Mo.",
            code="file_too_large",
        )


def validate_image_format(file) -> None:
    """Rejette toute image dont le type reel n'est pas JPEG, PNG ou WebP
    (CDC 6.7, 7.6).

    S'appuie sur l'attribut ``image`` pose par
    ``django.forms.ImageField.to_python`` (Pillow a deja ouvert et
    verifie le fichier a ce stade, y compris quand ce validateur est
    utilise via ``rest_framework.fields.ImageField(validators=[...])`` --
    voir sa docstring : elle differe entierement sa validation a
    ``django.forms.ImageField.clean()``, qui appelle les validateurs du
    champ APRES avoir pose cet attribut). Ce validateur ne verifie donc
    QUE le format reel de l'image, jamais seulement l'extension du nom de
    fichier.
    """

    if _is_already_stored(file):
        return

    # Chemin serializer : `forms.ImageField.to_python` a pose `image` sur le
    # fichier televerse. Chemin modele (`full_clean()` sur un fichier
    # televerse pas encore enregistre) : le `FieldFile` enveloppe ce fichier
    # (`file.file`), qui porte le meme attribut `image`. Sans cet attribut,
    # le fichier n'a pas ete verifie par Pillow a la frontiere API : rejete.
    image = getattr(file, "image", None)
    if image is None:
        image = getattr(getattr(file, "file", None), "image", None)
    image_format = getattr(image, "format", None) if image is not None else None
    if image_format is None or image_format.upper() not in _ALLOWED_IMAGE_FORMATS:
        raise ValidationError(
            "Seules les images JPEG, PNG ou WebP sont acceptées.",
            code="unsupported_image_format",
        )


# Taille de l'en-tete lue pour reconnaitre le type reel.
HEAD_SIZE = 1024

# En-tete PDF : `%PDF-1.x` / `%PDF-2.x`. Quelques octets parasites (BOM UTF-8,
# espaces, retours a la ligne, octets nuls) avant l'en-tete sont toleres ;
# rien d'autre.
_PDF_HEADER = re.compile(rb"\A(?:\xef\xbb\xbf|[\x00\t\n\x0c\r ]){0,8}%PDF-[12]\.\d")
# Un vrai PDF ne contient pas de balisage web lisible dans son premier Ko
# (flux compresses) : un fichier qui en contient se fait passer pour un PDF.
_MARKUP_IN_HEAD = re.compile(rb"<\s*(?:!doctype|html|head|body|script|svg|iframe|\?xml)", re.IGNORECASE)


def detect_image_or_pdf_kind(head: bytes) -> str | None:
    """Reconnait JPEG, PNG, WebP ou PDF d'apres les premiers octets
    (signatures), jamais d'apres le nom ni le content-type declares."""

    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    if _PDF_HEADER.match(head) and not _MARKUP_IN_HEAD.search(head):
        return "PDF"
    return None


_detect_image_or_pdf_kind = detect_image_or_pdf_kind


def validate_image_or_pdf(file) -> None:
    """Rejette tout fichier dont le contenu reel n'est pas JPEG, PNG, WebP
    ou PDF (CDC 6.7 « Formats acceptes : JPEG, PNG, WebP, PDF » ; 7.6
    « Verification du type reel des fichiers envoyes »).

    Le controle porte sur les octets du fichier : signature (magic bytes),
    puis, pour une image, ouverture et verification par Pillow (un fichier
    qui n'a que l'en-tete d'une image est refuse). Le nom du fichier et le
    ``content_type`` declares ne sont jamais consultes. A utiliser avec
    ``validate_upload_size`` (taille maximale de 10 Mo).

    Contrairement a ``validate_image_format``, ne depend pas de
    ``forms.ImageField`` : convient a un ``FileField`` de serializer ou de
    modele, qui accepte aussi le PDF.
    """

    if _is_already_stored(file):
        return

    try:
        file.seek(0)
        head = file.read(HEAD_SIZE)
    except (AttributeError, OSError, ValueError):
        raise ValidationError(
            "Ce fichier est illisible.",
            code="unreadable_file",
        ) from None

    if not head:
        raise ValidationError("Ce fichier est vide.", code="empty_file")

    kind = _detect_image_or_pdf_kind(head)
    if kind is None:
        raise ValidationError(
            "Format de fichier non accepté : seuls les fichiers JPEG, PNG, WebP ou PDF sont autorisés.",
            code="unsupported_file_type",
        )

    try:
        if kind != "PDF":
            from PIL import Image

            file.seek(0)
            try:
                with Image.open(file) as image:
                    image.verify()
                    real_format = (image.format or "").upper()
            except Exception:
                raise ValidationError(
                    "Ce fichier image est corrompu ou illisible.",
                    code="corrupted_image",
                ) from None
            if real_format not in _ALLOWED_IMAGE_FORMATS:
                raise ValidationError(
                    "Format de fichier non accepté : seuls les fichiers JPEG, PNG, WebP ou PDF sont autorisés.",
                    code="unsupported_file_type",
                )
    finally:
        # Laisse le flux au debut pour le stockage ou les validateurs suivants.
        try:
            file.seek(0)
        except (AttributeError, OSError, ValueError):
            pass


def validate_csv_file(file, *, check_structure: bool = True) -> None:
    """Verifie que le fichier envoye est reellement un CSV (CDC 7.6),
    jamais seulement son extension ``.csv``.

    ``check_structure=False`` (import des cotisations historiques, tache
    2.6) : saute uniquement le controle ``csv.Sniffer``, qui rejette les
    fichiers de suivi exportes d'un tableur avec une ligne de titre au-dessus
    de l'en-tete ; l'appelant verifie alors lui-meme la structure (en-tete
    reconnu obligatoire). Les controles de signature binaire, d'octet nul et
    de fichier vide restent toujours appliques.

    Rejette tout contenu qui commence par une signature binaire connue
    (image, PDF, archive, executable...) et tout contenu qui n'est pas
    reconnaissable comme une structure delimitee par
    virgule/point-virgule/tabulation (``csv.Sniffer``, meme principe de
    detection que la bibliotheque standard).

    Ne verifie PAS l'encodage exact (UTF-8 attendu) : ce controle, avec
    son message en francais deja existant, vit dans
    ``apps.clubs.services.import_players_from_csv`` (CLAUDE.md section 5 --
    pas de regle metier dupliquee ici) ; le decodage large ``latin-1``
    utilise ci-dessous (accepte tout octet 0-255) sert uniquement a
    detecter une structure CSV plausible, jamais a valider l'encodage.
    """

    file.seek(0)
    sample = file.read(8192)
    file.seek(0)

    if any(sample.startswith(prefix) for prefix in _BINARY_MAGIC_PREFIXES) or b"\x00" in sample:
        raise ValidationError(
            "Ce fichier n'est pas un fichier CSV valide (type réel incorrect).",
            code="invalid_csv_type",
        )

    text_sample = sample.decode("latin-1")

    if not text_sample.strip():
        raise ValidationError(
            "Ce fichier est vide.",
            code="invalid_csv_type",
        )

    if not check_structure:
        return

    try:
        csv.Sniffer().sniff(text_sample, delimiters=",;\t")
    except csv.Error:
        raise ValidationError(
            "Ce fichier n'est pas un fichier CSV valide (structure incorrecte).",
            code="invalid_csv_type",
        ) from None
