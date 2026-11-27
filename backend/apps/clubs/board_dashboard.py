"""Tableau de bord du Président et du Vice-président : lecture (cartes et détails).

Fiche d'écran ``docs/ecrans/club-tableau-de-bord-bureau.md`` (§4 les 17 cartes,
§5 modales de détail, §9 règles, §10 API) ; CDC 2.4, 4.3, 4.7 à 4.10, 4.12,
4.13, 4.15, 4.16 ; CLAUDE.md règles 2, 3, 8, 9 et 11.

**Lecture seule** : aucune écriture, aucune entrée de journal (la consultation
n'est pas journalisée, fiche §9). Chaque requête est filtrée explicitement sur
le club (``all_objects.for_club(club)``) ; les listes sont calculées en
mémoire à partir de requêtes agrégées (nombre de requêtes indépendant du
nombre de joueurs). Les cartes financières viennent de
``apps.treasury.dashboard`` (non modifié) ; ce module y ajoute le segment
« Suspendu » et les photos.

**Confidentialité (règle 11)** : la carte « Aptitude » ne lit QUE le statut
d'aptitude et la date de retour de ``HealthRecord`` (``values()`` limité à ces
colonnes) : aucun diagnostic, aucune blessure, aucun consentement, même quand
le joueur a donné accès à son dossier au Président. Aucun téléphone ni
coordonnée privée n'est renvoyé.

Contrat de chaque section : la carte (``board_cards``) vaut le ``summary`` du
détail (``board_section``). Les sections non financières renvoient
``{"section", "period", "summary", <extras>, <listes paginées>}`` ; une liste
paginée vaut ``{"items", "count", "next_offset"}``.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from django.db.models import Count, F, Q, Sum

from apps.clubs.models import ClubSettings, Membership, MembershipApplication, Season
from apps.licences.models import Licence
from apps.treasury import dashboard as fin
from apps.treasury import services as svc
from apps.treasury.models import Expense, SocialAssistanceRequest, Transaction

logger = logging.getLogger(__name__)

FINANCE_SECTIONS = fin.FINANCE_SECTIONS
FINANCE_CARD_KEYS = ("contributions", "squad_status", "cash", "expenses_by_category", "upcoming_finance")
NON_FINANCE_SECTIONS = (
    "attendance",
    "newcomers",
    "results",
    "discipline",
    "squad_trend",
    "fitness",
    "upcoming",
    "attendance_ranking",
    "to_process",
    "equipment_out",
    "coach_notes",
    "feed_activity",
)
ALL_SECTIONS = FINANCE_SECTIONS + NON_FINANCE_SECTIONS

CARD_ERRORS = {
    "attendance": "Impossible de charger les présences.",
    "newcomers": "Impossible de charger les nouveaux venus.",
    "results": "Impossible de charger les résultats.",
    "discipline": "Impossible de charger la discipline.",
    "squad_trend": "Impossible de charger l'évolution de l'effectif.",
    "fitness": "Impossible de charger l'aptitude de l'effectif.",
    "upcoming": "Impossible de charger les prochaines échéances.",
    "attendance_ranking": "Impossible de charger l'assiduité par joueur.",
    "to_process": "Impossible de charger les éléments à traiter.",
    "equipment_out": "Impossible de charger le matériel à retourner.",
    "coach_notes": "Impossible de charger les notes du Coach.",
    "feed_activity": "Impossible de charger l'activité du fil.",
    "squad_status": "Impossible de charger la situation de l'effectif.",
}

CARD_LIST_ITEMS = 5
POINTS_MAX = 10
DEFAULT_LIMIT = fin.DEFAULT_LIMIT
MAX_LIMIT = fin.MAX_LIMIT
UPCOMING_DAYS = fin.UPCOMING_DAYS
# Matériel prêté : le modèle n'a pas d'échéance de retour. Décision du client
# (16/11/2026) : un matériel est « en retard » quand plus de ce nombre de jours
# s'est écoulé depuis la date du match (sinon du prêt) sans retour.
EQUIPMENT_OVERDUE_AFTER_DAYS = 7
BLOCKED_APPLICATION_DELAY_NOTE = "Parrain sans réponse depuis plus de 7 jours."


class BoardDashboardError(Exception):
    """Erreur de requête du tableau de bord (message français, rendu en 400)."""


# ---------------------------------------------------------------------------
# Paramètres de la requête
# ---------------------------------------------------------------------------


def period_from_query(club, params) -> Optional[dict]:
    """Période du ``PeriodPicker`` à partir des paramètres GET.

    ``?period=month&month=AAAA-MM`` ou ``?period=season&season=<id>`` (alias
    acceptés : ``period_mode`` pour ``period``, ``season_id`` pour ``season``).
    Rien = mois courant (``None``). ``period=season`` sans identifiant = saison
    courante du club.
    """

    mode = params.get("period") or params.get("period_mode")
    month = params.get("month")
    season = params.get("season") or params.get("season_id")
    if not mode and month is None and not season:
        return None
    if not mode:
        mode = "season" if season and month is None else "month"
    if mode == "month":
        return {"mode": "month", "month": month} if month is not None else {"mode": "month"}
    if mode == "season":
        if not season:
            current = Season.all_objects.for_club(club).filter(is_current=True).first()
            if current is None:
                raise BoardDashboardError("Aucune saison courante n'est définie pour ce club.")
            season = current.pk
        return {"mode": "season", "season_id": season}
    return {"mode": mode}


def paging_from_query(params) -> tuple[int, int]:
    def parse(raw, default, message):
        if raw in (None, ""):
            return default
        try:
            return int(str(raw).strip())
        except ValueError:
            raise BoardDashboardError(message) from None

    limit = parse(params.get("limit"), DEFAULT_LIMIT, f"La limite doit être un entier entre 1 et {MAX_LIMIT}.")
    offset = parse(params.get("offset"), 0, "Le décalage doit être un entier positif ou nul.")
    if not 1 <= limit <= MAX_LIMIT:
        raise BoardDashboardError(f"La limite doit être un entier entre 1 et {MAX_LIMIT}.")
    if offset < 0:
        raise BoardDashboardError("Le décalage doit être un entier positif ou nul.")
    return limit, offset


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------


def _pct(numerator: int, denominator: int) -> Optional[str]:
    """Taux de présence : même règle d'arrondi (unité) que la page
    Entraînements (``apps.sport.session_stats.attendance_rate_percent``),
    spec ``club-tableau-de-bord-bureau.md`` §9. Renvoyé en chaîne (contrat
    ``Rate`` de l'interface), ex. ``"34"``."""

    from apps.sport.session_stats import attendance_rate_percent

    rate = attendance_rate_percent(numerator, denominator)
    return None if rate is None else str(rate)


def _avg(total: Decimal, count: int) -> Optional[str]:
    if count <= 0:
        return None
    return f"{(Decimal(total) / Decimal(count)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _page(values: list, limit: int, offset: int) -> dict:
    return {
        "items": values[offset:offset + limit],
        "count": len(values),
        "next_offset": offset + limit if offset + limit < len(values) else None,
    }


def _name_key(membership: Membership):
    user = membership.user
    return ((user.last_name or "").lower(), (user.first_name or "").lower(), membership.pk)


class _Ctx:
    """Contexte d'un appel : période résolue par le module financier (mêmes
    bornes que ses cartes), club, fuseau, mémoïsation des lectures."""

    def __init__(self, club, period: Optional[dict], request=None):
        self.club = club
        self.request = request
        self.board = fin._Board(club, period)  # valide le club actif et la période
        self.period = self.board.period
        self.today: date = self.board.today
        self.until: date = min(self.period.end, self.today)
        self._cache: dict[str, Any] = {}

    def memo(self, key: str, compute: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = compute()
        return self._cache[key]

    # -- Réglages ----------------------------------------------------------

    def club_settings(self) -> ClubSettings:
        return self.memo("settings", lambda: svc._club_settings(self.club))

    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.club_settings().timezone)

    # -- Joueurs -----------------------------------------------------------

    def members(self) -> dict[int, Membership]:
        """Toutes les adhésions du club (une requête, ``user`` joint) : noms,
        photos, dates et statuts de toutes les cartes."""

        def compute():
            return {
                m.pk: m for m in Membership.all_objects.for_club(self.club).select_related("user")
            }

        return self.memo("members", compute)

    def photo(self, membership: Membership) -> Optional[str]:
        user = membership.user
        if not user.photo or self.request is None:
            return None
        return self.request.build_absolute_uri(user.photo.url)

    def player(self, membership_id: Optional[int]) -> dict:
        membership = self.members().get(membership_id)
        if membership is None:
            return {"membership_id": membership_id, "player_name": None, "photo": None}
        return {
            "membership_id": membership.pk,
            "player_name": f"{membership.user.first_name} {membership.user.last_name}".strip(),
            "photo": self.photo(membership),
        }

    def counted_members(self) -> list[Membership]:
        """Adhésions comptées dans l'effectif historique : ni en attente, ni
        annulées avant l'inscription, ni parties sans date de départ."""

        def compute():
            result = []
            for m in self.members().values():
                if m.status == Membership.Status.PENDING:
                    continue
                if m.status == Membership.Status.DEPARTED and (
                    m.left_on is None or m.left_reason == Membership.LeftReason.CANCELLED
                ):
                    continue
                result.append(m)
            return result

        return self.memo("counted", compute)

    def suspended(self) -> dict[int, Any]:
        """Suspensions en cours (une par joueur, la plus récente), joueurs
        encore au club : source de vérité de ``apps.sport`` (même filtre que
        ``Suspension.is_active``)."""

        def compute():
            from apps.sport.models import Suspension

            rows = (
                Suspension.all_objects.for_club(self.club)
                .filter(lifted_at__isnull=True, matches_served__lt=F("matches_total"))
                .order_by("created_at", "pk")
            )
            result = {}
            for suspension in rows:
                member = self.members().get(suspension.membership_id)
                if member is None or member.status != Membership.Status.ACTIVE:
                    continue
                result[suspension.membership_id] = suspension
            return result

        return self.memo("suspended", compute)


# ---------------------------------------------------------------------------
# Présences (carte 1) et assiduité (carte 12)
# ---------------------------------------------------------------------------

_KIND_LABELS = {"session": "Séance", "match": "Match"}


def _attendance_data(ctx: _Ctx) -> dict:
    """Présences de la période : **aucun calcul propre**. La moyenne, les taux
    par séance et l'assiduité viennent de
    ``apps.sport.session_stats.summarize_attendance`` (définition unique,
    CDC 10.3 n° 185, position provisoire) : séances seulement, séance non
    pointée exclue (jamais 0 %), un seul arrondi. Les matchs sont résumés à
    part par la même fonction (``by_kind["match"]``).

    Requêtes : événements (1) + pointages (1) ; adhésions et réglages viennent
    du contexte déjà mémoïsé (nombre de requêtes inchangé)."""

    def compute():
        from apps.sport.models import Event
        from apps.sport.session_stats import attendance_rows, summarize_attendance

        counts_absent = ctx.club_settings().late_arrival_counts_absent
        window = Event.all_objects.for_club(ctx.club).filter(
            event_date__gte=ctx.period.query_start, event_date__lte=ctx.until
        )
        events = list(window.order_by("event_date", "pk").only("pk", "kind", "event_date"))
        # Sous-requête : une seule requête de pointages, même sans événement.
        rows = attendance_rows(ctx.club, window.values("pk"))
        roster = ctx.counted_members()

        def summarize(selected):
            return summarize_attendance(
                ctx.club, selected, roster=roster, rows=rows, counts_absent=counts_absent
            )

        def in_period(event):
            return ctx.period.start <= event.event_date <= ctx.until

        sessions_window = [e for e in events if e.kind == Event.Kind.SESSION]
        sessions = [e for e in sessions_window if in_period(e)]
        matches = [e for e in events if e.kind == Event.Kind.MATCH and in_period(e)]
        return {
            "sessions": sessions,
            "sessions_window": sessions_window,
            "period": summarize(sessions),  # moyenne, courbe, assiduité
            "window": summarize(sessions_window),  # série mensuelle (mois antérieurs compris)
            "matches": summarize(matches),  # taux propre des matchs, présenté à part
            "late_counts_absent": counts_absent,
        }

    return ctx.memo("attendance_raw", compute)


def _event_json(event, counts: dict) -> dict:
    rate = counts["rate"]
    return {
        "event_id": event.pk,
        "kind": event.kind,
        "kind_label": _KIND_LABELS.get(event.kind, event.kind),
        "date": event.event_date.isoformat(),
        "expected": counts["expected"],
        "present": counts["present"],
        "late": counts["late"],
        "excused": counts["excused"],
        "absent": counts["absent"],
        "marked": counts["marked"],
        "rate": None if rate is None else str(rate),
    }


def _rate_str(rate: Optional[int]) -> Optional[str]:
    return None if rate is None else str(rate)


def _attendance(ctx: _Ctx) -> dict:
    def compute():
        from apps.sport.session_stats import aggregate_attendance

        raw = _attendance_data(ctx)
        summary = raw["period"]
        per_event = summary["per_event"]
        points = [
            _event_json(e, per_event[e.pk])
            for e in raw["sessions"]
            if per_event[e.pk]["marked"] and per_event[e.pk]["expected"] > 0
        ][-POINTS_MAX:]
        window_counts = raw["window"]["per_event"]
        by_month: dict[date, list] = defaultdict(list)
        for e in raw["sessions_window"]:
            by_month[svc._period_start(e.event_date)].append(window_counts[e.pk])
        monthly = {month: aggregate_attendance(by_month.get(month, [])) for month in ctx.period.months}
        matches = raw["matches"]
        card = {
            # Séances pointées de la période (celles qui entrent dans la moyenne).
            "events_count": summary["sessions_counted"],
            "unmarked_count": sum(1 for e in raw["sessions"] if not per_event[e.pk]["marked"]),
            "average_rate": _rate_str(summary["average_rate"]),
            "last_rate": points[-1]["rate"] if points else None,
            "late_counts_absent": raw["late_counts_absent"],
            "totals": {k: summary["totals"][k] for k in ("expected", "present", "late", "excused", "absent")},
            "by_kind": {
                "session": {"events": summary["sessions_counted"], "average_rate": _rate_str(summary["average_rate"])},
                "match": {"events": matches["sessions_counted"], "average_rate": _rate_str(matches["average_rate"])},
            },
            "points": points,
            "series": [
                {
                    "month": fin._month_key(month),
                    "label": svc.french_month_label(month),
                    "events": monthly[month]["events"],
                    "rate": _rate_str(monthly[month]["rate"]),
                }
                for month in ctx.period.months
            ],
        }
        sessions = [_event_json(e, per_event[e.pk]) for e in reversed(raw["sessions"])]
        return {"card": card, "extras": {}, "lists": {"sessions": sessions}}

    return ctx.memo("attendance", compute)


def _player_attendance_rows(ctx: _Ctx) -> list[dict]:
    """Assiduité par joueur : valeurs de ``summarize_attendance`` (séances
    pointées de la période), joueurs encore au club seulement."""

    players = _attendance_data(ctx)["period"]["players"]
    rows = []
    for m in ctx.counted_members():
        if m.status != Membership.Status.ACTIVE:
            continue
        entry = players.get(m.pk)
        if not entry or not entry["sessions"]:
            continue
        rows.append(
            {
                **ctx.player(m.pk),
                "expected": entry["sessions"],
                "present": entry["present"],
                "late": entry["late"],
                "excused": entry["excused"],
                "absent": entry["absent"],
                "rate": _rate_str(entry["rate"]),
                "_ratio": Decimal(entry["attended"]) / Decimal(entry["sessions"]),
                "_key": _name_key(m),
            }
        )
    return rows


def _attendance_ranking(ctx: _Ctx) -> dict:
    def compute():
        rows = _player_attendance_rows(ctx)
        by_best = sorted(rows, key=lambda r: (-r["_ratio"], -r["expected"], r["_key"]))
        by_worst = sorted(rows, key=lambda r: (r["_ratio"], -r["expected"], r["_key"]))

        def clean(row):
            return {k: v for k, v in row.items() if not k.startswith("_")}

        top = by_best[:CARD_LIST_ITEMS]
        top_ids = {r["membership_id"] for r in top}
        bottom = [r for r in by_worst if r["membership_id"] not in top_ids][:CARD_LIST_ITEMS]
        card = {"players_count": len(rows), "top": [clean(r) for r in top], "bottom": [clean(r) for r in bottom]}
        return {"card": card, "extras": {}, "lists": {"players": [clean(r) for r in by_best]}}

    return ctx.memo("attendance_ranking", compute)


# ---------------------------------------------------------------------------
# Nouveaux venus (carte 3) et évolution de l'effectif (carte 9)
# ---------------------------------------------------------------------------


def _arrival_json(ctx: _Ctx, m: Membership) -> dict:
    sponsor = ctx.members().get(m.sponsor_id) if m.sponsor_id else None
    return {
        **ctx.player(m.pk),
        "position": m.position,
        "position_label": m.get_position_display() if m.position else "",
        "joined_on": m.joined_on.isoformat(),
        "sponsor_name": f"{sponsor.user.first_name} {sponsor.user.last_name}".strip() if sponsor else None,
    }


def _departure_json(ctx: _Ctx, m: Membership) -> dict:
    return {
        **ctx.player(m.pk),
        "left_on": _iso(m.left_on),
        "left_reason": m.left_reason,
        "left_reason_label": m.get_left_reason_display() if m.left_reason else "",
    }


def _movements(ctx: _Ctx, start: date, end: date) -> tuple[list[Membership], list[Membership]]:
    members = ctx.counted_members()
    arrivals = sorted((m for m in members if start <= m.joined_on <= end), key=lambda m: (-m.joined_on.toordinal(), m.pk))
    departures = sorted(
        (m for m in members if m.status == Membership.Status.DEPARTED and start <= m.left_on <= end),
        key=lambda m: (-m.left_on.toordinal(), m.pk),
    )
    return arrivals, departures


def _pending_applications(ctx: _Ctx) -> list[dict]:
    pending = sorted(
        (m for m in ctx.members().values() if m.status == Membership.Status.PENDING), key=_name_key
    )
    if not pending:
        return []
    ids = [m.pk for m in pending]
    applications = {
        row["membership_id"]: row
        for row in MembershipApplication.all_objects.for_club(ctx.club)
        .filter(membership_id__in=ids, resolved_at__isnull=True)
        .values("membership_id", "sponsor_decision")
    }
    # Même définition que ``apps.treasury.services.has_paid_membership_fee``,
    # agrégée pour tous les dossiers en une requête.
    fee_rows = (
        Transaction.all_objects.for_club(ctx.club)
        .filter(
            membership_id__in=ids,
            contribution_type__is_membership_fee=True,
            status=Transaction.Status.SUCCEEDED,
            sealed_at__isnull=False,
        )
        .values("membership_id", "contribution_type_id", "contribution_type__amount")
        .annotate(net=Sum("amount"))
    )
    paid = {
        row["membership_id"]
        for row in fee_rows
        if row["contribution_type__amount"] is not None and row["net"] >= row["contribution_type__amount"]
    }
    items = []
    for m in pending:
        application = applications.get(m.pk)
        missing = []
        if application is None:
            missing.append(("application", "Dossier d'adhésion à compléter"))
        else:
            if application["sponsor_decision"] == MembershipApplication.SponsorDecision.REFUSED:
                missing.append(("sponsor_refused", "Refus du parrain : décision du Président attendue"))
            if m.pk not in paid:
                missing.append(("fee_unpaid", "Frais non payés"))
            if application["sponsor_decision"] == MembershipApplication.SponsorDecision.PENDING:
                missing.append(("sponsor_signature", "Signature du parrain attendue"))
        stage, label = missing[0] if missing else ("president_decision", "Validation en cours")
        items.append(
            {
                **_arrival_json(ctx, m),
                "stage": stage,
                "stage_label": label,
                "missing_steps": [{"code": code, "label": text} for code, text in missing],
            }
        )
    return items


def _newcomers(ctx: _Ctx) -> dict:
    def compute():
        arrivals, departures = _movements(ctx, ctx.period.start, ctx.until)
        arrivals_json = [_arrival_json(ctx, m) for m in arrivals]
        pending = _pending_applications(ctx)
        by_month_a = Counter(svc._period_start(m.joined_on) for m in ctx.counted_members())
        by_month_d = Counter(
            svc._period_start(m.left_on) for m in ctx.counted_members() if m.status == Membership.Status.DEPARTED
        )
        card = {
            "arrivals_count": len(arrivals),
            "departures_count": len(departures),
            "avatars": [
                {k: a[k] for k in ("membership_id", "player_name", "photo")} for a in arrivals_json[:CARD_LIST_ITEMS]
            ],
            "pending_count": len(pending),
            "series": [
                {
                    "month": fin._month_key(month),
                    "label": svc.french_month_label(month),
                    "arrivals": by_month_a[month],
                    "departures": by_month_d[month],
                }
                for month in ctx.period.months
            ],
        }
        return {
            "card": card,
            "extras": {},
            "lists": {
                "arrivals": arrivals_json,
                "pending": pending,
                "departures": [_departure_json(ctx, m) for m in departures],
            },
        }

    return ctx.memo("newcomers", compute)


def _squad_trend(ctx: _Ctx) -> dict:
    def compute():
        members = ctx.counted_members()
        series = []
        for month in ctx.period.months:
            month_end = min(fin._month_end(month), ctx.today)
            count = sum(
                1 for m in members if m.joined_on <= month_end and (m.left_on is None or m.left_on > month_end)
            )
            series.append(
                {
                    "month": fin._month_key(month),
                    "label": svc.french_month_label(month),
                    "count": count,
                    "arrivals": sum(1 for m in members if svc._period_start(m.joined_on) == month),
                    "departures": sum(
                        1
                        for m in members
                        if m.status == Membership.Status.DEPARTED and svc._period_start(m.left_on) == month
                    ),
                }
            )
        window_start = ctx.period.months[0] if ctx.period.months else ctx.period.start
        arrivals, departures = _movements(ctx, window_start, ctx.until)
        card = {
            "current_count": sum(1 for m in members if m.status == Membership.Status.ACTIVE),
            "window_start": window_start.isoformat(),
            "window_end": ctx.until.isoformat(),
            "arrivals_count": len(arrivals),
            "departures_count": len(departures),
            "series": series,
        }
        return {
            "card": card,
            "extras": {},
            "lists": {
                "arrivals": [_arrival_json(ctx, m) for m in arrivals],
                "departures": [_departure_json(ctx, m) for m in departures],
            },
        }

    return ctx.memo("squad_trend", compute)


# ---------------------------------------------------------------------------
# Résultats (carte 4) et discipline (carte 5)
# ---------------------------------------------------------------------------

_RESULT_LABELS = {"V": "Victoire", "N": "Nul", "D": "Défaite"}


def _match_json(ctx: _Ctx, sheet) -> dict:
    match = sheet.match
    goals_for, goals_against = sheet.score_home, sheet.score_away
    result = "V" if goals_for > goals_against else ("D" if goals_for < goals_against else "N")
    opponent = match.opponent_club.name if match.opponent_club_id else match.opponent_name
    return {
        "match_id": match.pk,
        "date": match.event.event_date.isoformat(),
        "opponent": opponent,
        "venue": match.venue,
        "venue_label": match.get_venue_display(),
        "match_type": match.match_type,
        "match_type_label": match.get_match_type_display(),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "result": result,
        "result_label": _RESULT_LABELS[result],
    }


def _results(ctx: _Ctx) -> dict:
    def compute():
        from apps.sport.models import MatchGoal, MatchSheet

        sheets = MatchSheet.all_objects.for_club(ctx.club).select_related("match__event", "match__opponent_club")
        in_period = list(
            sheets.filter(match__event__event_date__gte=ctx.period.start, match__event__event_date__lte=ctx.until)
            .order_by("-match__event__event_date", "-match_id")
        )
        recent = list(
            sheets.filter(match__event__event_date__lte=ctx.until).order_by("-match__event__event_date", "-match_id")[:5]
        )
        matches = [_match_json(ctx, s) for s in in_period]
        counts = Counter(m["result"] for m in matches)
        goals = (
            MatchGoal.all_objects.for_club(ctx.club)
            .filter(
                match_sheet__match__event__event_date__gte=ctx.period.start,
                match_sheet__match__event__event_date__lte=ctx.until,
            )
            .values_list("scorer_membership_id", "assist_membership_id")
        )
        scorers, assists = Counter(), Counter()
        for scorer_id, assist_id in goals:
            if scorer_id:
                scorers[scorer_id] += 1
            if assist_id:
                assists[assist_id] += 1

        def ranking(counter):
            order = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:CARD_LIST_ITEMS]
            return [{**ctx.player(mid), "count": n} for mid, n in order]

        card = {
            "played": len(matches),
            "wins": counts["V"],
            "draws": counts["N"],
            "losses": counts["D"],
            "goals_for": sum(m["goals_for"] for m in matches),
            "goals_against": sum(m["goals_against"] for m in matches),
            # Les 5 derniers matchs joués jusqu'à la fin de la période, du plus ancien au plus récent.
            "form": [_match_json(ctx, s) for s in reversed(recent)],
        }
        return {
            "card": card,
            "extras": {"top_scorers": ranking(scorers), "top_assists": ranking(assists)},
            "lists": {"matches": matches},
        }

    return ctx.memo("results", compute)


