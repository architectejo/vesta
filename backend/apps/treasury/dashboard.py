"""Tableau de bord du Président et du Vice-président : partie financière.

Fiche d'écran ``docs/ecrans/club-tableau-de-bord-bureau.md`` (cartes 2
Cotisations, 6 Situation de l'effectif, 7 Caisse, 8 Dépenses par catégorie,
§5 modales, §10 « Contrat API financier ») ; CDC 4.4.2, 4.4.6, 4.5 ;
CLAUDE.md règles 2 (solde toujours calculé) et 3 (cotisation libre jamais
en dette).

**Fonctions pures de lecture** : aucune écriture, aucun journal (la
consultation n'est pas journalisée, fiche §9), aucune vue ni URL (l'endpoint
est branché dans ``apps.clubs``, qui contrôle la permission Président / VP).

Une seule source de vérité : l'encaissé, le taux de recouvrement, le solde
et la caisse disponible réutilisent les définitions de
``apps.treasury.services`` (``_collected_transactions``,
``_matured_dues_coverage``, ``_balance_aggregates``, ``get_available_cash``,
``can_release_expense``) ; les chiffres sont donc égaux à ceux de la page
Trésorerie pour la même période (critère d'acceptation, fiche §9).

Étanchéité : chaque requête est filtrée explicitement sur le club passé en
paramètre (``for_club`` / ``club=``) et un club actif différent est refusé
(``TenantMismatchError``). Montants en ``Decimal``, sérialisés en chaînes à
2 décimales, devise du club. Requêtes agrégées : le nombre de requêtes ne
dépend pas du nombre de joueurs ni de transactions.

Période (même contrat que le ``PeriodPicker`` du frontend) :
``{"mode": "month", "month": "AAAA-MM"}`` ou
``{"mode": "season", "season_id": int}`` ; ``None`` = mois en cours dans le
fuseau du club. Une saison est arrondie aux mois entiers (du premier jour
de son mois de début au dernier jour de son mois de fin).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Optional

from django.db.models import Count, Exists, F, OuterRef, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.clubs.models import Membership, Season
from apps.treasury import services as svc
from apps.treasury.models import ContributionType, Due, Expense, Payment, PaymentReversal, Transaction

logger = logging.getLogger(__name__)

FINANCE_SECTIONS = ("contributions", "squad_status", "cash", "expenses_by_category", "upcoming_finance")
SERIES_MONTHS = 12
CARD_TOP_CATEGORIES = 5
CARD_UPCOMING_ITEMS = 5
UPCOMING_DAYS = 30
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

SECTION_ERRORS = {
    "contributions": "Impossible de charger les cotisations.",
    "squad_status": "Impossible de charger la situation de l'effectif.",
    "cash": "Impossible de charger la caisse.",
    "expenses_by_category": "Impossible de charger les dépenses.",
    "upcoming_finance": "Impossible de charger les échéances.",
}

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Outils de format
# ---------------------------------------------------------------------------


def _money(value) -> str:
    return f"{svc._quantize(value):.2f}"


def _rate(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else f"{value:.2f}"


def _share(count: int, total: int) -> Optional[str]:
    if total <= 0:
        return None
    return f"{(Decimal(count) * 100 / Decimal(total)).quantize(svc.MONEY_QUANTUM, rounding=ROUND_HALF_UP):.2f}"


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _month_end(value: date) -> date:
    return svc._next_period(value) - timedelta(days=1)


def _previous_period(value: date) -> date:
    return (svc._period_start(value) - timedelta(days=1)).replace(day=1)


def _as_month(value) -> Optional[date]:
    """``TruncMonth`` renvoie une date (ou une date-heure selon le moteur)."""

    if value is None:
        return None
    if hasattr(value, "date") and callable(value.date):
        value = value.date()
    return svc._period_start(value)


# ---------------------------------------------------------------------------
# Période
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Period:
    mode: str
    month: Optional[date]
    season: Optional[Season]
    start: date  # premier jour du premier mois
    end: date  # dernier jour du dernier mois (inclus)
    months: tuple  # mois de la série (jamais de mois futur)

    @property
    def end_exclusive(self) -> date:
        return self.end + timedelta(days=1)

    @property
    def query_start(self) -> date:
        return min(self.start, self.months[0]) if self.months else self.start

    def contains(self, month: date) -> bool:
        return self.start <= month < self.end_exclusive

    def as_json(self) -> dict:
        if self.mode == "month":
            label = svc.french_month_label(self.start)
        else:
            label = f"Saison {self.season.label}"
        return {
            "mode": self.mode,
            "month": _month_key(self.month) if self.month else None,
            "season_id": self.season.pk if self.season else None,
            "label": label,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "months": [_month_key(m) for m in self.months],
        }


def _parse_month(value: Any) -> date:
    message = "Le mois demandé est invalide (format attendu : AAAA-MM)."
    match = _MONTH_RE.match(value) if isinstance(value, str) else None
    if not match:
        raise svc.TreasuryValidationError(message)
    year, month = int(match.group(1)), int(match.group(2))
    if not (1 <= month <= 12) or year < 1900:
        raise svc.TreasuryValidationError(message)
    return date(year, month, 1)


def _parse_season_id(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _resolve_period(club, period: Optional[dict], today: date) -> _Period:
    current = svc._period_start(today)
    period = period or {}
    if not isinstance(period, dict):
        raise svc.TreasuryValidationError("Le type de période est invalide (« month » ou « season »).")
    mode = period.get("mode") or "month"
    if mode == "month":
        raw = period.get("month")
        start = current if raw in (None, "") and "month" not in period else _parse_month(raw)
        if start > current:
            raise svc.TreasuryValidationError("Le mois demandé est dans le futur.")
        months = [start]
        while len(months) < SERIES_MONTHS:
            months.insert(0, _previous_period(months[0]))
        return _Period("month", start, None, start, _month_end(start), tuple(months))
    if mode == "season":
        season_id = _parse_season_id(period.get("season_id"))
        season = Season.all_objects.for_club(club).filter(pk=season_id).first() if season_id is not None else None
        if season is None:
            raise svc.TreasuryValidationError("Saison introuvable pour ce club.")
        start = svc._period_start(season.start_date)
        end = _month_end(svc._period_start(season.end_date))
        months = []
        cursor = start
        while cursor <= end and cursor <= current:
            months.append(cursor)
            cursor = svc._next_period(cursor)
        return _Period("season", None, season, start, end, tuple(months))
    raise svc.TreasuryValidationError("Le type de période est invalide (« month » ou « season »).")


# ---------------------------------------------------------------------------
# Contexte de calcul (une lecture des paramètres, agrégations mémorisées)
# ---------------------------------------------------------------------------


class _Board:
    """Données agrégées partagées entre cartes d'un même appel : chaque
    agrégation SQL n'est exécutée qu'une fois (cartes Cotisations et Caisse
    lisent le même encaissé)."""

    def __init__(self, club, period: Optional[dict]):
        svc._require_service_club(club)
        settings_obj = svc._club_settings(club)
        self.club = club
        self.currency = settings_obj.currency
        self.tolerance = settings_obj.debt_tolerance_days
        self.today = svc._club_today(settings_obj, timezone.now())
        self.period = _resolve_period(club, period, self.today)
        self._cache: dict[str, Any] = {}

    def _memo(self, key: str, compute: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = compute()
        return self._cache[key]

    # -- Encaissements ------------------------------------------------------

    def collected_rows(self) -> dict[tuple[date, str], Decimal]:
        """Encaissé net par (mois, nature du type) sur la période et la série."""

        def compute():
            rows = (
                svc._collected_transactions(self.club, self.period.query_start, self.period.end_exclusive)
                .annotate(month=TruncMonth("value_date"))
                .values("month", "contribution_type__nature")
                .annotate(total=Sum("amount"))
                .order_by()
            )
            result: dict[tuple[date, str], Decimal] = {}
            for row in rows:
                key = (_as_month(row["month"]), row["contribution_type__nature"])
                result[key] = result.get(key, _ZERO) + (row["total"] or _ZERO)
            return result

        return self._memo("collected", compute)

    def collected_in(self, month_filter: Callable[[date], bool], nature: Optional[str] = None) -> Decimal:
        return sum(
            (amount for (month, kind), amount in self.collected_rows().items()
             if month_filter(month) and (nature is None or kind == nature)),
            _ZERO,
        )

    def spent_rows(self) -> dict[date, Decimal]:
        """Dépenses libérées (montant positif) par mois de libération."""

        def compute():
            rows = (
                Transaction.all_objects.for_club(self.club)
                .filter(
                    kind=Transaction.Kind.EXPENSE_RELEASE,
                    status=Transaction.Status.SUCCEEDED,
                    sealed_at__isnull=False,
                    value_date__gte=self.period.query_start,
                    value_date__lt=self.period.end_exclusive,
                )
                .annotate(month=TruncMonth("value_date"))
                .values("month")
                .annotate(total=Sum("amount"))
                .order_by()
            )
            result: dict[date, Decimal] = {}
            for row in rows:
                month = _as_month(row["month"])
                result[month] = result.get(month, _ZERO) - (row["total"] or _ZERO)
            return result

        return self._memo("spent", compute)

    # -- Montants dus -------------------------------------------------------

    def matured_rows(self) -> dict[date, tuple[Decimal, Decimal]]:
        """(dû échu, dû couvert) par mois, définition du taux de recouvrement."""

        def compute():
            rows = (
                svc._matured_dues_coverage(self.club, self.period.query_start, self.period.end_exclusive, self.today)
                .values("period")
                .annotate(due=Sum("amount"), covered=Sum("capped"))
                .order_by()
            )
            return {
                svc._period_start(row["period"]): (row["due"] or _ZERO, row["covered"] or _ZERO) for row in rows
            }

        return self._memo("matured", compute)

    def due_rows(self) -> dict[date, Decimal]:
        """Tous les montants dus (échus ou non) des types obligatoires, par mois."""

        def compute():
            rows = (
                Due.all_objects.for_club(self.club)
                .filter(
                    contribution_type__nature=ContributionType.Nature.MANDATORY,
                    cancellation__isnull=True,
                    period__gte=self.period.query_start,
                    period__lt=self.period.end_exclusive,
                )
                .values("period")
                .annotate(total=Sum("amount"))
                .order_by()
            )
            return {svc._period_start(row["period"]): row["total"] or _ZERO for row in rows}

        return self._memo("dues", compute)

    # -- Effectif -----------------------------------------------------------

    def squad(self) -> dict[str, list]:
        """Classement exclusif des adhésions non parties à la date du jour :
        « En attente » (adhésion), sinon « En dette » / « En ordre » selon le
        solde calculé (``_balance_aggregates`` + ``_summary_from_balance``,
        mêmes règles que ``is_in_good_standing``)."""

        def compute():
            memberships = sorted(
                Membership.all_objects.for_club(self.club)
                .exclude(status=Membership.Status.DEPARTED)
                .select_related("user"),
                key=svc._membership_sort_key,
            )
            paid, owed = svc._balance_aggregates(club=self.club, at_date=self.today)
            groups: dict[str, list] = {"in_good_standing": [], "in_debt": [], "pending": []}
            for membership in memberships:
                if membership.status == Membership.Status.PENDING:
                    groups["pending"].append((membership, None))
                    continue
                balance = (paid.get(membership.pk) or _ZERO) - (owed.get(membership.pk) or _ZERO)
                summary = svc._summary_from_balance(balance, self.currency)
                key = "in_good_standing" if summary.is_in_good_standing else "in_debt"
                groups[key].append((membership, summary.amount_due))
            groups["in_debt"].sort(key=lambda pair: -pair[1])  # tri stable : nom ensuite
            return groups

        return self._memo("squad", compute)


# ---------------------------------------------------------------------------
# Pagination des listes « Voir plus »
# ---------------------------------------------------------------------------


def _check_paging(limit: Any, offset: Any) -> tuple[int, int]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= MAX_LIMIT):
        raise svc.TreasuryValidationError(f"La limite doit être un entier entre 1 et {MAX_LIMIT}.")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise svc.TreasuryValidationError("Le décalage doit être un entier positif ou nul.")
    return limit, offset


def _page(items: list, count: int, limit: int, offset: int) -> dict:
    next_offset = offset + limit if offset + limit < count else None
    return {"items": items, "count": count, "next_offset": next_offset}


def _page_list(values: list, limit: int, offset: int, serialize: Callable) -> dict:
    return _page([serialize(v) for v in values[offset:offset + limit]], len(values), limit, offset)


def _page_queryset(qs, limit: int, offset: int, serialize: Callable) -> dict:
    count = qs.count()
    items = [serialize(obj) for obj in qs[offset:offset + limit]] if offset < count else []
    return _page(items, count, limit, offset)


# ---------------------------------------------------------------------------
# Cartes
# ---------------------------------------------------------------------------


def _contributions_values(board: _Board, month_filter: Callable[[date], bool]) -> dict:
    due = sum((v for m, v in board.due_rows().items() if month_filter(m)), _ZERO)
    matured = [v for m, v in board.matured_rows().items() if month_filter(m)]
    matured_due = svc._quantize(sum((d for d, _ in matured), _ZERO))
    covered = svc._quantize(sum((c for _, c in matured), _ZERO))
    return {
        "collected": _money(board.collected_in(month_filter)),
        "collected_mandatory": _money(board.collected_in(month_filter, ContributionType.Nature.MANDATORY)),
        "collected_free": _money(board.collected_in(month_filter, ContributionType.Nature.FREE)),
        "due_total": _money(due),
        "matured_due_total": _money(matured_due),
        "matured_due_covered": _money(covered),
        "collection_rate": _rate(svc._collection_rate(matured_due, covered)),
    }


def _contributions_card(board: _Board) -> dict:
    values = _contributions_values(board, board.period.contains)
    series = []
    for month in board.period.months:
        row = _contributions_values(board, lambda m, month=month: m == month)
        series.append({
            "month": _month_key(month),
            "label": svc.french_month_label(month),
            "collected": row["collected"],
            "matured_due_total": row["matured_due_total"],
            "matured_due_covered": row["matured_due_covered"],
            "collection_rate": row["collection_rate"],
        })
    return {**values, "series": series}


def _squad_card(board: _Board) -> dict:
    groups = board.squad()
    total = sum(len(v) for v in groups.values())
    debt_amount = sum((amount for _, amount in groups["in_debt"]), _ZERO)
    return {
        "as_of": board.today.isoformat(),
        "total": total,
        "in_good_standing": {"count": len(groups["in_good_standing"]), "rate": _share(len(groups["in_good_standing"]), total)},
        "in_debt": {
            "count": len(groups["in_debt"]),
            "rate": _share(len(groups["in_debt"]), total),
            "amount": _money(debt_amount),
        },
        "pending": {"count": len(groups["pending"]), "rate": _share(len(groups["pending"]), total)},
    }


def _cash_card(board: _Board) -> dict:
    collected = board.collected_in(board.period.contains)
    spent = sum((v for m, v in board.spent_rows().items() if board.period.contains(m)), _ZERO)
    return {
        "collected": _money(collected),
        "spent": _money(spent),
        "net": _money(collected - spent),
        "available_cash": _money(svc.get_available_cash(board.club)),
        "series": [
            {
                "month": _month_key(month),
                "label": svc.french_month_label(month),
                "collected": _money(board.collected_in(lambda m, month=month: m == month)),
                "spent": _money(board.spent_rows().get(month, _ZERO)),
            }
            for month in board.period.months
        ],
    }


def _released_expenses(board: _Board):
    return Expense.all_objects.for_club(board.club).filter(
        status__in=Expense.RELEASED_STATUSES,
        transaction__status=Transaction.Status.SUCCEEDED,
        transaction__sealed_at__isnull=False,
        transaction__value_date__gte=board.period.start,
        transaction__value_date__lt=board.period.end_exclusive,
    )


def _category_totals(board: _Board) -> list[dict]:
    rows = (
        _released_expenses(board)
        .values("category_id", "category__name")
        .annotate(amount=Sum("amount"), count=Count("pk"))
        .order_by()
    )
    ordered = sorted(rows, key=lambda r: (-(r["amount"] or _ZERO), svc._fold(r["category__name"]), r["category_id"]))
    return [
        {"category_id": r["category_id"], "name": r["category__name"], "amount": r["amount"] or _ZERO, "count": r["count"]}
        for r in ordered
    ]


def _expenses_values(board: _Board, categories: list[dict]) -> dict:
    pending = Expense.all_objects.for_club(board.club).filter(status=Expense.Status.PENDING).aggregate(
        count=Count("pk"), amount=Sum("amount")
    )
    check = svc.can_release_expense(board.club, today=board.today)
    return {
        "total_spent": _money(sum((c["amount"] for c in categories), _ZERO)),
        "pending_count": pending["count"] or 0,
        "pending_amount": _money(pending["amount"]),
        "unjustified_count": len(check.blocking_expense_ids),
        "release_blocked": not check.allowed,
        "release_blocked_reason": None if check.allowed else check.reason,
    }


def _category_json(row: dict) -> dict:
    return {"category_id": row["category_id"], "name": row["name"], "amount": _money(row["amount"]), "count": row["count"]}


def _expenses_card(board: _Board) -> dict:
    categories = _category_totals(board)
    top = [_category_json(row) for row in categories[:CARD_TOP_CATEGORIES]]
    rest = categories[CARD_TOP_CATEGORIES:]
    if rest:
        top.append({
            "category_id": None,
            "name": "Autres",
            "amount": _money(sum((r["amount"] for r in rest), _ZERO)),
            "count": sum(r["count"] for r in rest),
        })
    return {**_expenses_values(board, categories), "categories": top}


def _upcoming_items(board: _Board) -> list[dict]:
    """Échéances financières des 30 prochains jours : montants dus non
    encore échus restant à couvrir (groupés par type et date d'échéance) et
    justificatifs de dépense attendus. Les échéances sportives (matchs,
    séances, AG, licences : carte 11) ne relèvent pas de la trésorerie."""

    until = board.today + timedelta(days=UPCOMING_DAYS)
    dues = (
        svc._annotate_due_coverage(
            board.club,
            Due.all_objects.for_club(board.club)
            .filter(
                contribution_type__nature=ContributionType.Nature.MANDATORY,
                cancellation__isnull=True,
                due_date__gte=board.today - timedelta(days=board.tolerance),
                due_date__lte=until,
            )
            .exclude(membership__status=Membership.Status.DEPARTED),
        )
        .annotate(remaining=F("amount") - F("capped"))
        .filter(remaining__gt=0)
        .values("contribution_type_id", "contribution_type__name", "due_date")
        .annotate(players=Count("membership_id", distinct=True), amount=Sum("remaining"))
        .order_by()
    )
    items = [
        {
            "kind": "contribution_due",
            "date": row["due_date"].isoformat(),
            "debt_on": (row["due_date"] + timedelta(days=board.tolerance + 1)).isoformat(),
            "label": f"Échéance « {row['contribution_type__name']} »",
            "contribution_type_id": row["contribution_type_id"],
            "players_count": row["players"],
            "amount": _money(row["amount"]),
        }
        for row in dues
    ]
    expenses = (
        Expense.all_objects.for_club(board.club)
        .filter(
            status=Expense.Status.RELEASED,
            justification_deadline__gte=board.today,
            justification_deadline__lte=until,
        )
        .select_related("category")
    )
    items.extend(
        {
            "kind": "expense_justification",
            "date": expense.justification_deadline.isoformat(),
            "label": f"Justificatif attendu : {expense.category.name}",
            "expense_id": expense.pk,
            "amount": _money(expense.amount),
        }
        for expense in expenses
    )
    items.sort(key=lambda item: (item["date"], item["kind"], item["label"]))
    return items


def _upcoming_card(board: _Board) -> dict:
    items = _upcoming_items(board)
    return {
        "as_of": board.today.isoformat(),
        "until": (board.today + timedelta(days=UPCOMING_DAYS)).isoformat(),
        "items": items[:CARD_UPCOMING_ITEMS],
        "count": len(items),
    }


_CARD_BUILDERS = {
    "contributions": "_contributions_card",
    "squad_status": "_squad_card",
    "cash": "_cash_card",
    "expenses_by_category": "_expenses_card",
    "upcoming_finance": "_upcoming_card",
}


def finance_cards(club, period: Optional[dict] = None) -> dict:
    """Valeurs synthétiques des cartes financières du tableau de bord du
    bureau (fiche §4 cartes 2, 6, 7, 8 + échéances financières).

    Lève ``TreasuryValidationError`` (période invalide, mois futur, saison
    d'un autre club) et ``TenantMismatchError`` (club actif différent). Une
    erreur inattendue dans une carte ne fait pas échouer les autres : la
    carte vaut alors ``{"error": "Impossible de charger …"}`` (fiche §10).

    Forme exacte (montants : chaînes à 2 décimales ; taux : chaînes en
    pourcentage à 2 décimales ou ``null``)::

        {
          "period": {"mode": "month" | "season", "month": "AAAA-MM" | null,
                     "season_id": int | null, "label": "novembre 2026" | "Saison 2026-2027",
                     "start": "AAAA-MM-JJ", "end": "AAAA-MM-JJ",
                     "months": ["AAAA-MM", ...]},   # mois des séries, jamais futurs
          "currency": "USD",
          "contributions": {
            "collected": "17.00", "collected_mandatory": "14.00", "collected_free": "3.00",
            "due_total": "30.00", "matured_due_total": "30.00", "matured_due_covered": "14.00",
            "collection_rate": "46.67" | null,
            "series": [{"month": "AAAA-MM", "label": "septembre 2026", "collected": "…",
                        "matured_due_total": "…", "matured_due_covered": "…",
                        "collection_rate": "…" | null}, ...]
          },
          "squad_status": {               # aujourd'hui, indépendant de la période
            "as_of": "AAAA-MM-JJ", "total": 10,
            "in_good_standing": {"count": 7, "rate": "70.00"},
            "in_debt": {"count": 2, "rate": "20.00", "amount": "26.00"},
            "pending": {"count": 1, "rate": "10.00"}
          },
          "cash": {
            "collected": "10.00", "spent": "8.00", "net": "2.00",
            "available_cash": "19.00",    # aujourd'hui, tous mouvements
            "series": [{"month": "AAAA-MM", "label": "…", "collected": "…", "spent": "…"}, ...]
          },
          "expenses_by_category": {
            "total_spent": "8.00",
            "categories": [{"category_id": 3, "name": "Transport", "amount": "5.00", "count": 1},
                           ..., {"category_id": null, "name": "Autres", ...}],  # 5 + « Autres »
            "pending_count": 1, "pending_amount": "40.00",       # aujourd'hui
            "unjustified_count": 1, "release_blocked": true,     # aujourd'hui
            "release_blocked_reason": "…" | null
          },
          "upcoming_finance": {           # aujourd'hui -> +30 jours, 5 éléments
            "as_of": "AAAA-MM-JJ", "until": "AAAA-MM-JJ", "count": 3,
            "items": [
              {"kind": "contribution_due", "date": "AAAA-MM-JJ", "debt_on": "AAAA-MM-JJ",
               "label": "Échéance « Mensuelle 10 »", "contribution_type_id": 4,
               "players_count": 6, "amount": "60.00"},
              {"kind": "expense_justification", "date": "AAAA-MM-JJ",
               "label": "Justificatif attendu : Transport", "expense_id": 9, "amount": "12.00"}
            ]
          }
        }
    """

    board = _Board(club, period)
    result: dict[str, Any] = {"period": board.period.as_json(), "currency": board.currency}
    for section, builder_name in _CARD_BUILDERS.items():
        try:
            result[section] = globals()[builder_name](board)
        except Exception:  # une carte en erreur ne fait pas échouer la page (fiche §10)
            logger.exception("Carte financière %s en erreur (club %s)", section, club.pk)
            result[section] = {"error": SECTION_ERRORS[section]}
    return result


# ---------------------------------------------------------------------------
# Détail des cartes (modales)
# ---------------------------------------------------------------------------


def _without(data: dict, *keys: str) -> dict:
    return {k: v for k, v in data.items() if k not in keys}


def _player_json(membership: Membership, amount_due: Optional[Decimal] = None) -> dict:
    item = {"membership_id": membership.pk, "player_name": svc._membership_name(membership)}
    if amount_due is not None:
        item["amount_due"] = _money(amount_due)
    return item


def _debtors_page(board: _Board, limit: int, offset: int) -> dict:
    page = _page_list(board.squad()["in_debt"], limit, offset, lambda pair: _player_json(*pair))
    return {"as_of": board.today.isoformat(), **page}


def _payments_page(board: _Board, limit: int, offset: int) -> dict:
    approved = PaymentReversal.all_objects.filter(
        club=board.club, payment=OuterRef("pk"), status=PaymentReversal.Status.APPROVED
    )
    qs = (
        Payment.all_objects.for_club(board.club)
        .filter(
            transaction__status=Transaction.Status.SUCCEEDED,
            transaction__sealed_at__isnull=False,
            transaction__value_date__gte=board.period.start,
            transaction__value_date__lt=board.period.end_exclusive,
        )
        .annotate(cancelled=Exists(approved))
        .select_related("membership__user", "contribution_type")
        .order_by("-transaction__value_date", "-pk")
    )

    def serialize(payment: Payment) -> dict:
        status = "cancelled" if payment.cancelled else "validated"
        return {
            "payment_id": payment.pk,
            "paid_on": payment.paid_on.isoformat(),
            "membership_id": payment.membership_id,
            "player_name": svc._membership_name(payment.membership),
            "contribution_type_id": payment.contribution_type_id,
            "contribution_type_name": payment.contribution_type.name,
            "nature": payment.contribution_type.nature,
            "amount": _money(payment.amount),
            "status": status,
            "status_label": svc.PAYMENT_STATUS_LABELS[status],
        }

    return _page_queryset(qs, limit, offset, serialize)


def _contributions_by_type(board: _Board) -> list[dict]:
    start, end = board.period.start, board.period.end_exclusive
    collected = {
        row["contribution_type_id"]: row["total"] or _ZERO
        for row in svc._collected_transactions(board.club, start, end)
        .values("contribution_type_id").annotate(total=Sum("amount")).order_by()
    }
    dues = {
        row["contribution_type_id"]: row["total"] or _ZERO
        for row in Due.all_objects.for_club(board.club)
        .filter(
            contribution_type__nature=ContributionType.Nature.MANDATORY,
            cancellation__isnull=True,
            period__gte=start,
            period__lt=end,
        )
        .values("contribution_type_id").annotate(total=Sum("amount")).order_by()
    }
    matured = {
        row["contribution_type_id"]: (row["due"] or _ZERO, row["covered"] or _ZERO)
        for row in svc._matured_dues_coverage(board.club, start, end, board.today)
        .values("contribution_type_id").annotate(due=Sum("amount"), covered=Sum("capped")).order_by()
    }
    active_ids = set(collected) | set(dues) | set(matured)
    types = ContributionType.all_objects.for_club(board.club).filter(pk__in=active_ids) | (
        ContributionType.all_objects.for_club(board.club).filter(status=ContributionType.Status.ACTIVE)
    )
    ordered = sorted(
        types.distinct(),
        key=lambda t: (t.nature != ContributionType.Nature.MANDATORY, svc._fold(t.name), t.pk),
    )
    rows = []
    for ctype in ordered:
        mandatory = ctype.nature == ContributionType.Nature.MANDATORY
        due_value, covered_value = matured.get(ctype.pk, (_ZERO, _ZERO))
        rows.append({
            "contribution_type_id": ctype.pk,
            "name": ctype.name,
            "nature": ctype.nature,
            "nature_label": ctype.get_nature_display(),
            "collected": _money(collected.get(ctype.pk, _ZERO)),
            "due_total": _money(dues.get(ctype.pk, _ZERO)) if mandatory else None,
            "matured_due_total": _money(due_value) if mandatory else None,
            "matured_due_covered": _money(covered_value) if mandatory else None,
            "collection_rate": _rate(svc._collection_rate(svc._quantize(due_value), svc._quantize(covered_value)))
            if mandatory else None,
        })
    return rows


def _expenses_page(board: _Board, limit: int, offset: int) -> dict:
    qs = (
        Expense.all_objects.for_club(board.club)
        .exclude(status=Expense.Status.REFUSED)
        .filter(expense_date__gte=board.period.start, expense_date__lt=board.period.end_exclusive)
        .select_related("category")
        .order_by("-expense_date", "-pk")
    )

    def serialize(expense: Expense) -> dict:
        return {
            "expense_id": expense.pk,
            "expense_date": expense.expense_date.isoformat(),
            "category_id": expense.category_id,
            "category_name": expense.category.name,
            "amount": _money(expense.amount),
            "beneficiary_name": expense.beneficiary_name,
            "status": expense.status,
            "status_label": expense.get_status_display(),
            "justification_deadline": (
                expense.justification_deadline.isoformat() if expense.justification_deadline else None
            ),
            "is_overdue": svc.is_expense_overdue(expense, board.today),
        }

    return _page_queryset(qs, limit, offset, serialize)


def _cash_months(board: _Board) -> tuple[Decimal, list[dict]]:
    months = board.period.months
    first = months[0] if months else board.period.start
    opening = (
        Transaction.all_objects.for_club(board.club)
        .filter(status=Transaction.Status.SUCCEEDED, sealed_at__isnull=False, value_date__lt=first)
        .aggregate(total=Sum("amount"))["total"]
        or _ZERO
    )
    running = opening
    rows = []
    for month in months:
        collected = board.collected_in(lambda m, month=month: m == month)
        spent = board.spent_rows().get(month, _ZERO)
        running += collected - spent
        rows.append({
            "month": _month_key(month),
            "label": svc.french_month_label(month),
            "collected": _money(collected),
            "spent": _money(spent),
            "net": _money(collected - spent),
            "cash_end": _money(running),
        })
    return opening, rows


# Listes paginées de chaque section : nom -> fonction(board, limit, offset).
_SECTION_LISTS: dict[str, dict[str, Callable]] = {
    "contributions": {"payments": _payments_page, "debtors": _debtors_page},
    "squad_status": {
        "in_good_standing": lambda b, limit, offset: _page_list(
            b.squad()["in_good_standing"], limit, offset, lambda pair: _player_json(pair[0])
        ),
        "in_debt": lambda b, limit, offset: _page_list(b.squad()["in_debt"], limit, offset, lambda pair: _player_json(*pair)),
        "pending": lambda b, limit, offset: _page_list(
            b.squad()["pending"], limit, offset, lambda pair: _player_json(pair[0])
        ),
    },
    "cash": {},
    "expenses_by_category": {"expenses": _expenses_page},
    "upcoming_finance": {
        "upcoming": lambda b, limit, offset: {
            "as_of": b.today.isoformat(),
            "until": (b.today + timedelta(days=UPCOMING_DAYS)).isoformat(),
            **_page_list(_upcoming_items(b), limit, offset, lambda item: item),
        },
    },
}


def _section_extras(board: _Board, section: str) -> dict:
    if section == "contributions":
        card = _contributions_card(board)
        return {"summary": _without(card, "series"), "series": card["series"], "by_type": _contributions_by_type(board)}
    if section == "squad_status":
        return {"summary": _squad_card(board)}
    if section == "cash":
        opening, months = _cash_months(board)
        return {"summary": _without(_cash_card(board), "series"), "opening_cash": _money(opening), "months": months}
    if section == "expenses_by_category":
        categories = _category_totals(board)
        return {"summary": _expenses_values(board, categories), "categories": [_category_json(r) for r in categories]}
    return {}


def finance_section(
    club,
    section: str,
    period: Optional[dict] = None,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    only: Optional[str] = None,
) -> dict:
    """Détail d'une carte financière pour sa modale (fiche §5).

    ``section`` : une valeur de :data:`FINANCE_SECTIONS`. ``limit`` (1 à
    100, défaut 20) et ``offset`` (≥ 0) paginent chaque liste « Voir plus »
    ; ``only`` (nom d'une liste de la section) ne renvoie que cette liste,
    pour le bouton « Voir plus ». Erreurs : ``TreasuryValidationError``
    (section, liste, pagination ou période invalide), ``TenantMismatchError``.

    Toute réponse contient ``"section"``, ``"period"`` (même forme que
    :func:`finance_cards`) et ``"currency"``. Une liste paginée a la forme
    ``{"items": [...], "count": int, "next_offset": int | null}``.

    Montants individuels par joueur : uniquement ``amount_due`` des joueurs
    en dette (fiche §5 cartes 2 et 6, droit « L » du Président et du VP sur
    la grille ; question Q5 de la fiche encore ouverte).

    ``contributions``::

        {"summary": {<carte contributions sans "series">},
         "series": [<12 mois (mode mois) ou mois de la saison, comme la carte>],
         "by_type": [{"contribution_type_id": 4, "name": "Mensuelle 10",
                      "nature": "mandatory" | "free", "nature_label": "Obligatoire" | "Libre",
                      "collected": "14.00",
                      "due_total": "30.00" | null, "matured_due_total": "30.00" | null,
                      "matured_due_covered": "14.00" | null,
                      "collection_rate": "46.67" | null}, ...],   # libre : null
         "payments": {"items": [{"payment_id": 1, "paid_on": "AAAA-MM-JJ",
                                 "membership_id": 7, "player_name": "Bruno Bb",
                                 "contribution_type_id": 4, "contribution_type_name": "Mensuelle 10",
                                 "nature": "mandatory", "amount": "4.00",
                                 "status": "validated" | "cancelled",
                                 "status_label": "Validé" | "Annulé"}], "count": 4, "next_offset": null},
         "debtors": {"as_of": "AAAA-MM-JJ",
                     "items": [{"membership_id": 9, "player_name": "Cedric Cc", "amount_due": "20.00"}],
                     "count": 2, "next_offset": null}}       # tri : montant dû décroissant

    ``squad_status`` (aujourd'hui)::

        {"summary": {<carte squad_status>},
         "in_good_standing": {"items": [{"membership_id": 3, "player_name": "Alain Aa"}], ...},
         "in_debt": {"items": [{"membership_id": 9, "player_name": "Cedric Cc", "amount_due": "20.00"}], ...},
         "pending": {"items": [{"membership_id": 5, "player_name": "…"}], ...}}

    ``cash``::

        {"summary": {<carte cash sans "series">},
         "opening_cash": "0.00",                       # caisse avant le premier mois
         "months": [{"month": "AAAA-MM", "label": "…", "collected": "17.00", "spent": "0.00",
                     "net": "17.00", "cash_end": "17.00"}, ...]}

    ``expenses_by_category``::

        {"summary": {<carte expenses_by_category sans "categories">},
         "categories": [{"category_id": 3, "name": "Transport", "amount": "5.00", "count": 1}, ...],  # toutes
         "expenses": {"items": [{"expense_id": 12, "expense_date": "AAAA-MM-JJ",
                                 "category_id": 3, "category_name": "Transport", "amount": "5.00",
                                 "beneficiary_name": "…",
                                 "status": "pending" | "released" | "justified" | "unjustified",
                                 "status_label": "En attente" | "Libérée" | "Justifiée" | "Non justifiée",
                                 "justification_deadline": "AAAA-MM-JJ" | null,
                                 "is_overdue": bool}], "count": 2, "next_offset": null}}

    ``upcoming_finance``::

        {"upcoming": {"as_of": "AAAA-MM-JJ", "until": "AAAA-MM-JJ",
                      "items": [<éléments de la carte upcoming_finance>], "count": 3, "next_offset": null}}
    """

    if section not in FINANCE_SECTIONS:
        raise svc.TreasuryValidationError("Section inconnue du tableau de bord.")
    limit, offset = _check_paging(limit, offset)
    lists = _SECTION_LISTS[section]
    if only is not None and only not in lists:
        raise svc.TreasuryValidationError("Liste inconnue pour cette section du tableau de bord.")
    board = _Board(club, period)
    result: dict[str, Any] = {"section": section, "period": board.period.as_json(), "currency": board.currency}
    if only is not None:
        result[only] = lists[only](board, limit, offset)
        return result
    result.update(_section_extras(board, section))
    for name, build in lists.items():
        result[name] = build(board, limit, offset)
    return result
