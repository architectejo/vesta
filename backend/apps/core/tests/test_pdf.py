"""Tests du cadre PDF commun (docs/annexes/modeles-documents.md §1),
tache 4.9 : utilitaires purs de `apps.core.pdf`, reutilises par
`apps.assemblies.services._build_minutes_pdf` et
`apps.mercato.services._build_quitus_pdf`."""

from __future__ import annotations

import datetime
import io
from decimal import Decimal

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from apps.core.pdf import (
    NumberedDocumentCanvas,
    club_stripe_colors,
    contrast_ratio,
    darken_until_contrast,
    format_date_longue,
    format_percentage,
    hex_to_rgb01,
    make_footer_drawer,
    wrap_text,
)


class TestHexToRgb01:
    def test_valid_hex(self):
        assert hex_to_rgb01("#FFFFFF") == (1.0, 1.0, 1.0)
        assert hex_to_rgb01("#000000") == (0.0, 0.0, 0.0)

    @pytest.mark.parametrize("value", ["", None, "bleu", "#FFF", "#GGGGGG"])
    def test_invalid_returns_none(self, value):
        assert hex_to_rgb01(value) is None


class TestDarkenUntilContrast:
    def test_already_readable_color_is_untouched(self):
        black = (0.0, 0.0, 0.0)
        assert darken_until_contrast(black, 1.5) == black

    def test_too_light_color_is_darkened_until_the_target_is_reached(self):
        pale_yellow = (1.0, 1.0, 0.85)
        darkened = darken_until_contrast(pale_yellow, 1.5)
        assert contrast_ratio(darkened, (1.0, 1.0, 1.0)) >= 1.5
        assert darkened != pale_yellow


class TestClubStripeColors:
    def test_missing_colors_fall_back_to_neutral_not_navy(self):
        class _Club:
            primary_color = ""
            secondary_color = ""

        primary, secondary = club_stripe_colors(_Club())
        # Ancien repli interdit par le gabarit §1.3 : le bleu marine
        # (0.12, 0.16, 0.32) ecrit en dur ne doit plus jamais apparaitre.
        assert primary != (0.12, 0.16, 0.32)
        assert secondary != (0.12, 0.16, 0.32)


class TestFormatDateLongue:
    def test_matches_the_expected_french_wording(self):
        assert format_date_longue(datetime.date(2026, 9, 27)) == "dimanche 27 septembre 2026"


class TestFormatPercentage:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (Decimal("50.00"), "50 %"),
            (Decimal("100"), "100 %"),
            (Decimal("66.6666"), "66,67 %"),
        ],
    )
    def test_hides_null_decimals_and_uses_a_comma(self, value, expected):
        assert format_percentage(value) == expected


class TestWrapText:
    def test_never_drops_characters(self):
        long_text = (
            "Une phrase suffisamment longue pour depasser cent vingt caracteres afin de verifier "
            "qu'aucun caractere n'est perdu lors du repli automatique a la largeur utile du document."
        )
        assert len(long_text) > 120
        lines = wrap_text(long_text, font="Helvetica", size=10, max_width=200)
        assert len(lines) > 1
        # Reconstruit le texte original (les espaces de repli remplacent
        # exactement les espaces d'origine, aucun mot n'est coupe).
        assert " ".join(lines) == long_text

    def test_single_line_when_width_is_generous(self):
        text = "Court texte"
        assert wrap_text(text, font="Helvetica", size=10, max_width=2000) == [text]


class TestNumberedDocumentCanvas:
    def test_writes_the_correct_total_page_count(self):
        width, _height = A4
        pages_seen = []

        def footer_fn(pdf, page_number, total_pages):
            pages_seen.append((page_number, total_pages))

        buffer = io.BytesIO()
        pdf = NumberedDocumentCanvas(buffer, pagesize=A4, pageCompression=0, footer_fn=footer_fn)
        pdf.drawString(20 * mm, 700, "Page 1")
        pdf.showPage()
        pdf.drawString(20 * mm, 700, "Page 2")
        pdf.showPage()
        pdf.drawString(20 * mm, 700, "Page 3")
        # Pas de ``showPage()`` explicite avant ``save()`` : verifie le
        # filet de securite (comme ``reportlab.pdfgen.canvas.Canvas.save()``
        # standard), sinon la derniere page serait perdue.
        pdf.save()

        assert pages_seen == [(1, 3), (2, 3), (3, 3)]
        data = buffer.getvalue()
        assert data.startswith(b"%PDF")

    def test_single_page_document_reports_one_of_one(self):
        pages_seen = []

        def footer_fn(pdf, page_number, total_pages):
            pages_seen.append((page_number, total_pages))

        buffer = io.BytesIO()
        pdf = NumberedDocumentCanvas(buffer, pagesize=A4, pageCompression=0, footer_fn=footer_fn)
        pdf.drawString(20 * mm, 700, "Seule page")
        pdf.showPage()
        pdf.save()

        assert pages_seen == [(1, 1)]


class TestMakeFooterDrawer:
    def test_footer_never_mentions_the_editor_or_vesta(self):
        width, _height = A4
        footer_fn = make_footer_drawer(
            club_name="Loisirs Club Discovery",
            doc_type_label="Quitus de transfert",
            reference="Q-1",
            generated_at_text="27/09/2026 à 10:00",
            width=width,
        )
        buffer = io.BytesIO()
        pdf = NumberedDocumentCanvas(buffer, pagesize=A4, pageCompression=0, footer_fn=footer_fn)
        pdf.showPage()
        pdf.save()
        text = buffer.getvalue().decode("latin-1")
        assert "IMARA" not in text
        assert "Vesta" not in text
        assert "orphelinat" not in text.lower()