def _discipline(ctx: _Ctx) -> dict:
    def compute():
        from apps.sport.models import Incident

        labels = dict(Incident.IncidentType.choices)
        causes = dict(Incident.Cause.choices)
        rows = list(
            Incident.all_objects.for_club(ctx.club)
            .filter(event__event_date__gte=ctx.period.query_start, event__event_date__lte=ctx.until)
            .order_by("-event__event_date", "-pk")
            .values(
                "pk", "membership_id", "incident_type", "cause", "cause_detail", "minute", "event__event_date",
            )
        )
        kind_key = {
            Incident.IncidentType.YELLOW_CARD: "yellow",
            Incident.IncidentType.RED_CARD: "red",
            Incident.IncidentType.INTERNAL_SANCTION: "internal",
        }
        in_period = [r for r in rows if r["event__event_date"] >= ctx.period.start]
        totals = Counter(kind_key[r["incident_type"]] for r in in_period)
        monthly: dict[date, Counter] = defaultdict(Counter)
        for r in rows:
            monthly[svc._period_start(r["event__event_date"])][kind_key[r["incident_type"]]] += 1
        per_player: dict[int, Counter] = defaultdict(Counter)
        for r in in_period:
            per_player[r["membership_id"]][kind_key[r["incident_type"]]] += 1
        most = sorted(per_player.items(), key=lambda kv: (-sum(kv[1].values()), -kv[1]["red"], kv[0]))
        suspensions = []
        for membership_id, s in sorted(ctx.suspended().items(), key=lambda kv: _name_key(ctx.members()[kv[0]])):
            suspensions.append(
                {
                    **ctx.player(membership_id),
                    "reason": s.reason,
                    "reason_label": s.get_reason_display(),
                    "matches_total": s.matches_total,
                    "matches_served": s.matches_served,
                    "matches_remaining": s.matches_total - s.matches_served,
                    "since": s.created_at.date().isoformat(),
                }
            )
        card = {
            "yellow_cards": totals["yellow"],
            "red_cards": totals["red"],
            "internal_sanctions": totals["internal"],
            "suspended_count": len(suspensions),
            "series": [
                {
                    "month": fin._month_key(month),
                    "label": svc.french_month_label(month),
                    "yellow": monthly[month]["yellow"],
                    "red": monthly[month]["red"],
                    "internal": monthly[month]["internal"],
                }
                for month in ctx.period.months
            ],
        }
        incidents = [
            {
                "incident_id": r["pk"],
                **ctx.player(r["membership_id"]),
                "date": r["event__event_date"].isoformat(),
                "type": r["incident_type"],
                "type_label": labels[r["incident_type"]],
                "cause": r["cause"],
                "cause_label": causes[r["cause"]],
                "cause_detail": r["cause_detail"],
                "minute": r["minute"],
            }
            for r in in_period
        ]
        extras = {
            "most_sanctioned": [
                {
                    **ctx.player(mid),
                    "yellow": c["yellow"],
                    "red": c["red"],
                    "internal": c["internal"],
                    "total": sum(c.values()),
                }
                for mid, c in most[:CARD_LIST_ITEMS]
            ]
        }
        return {"card": card, "extras": extras, "lists": {"suspensions": suspensions, "incidents": incidents}}

    return ctx.memo("discipline", compute)


