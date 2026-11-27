"""Statistiques de séance et évolution d'une séance à l'autre (CDC 4.7, 4.10 ;
docs/ecrans/sport-statistiques-seance.md, parties A et B). Lecture seule :
aucune migration, aucune écriture, donc aucune entrée de journal.

Toute valeur affichée est calculée ici, jamais par l'interface. Le filtrage
par rôle est fait ici aussi (matrice 2.4, A3) : le bloc « Notes du Coach »
n'est renvoyé qu'aux rôles autorisés (``evaluations: null`` pour les autres) ;
le joueur reçoit seulement ``my_evaluation`` (sa note, ses critères, les
commentaires que l'évaluateur a rendus visibles, jamais l'identité des
évaluateurs).

Positions par défaut appliquées (questions de la spec, à valider) :

- C-Q1 : les coéquipiers ne voient ni moyenne d'équipe ni classement des
  notes (provisoire, position prudente de la spec).
- C-Q2 : un joueur « En attente d'adhésion » n'est pas « attendu ».
- Joueur attendu à une date : adhésion commencée (``joined_on``) et non
  terminée (``left_on``) à cette date. Un joueur parti après la séance était
  donc attendu ce jour-là (même règle que le tableau de bord du bureau) ;
  une adhésion annulée avant l'inscription n'est jamais comptée.
- Une séance sans aucun pointage a un taux « null » (jamais 0 %) : elle ne
  fausse ni les moyennes ni les courbes.
- « Meilleures » et « plus faibles » notes : au plus 3 rangs, ex æquo tous
  affichés (5 lignes au plus) ; un joueur déjà cité parmi les meilleures
  n'est pas répété parmi les plus faibles. Sous 6 joueurs évalués, les deux
  listes se partagent l'effectif (meilleures : moitié haute arrondie au-dessus,
  plus faibles : le reste, ex. 3 évalués = 2 + 1) pour que « Notes les plus
  faibles » ne soit jamais vide dès 2 notes distinctes (décision par défaut,
  à confirmer). Moins de 2 joueurs évalués : pas de classement.
- Écart avec la moyenne : calculé sur les 10 séances précédentes, absent
  (null) s'il y en a moins de 3 de comparables.
"""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.db.models import QuerySet
from django.utils import timezone

from apps.clubs.models import Membership, Season
from apps.core.roles import get_active_roles
from apps.sport import performance, services
from apps.sport.models import Attendance, Evaluation, Event, Session
from apps.sport.permissions import (
    EVALUATION_STATS_ROLES,
    EVALUATOR_ROLES,
    PERFORMANCE_MANAGER_ROLES,
    PERFORMANCE_VIEW_ALL_ROLES,
)
from apps.sport.serializers import serialize_membership_brief
from apps.sport.services import SportValidationError

PERIODS = ("last10", "season")
LAST_N = 10
MIN_PRIOR_FOR_DELTA = 3
RANKING_MAX_RANK = 3
RANKING_MAX_LINES = 5

_ONE = Decimal("1")
_TENTH = Decimal("0.1")
_CRITERIA = (
    ("technical", "technical_score"),
    ("physical", "physical_score"),
    ("tactical", "tactical_score"),
    ("mental", "mental_score"),
    ("attitude", "attitude_score"),
)
_BUCKETS = (
    ("0 à 2", Decimal("0"), Decimal("2")),
    ("2 à 4", Decimal("2"), Decimal("4")),
    ("4 à 6", Decimal("4"), Decimal("6")),
    ("6 à 8", Decimal("6"), Decimal("8")),
    ("8 à 10", Decimal("8"), Decimal("10")),
)
_EXCUSE_LABELS = ("Blessé", "Voyage", "Autre")


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def parse_period(value) -> str:
    value = value or "last10"
    if value not in PERIODS:
        raise SportValidationError("Période invalide : choisissez « 10 dernières séances » ou « Saison ».")
    return value


