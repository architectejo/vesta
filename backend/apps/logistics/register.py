"""Registre de l'intendance : données, PDF et CSV (CDC 4.13 ;
docs/ecrans/logistique-intendance-registre.md §10, lot 5).

Une seule source de données (``build_register``) alimente la page, le PDF et
le CSV. Aucun nom de club écrit en dur : nom et logo viennent du club actif
(règle 18) ; aucune mention de l'éditeur dans le document (règle 19).

Position retenue : une ligne du registre = une entrée de stock (achat,
dotation, reprise du registre) ; un article n'apparaît que s'il est encore en
stock (chez le détenteur filtré le cas échéant), sauf « Afficher les sorties ».
"""

from __future__ import annotations

import csv
import datetime
import io
from functools import partial
from typing import Optional
from xml.sax.saxutils import escape

from django.utils import timezone

from apps.logistics import services
from apps.logistics.models import Article, Decommission, Holder, StockMovement

__all__ = [
    "build_register",
    "format_quantity",
    "STOCK_TOTAL_LABEL",
    "render_register_csv",
    "render_register_pdf",
    "register_filters_snapshot",
    "CSV_COLUMNS",
]

CSV_COLUMNS = ["nature", "designation", "quantite", "unite", "origine", "date_acquisition", "localisation", "etat"]
_EXIT_TYPES = (
    StockMovement.MovementType.OUT_WEAR,
    StockMovement.MovementType.OUT_LOSS,
    StockMovement.MovementType.OUT_DECOMMISSION,
)


def _fmt_date(value: Optional[datetime.date]) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


#: Libellé du pied de section : c'est le STOCK ACTUEL (après sorties et
#: déplacements), pas la somme des lignes, qui listent des entrées (registre
#: §10.2) -- libellé explicite pour lever l'ambiguïté (demande dev-b B4 n° 4).
STOCK_TOTAL_LABEL = "Stock actuel"

# Unités abrégées, invariables (« 2 kg », jamais « 2 kgs »).
_INVARIABLE_UNITS = frozenset({"kg", "g", "mg", "l", "cl", "ml", "m", "cm", "mm", "km"})


def _plural_unit(unit: str) -> str:
    """Pluriel français d'une unité saisie librement (« pièce » → « pièces »,
    « jeu » → « jeux », « paire » → « paires »). Prudence : une unité de
    plusieurs mots, abrégée ou déjà terminée par s, x ou z reste inchangée."""

    word = unit.strip()
    if not word or not word.isalpha() or word.casefold() in _INVARIABLE_UNITS:
        return unit
    lower = word.casefold()
    if lower.endswith(("s", "x", "z")):
        return word
    if lower.endswith(("au", "eu")):
        return word + "x"
    return word + "s"


def format_quantity(quantity: int, unit: str) -> str:
    """« 1 pièce », « 26 pièces » : accord en nombre (en français, 0 et 1 au
    singulier, pluriel à partir de 2). L'unité stockée n'est jamais modifiée
    (la colonne ``unite`` du CSV garde la forme d'import, registre §9.1)."""

    unit = unit or ""
    shown = _plural_unit(unit) if abs(quantity) >= 2 else unit
    return f"{quantity} {shown}".strip()


def stock_total_label(totals_by_unit: list[dict]) -> str:
    parts = " · ".join(format_quantity(t["quantity"], t["unit"]) for t in totals_by_unit) or "0"
    return f"{STOCK_TOTAL_LABEL} : {parts}"


def _person_name(membership) -> str:
    return f"{membership.user.first_name} {membership.user.last_name}".strip()


def _donor_name(movement: StockMovement) -> str:
    if movement.donor_membership_id:
        return _person_name(movement.donor_membership)
    return movement.donor_name


def _origin_label(movement: StockMovement) -> str:
    kind = movement.origin_kind
    if kind == StockMovement.OriginKind.DONATION:
        donor = _donor_name(movement)
        return f"Don de {donor}" if donor else "Don"
    if kind == StockMovement.OriginKind.CLUB_FUNDS:
        return "Frais de l'équipe"
    if kind == StockMovement.OriginKind.UNKNOWN:
        return "Origine inconnue"
    return "Origine non renseignée"


