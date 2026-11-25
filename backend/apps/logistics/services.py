"""Règles métier de l'app logistics (CDC 4.13 ; tâche 4.3).

Sources : docs/ecrans/logistique.md (spec validée) ; docs/lot0/schema-donnees.md
§7 et §17 ; CLAUDE.md section 5 (règles métier ici, jamais dans les vues).

Décisions par défaut appliquées (points ouverts de la fiche d'écran,
signalées au compte rendu, jamais tranchées ici) :

- **point n° 5** : aucun mouvement de stock n'est modifiable ni
  supprimable une fois enregistré (voir ``models.StockMovement``) ;
- **point n° 9** : la date d'un mouvement ne peut pas être dans le futur
  (fuseau du club) ;
- **point n° 10** : la sortie d'équipements pour un match est
  enregistrée « tout ou rien » : si une ligne est refusée, rien n'est
  créé ;
- **point n° 11** : un inventaire ouvert ne bloque l'ouverture du
  trimestre suivant, et ne déclenche l'alerte hebdomadaire, qu'une fois
  SON propre trimestre terminé (lecture « qui paraît naturelle » de la
  fiche d'écran) ;
- **point n° 6** : l'archivage d'un article est refusé si son stock
  théorique n'est pas nul (position la plus prudente : l'historique ne
  serait sinon plus jamais rapprochable d'un stock physique cohérent).
"""

from __future__ import annotations

import datetime
import unicodedata
import uuid
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from apps.core.services import log_action
from apps.logistics.models import Article, Decommission, Holder, Inventory, InventoryLine, StockMovement

__all__ = [
    "LogisticsError",
    "get_club_today",
    "quarter_label_for_date",
    "quarter_label_ordinal",
    "next_quarter_label",
    "theoretical_quantity",
    "match_equipment_summary",
    "create_article",
    "update_article",
    "archive_article",
    "reactivate_article",
    "record_movement",
    "record_transfer",
    "UNLOCATED_LABEL",
    "holder_stock",
    "stock_by_holder",
    "bulk_stock_by_holder",
    "suggest_holder",
    "holders_overview",
    "holder_holdings",
    "holder_pieces",
    "create_holder",
    "update_holder",
    "archive_holder",
    "flag_decommission",
    "execute_decommission",
    "cancel_decommission",
    "pending_decommission_by_article",
    "recent_provenances",
    "record_match_equipment_out",
    "record_match_equipment_return",
    "get_open_inventory",
    "get_current_quarter_label",
    "get_material_overview",
    "can_open_inventory",
    "open_inventory",
    "record_counts",
    "justify_discrepancy",
    "can_close_inventory",
    "close_inventory",
    "send_inventory_open_alerts",
]


class LogisticsError(Exception):
    """Erreur métier de l'app logistics : refus renvoyé tel quel à l'API."""


# ---------------------------------------------------------------------------
# Fuseau du club et trimestre (même convention qu'apps.sport.services)
# ---------------------------------------------------------------------------


def _club_tz(club) -> ZoneInfo:
    settings_obj = getattr(club, "settings", None)
    tz_name = getattr(settings_obj, "timezone", None) or "UTC"
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise LogisticsError("Le fuseau horaire du club est invalide.") from None


def get_club_today(club, *, now: Optional[datetime.datetime] = None) -> datetime.date:
    now = now or timezone.now()
    return now.astimezone(_club_tz(club)).date()


def quarter_label_for_date(d: datetime.date) -> str:
    quarter = (d.month - 1) // 3 + 1
    return f"{d.year}-Q{quarter}"


_ORDINALS = {1: "1er", 2: "2e", 3: "3e", 4: "4e"}


def quarter_label_ordinal(quarter_label: str) -> str:
    """« 2026-Q3 » -> « 3e trimestre 2026 » (libellé français, fiche §9)."""

    try:
        year_str, q_str = quarter_label.split("-Q")
        quarter = int(q_str)
        year = int(year_str)
    except (ValueError, AttributeError):
        return quarter_label
    return f"{_ORDINALS.get(quarter, f'{quarter}e')} trimestre {year}"


def next_quarter_label(quarter_label: str) -> str:
    try:
        year_str, q_str = quarter_label.split("-Q")
        year = int(year_str)
        quarter = int(q_str)
    except (ValueError, AttributeError):
        return quarter_label
    if quarter >= 4:
        return f"{year + 1}-Q1"
    return f"{year}-Q{quarter + 1}"


def get_current_quarter_label(club, *, now: Optional[datetime.datetime] = None) -> str:
    return quarter_label_for_date(get_club_today(club, now=now))


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


def theoretical_quantity(article: Article, *, at_date: Optional[datetime.date] = None) -> int:
    """Stock théorique = somme signée des mouvements (invariant J1, schema §7.1/§15)."""

    queryset = StockMovement.objects.filter(article=article)
    if at_date is not None:
        queryset = queryset.filter(movement_date__lte=at_date)
    total = 0
    for movement_type, quantity in queryset.values_list("movement_type", "quantity"):
        total += quantity if movement_type in StockMovement.IN_TYPES else -quantity
    return total


def _loaned_and_returned_for_match(match) -> dict[int, dict[str, int]]:
    """Par article : quantité sortie et quantité rendue pour un match donné."""

    result: dict[int, dict[str, int]] = {}
    movements = StockMovement.objects.filter(
        match=match, movement_type__in=(StockMovement.MovementType.OUT_LOAN, StockMovement.MovementType.IN_RETURN)
    ).values_list("article_id", "movement_type", "quantity")
    for article_id, movement_type, quantity in movements:
        entry = result.setdefault(article_id, {"out": 0, "returned": 0})
        if movement_type == StockMovement.MovementType.OUT_LOAN:
            entry["out"] += quantity
        else:
            entry["returned"] += quantity
    return result