def attendance_rate_percent(numerator: int, denominator: int) -> Optional[int]:
    """Taux de présence en pourcentage, arrondi à l'unité (demi vers le haut).

    Règle unique d'arrondi des taux de présence (spec A4.1) : réutilisée par le
    tableau de bord du bureau, qui doit afficher le même chiffre
    (``club-tableau-de-bord-bureau.md`` §9). Dénominateur nul : ``None``.
    """

    if not denominator:
        return None
    return int((Decimal(numerator * 100) / Decimal(denominator)).quantize(_ONE, rounding=ROUND_HALF_UP))


_pct = attendance_rate_percent


def _name(membership: Membership) -> str:
    return f"{membership.user.first_name} {membership.user.last_name}".strip()


def _mean(values, places: Decimal) -> Optional[Decimal]:
    values = list(values)
    if not values:
        return None
    return (sum(values, Decimal("0")) / Decimal(len(values))).quantize(places, rounding=ROUND_HALF_UP)


def is_expectable(membership: Membership) -> bool:
    """Règle UNIQUE « qui peut être attendu » (CDC 10.3 n° 185) : ni en
    attente (C-Q2), ni partie sans date de départ, ni annulée avant
    l'inscription. Partagée par la page Entraînements (:func:`_roster`) et le
    tableau de bord du bureau (:func:`roster_from`), qui n'a aucun calcul
    propre."""

    if membership.status == Membership.Status.PENDING:
        return False
    if membership.status == Membership.Status.DEPARTED and (
        membership.left_on is None or membership.left_reason == Membership.LeftReason.CANCELLED
    ):
        return False
    return True


def roster_from(memberships) -> list[Membership]:
    """Filtre des adhésions déjà chargées (aucune requête) selon
    :func:`is_expectable`."""

    return [m for m in memberships if is_expectable(m)]


def _roster(club) -> list[Membership]:
    """Adhésions pouvant être « attendues » à une date (:func:`is_expectable`),
    en une requête, ``user`` joint."""

    return roster_from(Membership.all_objects.filter(club=club).select_related("user"))


def _expected_on(roster, day) -> list[Membership]:
    return [m for m in roster if m.joined_on <= day and (m.left_on is None or m.left_on >= day)]


def _attendance_rows(club, event_ids) -> dict[int, dict[int, tuple]]:
    rows: dict[int, dict[int, tuple]] = defaultdict(dict)
    ids = event_ids if isinstance(event_ids, QuerySet) else list(event_ids)
    queryset = Attendance.all_objects.filter(club=club, event_id__in=ids).values_list(
        "event_id", "membership_id", "status", "arrived_at", "excused_reason"
    )
    for event_id, membership_id, status, arrived_at, reason in queryset:
        rows[event_id][membership_id] = (status, arrived_at, reason)
    return rows


def _event_counts(expected, rows_for_event: dict, counts_absent: bool) -> dict:
    counts = {"expected": len(expected), "present": 0, "late": 0, "excused": 0, "absent": 0}
    for membership in expected:
        row = rows_for_event.get(membership.pk)
        status = row[0] if row else None
        if status == Attendance.Status.PRESENT:
            counts["present"] += 1
        elif status == Attendance.Status.LATE_ABSENT:
            counts["late"] += 1
        elif status == Attendance.Status.EXCUSED_ABSENT:
            counts["excused"] += 1
        else:
            counts["absent"] += 1
    counts["counted_present"] = counts["present"] + (0 if counts_absent else counts["late"])
    counts["marked"] = bool(rows_for_event)
    counts["rate"] = _pct(counts["counted_present"], counts["expected"]) if counts["marked"] else None
    return counts