def _acquisition_label(movement: StockMovement) -> str:
    if movement.acquisition_date_unknown:
        note = movement.acquisition_date_note
        return f"Date inconnue — {note}" if note else "Date inconnue"
    return _fmt_date(movement.acquisition_date or movement.movement_date)


def _scope_stock(per_holder: dict, holder_filter) -> int:
    if holder_filter is None:
        return sum(per_holder.values())
    if holder_filter == "none":
        return per_holder.get(None, 0)
    return per_holder.get(holder_filter.pk, 0)


def _in_scope(holder_id, holder_filter) -> bool:
    if holder_filter is None:
        return True
    if holder_filter == "none":
        return holder_id is None
    return holder_id == holder_filter.pk


def register_filters_snapshot(*, search: str, category: str, holder_filter, include_exits: bool = False) -> dict:
    return {
        "search": search or "",
        "category": category or "",
        "holder": (
            "none"
            if holder_filter == "none"
            else (holder_filter.pk if isinstance(holder_filter, Holder) else None)
        ),
        "include_exits": bool(include_exits),
    }


def build_register(
    club,
    *,
    search: str = "",
    category: str = "",
    holder_filter=None,
    include_exits: bool = False,
    now: Optional[datetime.datetime] = None,
) -> dict:
    """Données du registre pour le club actif.

    ``holder_filter`` : ``None`` (tous), ``"none"`` (« Non localisé ») ou un ``Holder``.
    """

    today = services.get_club_today(club, now=now)
    wanted = services._normalize_name(search)
    holders_by_id = services.club_holders_by_id()
    bulk = services.bulk_stock_by_holder()
    holder_names = {pk: h.display_name for pk, h in holders_by_id.items()}

    def holder_label(holder_id) -> str:
        return holder_names.get(holder_id, services.UNLOCATED_LABEL) if holder_id is not None else services.UNLOCATED_LABEL

    def matches_search(*texts: str) -> bool:
        return not wanted or any(wanted in services._normalize_name(t) for t in texts)

    entries = (
        StockMovement.objects.filter(movement_type__in=StockMovement.PROVENANCE_TYPES)
        .select_related("article", "donor_membership__user")
        .order_by("movement_date", "pk")
    )
    sections: dict[str, dict] = {}
    for movement in entries:
        article = movement.article
        if category and article.category != category:
            continue
        if not _in_scope(movement.holder_id, holder_filter):
            continue
        per_holder = bulk.get(article.pk, {})
        if not include_exits and _scope_stock(per_holder, holder_filter) <= 0:
            continue
        if not matches_search(article.name, _donor_name(movement)):
            continue
        # État à l'entrée, sinon état de référence de l'article (registre §8.2).
        condition = movement.condition_at_entry
        if not condition or condition == Article.Condition.UNKNOWN:
            condition = article.reference_condition
        section = sections.setdefault(
            article.category,
            {"category": article.category, "category_display": article.get_category_display(), "lines": [], "_articles": {}},
        )
        section["_articles"][article.pk] = article
        section["lines"].append(
            {
                "movement_id": movement.pk,
                "article_id": article.pk,
                "designation": article.name,
                "category": article.category,
                "category_display": article.get_category_display(),
                "unit": article.unit,
                "quantity": movement.quantity,
                "quantity_label": format_quantity(movement.quantity, article.unit),
                "movement_type": movement.movement_type,
                "origin_kind": movement.origin_kind,
                "donor_name": _donor_name(movement),
                "origin": _origin_label(movement),
                "acquisition_date": None if movement.acquisition_date_unknown else (movement.acquisition_date or movement.movement_date),
                "acquisition_date_unknown": movement.acquisition_date_unknown,
                "acquisition_date_note": movement.acquisition_date_note,
                "acquisition_label": _acquisition_label(movement),
                "recorded_on": movement.movement_date,
                "holder_id": movement.holder_id,
                "location": holder_label(movement.holder_id),
                "condition": condition,
                "condition_display": dict(Article.Condition.choices).get(condition, ""),
            }
        )

    ordered = []
    for code in Article.REGISTER_ORDER:
        section = sections.get(code)
        if section is None:
            continue
        section["lines"].sort(
            key=lambda line: (
                line["designation"].casefold(),
                line["acquisition_date"] is None,
                line["acquisition_date"] or datetime.date.min,
                line["movement_id"],
            )
        )
        totals: dict[str, int] = {}
        distribution: dict[Optional[int], int] = {}
        for article in section["_articles"].values():
            per_holder = bulk.get(article.pk, {})
            quantity = _scope_stock(per_holder, holder_filter)
            if quantity > 0:
                totals[article.unit] = totals.get(article.unit, 0) + quantity
            for holder_id, qty in per_holder.items():
                if qty > 0 and _in_scope(holder_id, holder_filter):
                    distribution[holder_id] = distribution.get(holder_id, 0) + qty
        section["stock_total_by_unit"] = [{"unit": unit, "quantity": qty} for unit, qty in totals.items()]
        section["stock_total_label"] = stock_total_label(section["stock_total_by_unit"])
        rows = [
            {"holder_id": hid, "holder_name": holder_label(hid), "quantity": qty} for hid, qty in distribution.items()
        ]
        rows.sort(key=lambda r: (r["holder_id"] is None, -r["quantity"], r["holder_name"].casefold()))
        section["current_distribution"] = rows
        del section["_articles"]
        ordered.append(section)

    decommissions = []
    pending = (
        Decommission.objects.filter(status=Decommission.Status.PENDING)
        .select_related("article")
        .order_by("noted_on", "pk")
    )
    for dec in pending:
        if category and dec.article.category != category:
            continue
        if not _in_scope(dec.holder_id, holder_filter) or not matches_search(dec.article.name):
            continue
        decommissions.append(
            {
                "id": dec.pk,
                "article_id": dec.article_id,
                "designation": dec.article.name,
                "unit": dec.article.unit,
                "quantity": dec.quantity,
                "quantity_label": format_quantity(dec.quantity, dec.article.unit),
                "reason": dec.reason,
                "reason_display": dec.get_reason_display(),
                "reason_note": dec.reason_note,
                "holder_id": dec.holder_id,
                "location": holder_label(dec.holder_id),
                "noted_on": dec.noted_on,
            }
        )

    exits = []
    if include_exits:
        out_qs = (
            StockMovement.objects.filter(movement_type__in=_EXIT_TYPES, movement_date__year=today.year)
            .select_related("article")
            .order_by("movement_date", "pk")
        )
        for movement in out_qs:
            if category and movement.article.category != category:
                continue
            if not _in_scope(movement.holder_id, holder_filter) or not matches_search(movement.article.name):
                continue
            exits.append(
                {
                    "movement_id": movement.pk,
                    "designation": movement.article.name,
                    "unit": movement.article.unit,
                    "quantity": movement.quantity,
                    "quantity_label": format_quantity(movement.quantity, movement.article.unit),
                    "movement_type": movement.movement_type,
                    "movement_type_display": movement.get_movement_type_display(),
                    "movement_date": movement.movement_date,
                    "location": holder_label(movement.holder_id),
                    "reason": movement.reason,
                }
            )

    return {
        "club": {"id": club.pk, "name": club.name},
        "as_of": today,
        "filters": register_filters_snapshot(
            search=search, category=category, holder_filter=holder_filter, include_exits=include_exits
        ),
        "filters_label": _filters_label(search=search, category=category, holder_filter=holder_filter, holder_label=holder_label),
        "include_exits": include_exits,
        "sections": ordered,
        "decommissions": decommissions,
        "exits": exits,
        "is_empty": not ordered,
    }