def match_equipment_summary(match) -> list[dict]:
    """Ligne par article prêté pour ``match`` (§4.6, §5.2 de la fiche d'écran)."""

    data = _loaned_and_returned_for_match(match)
    articles = Article.all_objects.filter(pk__in=data.keys())
    articles_by_id = {a.pk: a for a in articles}
    lines = []
    for article_id, counts in data.items():
        out_qty = counts["out"]
        returned_qty = counts["returned"]
        remaining = out_qty - returned_qty
        if returned_qty == 0:
            state = "out"
        elif remaining > 0:
            state = "partially_returned"
        else:
            state = "returned"
        lines.append(
            {
                "article": articles_by_id.get(article_id),
                "article_id": article_id,
                "out_quantity": out_qty,
                "returned_quantity": returned_qty,
                "remaining_quantity": remaining,
                "status": state,
                "holder": _match_out_holder(match, articles_by_id[article_id]) if article_id in articles_by_id else None,
            }
        )
    return lines


def _snapshot_article(article: Article) -> dict:
    return {
        "name": article.name,
        "category": article.category,
        "unit": article.unit,
        "reference_condition": article.reference_condition,
        "status": article.status,
    }


DUPLICATE_ARTICLE_NAME_MESSAGE = "Un article porte déjà ce nom dans votre club."


def _ensure_article_name_available(*, club, name: str, exclude_pk=None) -> None:
    """Refuse un nom déjà pris dans le club, sans tenir compte de la casse ni
    des espaces de bord. Comparaison faite ici et non par la base : MySQL
    (collation insensible à la casse) refuserait « test b2 maillot » là où
    SQLite l'accepte ; le comportement ne doit pas dépendre du moteur."""

    wanted = (name or "").strip().casefold()
    queryset = Article.all_objects.filter(club=club)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    if any(existing.strip().casefold() == wanted for existing in queryset.values_list("name", flat=True)):
        raise LogisticsError(DUPLICATE_ARTICLE_NAME_MESSAGE)


def create_article(
    *, club, actor, name: str, category: str, unit: str = "pièce", reference_condition: str = Article.Condition.NEW
) -> Article:
    _ensure_article_name_available(club=club, name=name)
    now = timezone.now()
    article = Article(
        club=club,
        name=name,
        category=category,
        unit=unit or "pièce",
        reference_condition=reference_condition,
        created_at=now,
        created_by=actor,
    )
    article.save()
    log_action(actor=actor, club=club, action_type="logistics.article.created", obj=article, after=_snapshot_article(article))
    return article


def update_article(*, article: Article, actor, **fields) -> Article:
    if fields.get("name") is not None:
        _ensure_article_name_available(club=article.club, name=fields["name"], exclude_pk=article.pk)
    before = _snapshot_article(article)
    for field in ("name", "category", "unit", "reference_condition"):
        if field in fields and fields[field] is not None:
            setattr(article, field, fields[field])
    article.save()
    log_action(
        actor=actor,
        club=article.club,
        action_type="logistics.article.updated",
        obj=article,
        before=before,
        after=_snapshot_article(article),
    )
    return article


def archive_article(*, article: Article, actor, now: Optional[datetime.datetime] = None) -> Article:
    if article.status == Article.Status.ARCHIVED:
        return article
    stock = theoretical_quantity(article)
    if stock != 0:
        raise LogisticsError(
            f"Le stock de « {article.name} » n'est pas nul ({stock} {article.unit}) : archivez-le une fois le "
            "stock ramené à zéro (logistique.md §12 point n° 6)."
        )
    before = _snapshot_article(article)
    now = now or timezone.now()
    article.status = Article.Status.ARCHIVED
    article.archived_at = now
    article.archived_by = actor
    article.save()
    log_action(
        actor=actor,
        club=article.club,
        action_type="logistics.article.archived",
        obj=article,
        before=before,
        after=_snapshot_article(article),
    )
    return article


def reactivate_article(*, article: Article, actor) -> Article:
    if article.status == Article.Status.ACTIVE:
        return article
    before = _snapshot_article(article)
    article.status = Article.Status.ACTIVE
    article.archived_at = None
    article.archived_by = None
    article.save()
    log_action(
        actor=actor,
        club=article.club,
        action_type="logistics.article.reactivated",
        obj=article,
        before=before,
        after=_snapshot_article(article),
    )
    return article


# ---------------------------------------------------------------------------
# Mouvements
# ---------------------------------------------------------------------------


UNLOCATED_LABEL = "Non localisé"


def _snapshot_movement(movement: StockMovement) -> dict:
    return {
        "article_id": movement.article_id,
        "movement_type": movement.movement_type,
        "quantity": movement.quantity,
        "movement_date": movement.movement_date.isoformat(),
        "membership_id": movement.membership_id,
        "match_id": movement.match_id,
        "expense_id": movement.expense_id,
        "holder_id": movement.holder_id,
        "origin_kind": movement.origin_kind,
        "donor_membership_id": movement.donor_membership_id,
        "donor_name": movement.donor_name,
        "acquisition_date": movement.acquisition_date.isoformat() if movement.acquisition_date else None,
        "acquisition_date_unknown": movement.acquisition_date_unknown,
        "acquisition_date_note": movement.acquisition_date_note,
        "condition_at_entry": movement.condition_at_entry,
        "transfer_group": str(movement.transfer_group) if movement.transfer_group else None,
        "decommission_id": movement.decommission_id,
    }


def _normalize_name(text: str) -> str:
    """Casse, accents et espaces ignorés : comparaison faite en Python, jamais
    par la base (le comportement ne doit pas dépendre du moteur)."""

    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


def _lock_article(article: Article) -> None:
    """Verrou de ligne sur l'article (à appeler dans une transaction) pour que
    deux sorties concurrentes ne dépassent pas le stock."""

    Article.all_objects.select_for_update().filter(pk=article.pk).first()


def _holder_name(holder: Optional[Holder]) -> str:
    return holder.display_name if holder is not None else UNLOCATED_LABEL


# ---------------------------------------------------------------------------
# Stock par détenteur (calculé, jamais stocké)
# ---------------------------------------------------------------------------


def holder_stock(article: Article, holder: Optional[Holder] = None) -> int:
    """Stock d'un article chez un détenteur ; ``holder=None`` = « Non localisé »."""

    total = 0
    for movement_type, quantity in StockMovement.objects.filter(article=article, holder=holder).values_list(
        "movement_type", "quantity"
    ):
        total += quantity if movement_type in StockMovement.IN_TYPES else -quantity
    return total