# ---------------------------------------------------------------------------
# Aptitude de l'effectif (carte 10) : AUCUN diagnostic (règle 11)
# ---------------------------------------------------------------------------


def _fitness(ctx: _Ctx) -> dict:
    def compute():
        from apps.medical.models import HealthRecord

        # Colonnes d'aptitude uniquement : le reste de la fiche (diagnostic,
        # blessures, déclaration, consentement) n'est jamais lu ici.
        records = {
            row["membership_id"]: row
            for row in HealthRecord.all_objects.for_club(ctx.club).values(
                "membership_id", "fitness_status", "fitness_return_date"
            )
        }
        groups: dict[str, list] = {"unfit": [], "fit_with_restriction": [], "fit": []}
        statuses = HealthRecord.FitnessStatus
        active = sorted(
            (m for m in ctx.members().values() if m.status == Membership.Status.ACTIVE), key=_name_key
        )
        for m in active:
            record = records.get(m.pk)
            status = record["fitness_status"] if record else statuses.FIT.value
            item = {**ctx.player(m.pk), "fitness_status": status, "return_date": None}
            if record and status != statuses.FIT:
                item["return_date"] = _iso(record["fitness_return_date"])
            groups[status].append(item)
        groups["unfit"].sort(key=lambda i: (i["return_date"] is None, i["return_date"] or ""))
        recorded = sum(1 for m in active if m.pk in records)
        card = {
            "total": len(active),
            "fit": len(groups["fit"]),
            "fit_with_restriction": len(groups["fit_with_restriction"]),
            "unfit": len(groups["unfit"]),
            "recorded_count": recorded,
            "no_information": recorded == 0,
            "unfit_players": groups["unfit"][:CARD_LIST_ITEMS],
            "notice": "Le détail médical n'est visible que par le Médecin et le joueur.",
        }
        return {
            "card": card,
            "extras": {},
            "lists": {
                "unfit": groups["unfit"],
                "restricted": groups["fit_with_restriction"],
                "fit": groups["fit"],
            },
        }

    return ctx.memo("fitness", compute)