def _filters_label(*, search: str, category: str, holder_filter, holder_label) -> str:
    parts = []
    if search:
        parts.append(f"recherche « {search} »")
    if category:
        parts.append(f"nature « {dict(Article.Category.choices).get(category, category)} »")
    if holder_filter == "none":
        parts.append(f"détenteur « {services.UNLOCATED_LABEL} »")
    elif isinstance(holder_filter, Holder):
        parts.append(f"détenteur « {holder_filter.display_name} »")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# CSV (mêmes colonnes que l'import du registre, §9.1 / §10.4)
# ---------------------------------------------------------------------------


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def render_register_csv(register: dict) -> bytes:
    """UTF-8 avec BOM (Excel), séparateur « ; »."""

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for section in register["sections"]:
        for line in section["lines"]:
            # Format d'import (registre §9.1, colonne ``origine``) : le texte
            # libre d'un don est le NOM du donateur, que l'import relit en
            # « Don de {texte} ». Écrire « Don de X » ici casserait l'aller-
            # retour exigé au §10.4 (le donateur deviendrait « Don de X »).
            if line["origin_kind"] == StockMovement.OriginKind.DONATION:
                origin = line["donor_name"]
            elif line["origin_kind"] == StockMovement.OriginKind.CLUB_FUNDS:
                origin = "Frais de l'équipe"
            else:
                origin = ""
            if line["acquisition_date_unknown"]:
                acquired = line["acquisition_date_note"]
            else:
                acquired = _fmt_date(line["acquisition_date"])
            condition = "" if line["condition"] == Article.Condition.UNKNOWN else line["condition_display"]
            location = "" if line["holder_id"] is None else line["location"]
            writer.writerow(
                [
                    _csv_safe(line["category_display"]),
                    _csv_safe(line["designation"]),
                    line["quantity"],
                    _csv_safe(line["unit"]),
                    _csv_safe(origin),
                    _csv_safe(acquired),
                    _csv_safe(location),
                    _csv_safe(condition),
                ]
            )
    return ("﻿" + buffer.getvalue()).encode("utf-8")