def bulk_stock_by_holder() -> dict[int, dict[Optional[int], int]]:
    """``{article_id: {holder_id|None: quantité}}`` du club actif, en une requête."""

    result: dict[int, dict[Optional[int], int]] = {}
    for article_id, holder_id, movement_type, quantity in StockMovement.objects.values_list(
        "article_id", "holder_id", "movement_type", "quantity"
    ):
        bucket = result.setdefault(article_id, {})
        bucket[holder_id] = bucket.get(holder_id, 0) + (quantity if movement_type in StockMovement.IN_TYPES else -quantity)
    return result


def stock_rows_for(holder_stocks: dict[Optional[int], int], holders_by_id: dict[int, Holder]) -> list[dict]:
    """Lignes non nulles triées par quantité décroissante, « Non localisé » en dernier."""

    rows = []
    for holder_id, quantity in holder_stocks.items():
        if quantity == 0:
            continue
        rows.append({"holder": holders_by_id.get(holder_id) if holder_id is not None else None, "holder_id": holder_id, "quantity": quantity})
    rows.sort(key=lambda r: (r["holder_id"] is None, -r["quantity"], _holder_name(r["holder"]).casefold()))
    return rows


def club_holders_by_id() -> dict[int, Holder]:
    return {h.pk: h for h in Holder.objects.select_related("membership__user")}


def stock_by_holder(article: Article) -> list[dict]:
    stocks = bulk_stock_by_holder().get(article.pk, {})
    return stock_rows_for(stocks, club_holders_by_id())


def suggest_holder(article: Article) -> Optional[Holder]:
    """Détenteur proposé pour une sortie : celui qui a le plus de stock
    (``None`` = « Non localisé », y compris pour un article sans détenteur)."""

    rows = [r for r in stock_by_holder(article) if r["quantity"] > 0]
    return rows[0]["holder"] if rows else None


def holders_overview(*, include_archived: bool = False) -> dict:
    """Carte « Où est le matériel » : détenteurs avec stock calculé + ligne « Non localisé »."""

    holders = list(Holder.objects.select_related("membership__user"))
    if not include_archived:
        holders = [h for h in holders if h.status == Holder.Status.ACTIVE]
    pieces: dict[Optional[int], int] = {}
    articles: dict[Optional[int], int] = {}
    for per_holder in bulk_stock_by_holder().values():
        for holder_id, quantity in per_holder.items():
            if quantity > 0:
                pieces[holder_id] = pieces.get(holder_id, 0) + quantity
                articles[holder_id] = articles.get(holder_id, 0) + 1
    rows = [
        {"holder": h, "stock_total": pieces.get(h.pk, 0), "articles_count": articles.get(h.pk, 0)} for h in holders
    ]
    rows.sort(key=lambda r: (-r["stock_total"], r["holder"].display_name.casefold()))
    return {
        "holders": rows,
        "unlocated": {"stock_total": pieces.get(None, 0), "articles_count": articles.get(None, 0)},
    }


def holder_holdings(holder: Holder) -> list[dict]:
    """Articles détenus (stock > 0) avec la quantité à déclasser."""

    per_article: dict[int, int] = {}
    for article_id, movement_type, quantity in StockMovement.objects.filter(holder=holder).values_list(
        "article_id", "movement_type", "quantity"
    ):
        per_article[article_id] = per_article.get(article_id, 0) + (
            quantity if movement_type in StockMovement.IN_TYPES else -quantity
        )
    articles = {a.pk: a for a in Article.objects.filter(pk__in=per_article.keys())}
    pending: dict[int, int] = {}
    for article_id, quantity in Decommission.objects.filter(holder=holder, status=Decommission.Status.PENDING).values_list(
        "article_id", "quantity"
    ):
        pending[article_id] = pending.get(article_id, 0) + quantity
    rows = [
        {"article": articles[aid], "quantity": qty, "pending_decommission": pending.get(aid, 0)}
        for aid, qty in per_article.items()
        if qty > 0 and aid in articles
    ]
    rows.sort(key=lambda r: (-r["quantity"], r["article"].name.casefold()))
    return rows


def holder_pieces(holder: Holder) -> int:
    return sum(row["quantity"] for row in holder_holdings(holder))


# ---------------------------------------------------------------------------
# Détenteurs
# ---------------------------------------------------------------------------


def _snapshot_holder(holder: Holder) -> dict:
    return {
        "kind": holder.kind,
        "membership_id": holder.membership_id,
        "label": holder.label,
        "status": holder.status,
    }


def _ensure_holder_key_free(*, club, key: str, kind: str, exclude_pk=None) -> None:
    queryset = Holder.all_objects.filter(club=club)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    if any(existing == key for existing in queryset.values_list("holder_key", flat=True)):
        raise LogisticsError("Ce joueur est déjà détenteur." if kind == Holder.Kind.MEMBER else "Ce lieu existe déjà.")


def _clean_place_label(label: str) -> str:
    label = " ".join((label or "").split())
    if not label:
        raise LogisticsError("Ce champ est obligatoire.")
    if len(label) > 60:
        raise LogisticsError("Le nom du lieu ne peut pas dépasser 60 caractères.")
    return label


def create_holder(
    *, club, actor, kind: str, membership=None, label: str = "", now: Optional[datetime.datetime] = None
) -> Holder:
    now = now or timezone.now()
    if kind == Holder.Kind.MEMBER:
        if membership is None:
            raise LogisticsError("Choisissez un joueur.")
        if membership.club_id != club.id or membership.status not in ("active", "pending"):
            raise LogisticsError("Ce joueur n'appartient pas au club actif.")
        key = f"m{membership.pk}"
        label = ""
    elif kind == Holder.Kind.PLACE:
        label = _clean_place_label(label)
        key = f"p:{_normalize_name(label)}"
        membership = None
    else:
        raise LogisticsError("Choisissez un joueur ou un lieu.")
    _ensure_holder_key_free(club=club, key=key, kind=kind)
    holder = Holder(
        club=club, kind=kind, membership=membership, label=label, holder_key=key, created_at=now, created_by=actor
    )
    holder.save()
    log_action(actor=actor, club=club, action_type="logistics.holder.created", obj=holder, after=_snapshot_holder(holder))
    return holder


