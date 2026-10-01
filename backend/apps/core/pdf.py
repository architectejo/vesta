"""Cadre commun aux documents PDF de l'annexe D (quitus, PV d'AG, et a
terme recu et fiche d'adhesion -- docs/annexes/modeles-documents.md §1).

Regroupe ici (plutot que duplique dans chaque app generatrice) parce que
le gabarit §1 s'applique **tel quel** a plusieurs generateurs
(`apps.assemblies.services._build_minutes_pdf`,
`apps.mercato.services._build_quitus_pdf`, et a terme
`apps.clubs.services._build_membership_application_pdf`) : une seule
source pour l'en-tete, le pied de page, les couleurs et le format des
dates evite que les generateurs divergent silencieusement les uns des
autres (regle de synchronisation en tete du gabarit).

Ne contient aucune regle metier (CLAUDE.md : les regles metier vivent
dans `services.py` de chaque app) -- uniquement du rendu PDF bas niveau
et des utilitaires de format purs.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Optional

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdf_canvas

__all__ = [
    "MARGIN",
    "DARK_TEXT_RGB",
    "MUTED_TEXT_RGB",
    "NEUTRAL_PRIMARY_RGB",
    "NEUTRAL_SECONDARY_RGB",
    "STATUS_COLORS",
    "hex_to_rgb01",
    "contrast_ratio",
    "darken_until_contrast",
    "club_stripe_colors",
    "format_date_longue",
    "format_percentage",
    "wrap_text",
    "NumberedDocumentCanvas",
    "draw_header",
    "draw_continuation_header",
    "make_footer_drawer",
    "draw_status_badge",
]

# ---------------------------------------------------------------------------
# Couleurs (gabarit §1.2, §1.3, §1.6)
# ---------------------------------------------------------------------------

DARK_TEXT_RGB = (0x11 / 255, 0x18 / 255, 0x27 / 255)  # #111827
MUTED_TEXT_RGB = (0x4B / 255, 0x55 / 255, 0x63 / 255)  # #4B5563
NEUTRAL_PRIMARY_RGB = (0x4B / 255, 0x55 / 255, 0x63 / 255)  # #4B5563 (repli liseré principal)
NEUTRAL_SECONDARY_RGB = (0xE1 / 255, 0xE5 / 255, 0xEB / 255)  # #E1E5EB (repli liseré secondaire)
_WHITE_RGB = (1.0, 1.0, 1.0)

# Pastilles de statut (gabarit §1.6, meme charte que design-system.md §2.5)
STATUS_COLORS = {
    "green": {"dot": (0x16 / 255, 0xA3 / 255, 0x4A / 255), "bg": (0xDC / 255, 0xFC / 255, 0xE7 / 255), "text": (0x14 / 255, 0x53 / 255, 0x2D / 255)},
    "orange": {"dot": (0xEA / 255, 0x58 / 255, 0x0C / 255), "bg": (0xFF / 255, 0xED / 255, 0xD5 / 255), "text": (0x7C / 255, 0x2D / 255, 0x12 / 255)},
    "gray": {"dot": (0x6B / 255, 0x72 / 255, 0x80 / 255), "bg": (0xF3 / 255, 0xF4 / 255, 0xF6 / 255), "text": (0x1F / 255, 0x29 / 255, 0x37 / 255)},
}


def hex_to_rgb01(value: str) -> Optional[tuple[float, float, float]]:
    """Convertit une couleur hex ``#RRGGBB`` en triplet 0-1, ``None`` si la
    valeur est absente ou mal formee (gabarit §1.3 : jamais d'echec)."""

    value = (value or "").strip()
    if not (value.startswith("#") and len(value) == 7):
        return None
    try:
        return (
            int(value[1:3], 16) / 255,
            int(value[3:5], 16) / 255,
            int(value[5:7], 16) / 255,
        )
    except ValueError:
        return None


def _channel_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 0.2126 * _channel_to_linear(r) + 0.7152 * _channel_to_linear(g) + 0.0722 * _channel_to_linear(b)


def contrast_ratio(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Ratio de contraste WCAG (meme formule que
    `frontend/src/design-system/tokens/color-contrast.ts`)."""

    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def darken_until_contrast(
    rgb: tuple[float, float, float], target: float, *, against: tuple[float, float, float] = _WHITE_RGB
) -> tuple[float, float, float]:
    """Assombrit ``rgb`` par pas de 5 % vers le noir jusqu'a ``target``
    (gabarit §1.3 : couleur de club trop claire sur fond blanc, seuil
    1,5:1 pour un liseré, meme principe que design-system.md §2.4 point 3)."""

    candidate = rgb
    for _ in range(20):
        if contrast_ratio(candidate, against) >= target:
            return candidate
        candidate = tuple(c - c * 0.05 for c in candidate)
    return candidate


def club_stripe_colors(club) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Couleurs du liseré d'en-tete (gabarit §1.3) : couleurs du club si
    valides et lisibles sur blanc (>= 1,5:1, assombries sinon), neutres du
    theme Clair en repli -- jamais le bleu marine ecrit en dur."""

    primary = hex_to_rgb01(getattr(club, "primary_color", "")) or NEUTRAL_PRIMARY_RGB
    secondary = hex_to_rgb01(getattr(club, "secondary_color", "")) or NEUTRAL_SECONDARY_RGB
    return darken_until_contrast(primary, 1.5), darken_until_contrast(secondary, 1.5)


# ---------------------------------------------------------------------------
# Formats (gabarit §1.7 ; CLAUDE.md §7 -- pas de locale serveur garantie)
# ---------------------------------------------------------------------------

_WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def format_date_longue(value: date) -> str:
    """« dimanche 27 septembre 2026 » (gabarit §1.7), table dediee en
    francais -- jamais la locale du serveur (l'hebergement cPanel ne
    garantit pas fr_FR)."""

    return f"{_WEEKDAYS_FR[value.weekday()]} {value.day} {_MONTHS_FR[value.month - 1]} {value.year}"


def format_percentage(value: Decimal) -> str:
    """« 50 % », « 66,67 % » : virgule decimale, decimales masquees si
    nulles (gabarit §1.7)."""

    quantized = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return f"{int(quantized)} %"
    return f"{quantized:.2f}".replace(".", ",") + " %"


def wrap_text(text: str, *, font: str, size: float, max_width: float) -> list[str]:
    """Repli d'une ligne de texte a la largeur utile, sans troncature
    (gabarit §3.5). Un mot plus large que ``max_width`` est laisse tel
    quel plutot que de boucler indefiniment."""

    words = (text or "").split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and stringWidth(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines or [""]


# ---------------------------------------------------------------------------
# Pagination fiable ("Page n sur N", gabarit §1.5) -- recette standard
# reportlab (report d'une passe : chaque page est mise en attente, le
# total n'est ecrit qu'a la sauvegarde finale).
# ---------------------------------------------------------------------------


class NumberedDocumentCanvas(pdf_canvas.Canvas):
    """Canvas bas niveau qui differe l'ecriture du pied de page jusqu'a
    connaitre le nombre total de pages. ``footer_fn(canvas, page_number,
    total_pages)`` est appele juste avant l'emission reelle de chaque
    page."""

    footer_fn: Optional[Callable[["NumberedDocumentCanvas", int, int], None]] = None

    def showPage(self) -> None:  # noqa: N802 - nom impose par reportlab
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        # Filet de securite (meme comportement que ``Canvas.save()``
        # standard) : si la derniere page n'a jamais ete close par un appel
        # explicite a ``showPage()``, son contenu serait sinon perdu --
        # jamais seulement prive de pied de page (regression detectee par
        # `apps.core.tests.test_pdf.TestNumberedDocumentCanvas`).
        if len(self._code):
            self.showPage()
        states = getattr(self, "_saved_page_states", [])
        total_pages = len(states)
        for state in states:
            self.__dict__.update(state)
            if self.footer_fn is not None:
                self.footer_fn(self, self._pageNumber, total_pages)
            pdf_canvas.Canvas.showPage(self)
        pdf_canvas.Canvas.save(self)

    def __init__(self, *args, footer_fn=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.footer_fn = footer_fn


# ---------------------------------------------------------------------------
# En-tete / pied de page (gabarit §1.3, §1.4, §1.5)
# ---------------------------------------------------------------------------

MARGIN = 18 * mm
_MARGIN = MARGIN
_HEADER_HEIGHT = 26 * mm
_LOGO_BOX = 18 * mm


def _draw_logo(pdf: pdf_canvas.Canvas, club, *, width, height) -> float:
    """Dessine le logo si present et lisible ; ne fait jamais echouer la
    generation (gabarit §1.3, meme principe que
    `apps.clubs.services._build_membership_application_pdf`). Renvoie
    l'abscisse a partir de laquelle le texte de l'en-tete doit commencer."""

    logo = getattr(club, "logo", None)
    if not logo:
        return _MARGIN
    try:
        with logo.open("rb") as handle:
            data = handle.read()
        image = ImageReader(io.BytesIO(data))
        iw, ih = image.getSize()
        if not iw or not ih:
            return _MARGIN
        scale = min(_LOGO_BOX / iw, _LOGO_BOX / ih)
        draw_w, draw_h = iw * scale, ih * scale
        x = _MARGIN
        y = height - 8 * mm - _LOGO_BOX + (_LOGO_BOX - draw_h) / 2
        pdf.drawImage(
            image,
            x + (_LOGO_BOX - draw_w) / 2,
            y,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
        return _MARGIN + _LOGO_BOX + 4 * mm
    except Exception:
        return _MARGIN


def draw_header(pdf: pdf_canvas.Canvas, *, club, doc_type_label: str, reference: str, width, height) -> float:
    """En-tete premiere page (gabarit §1.3) : logo, nom et ville du club a
    gauche, type de document et reference a droite, liseré deux tons
    dessous. Renvoie l'ordonnee (y) a partir de laquelle dessiner le
    corps du document."""

    primary, secondary = club_stripe_colors(club)
    text_x = _draw_logo(pdf, club, width=width, height=height)

    pdf.setFillColorRGB(*DARK_TEXT_RGB)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(text_x, height - 12 * mm, club.name)
    pdf.setFont("Helvetica", 9)
    pdf.setFillColorRGB(*MUTED_TEXT_RGB)
    city = getattr(club, "city", "") or ""
    country = getattr(club, "country", "") or ""
    location = ", ".join(part for part in (city, country) if part)
    if location:
        pdf.drawString(text_x, height - 17 * mm, location)

    pdf.setFillColorRGB(*MUTED_TEXT_RGB)
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(width - _MARGIN, height - 12 * mm, doc_type_label)
    pdf.drawRightString(width - _MARGIN, height - 17 * mm, reference)

    stripe_y = height - _HEADER_HEIGHT
    pdf.setFillColorRGB(*primary)
    pdf.rect(0, stripe_y + 0.6 * mm, width, 1.2 * mm, fill=1, stroke=0)
    pdf.setFillColorRGB(*secondary)
    pdf.rect(0, stripe_y, width, 0.6 * mm, fill=1, stroke=0)

    pdf.setFillColorRGB(*DARK_TEXT_RGB)
    return stripe_y - 8 * mm


def draw_continuation_header(pdf: pdf_canvas.Canvas, *, club, doc_type_label: str, reference: str, width, height) -> float:
    """En-tete reduit des pages suivantes (gabarit §1.4) : pas de logo."""

    primary, _secondary = club_stripe_colors(club)

    pdf.setFillColorRGB(*DARK_TEXT_RGB)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(_MARGIN, height - 8 * mm, club.name)
    pdf.setFillColorRGB(*MUTED_TEXT_RGB)
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(width - _MARGIN, height - 8 * mm, f"{doc_type_label} — {reference}")

    stripe_y = height - 12 * mm
    pdf.setFillColorRGB(*primary)
    pdf.rect(0, stripe_y, width, 0.8 * mm, fill=1, stroke=0)

    pdf.setFillColorRGB(*DARK_TEXT_RGB)
    return stripe_y - 8 * mm


def make_footer_drawer(
    *, club_name: str, doc_type_label: str, reference: str, generated_at_text: str, width
) -> Callable[["NumberedDocumentCanvas", int, int], None]:
    """Construit le ``footer_fn`` attendu par :class:`NumberedDocumentCanvas`
    (gabarit §1.5). Aucune mention de l'Editeur ni de « Vesta »
    (CLAUDE.md §2.19, gabarit §1.8)."""

    def _draw(pdf: "NumberedDocumentCanvas", page_number: int, total_pages: int) -> None:
        pdf.setFillColorRGB(*MUTED_TEXT_RGB)
        pdf.setLineWidth(0.5)
        pdf.line(_MARGIN, 16 * mm, width - _MARGIN, 16 * mm)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(_MARGIN, 12 * mm, f"{club_name} — {doc_type_label} — Réf. {reference}")
        pdf.drawRightString(width - _MARGIN, 12 * mm, f"Page {page_number} sur {total_pages}")
        pdf.drawString(_MARGIN, 8 * mm, f"Document généré le {generated_at_text}")

    return _draw


def draw_status_badge(pdf: pdf_canvas.Canvas, x: float, y: float, *, label: str, family: str) -> float:
    """Pastille + libellé (gabarit §1.6) : jamais la couleur seule. Renvoie
    la largeur totale dessinee."""

    colors = STATUS_COLORS[family]
    pdf.setFont("Helvetica-Bold", 10)
    text_width = stringWidth(label, "Helvetica-Bold", 10)
    padding = 3 * mm
    dot_r = 1.25 * mm
    total_width = padding + dot_r * 2 + 2 * mm + text_width + padding

    pdf.setFillColorRGB(*colors["bg"])
    pdf.roundRect(x, y - 3 * mm, total_width, 6 * mm, 1 * mm, fill=1, stroke=0)
    pdf.setFillColorRGB(*colors["dot"])
    pdf.circle(x + padding + dot_r, y, dot_r, fill=1, stroke=0)
    pdf.setFillColorRGB(*colors["text"])
    pdf.drawString(x + padding + dot_r * 2 + 2 * mm, y - 1.6 * mm, label)
    return total_width