# ---------------------------------------------------------------------------
# PDF A4 paysage (reportlab), généré par l'API
# ---------------------------------------------------------------------------


def _issuer_label(actor, club) -> str:
    from apps.clubs.models import MembershipRole
    from apps.core.roles import get_active_roles

    if getattr(actor, "is_superuser", False):
        return "Système Vesta"
    name = f"{actor.first_name} {actor.last_name}".strip()
    roles = get_active_roles(actor, club=club)
    labels = [label for code, label in MembershipRole.Role.choices if code in roles]
    return f"{name}, {' / '.join(labels)}" if labels else name


def render_register_pdf(club, register: dict, *, actor, now: Optional[datetime.datetime] = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from apps.core.pdf import (
        DARK_TEXT_RGB,
        MARGIN,
        MUTED_TEXT_RGB,
        NumberedDocumentCanvas,
        draw_continuation_header,
        draw_header,
    )

    now = now or timezone.now()
    page_size = landscape(A4)
    width, height = page_size
    as_of = register["as_of"]
    as_of_text = _fmt_date(as_of)
    issuer = _issuer_label(actor, club)
    doc_label = "INTENDANCE"
    reference = f"Arrêté au {as_of_text}"
    title = f"{club.name} — INTENDANCE"

    body = ParagraphStyle("body", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=colors.Color(*DARK_TEXT_RGB))
    head = ParagraphStyle("head", parent=body, fontName="Helvetica-Bold")
    muted = ParagraphStyle("muted", parent=body, textColor=colors.Color(*MUTED_TEXT_RGB), fontSize=8)
    h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=14, leading=18, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4)

    def p(text, style=body):
        return Paragraph(escape(str(text)), style)

    col_widths = [24 * mm, 52 * mm, 20 * mm, 46 * mm, 36 * mm, 41 * mm, 42 * mm]
    grid = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.94, 0.95)),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.Color(0.6, 0.62, 0.66)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
    )

    story = [p(title, h1)]
    if register["filters_label"]:
        story.append(p(f"Extrait : {register['filters_label']}", muted))
    story.append(Spacer(1, 3 * mm))

    def distribution_text(rows) -> str:
        if not rows:
            return ""
        parts = []
        for row in rows:
            who = row["holder_name"]
            parts.append(f"{who} {row['quantity']}" if row["holder_id"] is None else f"Chez {who} {row['quantity']}")
        return " — ".join(parts)

    group_of = {"jersey": 0, "shorts": 0, "socks": 0, "balls": 1}
    previous_group = None
    first = True
    for section in register["sections"]:
        group = group_of.get(section["category"], 2)
        if not first and group != previous_group:
            story.append(PageBreak())
        first = False
        previous_group = group
        rows = [
            [p(label, head) for label in ("Nature", "Désignation", "Quantité", "Origine", "Date d'acquisition", "Localisation", "État actuel")]
        ]
        for line in section["lines"]:
            rows.append(
                [
                    p(line["category_display"]),
                    p(line["designation"]),
                    p(line["quantity_label"]),
                    p(line["origin"]),
                    p(line["acquisition_label"]),
                    p(line["location"]),
                    p(line["condition_display"]),
                ]
            )
        table = Table(rows, colWidths=col_widths, repeatRows=1)
        table.setStyle(grid)
        story.append(p(section["category_display"], h2))
        story.append(table)
        story.append(Spacer(1, 1.5 * mm))
        story.append(p(section["stock_total_label"], head))
        dist = distribution_text(section["current_distribution"])
        if dist:
            story.append(p(f"Répartition actuelle : {dist}", body))
        story.append(
            p("La localisation de chaque ligne est celle de l'entrée en stock ; la répartition actuelle tient compte des déplacements.", muted)
        )
    if register["is_empty"]:
        story.append(p("Le registre est vide.", body))

    story.append(PageBreak())
    story.append(p("Éléments à déclasser du patrimoine du club", h2))
    if register["decommissions"]:
        rows = [[p(label, head) for label in ("Désignation", "Quantité", "Motif", "Localisation", "Constaté le")]]
        for dec in register["decommissions"]:
            reason = dec["reason_display"] + (f" — {dec['reason_note']}" if dec["reason_note"] else "")
            rows.append(
                [p(dec["designation"]), p(dec["quantity_label"]), p(reason), p(dec["location"]), p(_fmt_date(dec["noted_on"]))]
            )
        table = Table(rows, colWidths=[62 * mm, 24 * mm, 90 * mm, 50 * mm, 35 * mm], repeatRows=1)
        table.setStyle(grid)
        story.append(table)
    else:
        story.append(p("Aucun élément à déclasser.", body))

    if register["include_exits"]:
        story.append(p("Sorties de l'année", h2))
        if register["exits"]:
            rows = [[p(label, head) for label in ("Désignation", "Quantité", "Type", "Date", "Localisation")]]
            for ex in register["exits"]:
                rows.append(
                    [
                        p(ex["designation"]),
                        p(ex["quantity_label"]),
                        p(ex["movement_type_display"]),
                        p(_fmt_date(ex["movement_date"])),
                        p(ex["location"]),
                    ]
                )
            table = Table(rows, colWidths=[62 * mm, 24 * mm, 60 * mm, 35 * mm, 80 * mm], repeatRows=1)
            table.setStyle(grid)
            story.append(table)
        else:
            story.append(p("Aucune sortie cette année.", body))

    def footer(pdf, page_number: int, total_pages: int) -> None:
        pdf.setFillColorRGB(*MUTED_TEXT_RGB)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(MARGIN, 10 * mm, f"Arrêté au {as_of_text} · édité par {issuer} · page {page_number}/{total_pages}")

    def first_page(pdf, doc):
        draw_header(pdf, club=club, doc_type_label=doc_label, reference=reference, width=width, height=height)

    def later_pages(pdf, doc):
        draw_continuation_header(pdf, club=club, doc_type_label=doc_label, reference=reference, width=width, height=height)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=32 * mm,
        bottomMargin=18 * mm,
        title=title,
        author=club.name,
        creator=club.name,
        subject="Registre de l'intendance",
        pageCompression=0,
    )
    doc.build(
        story,
        onFirstPage=first_page,
        onLaterPages=later_pages,
        canvasmaker=partial(NumberedDocumentCanvas, footer_fn=footer),
    )
    return buffer.getvalue()