# ---------------------------------------------------------------------------
# Prochaines échéances (carte 11)
# ---------------------------------------------------------------------------


def _upcoming(ctx: _Ctx) -> dict:
    def compute():
        from apps.assemblies.models import Assembly
        from apps.sport.models import Event, Match, Session

        until = ctx.today + timedelta(days=UPCOMING_DAYS)
        events = list(
            Event.all_objects.for_club(ctx.club)
            .filter(event_date__gte=ctx.today, event_date__lte=until)
            .order_by("event_date", "pk")
            .values("pk", "kind", "event_date")
        )
        sessions = {
            s["event_id"]: s
            for s in Session.all_objects.for_club(ctx.club)
            .filter(event_id__in=[e["pk"] for e in events if e["kind"] == "session"])
            .values("event_id", "gathering_time", "location")
        }
        matches = {
            m.pk: m
            for m in Match.all_objects.for_club(ctx.club)
            .filter(event_id__in=[e["pk"] for e in events if e["kind"] == "match"])
            .select_related("opponent_club")
        }
        items = []
        for e in events:
            if e["kind"] == "session":
                s = sessions.get(e["pk"], {})
                items.append(
                    {
                        "kind": "session",
                        "date": e["event_date"].isoformat(),
                        "time": _iso(s.get("gathering_time")),
                        "label": "Séance d'entraînement",
                        "detail": s.get("location") or "",
                        "event_id": e["pk"],
                    }
                )
            else:
                m = matches.get(e["pk"])
                opponent = (m.opponent_club.name if m.opponent_club_id else m.opponent_name) if m else ""
                items.append(
                    {
                        "kind": "match",
                        "date": e["event_date"].isoformat(),
                        "time": _iso(m.kickoff_time) if m else None,
                        "label": f"Match contre {opponent}".strip(),
                        "detail": (m.location if m else "") or "",
                        "event_id": e["pk"],
                    }
                )
        for a in Assembly.all_objects.for_club(ctx.club).filter(
            status=Assembly.Status.SCHEDULED, scheduled_date__gte=ctx.today, scheduled_date__lte=until
        ):
            items.append(
                {
                    "kind": "assembly",
                    "date": a.scheduled_date.isoformat(),
                    "time": a.scheduled_time.isoformat(),
                    "label": f"Assemblée générale ({a.get_assembly_type_display().lower()})",
                    "detail": a.location,
                    "assembly_id": a.pk,
                }
            )
        licence = (
            Licence.objects.filter(
                club_id=ctx.club.pk,
                status__in=(Licence.Status.ACTIVE, Licence.Status.TRIAL),
                end_date__gte=ctx.today,
                end_date__lte=until,
            )
            .order_by("end_date")
            .first()
        )
        if licence is not None:
            items.append(
                {
                    "kind": "licence",
                    "date": licence.end_date.isoformat(),
                    "time": None,
                    "label": "Fin de la licence Vesta du club",
                    "detail": "",
                    "licence_id": licence.pk,
                }
            )
        items.sort(key=lambda i: (i["date"], i["time"] or "", i["kind"]))
        card = {
            "as_of": ctx.today.isoformat(),
            "until": until.isoformat(),
            "count": len(items),
            "items": items[:CARD_LIST_ITEMS],
        }
        return {"card": card, "extras": {}, "lists": {"items": items}}

    return ctx.memo("upcoming", compute)