def _retained_by_event(club, event_ids, *, membership_ids=None) -> dict[int, dict[int, dict]]:
    """``{event_id: {membership_id: {...}}}`` : note retenue d'un joueur =
    moyenne des notes globales de ses évaluateurs, arrondie à 0,1 (CDC 4.10).
    Une seule requête (``event_ids`` peut être une sous-requête) ; les
    moyennes sont calculées en Decimal."""

    ids = event_ids if isinstance(event_ids, QuerySet) else list(event_ids)
    queryset = Evaluation.all_objects.filter(club=club, event_id__in=ids)
    if membership_ids is not None:
        queryset = queryset.filter(membership_id__in=list(membership_ids))
    grouped: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for evaluation in queryset.order_by("created_at", "pk"):
        grouped[evaluation.event_id][evaluation.membership_id].append(evaluation)
    result: dict[int, dict[int, dict]] = {}
    for event_id, by_member in grouped.items():
        result[event_id] = {}
        for membership_id, items in by_member.items():
            criteria = {}
            for key, field in _CRITERIA:
                values = [getattr(item, field) for item in items if getattr(item, field) is not None]
                criteria[key] = _mean(values, _TENTH)
            result[event_id][membership_id] = {
                "overall": _mean([item.overall_score for item in items], _TENTH),
                "criteria": criteria,
                "evaluators_count": len(items),
                "items": items,
            }
    return result


def _event_average(retained_for_event: dict) -> Optional[Decimal]:
    return _mean([row["overall"] for row in retained_for_event.values()], _TENTH)


def summarize_ratings(club, events, *, retained=None) -> dict:
    """Définition UNIQUE de la note moyenne de l'équipe (CDC 10.3 n° 190,
    décision du client du 27/11/2026) : « moyenne par joueur, sur base de ça
    on calcule la moyenne de l'équipe ».

    1. note retenue par joueur et par événement = moyenne de ses évaluateurs
       (CDC 4.10, :func:`_retained_by_event`) ;
    2. moyenne par joueur sur les ``events`` donnés ;
    3. moyenne de l'équipe = moyenne des moyennes par joueur (un joueur
       évalué 20 fois ne pèse pas plus qu'un joueur évalué une fois).

    Arrondi à 0,1 à chaque étape, comme la page « Entraînements » (notes
    retenues et moyennes d'événement). Appelée par la page Entraînements et
    par le tableau de bord du bureau (aucun calcul propre). ``retained`` :
    notes retenues déjà chargées (sur-ensemble accepté) ; sinon une requête."""

    events = list(events)
    event_ids = [event.pk for event in events]
    if retained is None:
        retained = _retained_by_event(club, event_ids) if event_ids else {}
    per_player: dict[int, list] = defaultdict(list)
    per_event: dict[int, dict] = {}
    evaluations = 0
    for event_id in event_ids:
        by_member = retained.get(event_id, {})
        count = sum(row["evaluators_count"] for row in by_member.values())
        evaluations += count
        per_event[event_id] = {"average": _event_average(by_member), "evaluations": count}
        for membership_id, row in by_member.items():
            per_player[membership_id].append(row["overall"])
    player_averages = {pk: _mean(values, _TENTH) for pk, values in per_player.items()}
    return {
        "team_average": _mean(player_averages.values(), _TENTH),
        "player_averages": player_averages,
        "per_event": per_event,
        "evaluations": evaluations,
    }


def _prior_events(club, event: Event) -> list[Event]:
    from django.db.models import Q

    return list(
        Event.all_objects.filter(club=club, kind=Event.Kind.SESSION)
        .filter(Q(event_date__lt=event.event_date) | Q(event_date=event.event_date, pk__lt=event.pk))
        .order_by("-event_date", "-pk")[:LAST_N]
    )


def _viewer_membership(viewer, club) -> Optional[Membership]:
    if getattr(viewer, "is_superuser", False):
        return None
    return Membership.all_objects.filter(club=club, user=viewer, status=Membership.Status.ACTIVE).first()


def _sees_evaluations(viewer, roles) -> bool:
    return bool(getattr(viewer, "is_superuser", False) or (roles & EVALUATION_STATS_ROLES))