def update_holder(*, holder: Holder, actor, label: str) -> Holder:
    if holder.kind != Holder.Kind.PLACE:
        raise LogisticsError("Seul le nom d'un lieu peut être modifié.")
    label = _clean_place_label(label)
    key = f"p:{_normalize_name(label)}"
    _ensure_holder_key_free(club=holder.club, key=key, kind=holder.kind, exclude_pk=holder.pk)
    before = _snapshot_holder(holder)
    holder.label = label
    holder.holder_key = key
    holder.save()
    log_action(
        actor=actor,
        club=holder.club,
        action_type="logistics.holder.updated",
        obj=holder,
        before=before,
        after=_snapshot_holder(holder),
    )
    return holder


def archive_holder(*, holder: Holder, actor, now: Optional[datetime.datetime] = None) -> Holder:
    if holder.status == Holder.Status.ARCHIVED:
        return holder
    pieces = holder_pieces(holder)
    if pieces > 0:
        raise LogisticsError(
            f"{holder.display_name} détient encore {pieces} pièce(s) : déplacez-les avant d'archiver."
        )
    before = _snapshot_holder(holder)
    holder.status = Holder.Status.ARCHIVED
    holder.archived_at = now or timezone.now()
    holder.save()
    log_action(
        actor=actor,
        club=holder.club,
        action_type="logistics.holder.archived",
        obj=holder,
        before=before,
        after=_snapshot_holder(holder),
    )
    return holder


# ---------------------------------------------------------------------------
# Mouvements
# ---------------------------------------------------------------------------


def _validate_movement_inputs(
    *, club, article: Article, movement_type: str, quantity: int, movement_date: datetime.date
) -> None:
    if article.club_id != club.id:
        raise LogisticsError("Cet article n'appartient pas au club actif.")
    if article.status != Article.Status.ACTIVE:
        raise LogisticsError("Cet article est archivé : choisissez un article actif.")
    if quantity is None or quantity < 1:
        raise LogisticsError("Saisissez une quantité supérieure à 0.")
    if movement_date is None:
        raise LogisticsError("La date est obligatoire.")
    today = get_club_today(club)
    if movement_date > today:
        raise LogisticsError("La date ne peut pas être dans le futur.")
    if movement_type in StockMovement.OUT_TYPES:
        available = theoretical_quantity(article)
        if quantity > available:
            raise LogisticsError(f"Quantité supérieure au stock disponible ({available}).")


def _validate_holder(*, club, article: Article, holder: Optional[Holder], movement_type: str, quantity: int) -> None:
    if holder is not None:
        if holder.club_id != club.id:
            raise LogisticsError("Ce détenteur n'appartient pas au club actif.")
        if movement_type in StockMovement.IN_TYPES and holder.status != Holder.Status.ACTIVE:
            raise LogisticsError("Ce détenteur est archivé : choisissez un détenteur actif.")
    if movement_type in StockMovement.OUT_TYPES:
        available = holder_stock(article, holder)
        if quantity > available:
            raise LogisticsError(f"Quantité supérieure au stock de {_holder_name(holder)} ({available}).")


def _clean_provenance(*, club, movement_type: str, provenance, movement_date, donor_membership=None) -> dict:
    """Valide le bloc « provenance » d'une entrée (registre §5) et renvoie les
    champs du mouvement. Bloc vide ou absent : ``{}`` (mouvement sans provenance)."""

    provenance = dict(provenance or {})
    meaningful = any(value not in (None, "", False) for value in provenance.values())
    if not meaningful:
        return {}
    if movement_type not in StockMovement.PROVENANCE_TYPES:
        raise LogisticsError(
            "La provenance ne s'applique qu'aux entrées de stock (achat, dotation, reprise du registre)."
        )
    origin = provenance.get("origin_kind") or StockMovement.OriginKind.UNKNOWN
    if origin not in StockMovement.OriginKind.values:
        raise LogisticsError("Choisissez l'origine : don, frais de l'équipe ou inconnue.")
    donor_name = " ".join((provenance.get("donor_name") or "").split())
    if len(donor_name) > 120:
        raise LogisticsError("Le nom du donateur ne peut pas dépasser 120 caractères.")
    if origin == StockMovement.OriginKind.DONATION:
        if donor_membership is None and not donor_name:
            raise LogisticsError("Indiquez le donateur.")
        if donor_membership is not None and donor_membership.club_id != club.id:
            raise LogisticsError("Ce donateur n'appartient pas au club actif.")
    elif donor_membership is not None or donor_name:
        raise LogisticsError("Le donateur ne s'applique qu'à un don.")

    unknown = bool(provenance.get("acquisition_date_unknown"))
    acquisition_date = provenance.get("acquisition_date")
    note = " ".join((provenance.get("acquisition_date_note") or "").split())
    if len(note) > 60:
        raise LogisticsError("La précision sur la date ne peut pas dépasser 60 caractères.")
    if unknown and acquisition_date is not None:
        raise LogisticsError("Une date inconnue ne peut pas être accompagnée d'une date d'acquisition.")
    if note and not unknown:
        raise LogisticsError("La précision ne s'applique qu'à une date d'acquisition inconnue.")
    if acquisition_date is not None:
        if acquisition_date > get_club_today(club):
            raise LogisticsError("La date ne peut pas être dans le futur.")
        if acquisition_date > movement_date:
            raise LogisticsError("La date d'acquisition ne peut pas être postérieure à la date d'enregistrement.")

    condition = provenance.get("condition_at_entry") or Article.Condition.UNKNOWN
    if condition not in Article.Condition.values:
        raise LogisticsError("Choisissez l'état à l'entrée.")
    return {
        "origin_kind": origin,
        "donor_membership": donor_membership,
        "donor_name": donor_name,
        "acquisition_date": acquisition_date,
        "acquisition_date_unknown": unknown,
        "acquisition_date_note": note,
        "condition_at_entry": condition,
    }