# ---------------------------------------------------------------------------
# À traiter (carte 13)
# ---------------------------------------------------------------------------


def _to_process(ctx: _Ctx) -> dict:
    def compute():
        from apps.assemblies.models import Assembly, Minutes

        expenses = list(
            Expense.all_objects.for_club(ctx.club)
            .filter(status=Expense.Status.PENDING)
            .select_related("category")
            .order_by("expense_date", "pk")
        )
        requests = list(
            SocialAssistanceRequest.all_objects.for_club(ctx.club)
            .filter(status=SocialAssistanceRequest.Status.SUBMITTED)
            .order_by("submitted_at", "pk")
        )
        minutes = [
            mn
            for mn in Minutes.all_objects.for_club(ctx.club)
            .filter(assembly__status=Assembly.Status.HELD)
            .select_related("assembly")
            .order_by("assembly__scheduled_date")
            if not mn.is_complete
        ]
        blocked = MembershipApplication.all_objects.for_club(ctx.club).filter(
            resolved_at__isnull=True, membership__status=Membership.Status.PENDING
        ).filter(
            Q(sponsor_decision=MembershipApplication.SponsorDecision.REFUSED)
            | Q(sponsor_decision=MembershipApplication.SponsorDecision.PENDING, president_alerted_at__isnull=False)
        ).order_by("pk")
        blocked = list(blocked)
        items = []
        for e in expenses:
            items.append(
                {
                    "kind": "expense_to_validate",
                    "date": e.expense_date.isoformat(),
                    "label": f"Dépense à valider : {e.category.name}",
                    "amount": fin._money(e.amount),
                    "ref_id": e.pk,
                }
            )
        for r in requests:
            items.append(
                {
                    "kind": "assistance_request",
                    "date": r.submitted_at.astimezone(ctx.tz()).date().isoformat(),
                    "label": "Demande d'assistance sociale à traiter",
                    **ctx.player(r.membership_id),
                    "ref_id": r.pk,
                }
            )
        for mn in minutes:
            items.append(
                {
                    "kind": "minutes_to_sign",
                    "date": mn.assembly.scheduled_date.isoformat(),
                    "label": "Procès-verbal d'assemblée à signer",
                    "ref_id": mn.assembly_id,
                }
            )
        for a in blocked:
            refused = a.sponsor_decision == MembershipApplication.SponsorDecision.REFUSED
            items.append(
                {
                    "kind": "blocked_application",
                    "date": None,
                    "label": "Adhésion bloquée : le parrain a refusé" if refused else "Adhésion bloquée : "
                    + BLOCKED_APPLICATION_DELAY_NOTE.lower(),
                    **ctx.player(a.membership_id),
                    "ref_id": a.pk,
                }
            )
        counts = {
            "expenses_to_validate": len(expenses),
            "assistance_requests": len(requests),
            "minutes_to_sign": len(minutes),
            "blocked_applications": len(blocked),
        }
        card = {"counts": counts, "total": sum(counts.values())}
        return {"card": card, "extras": {}, "lists": {"items": items}}

    return ctx.memo("to_process", compute)