def _ranked(items, *, reverse: bool):
    """Rang « compétition » (ex æquo : même rang, le suivant saute)."""

    ordered = sorted(items, key=lambda pair: pair[1], reverse=reverse)
    ranked, previous, rank = [], None, 0
    for index, (membership, note) in enumerate(ordered, start=1):
        if note != previous:
            rank = index
            previous = note
        ranked.append((rank, membership, note))
    return ranked


def _ranking_caps(evaluated_count: int) -> tuple[int, int]:
    """Nombre de rangs des listes « Meilleures notes » et « Notes les plus
    faibles » (décision par défaut, à confirmer : la spec A4.2 ne règle pas
    le cas d'un petit effectif). 3 rangs chacune ; sous 6 joueurs évalués,
    moitié haute arrondie au-dessus pour les meilleures, moitié basse pour les
    plus faibles. Aucun joueur n'est cité dans les deux listes."""

    return (
        min(RANKING_MAX_RANK, math.ceil(evaluated_count / 2)),
        min(RANKING_MAX_RANK, evaluated_count // 2),
    )


# ---------------------------------------------------------------------------
# A : statistiques d'une séance
# ---------------------------------------------------------------------------


def get_session_stats(session: Session, *, viewer, request=None) -> dict:
    event = session.event
    club = event.club
    club_settings = services._club_settings(club)
    counts_absent = club_settings.late_arrival_counts_absent
    roles = get_active_roles(viewer, club=club)
    sees_evaluations = _sees_evaluations(viewer, roles)
    viewer_membership = _viewer_membership(viewer, club)

    roster = _roster(club)
    prior = _prior_events(club, event)
    rows = _attendance_rows(club, [event.pk, *[p.pk for p in prior]])
    members_by_id = {m.pk: m for m in roster}

    def brief(membership):
        return serialize_membership_brief(membership, request=request)

    # ---- Présence -------------------------------------------------------
    expected = _expected_on(roster, event.event_date)
    rows_here = rows.get(event.pk, {})
    counts = _event_counts(expected, rows_here, counts_absent)
    prior_rates = [
        _event_counts(_expected_on(roster, p.event_date), rows.get(p.pk, {}), counts_absent)["rate"] for p in prior
    ]
    prior_rates = [rate for rate in prior_rates if rate is not None]
    attendance_delta = None
    if counts["rate"] is not None and len(prior_rates) >= MIN_PRIOR_FOR_DELTA:
        average = Decimal(sum(prior_rates)) / Decimal(len(prior_rates))
        attendance_delta = int((Decimal(counts["rate"]) - average).quantize(_ONE, rounding=ROUND_HALF_UP))

    late_list, excused_list, absent_list = [], [], []
    for membership in sorted(expected, key=lambda m: (_name(m).lower(), m.pk)):
        row = rows_here.get(membership.pk)
        status = row[0] if row else None
        if status == Attendance.Status.LATE_ABSENT:
            late_list.append({**brief(membership), "arrived_at": row[1]})
        elif status == Attendance.Status.EXCUSED_ABSENT:
            label = (row[2] or "").split(" : ", 1)[0].strip()
            # Jamais de détail (médical ou autre) : seulement le motif de la liste fermée.
            excused_list.append({**brief(membership), "reason": label if label in _EXCUSE_LABELS else "Autre"})
        elif status in (None, Attendance.Status.ABSENT):
            absent_list.append(brief(membership))
    late_list.sort(key=lambda item: (item["arrived_at"] is None, item["arrived_at"]))

    attendance = {
        "expected": counts["expected"],
        "present": counts["present"],
        "late": counts["late"],
        "absent": counts["absent"],
        "excused": counts["excused"],
        "rate": counts["rate"],
        "nobody_marked": not counts["marked"],
        "late_counts_as_absent": counts_absent,
        "late_label": "En retard, compté absent" if counts_absent else "En retard",
        "late_family": "danger" if counts_absent else "warning",
        "delta_vs_average": attendance_delta,
        "late_list": late_list,
        "excused_list": excused_list,
        "absent_list": absent_list,
    }

    # ---- Évaluations ----------------------------------------------------
    locked = services.is_evaluation_locked(event)
    locks_at = services.evaluation_locks_at(event)
    pointed_ids = {
        membership_id
        for membership_id, row in rows_here.items()
        if row[0] in (Attendance.Status.PRESENT, Attendance.Status.LATE_ABSENT)
    }
    retained_event = _retained_by_event(
        club, [event.pk], membership_ids=None if sees_evaluations else (
            [viewer_membership.pk] if viewer_membership else []
        )
    ).get(event.pk, {})

    evaluations = None
    if sees_evaluations:
        evaluations = _build_evaluations_block(
            club=club,
            event=event,
            prior=prior,
            retained_event=retained_event,
            pointed_ids=pointed_ids,
            members_by_id=members_by_id,
            locked=locked,
            locks_at=locks_at,
            brief=brief,
        )

    my_evaluation = None
    if viewer_membership is not None and viewer_membership.pk in retained_event:
        mine = retained_event[viewer_membership.pk]
        my_evaluation = {
            "overall": str(mine["overall"]),
            "criteria": {key: (str(value) if value is not None else None) for key, value in mine["criteria"].items()},
            "comments": [item.comment for item in mine["items"] if item.comment and item.comment_visible_to_player],
        }

    return {
        "session_id": session.pk,
        "date": event.event_date,
        "attendance": attendance,
        "evaluations": evaluations,
        "my_evaluation": my_evaluation,
        "measures": performance.session_measures_summary(
            event, sees_all=bool(getattr(viewer, "is_superuser", False) or roles & PERFORMANCE_VIEW_ALL_ROLES),
            viewer_membership=viewer_membership,
        ),
        "capabilities": {
            "can_evaluate": bool(roles & EVALUATOR_ROLES) and not locked,
            "can_measure": bool(roles & PERFORMANCE_MANAGER_ROLES) and not locked,
        },
        "generated_at": timezone.now(),
    }


def _build_evaluations_block(
    *, club, event, prior, retained_event, pointed_ids, members_by_id, locked, locks_at, brief
) -> dict:
    notes = {mid: row["overall"] for mid, row in retained_event.items()}
    average = _mean(notes.values(), _TENTH)

    prior_ids = [p.pk for p in prior]
    prior_retained = _retained_by_event(club, prior_ids) if prior_ids else {}
    prior_averages = [
        avg for avg in (_event_average(prior_retained.get(pk, {})) for pk in prior_ids) if avg is not None
    ]
    delta = None
    if average is not None and len(prior_averages) >= MIN_PRIOR_FOR_DELTA:
        delta = (average - _mean(prior_averages, Decimal("0.01"))).quantize(_TENTH, rounding=ROUND_HALF_UP)

    evaluated_members = [(members_by_id.get(mid), note) for mid, note in notes.items() if mid in members_by_id]
    ranking_available = len(evaluated_members) >= 2
    best, lowest = [], []
    if ranking_available:
        # Moins de 6 joueurs évalués : les deux listes se partagent l'effectif
        # (meilleures = moitié haute, plus faibles = moitié basse) pour que
        # « Notes les plus faibles » apparaisse dès 2 joueurs évalués.
        best_max_rank, lowest_max_rank = _ranking_caps(len(evaluated_members))
        top_ranked = [r for r in _ranked(evaluated_members, reverse=True) if r[0] <= best_max_rank]
        best_ranked = top_ranked[:RANKING_MAX_LINES]
        best_ids = {m.pk for _rank, m, _note in top_ranked}  # ex æquo au-delà de 5 lignes : jamais « plus faibles »
        remaining = [(m, note) for m, note in evaluated_members if m.pk not in best_ids]
        lowest_ranked = [r for r in _ranked(remaining, reverse=False) if r[0] <= lowest_max_rank][
            :RANKING_MAX_LINES
        ]
        best = [{"rank": rank, "player": brief(m), "note": str(note)} for rank, m, note in best_ranked]
        lowest = [{"rank": rank, "player": brief(m), "note": str(note)} for rank, m, note in lowest_ranked]

    distribution = []
    for index, (label, low, high) in enumerate(_BUCKETS):
        last = index == len(_BUCKETS) - 1
        count = sum(1 for note in notes.values() if low <= note < high or (last and note == high))
        distribution.append({"label": label, "min": str(low), "max": str(high), "count": count})

    players = []
    for membership_id, row in retained_event.items():
        membership = members_by_id.get(membership_id)
        if membership is None:
            continue
        players.append(
            {
                "player": brief(membership),
                "overall": str(row["overall"]),
                **{key: (str(value) if value is not None else None) for key, value in row["criteria"].items()},
                "evaluators_count": row["evaluators_count"],
                "comments": [
                    {"text": item.comment, "visible_to_player": item.comment_visible_to_player}
                    for item in row["items"]
                    if item.comment
                ],
            }
        )
    players.sort(key=lambda item: (-Decimal(item["overall"]), item["player"]["name"].lower()))
    not_evaluated = [
        brief(members_by_id[mid])
        for mid in sorted(pointed_ids - set(notes), key=lambda i: (_name(members_by_id[i]).lower() if i in members_by_id else "", i))
        if mid in members_by_id
    ]
    hours_left = None
    if not locked:
        hours_left = max(0, math.ceil((locks_at - timezone.now()).total_seconds() / 3600))

    return {
        "average": str(average) if average is not None else None,
        "evaluated": len(notes),
        "eligible": len(pointed_ids),
        "remaining": len(not_evaluated),
        "delta_vs_average": str(delta) if delta is not None else None,
        "ranking_available": ranking_available,
        "best": best,
        "lowest": lowest,
        "distribution": distribution,
        "players": players,
        "not_evaluated": not_evaluated,
        "open_until": locks_at,
        "locked": locked,
        "hours_left": hours_left,
    }


# ---------------------------------------------------------------------------
# Moyenne de présence d'une période et assiduité : définition unique
# ---------------------------------------------------------------------------

_TOTAL_KEYS = ("expected", "present", "late", "excused", "absent", "counted_present")


def attendance_rows(club, event_ids) -> dict[int, dict[int, tuple]]:
    """Pointages des événements donnés, en une requête filtrée sur le club :
    ``{event_id: {membership_id: (status, arrived_at, excused_reason)}}``.
    ``event_ids`` peut être un ``QuerySet`` d'identifiants (sous-requête)."""

    return _attendance_rows(club, event_ids)


def aggregate_attendance(counts_list) -> dict:
    """Agrège des compteurs par événement (ceux de ``summarize_attendance``)
    selon la définition unique de la moyenne de présence (CDC 10.3 n° 185,
    position provisoire à confirmer ; spec A4.1) : seuls les événements
    pointés comptent ; taux = total des présents comptés ÷ total des attendus,
    arrondi à l'unité une seule fois (``attendance_rate_percent``)."""

    totals = {key: 0 for key in _TOTAL_KEYS}
    events = 0
    for counts in counts_list:
        if not counts["marked"]:
            continue  # non pointé : ni dans la moyenne ni dans la courbe (jamais 0 %)
        events += 1
        for key in _TOTAL_KEYS:
            totals[key] += counts[key]
    return {**totals, "events": events, "rate": _pct(totals["counted_present"], totals["expected"])}


def summarize_attendance(club, events, *, roster=None, rows=None, counts_absent=None) -> dict:
    """Présence d'une liste d'événements : **seule** fonction qui calcule la
    moyenne de présence d'une période et l'assiduité par joueur. Appelée par la
    page « Entraînements » (B2, assiduité) et par le tableau de bord du bureau
    (``apps.clubs.board_dashboard``, cartes 1 et 12), qui doivent afficher les
    mêmes chiffres (``club-tableau-de-bord-bureau.md`` §9).

    ``events`` : objets ``Event`` (``pk``, ``event_date``). L'appelant choisit
    la période et le type : la moyenne de présence ne porte que sur les
    séances (CDC 10.3 n° 185) ; un appel séparé sur les matchs donne leur taux
    propre. ``roster``, ``rows`` et ``counts_absent`` peuvent être fournis
    pour ne pas répéter les requêtes ; sinon une requête chacun.

    Règles (A4.1) : joueurs attendus = adhésion à la date (en attente exclus,
    C-Q2) ; retard compté absent selon le club (10.2 n° 25) ; absence excusée
    au dénominateur ; un événement sans aucun pointage a un taux ``None`` et
    n'entre ni dans la moyenne ni dans l'assiduité.
    """

    events = list(events)
    if counts_absent is None:
        counts_absent = services._club_settings(club).late_arrival_counts_absent
    if roster is None:
        roster = _roster(club)
    if rows is None:
        rows = _attendance_rows(club, [e.pk for e in events])

    per_event: dict[int, dict] = {}
    players: dict[int, dict] = {}
    for event in events:
        rows_here = rows.get(event.pk, {})
        expected = _expected_on(roster, event.event_date)
        counts = _event_counts(expected, rows_here, counts_absent)
        per_event[event.pk] = counts
        if not counts["marked"]:
            continue
        for membership in expected:
            entry = players.setdefault(
                membership.pk,
                {"membership": membership, "sessions": 0, "present": 0, "late": 0, "excused": 0, "absent": 0},
            )
            entry["sessions"] += 1
            status = (rows_here.get(membership.pk) or (None,))[0]
            if status == Attendance.Status.PRESENT:
                entry["present"] += 1
            elif status == Attendance.Status.LATE_ABSENT:
                entry["late"] += 1
            elif status == Attendance.Status.EXCUSED_ABSENT:
                entry["excused"] += 1
            else:
                entry["absent"] += 1
    for entry in players.values():
        entry["attended"] = entry["present"] + (0 if counts_absent else entry["late"])
        entry["rate"] = _pct(entry["attended"], entry["sessions"])

    period = aggregate_attendance(per_event.values())
    return {
        "per_event": per_event,
        "totals": {key: period[key] for key in _TOTAL_KEYS},
        "sessions_counted": period["events"],
        "average_rate": period["rate"],
        "players": players,
        "late_counts_absent": counts_absent,
    }


# ---------------------------------------------------------------------------
# B : évolution d'une séance à l'autre, assiduité
# ---------------------------------------------------------------------------


def _current_season(club) -> Optional[Season]:
    return (
        Season.all_objects.filter(club=club, is_current=True).order_by("-start_date").first()
        or Season.all_objects.filter(club=club).order_by("-start_date").first()
    )


def _period_events(club, period: str) -> tuple[list[Event], Optional[Season]]:
    today = services.get_club_today(club)
    base = Event.all_objects.filter(club=club, kind=Event.Kind.SESSION, event_date__lte=today)
    season = _current_season(club)
    if period == "season":
        if season is None:
            return [], None
        return list(base.filter(season=season).order_by("event_date", "pk")), season
    events = list(base.order_by("-event_date", "-pk")[:LAST_N])
    events.reverse()
    return events, season


def get_stats_history(club, *, viewer, period: str) -> dict:
    period = parse_period(period)
    events, season = _period_events(club, period)
    roles = get_active_roles(viewer, club=club)
    sees_evaluations = _sees_evaluations(viewer, roles)
    viewer_membership = _viewer_membership(viewer, club)
    summary = summarize_attendance(club, events)
    event_ids = [e.pk for e in events]
    retained = _retained_by_event(
        club,
        event_ids,
        membership_ids=None if sees_evaluations else ([viewer_membership.pk] if viewer_membership else []),
    )
    locations = dict(Session.all_objects.filter(club=club, event_id__in=event_ids).values_list("event_id", "location"))

    # Note moyenne de l'équipe : moyenne des moyennes par joueur (10.3
    # n° 190), même fonction que le tableau de bord du bureau.
    ratings = summarize_ratings(club, events, retained=retained) if sees_evaluations else None
    results = []
    for event in events:
        counts = summary["per_event"][event.pk]
        by_member = retained.get(event.pk, {})
        average_rating = ratings["per_event"][event.pk]["average"] if ratings else None
        my_rating = None
        if viewer_membership is not None and viewer_membership.pk in by_member:
            my_rating = by_member[viewer_membership.pk]["overall"]
        results.append(
            {
                "session_id": event.pk,
                "date": event.event_date,
                "location": locations.get(event.pk, ""),
                "expected": counts["expected"],
                "present": counts["present"],
                "attendance_rate": counts["rate"],
                "average_rating": str(average_rating) if average_rating is not None else None,
                "my_rating": str(my_rating) if my_rating is not None else None,
                "locked": services.is_event_locked(event),
            }
        )
    my_ratings = [Decimal(r["my_rating"]) for r in results if r["my_rating"] is not None]
    return {
        "period": period,
        "season": {"id": season.pk, "label": season.label} if season else None,
        # Définition unique (CDC 10.3 n° 185) : total des présents comptés ÷
        # total des attendus sur les séances pointées, arrondi une seule fois.
        "average_attendance_rate": summary["average_rate"],
        "average_rating": (
            str(ratings["team_average"]) if ratings and ratings["team_average"] is not None else None
        ),
        "my_average_rating": str(_mean(my_ratings, _TENTH)) if my_ratings else None,
        "results": results,
    }


def _player_totals(club, period: str):
    events, season = _period_events(club, period)
    summary = summarize_attendance(club, events)
    return summary["players"], summary["sessions_counted"], summary["late_counts_absent"], season


def get_attendance_ranking(club, *, period: str, request=None) -> dict:
    period = parse_period(period)
    totals, sessions_counted, counts_absent, _season = _player_totals(club, period)
    entries = sorted(
        totals.values(),
        key=lambda e: (-(e["rate"] if e["rate"] is not None else -1), -e["sessions"], _name(e["membership"]).lower()),
    )
    results = [
        {
            "player": serialize_membership_brief(entry["membership"], request=request),
            "sessions": entry["sessions"],
            "attended": entry["attended"],
            "present": entry["present"],
            "late": entry["late"],
            "excused": entry["excused"],
            "absent": entry["absent"],
            "rate": entry["rate"],
        }
        for entry in entries
    ]
    return {
        "period": period,
        "sessions_count": sessions_counted,
        "late_counts_as_absent": counts_absent,
        "results": results,
    }


def get_my_attendance(club, *, viewer, period: str) -> Optional[dict]:
    period = parse_period(period)
    membership = _viewer_membership(viewer, club)
    if membership is None:
        return None
    totals, sessions_counted, counts_absent, _season = _player_totals(club, period)
    entry = totals.get(membership.pk)
    entry = entry or {"sessions": 0, "attended": 0, "present": 0, "late": 0, "excused": 0, "absent": 0, "rate": None}
    return {
        "period": period,
        "sessions_count": sessions_counted,
        "sessions": entry["sessions"],
        "attended": entry["attended"],
        "present": entry["present"],
        "late": entry["late"],
        "excused": entry["excused"],
        "absent": entry["absent"],
        "rate": entry["rate"],
        "late_counts_as_absent": counts_absent,
    }