def _new_movement(**fields) -> StockMovement:
    movement = StockMovement(**fields)
    movement.save()
    return movement


def record_movement(
    *,
    club,
    actor,
    movement_type: str,
    article: Article,
    quantity: int,
    movement_date: datetime.date,
    reason: str = "",
    membership=None,
    match=None,
    expense=None,
    holder: Optional[Holder] = None,
    provenance: Optional[dict] = None,
    donor_membership=None,
    now: Optional[datetime.datetime] = None,
) -> StockMovement:
    if movement_type not in StockMovement.MANUAL_TYPES:
        raise LogisticsError("Ce type de mouvement se saisit depuis son écran dédié (déplacement ou déclassement).")
    now = now or timezone.now()
    with transaction.atomic():
        _lock_article(article)
        _validate_movement_inputs(
            club=club, article=article, movement_type=movement_type, quantity=quantity, movement_date=movement_date
        )
        _validate_holder(club=club, article=article, holder=holder, movement_type=movement_type, quantity=quantity)
        provenance_fields = _clean_provenance(
            club=club,
            movement_type=movement_type,
            provenance=provenance,
            movement_date=movement_date,
            donor_membership=donor_membership,
        )
        movement = _new_movement(
            club=club,
            article=article,
            movement_type=movement_type,
            quantity=quantity,
            movement_date=movement_date,
            reason=reason or "",
            membership=membership,
            match=match,
            expense=expense,
            holder=holder,
            recorded_by=actor,
            created_at=now,
            **provenance_fields,
        )
        log_action(
            actor=actor,
            club=club,
            action_type="logistics.stock_movement.created",
            obj=movement,
            after=_snapshot_movement(movement),
        )
    return movement


def record_transfer(
    *,
    club,
    actor,
    article: Article,
    source: Optional[Holder],
    destination: Optional[Holder],
    quantity: int,
    movement_date: datetime.date,
    reason: str = "",
    now: Optional[datetime.datetime] = None,
) -> tuple[StockMovement, StockMovement]:
    """Déplace du matériel d'un détenteur (``None`` = « Non localisé ») à un autre :
    une sortie « Transfert » et une entrée « Transfert reçu » liées par
    ``transfer_group``. Le stock total de l'article ne change pas."""

    if destination is None:
        raise LogisticsError("Choisissez le nouveau détenteur.")
    if source is not None and source.pk == destination.pk:
        raise LogisticsError("Le détenteur d'arrivée doit être différent du détenteur de départ.")
    for holder in (source, destination):
        if holder is not None and holder.club_id != club.id:
            raise LogisticsError("Ce détenteur n'appartient pas au club actif.")
    if destination.status != Holder.Status.ACTIVE:
        raise LogisticsError("Ce détenteur est archivé : choisissez un détenteur actif.")
    now = now or timezone.now()
    with transaction.atomic():
        _lock_article(article)
        _validate_movement_inputs(
            club=club,
            article=article,
            movement_type=StockMovement.MovementType.IN_TRANSFER,
            quantity=quantity,
            movement_date=movement_date,
        )
        available = holder_stock(article, source)
        if quantity > available:
            raise LogisticsError(f"Quantité supérieure au stock de {_holder_name(source)} ({available}).")
        group = uuid.uuid4()
        common = dict(
            club=club,
            article=article,
            quantity=quantity,
            movement_date=movement_date,
            reason=reason or "",
            transfer_group=group,
            recorded_by=actor,
            created_at=now,
        )
        out_movement = _new_movement(movement_type=StockMovement.MovementType.OUT_TRANSFER, holder=source, **common)
        in_movement = _new_movement(movement_type=StockMovement.MovementType.IN_TRANSFER, holder=destination, **common)
        log_action(
            actor=actor,
            club=club,
            action_type="logistics.transfer.created",
            obj=out_movement,
            after={
                "article_id": article.pk,
                "quantity": quantity,
                "movement_date": movement_date.isoformat(),
                "from_holder_id": source.pk if source else None,
                "to_holder_id": destination.pk,
                "transfer_group": str(group),
                "out_movement_id": out_movement.pk,
                "in_movement_id": in_movement.pk,
            },
        )
    return out_movement, in_movement


def _match_out_holder(match, article: Article) -> Optional[Holder]:
    """Détenteur de la sortie d'un match (par défaut du retour) : celui de la
    plus grosse sortie de l'article pour ce match."""

    per_holder: dict[Optional[int], int] = {}
    for holder_id, quantity in StockMovement.objects.filter(
        match=match, article=article, movement_type=StockMovement.MovementType.OUT_LOAN
    ).values_list("holder_id", "quantity"):
        per_holder[holder_id] = per_holder.get(holder_id, 0) + quantity
    if not per_holder:
        return None
    best = max(per_holder.items(), key=lambda item: item[1])[0]
    return Holder.objects.filter(pk=best).first() if best is not None else None


def record_match_equipment_out(
    *, club, actor, match, lines: Iterable[dict], now: Optional[datetime.datetime] = None
) -> list[StockMovement]:
    """Sortie « tout ou rien » (fiche §4.5, point ouvert n° 10) : si une ligne
    est refusée (stock insuffisant, article archivé), rien n'est enregistré.

    Une ligne peut porter ``holder`` (détenteur source, ``None`` = « Non
    localisé ») ; sans cette clé, la sortie se fait chez le détenteur qui a le
    plus de stock (``suggest_holder``)."""

    lines = list(lines)
    if not lines:
        raise LogisticsError("Ajoutez au moins un article.")
    today = get_club_today(club)
    with transaction.atomic():
        created = []
        for line in lines:
            article = line["article"]
            quantity = line["quantity"]
            holder = line["holder"] if "holder" in line else suggest_holder(article)
            movement = record_movement(
                club=club,
                actor=actor,
                movement_type=StockMovement.MovementType.OUT_LOAN,
                article=article,
                quantity=quantity,
                movement_date=today,
                match=match,
                holder=holder,
                now=now,
            )
            created.append(movement)
        return created