# ---------------------------------------------------------------------------
# Matériel à retourner (carte 14)
# ---------------------------------------------------------------------------


def _equipment_out(ctx: _Ctx) -> dict:
    """Prêts en cours : par match et article (``OUT_LOAN`` moins ``IN_RETURN``
    du même match), ou par article et joueur pour un prêt sans match. « Depuis »
    = date du prêt ; en retard = plus de ``EQUIPMENT_OVERDUE_AFTER_DAYS`` jours
    depuis la date du match (sinon du prêt) ; ``overdue_days`` = jours au-delà
    de ce délai."""

    def compute():
        from apps.logistics.models import Article, StockMovement

        types = StockMovement.MovementType
        rows = (
            StockMovement.all_objects.for_club(ctx.club)
            .filter(movement_type__in=(types.OUT_LOAN, types.IN_RETURN))
            .values("match_id", "article_id", "membership_id", "movement_type", "movement_date")
            .annotate(quantity_sum=Sum("quantity"))
            .order_by()
        )
        groups: dict[tuple, dict] = {}
        for row in rows:
            key = (row["match_id"], row["article_id"], None if row["match_id"] else row["membership_id"])
            g = groups.setdefault(key, {"out": 0, "back": 0, "since": None, "players": set()})
            if row["movement_type"] == types.OUT_LOAN:
                g["out"] += row["quantity_sum"]
                g["since"] = row["movement_date"] if g["since"] is None else min(g["since"], row["movement_date"])
                if row["membership_id"]:
                    g["players"].add(row["membership_id"])
            else:
                g["back"] += row["quantity_sum"]
        open_groups = {k: g for k, g in groups.items() if g["out"] - g["back"] > 0}
        match_ids = {k[0] for k in open_groups if k[0]}
        from apps.sport.models import Event

        match_dates = {
            e["pk"]: e["event_date"]
            for e in Event.all_objects.for_club(ctx.club).filter(pk__in=match_ids).values("pk", "event_date")
        }
        articles = {
            a["pk"]: a["name"]
            for a in Article.all_objects.for_club(ctx.club)
            .filter(pk__in={k[1] for k in open_groups})
            .values("pk", "name")
        }
        items = []
        for (match_id, article_id, _player), g in open_groups.items():
            reference = match_dates.get(match_id) or g["since"]
            overdue_days = max((ctx.today - reference).days - EQUIPMENT_OVERDUE_AFTER_DAYS, 0)
            players = sorted(g["players"])
            items.append(
                {
                    "article_id": article_id,
                    "article_name": articles.get(article_id, ""),
                    "quantity": g["out"] - g["back"],
                    "since": g["since"].isoformat(),
                    "match_id": match_id,
                    **(ctx.player(players[0]) if len(players) == 1 else {"membership_id": None, "player_name": None, "photo": None}),
                    "players_count": len(players),
                    "overdue_days": overdue_days,
                    "is_overdue": overdue_days > 0,
                }
            )
        items.sort(key=lambda i: (-i["overdue_days"], i["since"], i["article_name"]))
        card = {
            "lines_count": len(items),
            "articles_count": sum(i["quantity"] for i in items),
            "overdue_count": sum(1 for i in items if i["is_overdue"]),
            "items": items[:CARD_LIST_ITEMS],
        }
        return {"card": card, "extras": {}, "lists": {"loans": items}}

    return ctx.memo("equipment_out", compute)


