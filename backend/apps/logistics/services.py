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
from typing import Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from apps.core.services import log_action
from apps.logistics.models import Article, Inventory, InventoryLine, StockMovement

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


def create_article(
    *, club, actor, name: str, category: str, unit: str = "pièce", reference_condition: str = Article.Condition.NEW
) -> Article:
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


def _snapshot_movement(movement: StockMovement) -> dict:
    return {
        "article_id": movement.article_id,
        "movement_type": movement.movement_type,
        "quantity": movement.quantity,
        "movement_date": movement.movement_date.isoformat(),
        "membership_id": movement.membership_id,
        "match_id": movement.match_id,
        "expense_id": movement.expense_id,
    }


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
    now: Optional[datetime.datetime] = None,
) -> StockMovement:
    _validate_movement_inputs(
        club=club, article=article, movement_type=movement_type, quantity=quantity, movement_date=movement_date
    )
    now = now or timezone.now()
    movement = StockMovement(
        club=club,
        article=article,
        movement_type=movement_type,
        quantity=quantity,
        movement_date=movement_date,
        reason=reason or "",
        membership=membership,
        match=match,
        expense=expense,
        recorded_by=actor,
        created_at=now,
    )
    movement.save()
    log_action(
        actor=actor,
        club=club,
        action_type="logistics.stock_movement.created",
        obj=movement,
        after=_snapshot_movement(movement),
    )
    return movement


def record_match_equipment_out(
    *, club, actor, match, lines: Iterable[dict], now: Optional[datetime.datetime] = None
) -> list[StockMovement]:
    """Sortie « tout ou rien » (fiche §4.5, point ouvert n° 10) : si une ligne
    est refusée (stock insuffisant, article archivé), rien n'est enregistré."""

    lines = list(lines)
    if not lines:
        raise LogisticsError("Ajoutez au moins un article.")
    today = get_club_today(club)
    with transaction.atomic():
        created = []
        for line in lines:
            article = line["article"]
            quantity = line["quantity"]
            movement = record_movement(
                club=club,
                actor=actor,
                movement_type=StockMovement.MovementType.OUT_LOAN,
                article=article,
                quantity=quantity,
                movement_date=today,
                match=match,
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
            movement = record_movement(
                club=club,
                actor=actor,
                movement_type=StockMovement.MovementType.IN_RETURN,
                article=article,
                quantity=quantity_returned,
                movement_date=today,
                match=match,
                reason=observation or "",
                now=now,
            )
            created.append(movement)
        if not created:
            raise LogisticsError("Ajoutez au moins un article rendu.")
        return created


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
        return {
            "current_quarter_label": current_label,
            "open_inventory": None,
            "blocking": False,
            "to_count": 0,
            "to_justify": 0,
            "counted": 0,
            "total_active_articles": Article.objects.filter(status=Article.Status.ACTIVE).count(),
            "can_open": True,
            "openable_quarter_label": current_label,
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