def record_match_equipment_return(
    *, club, actor, match, lines: Iterable[dict], observation: str = "", now: Optional[datetime.datetime] = None
) -> list[StockMovement]:
    today = get_club_today(club)
    summary = {row["article_id"]: row for row in match_equipment_summary(match)}
    lines = list(lines)
    if not lines:
        raise LogisticsError("Ajoutez au moins un article rendu.")
    with transaction.atomic():
        created = []
        for line in lines:
            article = line["article"]
            quantity_returned = line["quantity_returned"]
            row = summary.get(article.pk)
            remaining = row["remaining_quantity"] if row else 0
            if quantity_returned < 0 or quantity_returned > remaining:
                raise LogisticsError(
                    f"La quantité rendue ne peut pas dépasser la quantité sortie ({remaining})."
                )
            if quantity_returned == 0:
                continue
            holder = line["holder"] if "holder" in line else _match_out_holder(match, article)
            movement = record_movement(
                club=club,
                actor=actor,
                movement_type=StockMovement.MovementType.IN_RETURN,
                article=article,
                quantity=quantity_returned,
                movement_date=today,
                match=match,
                holder=holder,
                reason=observation or "",
                now=now,
            )
            created.append(movement)
        if not created:
            raise LogisticsError("Ajoutez au moins un article rendu.")
        return created


# ---------------------------------------------------------------------------
# Déclassement en deux temps (registre de l'intendance §7)
# ---------------------------------------------------------------------------


def _snapshot_decommission(decommission: Decommission) -> dict:
    return {
        "article_id": decommission.article_id,
        "holder_id": decommission.holder_id,
        "quantity": decommission.quantity,
        "reason": decommission.reason,
        "reason_note": decommission.reason_note,
        "noted_on": decommission.noted_on.isoformat(),
        "status": decommission.status,
        "exit_date": decommission.exit_date.isoformat() if decommission.exit_date else None,
        "exit_destination": decommission.exit_destination,
        "exit_movement_id": decommission.exit_movement_id,
        "cancel_reason": decommission.cancel_reason,
    }


def pending_decommission_by_article() -> dict[int, int]:
    result: dict[int, int] = {}
    for article_id, quantity in Decommission.objects.filter(status=Decommission.Status.PENDING).values_list(
        "article_id", "quantity"
    ):
        result[article_id] = result.get(article_id, 0) + quantity
    return result


def _pending_decommission_quantity(article: Article, holder: Optional[Holder]) -> int:
    return sum(
        Decommission.objects.filter(article=article, holder=holder, status=Decommission.Status.PENDING).values_list(
            "quantity", flat=True
        )
    )


def flag_decommission(
    *,
    club,
    actor,
    article: Article,
    quantity: int,
    reason: str,
    noted_on: datetime.date,
    reason_note: str = "",
    holder: Optional[Holder] = None,
    now: Optional[datetime.datetime] = None,
) -> Decommission:
    """Signale des pièces à déclasser. Le stock ne change PAS."""

    if article.club_id != club.id:
        raise LogisticsError("Cet article n'appartient pas au club actif.")
    if article.status != Article.Status.ACTIVE:
        raise LogisticsError("Cet article est archivé : choisissez un article actif.")
    if holder is not None and holder.club_id != club.id:
        raise LogisticsError("Ce détenteur n'appartient pas au club actif.")
    if quantity is None or quantity < 1:
        raise LogisticsError("Saisissez une quantité supérieure à 0.")
    if reason not in Decommission.Reason.values:
        raise LogisticsError("Choisissez le motif.")
    reason_note = " ".join((reason_note or "").split())
    if reason == Decommission.Reason.OTHER and not reason_note:
        raise LogisticsError("Précisez le motif.")
    if len(reason_note) > 500:
        raise LogisticsError("La précision ne peut pas dépasser 500 caractères.")
    if noted_on is None:
        raise LogisticsError("La date du constat est obligatoire.")
    if noted_on > get_club_today(club):
        raise LogisticsError("La date ne peut pas être dans le futur.")
    now = now or timezone.now()
    with transaction.atomic():
        _lock_article(article)
        available = max(holder_stock(article, holder) - _pending_decommission_quantity(article, holder), 0)
        if quantity > available:
            raise LogisticsError(f"Il ne reste que {available} {article.unit} chez {_holder_name(holder)}.")
        decommission = Decommission(
            club=club,
            article=article,
            holder=holder,
            quantity=quantity,
            reason=reason,
            reason_note=reason_note,
            noted_on=noted_on,
            noted_by=actor,
            created_at=now,
        )
        decommission.save()
        log_action(
            actor=actor,
            club=club,
            action_type="logistics.decommission.flagged",
            obj=decommission,
            after=_snapshot_decommission(decommission),
        )
    return decommission


def execute_decommission(
    *,
    decommission: Decommission,
    actor,
    exit_date: datetime.date,
    destination: str = "",
    confirm: bool = False,
    now: Optional[datetime.datetime] = None,
) -> Decommission:
    """Sort réellement le stock : crée la sortie « Déclassement », après
    confirmation explicite."""

    if not confirm:
        raise LogisticsError("Confirmez la sortie du stock.")
    club = decommission.club
    destination = " ".join((destination or "").split())
    if len(destination) > 120:
        raise LogisticsError("La destination ne peut pas dépasser 120 caractères.")
    if exit_date is None:
        raise LogisticsError("La date de sortie est obligatoire.")
    if exit_date > get_club_today(club):
        raise LogisticsError("La date ne peut pas être dans le futur.")
    now = now or timezone.now()
    with transaction.atomic():
        fresh = Decommission.all_objects.select_for_update().get(pk=decommission.pk)
        if fresh.status != Decommission.Status.PENDING:
            raise LogisticsError("Ce signalement n'est plus en attente.")
        if exit_date < fresh.noted_on:
            raise LogisticsError("La date de sortie ne peut pas être antérieure au constat.")
        article = fresh.article
        _lock_article(article)
        total = theoretical_quantity(article)
        available = holder_stock(article, fresh.holder)
        if fresh.quantity > total or fresh.quantity > available:
            raise LogisticsError(
                f"Il ne reste que {max(min(available, total), 0)} {article.unit} chez {_holder_name(fresh.holder)}."
            )
        label = fresh.get_reason_display()
        parts = [f"Déclassement : {label}"]
        if fresh.reason_note:
            parts.append(fresh.reason_note)
        if destination:
            parts.append(f"Destination : {destination}")
        movement = _new_movement(
            club=club,
            article=article,
            movement_type=StockMovement.MovementType.OUT_DECOMMISSION,
            quantity=fresh.quantity,
            movement_date=exit_date,
            reason=" — ".join(parts),
            holder=fresh.holder,
            decommission=fresh,
            recorded_by=actor,
            created_at=now,
        )
        before = _snapshot_decommission(fresh)
        fresh.status = Decommission.Status.DONE
        fresh.exit_date = exit_date
        fresh.exit_destination = destination
        fresh.exit_movement = movement
        fresh.executed_by = actor
        fresh.save()
        log_action(
            actor=actor,
            club=club,
            action_type="logistics.decommission.executed",
            obj=fresh,
            before=before,
            after=_snapshot_decommission(fresh),
        )
    return fresh