# ---------------------------------------------------------------------------
# Notes du Coach (carte 15)
# ---------------------------------------------------------------------------


def _coach_notes(ctx: _Ctx) -> dict:
    def compute():
        from apps.sport.models import Evaluation

        rows = list(
            Evaluation.all_objects.for_club(ctx.club)
            .filter(event__event_date__gte=ctx.period.query_start, event__event_date__lte=ctx.until)
            .values("event_id", "event__event_date", "event__kind")
            .annotate(total=Sum("overall_score"), n=Count("pk"))
            .order_by("event__event_date", "event_id")
        )
        events = []
        monthly: dict[date, list] = defaultdict(lambda: [Decimal("0"), 0])
        for r in rows:
            monthly[svc._period_start(r["event__event_date"])][0] += r["total"]
            monthly[svc._period_start(r["event__event_date"])][1] += r["n"]
            if r["event__event_date"] >= ctx.period.start:
                events.append(
                    {
                        "event_id": r["event_id"],
                        "kind": r["event__kind"],
                        "kind_label": _KIND_LABELS.get(r["event__kind"], r["event__kind"]),
                        "date": r["event__event_date"].isoformat(),
                        "average": _avg(r["total"], r["n"]),
                        "evaluations": r["n"],
                    }
                )
        total = sum((r["total"] for r in rows if r["event__event_date"] >= ctx.period.start), Decimal("0"))
        count = sum(r["n"] for r in rows if r["event__event_date"] >= ctx.period.start)
        card = {
            "average": _avg(total, count),
            "evaluations": count,
            "events_count": len(events),
            "points": events[-POINTS_MAX:],
            "series": [
                {
                    "month": fin._month_key(month),
                    "label": svc.french_month_label(month),
                    "average": _avg(*monthly[month]) if month in monthly else None,
                }
                for month in ctx.period.months
            ],
        }
        return {"card": card, "extras": {}, "lists": {"events": list(reversed(events))}}

    return ctx.memo("coach_notes", compute)


# ---------------------------------------------------------------------------
# Activité du fil (carte 16)
# ---------------------------------------------------------------------------


def _feed_activity(ctx: _Ctx) -> dict:
    def compute():
        from apps.social.models import Post

        tz = ctx.tz()
        start = datetime.combine(ctx.period.start, time.min, tzinfo=tz)
        end = datetime.combine(ctx.until + timedelta(days=1), time.min, tzinfo=tz)
        posts = list(
            Post.all_objects.for_club(ctx.club)
            .filter(deleted_at__isnull=True, created_at__gte=start, created_at__lt=end)
            .select_related("author")
            .annotate(
                likes_count=Count("likes", distinct=True),
                comments_count=Count("comments", filter=Q(comments__deleted_at__isnull=True), distinct=True),
            )
            .order_by("-created_at", "-pk")
        )
        weekly = ctx.period.mode == "month"
        buckets: Counter = Counter()
        for p in posts:
            day = p.created_at.astimezone(tz).date()
            buckets[day - timedelta(days=day.weekday()) if weekly else svc._period_start(day)] += 1
        if weekly:
            first = ctx.period.start - timedelta(days=ctx.period.start.weekday())
            keys = [first + timedelta(weeks=i) for i in range(((ctx.until - first).days // 7) + 1)]
            series = [
                {"start": k.isoformat(), "label": f"Semaine du {k:%d/%m}", "posts": buckets[k]} for k in keys
            ]
        else:
            series = [
                {"start": m.isoformat(), "label": svc.french_month_label(m), "posts": buckets[m]}
                for m in ctx.period.months
            ]
        kinds = dict(Post.PostKind.choices)
        card = {
            "posts_count": len(posts),
            "comments_count": sum(p.comments_count for p in posts),
            "likes_count": sum(p.likes_count for p in posts),
            "granularity": "week" if weekly else "month",
            "series": series,
        }
        items = [
            {
                "post_id": p.pk,
                "date": p.created_at.astimezone(tz).date().isoformat(),
                "kind": p.post_kind,
                "kind_label": kinds[p.post_kind],
                "author_name": f"{p.author.first_name} {p.author.last_name}".strip(),
                "excerpt": (p.body or "")[:140],
                "likes_count": p.likes_count,
                "comments_count": p.comments_count,
            }
            for p in posts
        ]
        return {"card": card, "extras": {}, "lists": {"posts": items}}

    return ctx.memo("feed_activity", compute)


# ---------------------------------------------------------------------------
# Situation de l'effectif : segment « Suspendu » (carte 6)
# ---------------------------------------------------------------------------


def _with_suspended(ctx: _Ctx, card: dict) -> dict:
    """Ajoute le 4e segment « Suspendu » à la carte financière.

    Priorité des statuts alignée sur ``apps.sport.services.get_playability`` :
    en attente d'adhésion, puis suspendu, puis dette (un joueur suspendu et en
    dette compte dans « Suspendu » ; sa dette reste visible dans
    ``suspended.also_in_debt_*`` et dans l'onglet « En dette » du détail). Les
    segments font toujours la somme de ``total``."""

    if "error" in card:
        return card
    groups = ctx.board.squad()
    suspended = ctx.suspended()
    good = [m for m, _ in groups["in_good_standing"] if m.pk not in suspended]
    debt = [(m, amount) for m, amount in groups["in_debt"] if m.pk not in suspended]
    in_debt_suspended = [amount for m, amount in groups["in_debt"] if m.pk in suspended]
    sus_count = sum(1 for m, _ in groups["in_good_standing"] + groups["in_debt"] if m.pk in suspended)
    total = card["total"]
    return {
        "as_of": card["as_of"],
        "total": total,
        "in_good_standing": {"count": len(good), "rate": fin._share(len(good), total)},
        "in_debt": {
            "count": len(debt),
            "rate": fin._share(len(debt), total),
            "amount": fin._money(sum((a for _, a in debt), Decimal("0"))),
        },
        "pending": card["pending"],
        "suspended": {
            "count": sus_count,
            "rate": fin._share(sus_count, total),
            "also_in_debt_count": len(in_debt_suspended),
            "also_in_debt_amount": fin._money(sum(in_debt_suspended, Decimal("0"))),
        },
    }


def _attach_photos(ctx: _Ctx, data: Any) -> Any:
    """Ajoute ``photo`` (URL absolue ou ``null``) à chaque ligne portant
    ``membership_id`` et ``player_name`` (listes financières)."""

    if isinstance(data, dict):
        if "membership_id" in data and "player_name" in data and "photo" not in data:
            member = ctx.members().get(data["membership_id"])
            data["photo"] = ctx.photo(member) if member else None
        for value in data.values():
            _attach_photos(ctx, value)
    elif isinstance(data, list):
        for value in data:
            _attach_photos(ctx, value)
    return data


# ---------------------------------------------------------------------------
# Points d'entrée
# ---------------------------------------------------------------------------

_BUILDERS: dict[str, Callable[[_Ctx], dict]] = {
    "attendance": _attendance,
    "newcomers": _newcomers,
    "results": _results,
    "discipline": _discipline,
    "squad_trend": _squad_trend,
    "fitness": _fitness,
    "upcoming": _upcoming,
    "attendance_ranking": _attendance_ranking,
    "to_process": _to_process,
    "equipment_out": _equipment_out,
    "coach_notes": _coach_notes,
    "feed_activity": _feed_activity,
}


def board_cards(club, period: Optional[dict] = None, *, request=None) -> dict:
    """Toutes les cartes du tableau de bord en un appel (fiche §10).

    Lève ``TreasuryValidationError`` / ``BoardDashboardError`` (période
    invalide) et ``TenantMismatchError``. Une carte qui plante vaut
    ``{"error": "…"}`` sans faire échouer les autres.

    Forme : ``{"period", "currency", "as_of", "contributions", "squad_status",
    "cash", "expenses_by_category", "upcoming_finance"`` (cartes financières,
    contrat ``finance_cards``)``, "attendance", "newcomers", "results",
    "discipline", "squad_trend", "fitness", "upcoming", "attendance_ranking",
    "to_process", "equipment_out", "coach_notes", "feed_activity"}``.
    """

    result = fin.finance_cards(club, period)
    ctx = _Ctx(club, period, request)
    result["as_of"] = ctx.today.isoformat()
    try:
        result["squad_status"] = _with_suspended(ctx, result["squad_status"])
    except Exception:
        logger.exception("Carte squad_status en erreur (club %s)", club.pk)
        result["squad_status"] = {"error": CARD_ERRORS["squad_status"]}
    for section, builder in _BUILDERS.items():
        try:
            result[section] = builder(ctx)["card"]
        except Exception:  # une carte en erreur ne casse pas les autres
            logger.exception("Carte %s en erreur (club %s)", section, club.pk)
            result[section] = {"error": CARD_ERRORS[section]}
    return result


def _suspended_list(ctx: _Ctx) -> list[dict]:
    debtors = {m.pk: amount for m, amount in ctx.board.squad()["in_debt"]}
    items = []
    for membership_id, s in sorted(ctx.suspended().items(), key=lambda kv: _name_key(ctx.members()[kv[0]])):
        items.append(
            {
                **ctx.player(membership_id),
                "reason": s.reason,
                "reason_label": s.get_reason_display(),
                "matches_remaining": s.matches_total - s.matches_served,
                "also_in_debt": membership_id in debtors,
                "amount_due": fin._money(debtors[membership_id]) if membership_id in debtors else None,
            }
        )
    return items


def board_section(
    club,
    section: str,
    period: Optional[dict] = None,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    only: Optional[str] = None,
    request=None,
) -> dict:
    """Détail d'une carte pour sa modale (fiche §5).

    ``section`` ∈ :data:`ALL_SECTIONS`. Sections financières : contrat de
    ``finance_section`` (+ ``photo`` sur chaque ligne joueur ; pour
    ``squad_status``, ``summary`` à 4 segments, drapeau ``is_suspended`` sur
    chaque ligne et liste ``suspended``). Sections non financières :
    ``{"section", "period", "summary", <extras>, <listes paginées>}``.
    Lève ``TreasuryValidationError`` / ``BoardDashboardError``.
    """

    if section not in ALL_SECTIONS:
        raise BoardDashboardError("Section inconnue du tableau de bord.")
    if not (isinstance(limit, int) and 1 <= limit <= MAX_LIMIT):
        raise BoardDashboardError(f"La limite doit être un entier entre 1 et {MAX_LIMIT}.")
    if not (isinstance(offset, int) and offset >= 0):
        raise BoardDashboardError("Le décalage doit être un entier positif ou nul.")
    ctx = _Ctx(club, period, request)

    if section in FINANCE_SECTIONS:
        if section == "squad_status" and only == "suspended":
            return {
                "section": section,
                "period": ctx.period.as_json(),
                "currency": ctx.board.currency,
                "suspended": _page(_suspended_list(ctx), limit, offset),
            }
        data = fin.finance_section(club, section, period, limit=limit, offset=offset, only=only)
        if section == "squad_status":
            suspended = ctx.suspended()
            for key in ("in_good_standing", "in_debt", "pending"):
                for item in data.get(key, {}).get("items", []):
                    item["is_suspended"] = item["membership_id"] in suspended
            if only is None:
                data["summary"] = _with_suspended(ctx, data["summary"])
                data["suspended"] = _page(_suspended_list(ctx), limit, offset)
        return _attach_photos(ctx, data)

    built = _BUILDERS[section](ctx)
    lists = built["lists"]
    if only is not None and only not in lists:
        raise BoardDashboardError("Liste inconnue pour cette section du tableau de bord.")
    result = {"section": section, "period": ctx.period.as_json()}
    if only is not None:
        result[only] = _page(lists[only], limit, offset)
        return result
    result["summary"] = built["card"]
    result.update(built["extras"])
    for name, values in lists.items():
        result[name] = _page(values, limit, offset)
    return result