def cancel_decommission(
    *, decommission: Decommission, actor, reason: str, now: Optional[datetime.datetime] = None
) -> Decommission:
    reason = " ".join((reason or "").split())
    if not reason:
        raise LogisticsError("Indiquez le motif de l'annulation.")
    if len(reason) > 500:
        raise LogisticsError("Le motif ne peut pas dépasser 500 caractères.")
    now = now or timezone.now()
    with transaction.atomic():
        fresh = Decommission.all_objects.select_for_update().get(pk=decommission.pk)
        if fresh.status != Decommission.Status.PENDING:
            raise LogisticsError("Ce signalement n'est plus en attente.")
        before = _snapshot_decommission(fresh)
        fresh.status = Decommission.Status.CANCELLED
        fresh.cancelled_at = now
        fresh.cancelled_by = actor
        fresh.cancel_reason = reason
        fresh.save()
        log_action(
            actor=actor,
            club=fresh.club,
            action_type="logistics.decommission.cancelled",
            obj=fresh,
            before=before,
            after=_snapshot_decommission(fresh),
        )
    return fresh


def recent_provenances(article: Article, limit: int = 5) -> list[StockMovement]:
    """Dernières entrées (achat, dotation, reprise du registre) d'un article."""

    return list(
        StockMovement.objects.filter(article=article, movement_type__in=StockMovement.PROVENANCE_TYPES)
        .select_related("holder__membership__user", "donor_membership__user")
        .order_by("-movement_date", "-created_at", "-pk")[:limit]
    )


# ---------------------------------------------------------------------------
# Inventaire trimestriel (CDC 4.13, §6 de la fiche d'écran)
# ---------------------------------------------------------------------------


def get_open_inventory(club) -> Optional[Inventory]:
    return Inventory.objects.filter(status=Inventory.Status.OPEN).order_by("-opened_at").first()


def get_material_overview(club, *, now: Optional[datetime.datetime] = None) -> dict:
    """État global consommé par le bandeau §6.1 et la carte §6.2."""

    current_label = get_current_quarter_label(club, now=now)
    open_inventory = get_open_inventory(club)
    last_closed = Inventory.objects.filter(status=Inventory.Status.CLOSED).order_by("-closed_at").first()

    if open_inventory is None:
        already_done = Inventory.objects.filter(quarter_label=current_label).exists()
        return {
            "current_quarter_label": current_label,
            "open_inventory": None,
            "blocking": False,
            "to_count": 0,
            "to_justify": 0,
            "counted": 0,
            "total_active_articles": Article.objects.filter(status=Article.Status.ACTIVE).count(),
            "can_open": not already_done,
            "openable_quarter_label": None if already_done else current_label,
            "last_closed_inventory": last_closed,
        }

    to_count, to_justify, counted = _inventory_progress(open_inventory)
    # Point ouvert n° 11 : le blocage/l'alerte ne s'appliquent qu'une fois le
    # trimestre PROPRE à l'inventaire ouvert terminé (lecture « naturelle »).
    blocking = open_inventory.quarter_label != current_label

    return {
        "current_quarter_label": current_label,
        "open_inventory": open_inventory,
        "blocking": blocking,
        "to_count": to_count,
        "to_justify": to_justify,
        "counted": counted,
        "total_active_articles": Article.objects.filter(status=Article.Status.ACTIVE).count(),
        "can_open": False,
        "openable_quarter_label": None,
        "last_closed_inventory": last_closed,
    }


def _inventory_progress(inventory: Inventory) -> tuple[int, int, int]:
    total_active = Article.objects.filter(status=Article.Status.ACTIVE).count()
    lines = InventoryLine.objects.filter(inventory=inventory)
    counted = lines.count()
    to_count = max(total_active - counted, 0)
    to_justify = sum(1 for discrepancy, reason in lines.values_list("discrepancy", "discrepancy_reason") if discrepancy != 0 and not reason)
    return to_count, to_justify, counted


def can_open_inventory(club) -> tuple[bool, str]:
    if get_open_inventory(club) is not None:
        return False, "Un inventaire est déjà ouvert : clôturez-le avant d'en ouvrir un autre."
    return True, ""


def open_inventory(*, club, actor, now: Optional[datetime.datetime] = None) -> Inventory:
    ok, reason = can_open_inventory(club)
    if not ok:
        raise LogisticsError(reason)
    now = now or timezone.now()
    label = get_current_quarter_label(club, now=now)
    if Inventory.objects.filter(quarter_label=label).exists():
        raise LogisticsError("L'inventaire de ce trimestre a déjà été réalisé : le prochain pourra être ouvert au trimestre suivant.")
    inventory = Inventory(club=club, quarter_label=label, opened_at=now, opened_by=actor)
    inventory.save()
    log_action(
        actor=actor,
        club=club,
        action_type="logistics.inventory.opened",
        obj=inventory,
        after={"quarter_label": inventory.quarter_label},
    )
    return inventory


def record_counts(
    *, inventory: Inventory, actor, counts: Iterable[dict], now: Optional[datetime.datetime] = None
) -> list[InventoryLine]:
    if inventory.status != Inventory.Status.OPEN:
        raise LogisticsError("Cet inventaire est clôturé : le comptage n'est plus modifiable.")
    now = now or timezone.now()
    today = get_club_today(inventory.club, now=now)
    result = []
    with transaction.atomic():
        for entry in counts:
            article = entry["article"]
            physical_quantity = entry["physical_quantity"]
            if article.club_id != inventory.club_id or article.status != Article.Status.ACTIVE:
                raise LogisticsError("Article invalide pour cet inventaire.")
            if physical_quantity is None or physical_quantity < 0:
                raise LogisticsError("Saisissez un nombre entier supérieur ou égal à 0.")
            theoretical = theoretical_quantity(article, at_date=today)
            discrepancy = physical_quantity - theoretical
            line = InventoryLine.all_objects.filter(inventory=inventory, article=article).first()
            if line is None:
                line = InventoryLine(
                    club=inventory.club,
                    inventory=inventory,
                    article=article,
                    theoretical_quantity=theoretical,
                    physical_quantity=physical_quantity,
                    discrepancy=discrepancy,
                    counted_at=now,
                    counted_by=actor,
                )
            else:
                discrepancy_changed = discrepancy != line.discrepancy
                line.theoretical_quantity = theoretical
                line.physical_quantity = physical_quantity
                line.discrepancy = discrepancy
                line.counted_at = now
                line.counted_by = actor
                if discrepancy_changed and line.justified_at is not None:
                    # Point ouvert n° 8 : le comptage change -> la justification
                    # existante est effacée, la ligne repasse « à justifier ».
                    line.discrepancy_reason = ""
                    line.justified_by = None
                    line.justified_at = None
                if discrepancy == 0:
                    line.discrepancy_reason = ""
                    line.justified_by = None
                    line.justified_at = None
            line.save()
            result.append(line)
    log_action(
        actor=actor,
        club=inventory.club,
        action_type="logistics.inventory.counted",
        obj=inventory,
        after={"lines_counted": len(result)},
    )
    return result


def justify_discrepancy(
    *, line: InventoryLine, actor, reason: str, now: Optional[datetime.datetime] = None
) -> InventoryLine:
    if line.inventory.status != Inventory.Status.OPEN:
        raise LogisticsError("Cet inventaire est clôturé : la justification n'est plus modifiable.")
    if line.discrepancy == 0:
        raise LogisticsError("Cette ligne n'a pas d'écart à justifier.")
    if reason not in InventoryLine.DiscrepancyReason.values:
        raise LogisticsError("Choisissez la cause de l'écart.")
    now = now or timezone.now()
    before = {"discrepancy_reason": line.discrepancy_reason, "justified_at": bool(line.justified_at)}
    line.discrepancy_reason = reason
    line.justified_by = actor
    line.justified_at = now
    line.save()
    log_action(
        actor=actor,
        club=line.club,
        action_type="logistics.inventory_line.justified",
        obj=line,
        before=before,
        after={"discrepancy_reason": line.discrepancy_reason},
    )
    return line


def can_close_inventory(inventory: Inventory) -> tuple[bool, str]:
    if inventory.status != Inventory.Status.OPEN:
        return False, "Cet inventaire est déjà clôturé."
    to_count, to_justify, _counted = _inventory_progress(inventory)
    if to_count or to_justify:
        return False, f"Comptez tous les articles et justifiez chaque écart avant de clôturer. ({to_count} à compter, {to_justify} à justifier)"
    return True, ""


def close_inventory(*, inventory: Inventory, actor, now: Optional[datetime.datetime] = None) -> Inventory:
    ok, reason = can_close_inventory(inventory)
    if not ok:
        raise LogisticsError(reason)
    now = now or timezone.now()
    inventory.status = Inventory.Status.CLOSED
    inventory.closed_at = now
    inventory.closed_by = actor
    inventory.save()
    log_action(
        actor=actor,
        club=inventory.club,
        action_type="logistics.inventory.closed",
        obj=inventory,
        after={"status": inventory.status},
    )
    return inventory


# ---------------------------------------------------------------------------
# Alerte hebdomadaire au Président (CDC 4.13 ; schema §17 `inventory_open_alert`)
# ---------------------------------------------------------------------------


def send_inventory_open_alerts(*, club, now: Optional[datetime.datetime] = None) -> int:
    """Notifie le Président (une fois par semaine, cron) tant que l'inventaire
    bloquant reste ouvert (§6.3 de la fiche d'écran). N'écrit jamais sur
    ``Inventory`` (schema §17 : « Notification uniquement »): la cadence
    hebdomadaire est assurée en ne renvoyant pas de notification si la
    dernière alerte de ce type pour ce club date de moins de 7 jours.

    Renvoie 1 si une alerte a été envoyée, 0 sinon (club sans blocage, ou
    déjà alerté cette semaine, ou club sans Président).
    """

    from apps.clubs.models import MembershipRole
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    now = now or timezone.now()
    overview = get_material_overview(club, now=now)
    if not overview["blocking"]:
        return 0

    president_role = (
        MembershipRole.objects.filter(
            club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        )
        .select_related("membership__user")
        .first()
    )
    if president_role is None:
        return 0
    president_user = president_role.membership.user

    week_ago = now - datetime.timedelta(days=7)
    already_alerted = Notification.objects.filter(
        club=club,
        recipient=president_user,
        event_type=Notification.EventType.INVENTORY_OPEN_ALERT,
        created_at__gte=week_ago,
    ).exists()
    if already_alerted:
        return 0

    label = quarter_label_ordinal(overview["open_inventory"].quarter_label)
    create_notification(
        recipient=president_user,
        event_type=Notification.EventType.INVENTORY_OPEN_ALERT,
        title=f"Inventaire du {label} non clôturé",
        message=(
            f"L'inventaire du {label} est toujours ouvert ({overview['to_count']} article(s) à compter, "
            f"{overview['to_justify']} écart(s) à justifier). L'inventaire suivant ne peut pas être ouvert "
            "tant qu'il n'est pas clôturé."
        ),
        club=club,
        target=overview["open_inventory"],
        now=now,
    )
    return 1
