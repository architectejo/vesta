"""Cartes de joueurs et statistiques sportives (CDC 4.2 ; docs/ecrans/
club-cartes-joueurs.md §7 et club-carte-joueur.md partie B). Lecture seule :
aucune migration, aucune écriture, donc aucune entrée de journal.

Toute valeur est calculée ici, jamais par l'interface, à partir des tables
existantes (matchs, buts, incidents, présences, évaluations), avec un nombre
FIXE de requêtes par appel (jamais une requête par joueur).

Visibilité (CDC 4.2 : « la carte et les statistiques sportives sont publiques »;
poids, taille, téléphone, finances et santé ne le sont jamais) : ce module ne
lit AUCUN de ces champs. Les seules données sensibles servies sont filtrées par
rôle ici (10.2 n° 16) : suspension en cours et aptitude (jamais de diagnostic)
au staff et au joueur lui-même ; mesures de performance au staff et au joueur.

Positions par défaut appliquées (à valider, voir le compte rendu) :

- Période : saison choisie (``season``), par défaut la saison courante du club
  (``is_current``, sinon la plus récente). Les cinq indicateurs, le radar et la
  forme récente suivent cette saison.
- Matchs joués : matchs de la saison dont le score est saisi et où le joueur
  figure dans la composition (titulaire ou remplaçant : les minutes ne sont pas
  suivies) ou a marqué / donné une passe. Un match compte une seule fois.
- Taux de présence : séances seulement (jamais les matchs : un joueur non
  convoqué serait compté absent), mêmes règles que les statistiques de séance
  (séance sans aucun pointage ignorée, retard compté absent selon le club).
- Note d'un événement : moyenne des notes globales des évaluateurs, arrondie à
  0,1 (4.10). Note moyenne : moyenne de ces notes sur la saison. Jamais
  l'identité d'un évaluateur ni un commentaire.
- Radar : les cinq critères d'évaluation du 4.10 (technique, physique, tactique,
  mental, attitude), moyenne sur la saison, échelle 0 à 10 (point ouvert 12 non
  tranché : aucune formule inventée pour « discipline », « assiduité »,
  « contribution offensive »).
- ``overall_rating`` reste ``None`` (point ouvert 4 non tranché).
- Cartons : seuls les jaunes et rouges comptent ; la cause est une catégorie,
  jamais le détail libre ni l'arbitre.
- Comparaison entre clubs : seulement les joueurs inscrits ayant consenti à la
  publication de leur carte, non mineurs (7.5) ; jamais le radar d'un autre club
  (point ouvert 13). Âge inconnu : traité comme adulte (on ne présume pas la
  minorité).
"""

from __future__ import annotations

import datetime
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from apps.clubs.models import Membership, Season
from apps.core.roles import get_active_roles
from apps.medical import services as medical_services
from apps.medical.models import HealthRecord
from apps.sport import performance, services
from apps.sport.models import Attendance, Evaluation, Event, Incident, Match, MatchComposition, MatchGoal, Suspension
from apps.sport.permissions import PERFORMANCE_VIEW_ALL_ROLES
from apps.sport.services import SportValidationError
from apps.sport.session_stats import _expected_on, _mean, _pct, _roster

#: Rôles qui voient disponibilité, suspension en cours et aptitude (10.2 n° 16,
#: spec §2 : Coach, Assistant, Président, VP, Directeur sportif, Médecin).
STAFF_AVAILABILITY_ROLES = services._FULL_DETAIL_ROLES

DEFAULT_LIMIT = 24
MAX_LIMIT = 100
RECENT_FORM_SIZE = 5
ADULT_AGE = 18

_TENTH = Decimal("0.1")
_CARD_TYPES = (Incident.IncidentType.YELLOW_CARD, Incident.IncidentType.RED_CARD)

#: Critères d'évaluation du 4.10 -> (clé, libellé, champ).
RADAR_AXES = (
    ("technical", "Technique", "technical_score"),
    ("physical", "Physique", "physical_score"),
    ("tactical", "Tactique", "tactical_score"),
    ("mental", "Mental", "mental_score"),
    ("attitude", "Attitude", "attitude_score"),
)

#: Clés de tri -> sens naturel (« name » croissant ; les statistiques se
#: demandent en décroissant avec le préfixe « - », comme DRF).
ORDERING_KEYS = ("name", "number", "average_rating", "goals", "assists", "attendance_rate", "matches_played")
AVAILABILITY_FILTERS = ("available", "unavailable")
STATUS_FILTERS = ("active", "left")


class PlayerStatsError(SportValidationError):
    """Paramètre invalide (traduit en 400 par les vues)."""


# ---------------------------------------------------------------------------
# Paramètres
# ---------------------------------------------------------------------------


def _int_param(raw, label: str, *, minimum: int, maximum: Optional[int] = None) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise PlayerStatsError(f"{label} : saisissez un nombre entier.") from None
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"entre {minimum} et {maximum}" if maximum is not None else f"d'au moins {minimum}"
        raise PlayerStatsError(f"{label} : saisissez un nombre {bound}.")
    return value


def parse_cards_params(params) -> dict:
    """Valide les paramètres de ``GET /clubs/players/cards/`` (messages en
    français, jamais le texte par défaut d'un champ de formulaire)."""

    position = (params.get("position") or "").strip()
    if position and position not in Membership.Position.values:
        raise PlayerStatsError("Poste inconnu : choisissez Gardien, Défenseur, Milieu ou Attaquant.")
    status = (params.get("status") or "active").strip() or "active"
    if status not in STATUS_FILTERS:
        raise PlayerStatsError("Statut inconnu : choisissez « Joueurs actifs » ou « Anciens joueurs ».")
    availability = (params.get("availability") or "").strip()
    if availability and availability not in AVAILABILITY_FILTERS:
        raise PlayerStatsError("Disponibilité inconnue : choisissez « Disponibles » ou « Indisponibles ».")
    ordering = (params.get("ordering") or "name").strip() or "name"
    if ordering.lstrip("-") not in ORDERING_KEYS:
        raise PlayerStatsError("Tri inconnu : choisissez le nom, le numéro, la note, les buts, les passes, la présence ou les matchs.")
    season_raw = params.get("season")
    return {
        "search": (params.get("search") or "").strip()[:120],
        "position": position,
        "status": status,
        "availability": availability,
        "ordering": ordering,
        "season_id": _int_param(season_raw, "Saison", minimum=1) if season_raw not in (None, "") else None,
        "limit": _int_param(params.get("limit", DEFAULT_LIMIT), "Nombre de joueurs", minimum=1, maximum=MAX_LIMIT),
        "offset": _int_param(params.get("offset", 0), "Décalage", minimum=0),
    }


def parse_compare_ids(raw) -> list[int]:
    """``ids=1,2,3`` : 2 à 4 identifiants distincts."""

    parts = [part.strip() for part in (raw or "").split(",") if part.strip()]
    try:
        ids = [int(part) for part in parts]
    except ValueError:
        raise PlayerStatsError("Identifiants de joueurs invalides.") from None
    if not 2 <= len(ids) <= 4:
        raise PlayerStatsError("Choisissez de 2 à 4 joueurs à comparer.")
    if len(set(ids)) != len(ids):
        raise PlayerStatsError("Un joueur ne peut être choisi qu'une fois.")
    return ids


# ---------------------------------------------------------------------------
# Saison
# ---------------------------------------------------------------------------


def resolve_season(club, season_id: Optional[int] = None) -> Optional[Season]:
    queryset = Season.all_objects.filter(club=club)
    if season_id is not None:
        season = queryset.filter(pk=season_id).first()
        if season is None:
            raise PlayerStatsError("Cette saison n'existe pas dans ce club.")
        return season
    return queryset.filter(is_current=True).order_by("-start_date").first() or queryset.order_by("-start_date").first()


def list_seasons(club) -> list[dict]:
    return [
        {"id": season.pk, "label": season.label, "is_current": season.is_current}
        for season in Season.all_objects.filter(club=club).order_by("-start_date", "-pk")
    ]


# ---------------------------------------------------------------------------
# Agrégats d'un club pour une saison (nombre de requêtes fixe)
# ---------------------------------------------------------------------------


@dataclass
class PlayerAggregate:
    matches_played: int = 0
    goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    sessions_expected: int = 0
    sessions_present: int = 0
    late: int = 0
    excused: int = 0
    absent: int = 0
    attendance_rate: Optional[int] = None
    average_rating: Optional[Decimal] = None
    radar: dict = field(default_factory=dict)
    #: (date, event_id, kind, note) de la plus récente à la plus ancienne.
    ratings: list = field(default_factory=list)


def compute_aggregates(club, season: Optional[Season]) -> dict[int, PlayerAggregate]:
    """``{adhésion: PlayerAggregate}`` pour toute la saison, en 6 requêtes
    groupées (effectif, présences, compositions, buts, cartons, évaluations).
    Un joueur absent du dictionnaire n'a aucune donnée : l'appelant utilise
    :func:`aggregate_of`."""

    if season is None:
        return {}
    today = services.get_club_today(club)
    result: dict[int, PlayerAggregate] = {}

    def entry(membership_id: int) -> PlayerAggregate:
        return result.setdefault(membership_id, PlayerAggregate())

    # Matchs joués, buts, passes.
    played: dict[int, set] = defaultdict(set)
    for membership_id, match_id in MatchComposition.all_objects.filter(
        club=club, match__event__season=season, match__sheet__isnull=False
    ).values_list("membership_id", "match_id"):
        played[membership_id].add(match_id)
    for scorer_id, assist_id, match_id in MatchGoal.all_objects.filter(
        club=club, match_sheet__match__event__season=season
    ).values_list("scorer_membership_id", "assist_membership_id", "match_sheet_id"):
        if scorer_id:
            entry(scorer_id).goals += 1
            played[scorer_id].add(match_id)
        if assist_id:
            entry(assist_id).assists += 1
            played[assist_id].add(match_id)
    for membership_id, match_ids in played.items():
        entry(membership_id).matches_played = len(match_ids)

    # Cartons.
    for membership_id, incident_type in Incident.all_objects.filter(
        club=club, event__season=season, incident_type__in=_CARD_TYPES
    ).values_list("membership_id", "incident_type"):
        if incident_type == Incident.IncidentType.YELLOW_CARD:
            entry(membership_id).yellow_cards += 1
        else:
            entry(membership_id).red_cards += 1

    # Présences aux séances déjà passées et pointées.
    counts_absent = services._club_settings(club).late_arrival_counts_absent
    roster = _roster(club)
    status_by_event: dict[int, dict[int, str]] = defaultdict(dict)
    date_by_event: dict[int, datetime.date] = {}
    for event_id, event_date, membership_id, status in Attendance.all_objects.filter(
        club=club, event__kind=Event.Kind.SESSION, event__season=season, event__event_date__lte=today
    ).values_list("event_id", "event__event_date", "membership_id", "status"):
        status_by_event[event_id][membership_id] = status
        date_by_event[event_id] = event_date
    for event_id, statuses in status_by_event.items():
        for membership in _expected_on(roster, date_by_event[event_id]):
            row = entry(membership.pk)
            row.sessions_expected += 1
            status = statuses.get(membership.pk)
            if status == Attendance.Status.PRESENT:
                row.sessions_present += 1
            elif status == Attendance.Status.LATE_ABSENT:
                row.late += 1
                if not counts_absent:
                    row.sessions_present += 1
            elif status == Attendance.Status.EXCUSED_ABSENT:
                row.excused += 1
            else:
                row.absent += 1
    for row in result.values():
        row.attendance_rate = _pct(row.sessions_present, row.sessions_expected)

    # Évaluations : note retenue par événement, puis moyennes de la saison.
    grouped: dict[tuple[int, int], list] = defaultdict(list)
    event_info: dict[int, tuple] = {}
    for event_id, event_date, kind, membership_id, overall, *criteria in Evaluation.all_objects.filter(
        club=club, event__season=season, event__event_date__lte=today
    ).values_list(
        "event_id", "event__event_date", "event__kind", "membership_id", "overall_score",
        *(field_name for _key, _label, field_name in RADAR_AXES),
    ):
        grouped[(membership_id, event_id)].append((overall, criteria))
        event_info[event_id] = (event_date, kind)
    retained: dict[int, list] = defaultdict(list)
    criteria_values: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for (membership_id, event_id), items in grouped.items():
        event_date, kind = event_info[event_id]
        note = _mean([overall for overall, _criteria in items], _TENTH)
        retained[membership_id].append((event_date, event_id, kind, note))
        for index, (key, _label, _field) in enumerate(RADAR_AXES):
            values = [criteria[index] for _overall, criteria in items if criteria[index] is not None]
            if values:
                criteria_values[membership_id][key].append(_mean(values, _TENTH))
    for membership_id, notes in retained.items():
        row = entry(membership_id)
        row.ratings = sorted(notes, key=lambda note: (note[0], note[1]), reverse=True)
        row.average_rating = _mean([note[3] for note in notes], _TENTH)
        row.radar = {key: _mean(criteria_values[membership_id].get(key, []), _TENTH) for key, _l, _f in RADAR_AXES}
    return result


def aggregate_of(aggregates: dict[int, PlayerAggregate], membership_id: int) -> PlayerAggregate:
    return aggregates.get(membership_id) or PlayerAggregate()


def _rating(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else str(value)


def stats_block(aggregate: PlayerAggregate) -> dict:
    """Les statistiques de la carte (spec B1). Les compteurs valent 0 sans
    donnée ; taux et note valent ``None`` (« — » à l'écran)."""

    return {
        "matches_played": aggregate.matches_played,
        "goals": aggregate.goals,
        "assists": aggregate.assists,
        "yellow_cards": aggregate.yellow_cards,
        "red_cards": aggregate.red_cards,
        "attendance_rate": aggregate.attendance_rate,
        "average_rating": _rating(aggregate.average_rating),
    }


# ---------------------------------------------------------------------------
# Disponibilité (même règle que ``services.get_playability``, en groupé)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Availability:
    code: str  # "" | "pending_membership" | "suspension" | "unfit" | "debt"
    matches_remaining: Optional[int] = None
    return_date: Optional[datetime.date] = None
    #: Montant à régulariser et devise (motif « debt » seulement), calculés
    #: par la trésorerie (jamais stockés, CLAUDE.md règle n° 2).
    amount_due: Optional[Decimal] = None
    currency: str = ""


def get_availabilities(club, memberships) -> dict[int, Availability]:
    """``{adhésion: Availability}`` pour chaque adhésion (``code`` vide =
    disponible). Mêmes motifs et même priorité que
    :func:`apps.sport.services.get_playability` (attente, suspension,
    inaptitude, dette) ; le statut financier vient du service de trésorerie.
    Nombre de requêtes fixe."""

    memberships = list(memberships)
    result = {membership.pk: Availability("") for membership in memberships}
    open_ids = [m.pk for m in memberships if m.status != Membership.Status.PENDING]
    for membership in memberships:
        if membership.status == Membership.Status.PENDING:
            result[membership.pk] = Availability("pending_membership")
    if not open_ids:
        return result

    latest: dict[int, Suspension] = {}
    for suspension in Suspension.all_objects.filter(
        club=club, membership_id__in=open_ids, lifted_at__isnull=True
    ).order_by("created_at", "pk"):
        latest[suspension.membership_id] = suspension
    for membership_id, suspension in latest.items():
        if suspension.is_active:
            result[membership_id] = Availability(
                "suspension", matches_remaining=suspension.matches_total - suspension.matches_served
            )

    still_open = [pk for pk in open_ids if not result[pk].code]
    for membership_id, return_date in medical_services.get_unfit_membership_dates(club, still_open).items():
        result[membership_id] = Availability("unfit", return_date=return_date)

    still_open = [pk for pk in open_ids if not result[pk].code]
    if still_open:
        from apps.treasury.services import TreasuryError, get_balance_summaries

        try:
            summaries = get_balance_summaries(club, still_open)
        except TreasuryError:
            # Paramètres financiers du club non configurés : aucune dette n'est
            # calculable, donc aucune indisponibilité pour dette (comme le
            # solde, jamais deviné).
            summaries = {}
        for membership_id, summary in summaries.items():
            if not summary.is_in_good_standing:
                result[membership_id] = Availability(
                    "debt", amount_due=summary.amount_due, currency=summary.currency
                )
    return result


def unavailable_membership_ids(club, memberships) -> set[int]:
    """Identifiants indisponibles (booléen seul, SANS motif, pour tous les
    rôles : « Indisponible », 10.2 n° 16)."""

    return {pk for pk, availability in get_availabilities(club, memberships).items() if availability.code}


def _unfit_label(return_date: Optional[datetime.date]) -> str:
    return medical_services.unfitness_label(return_date)


def staff_availability(availability: Availability) -> Optional[dict]:
    """Disponibilité telle que le staff la voit sur la page sportive :
    suspension et inaptitude avec leur libellé ; une dette n'est JAMAIS
    nommée ici (page sans donnée financière) : simple « Indisponible »."""

    if not availability.code:
        return None
    if availability.code == "suspension":
        return {"label": f"Suspendu : encore {availability.matches_remaining} match(s).", "family": "suspension"}
    if availability.code == "unfit":
        return {"label": _unfit_label(availability.return_date), "family": "unfit"}
    if availability.code == "pending_membership":
        return {"label": "En attente d'adhésion", "family": "pending"}
    return {"label": "Indisponible", "family": "unavailable"}


def viewer_roles(club, viewer) -> frozenset:
    return get_active_roles(viewer, club=club)


def sees_availability(club, viewer, *, target_user_id: Optional[int] = None) -> bool:
    """Staff de la liste 10.2 n° 16, ou le joueur lui-même."""

    if target_user_id is not None and getattr(viewer, "id", None) == target_user_id:
        return True
    return bool(viewer_roles(club, viewer) & STAFF_AVAILABILITY_ROLES)


# ---------------------------------------------------------------------------
# Identité et URL absolues
# ---------------------------------------------------------------------------


def _absolute(request, file_field) -> Optional[str]:
    if not file_field:
        return None
    return request.build_absolute_uri(file_field.url) if request is not None else file_field.url


def _identity(membership: Membership, request) -> dict:
    user = membership.user
    return {
        "membership_id": membership.pk,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "photo": _absolute(request, user.photo),
        "jersey_number": membership.jersey_number,
        "position": membership.position,
        "position_label": membership.get_position_display() if membership.position else "",
        "position_detail": membership.position_detail,
    }


def _club_brief(club, request) -> dict:
    return {"id": club.pk, "name": club.name, "logo": _absolute(request, club.logo)}


# ---------------------------------------------------------------------------
# Liste des cartes
# ---------------------------------------------------------------------------


def _fold(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", text or "") if unicodedata.category(char) != "Mn"
    ).casefold()


def _matches_search(membership: Membership, tokens: list[str]) -> bool:
    first, last = _fold(membership.user.first_name), _fold(membership.user.last_name)
    for token in tokens:
        if token in first or token in last:
            continue
        if token.isdigit() and membership.jersey_number == int(token):
            continue
        return False
    return True


def _name_key(membership: Membership):
    return (_fold(membership.user.last_name), _fold(membership.user.first_name), membership.pk)


def _sort_rows(rows: list[Membership], ordering: str, aggregates: dict[int, PlayerAggregate]) -> list[Membership]:
    descending = ordering.startswith("-")
    key = ordering.lstrip("-")
    rows = sorted(rows, key=_name_key)  # départage stable : nom puis identifiant
    if key == "name":
        return list(reversed(rows)) if descending else rows

    def value(membership: Membership):
        aggregate = aggregate_of(aggregates, membership.pk)
        if key == "number":
            return membership.jersey_number
        return getattr(aggregate, key)

    with_value = [m for m in rows if value(m) is not None]
    without_value = [m for m in rows if value(m) is None]  # « — » toujours en fin de liste
    with_value.sort(key=value, reverse=descending)
    return with_value + without_value


def list_player_cards(*, club, viewer, params: dict, request=None) -> dict:
    """``GET /clubs/players/cards/`` : une page de cartes avec leurs
    statistiques. Le filtrage, le tri et la pagination se font sur l'effectif
    complet du club (un jeu de requêtes fixe), donc jamais de doublon ni de
    trou entre deux pages."""

    season = resolve_season(club, params.get("season_id"))
    queryset = Membership.all_objects.filter(club=club).select_related("user")
    if params["status"] == "left":
        queryset = queryset.filter(status=Membership.Status.DEPARTED).exclude(
            left_reason=Membership.LeftReason.CANCELLED
        )
    else:
        queryset = queryset.filter(status=Membership.Status.ACTIVE)
    if params["position"]:
        queryset = queryset.filter(position=params["position"])
    members = list(queryset)
    tokens = [_fold(token) for token in params["search"].split() if token]
    if tokens:
        members = [m for m in members if _matches_search(m, tokens)]

    staff = bool(viewer_roles(club, viewer) & STAFF_AVAILABILITY_ROLES)
    if params["availability"] and not staff:
        raise PlayerStatsError("Le filtre de disponibilité est réservé au staff du club.")
    availabilities: dict[int, Availability] = {}
    if staff:
        availabilities = get_availabilities(club, members)
        if params["availability"] == "available":
            members = [m for m in members if not availabilities[m.pk].code]
        elif params["availability"] == "unavailable":
            members = [m for m in members if availabilities[m.pk].code]

    aggregates = compute_aggregates(club, season)
    members = _sort_rows(members, params["ordering"], aggregates)
    page = members[params["offset"]: params["offset"] + params["limit"]]

    results = []
    for membership in page:
        aggregate = aggregate_of(aggregates, membership.pk)
        row = _identity(membership, request)
        row.update(
            {
                "overall_rating": None,
                "stats": stats_block(aggregate),
                "recent_ratings": [str(note[3]) for note in aggregate.ratings[:RECENT_FORM_SIZE]],
                "availability": staff_availability(availabilities[membership.pk]) if staff else None,
            }
        )
        results.append(row)
    return {
        "count": len(members),
        "limit": params["limit"],
        "offset": params["offset"],
        "has_more": params["offset"] + params["limit"] < len(members),
        "results": results,
        "season_id": season.pk if season else None,
        "season_label": season.label if season else None,
        "seasons": list_seasons(club),
        "can_see_availability": staff,
        "can_compare": True,
    }


# ---------------------------------------------------------------------------
# Statistiques détaillées d'un joueur
# ---------------------------------------------------------------------------


def _event_labels(club, event_ids) -> dict[int, str]:
    matches = Match.all_objects.filter(club=club, pk__in=list(event_ids)).select_related("opponent_club")
    return {match.pk: f"Match contre {services._opponent_label(match)}" for match in matches}


def _discipline(club, membership: Membership, season: Optional[Season], *, sees_private: bool) -> dict:
    cards = []
    if season is not None:
        incidents = (
            Incident.all_objects.filter(club=club, membership=membership, event__season=season, incident_type__in=_CARD_TYPES)
            .select_related("event")
            .order_by("-event__event_date", "-pk")
        )
        cards = [
            {
                "id": incident.pk,
                "date": incident.event.event_date,
                "event_kind": incident.event.kind,
                "incident_type": incident.incident_type,
                "incident_type_label": incident.get_incident_type_display(),
                "cause": incident.cause,
                "cause_label": incident.get_cause_display(),
                "minute": incident.minute,
            }
            for incident in incidents
        ]
    active = None
    if sees_private:
        suspension = (
            Suspension.all_objects.filter(club=club, membership=membership, lifted_at__isnull=True)
            .order_by("-created_at", "-pk")
            .first()
        )
        if suspension is not None and suspension.is_active:
            remaining = suspension.matches_total - suspension.matches_served
            active = {
                "reason": suspension.reason,
                "reason_label": suspension.get_reason_display(),
                "matches_total": suspension.matches_total,
                "matches_served": suspension.matches_served,
                "matches_remaining": remaining,
                "label": f"Suspendu : encore {remaining} match(s).",
            }
    return {"cards": cards, "active_suspension": active}


def get_player_stats(*, membership: Membership, viewer, season_id: Optional[int] = None, request=None) -> dict:
    """``GET /clubs/players/{id}/stats/`` : ``membership`` appartient au club
    actif (contrôlé par la vue). Suspension en cours, aptitude et mesures de
    performance : staff de la liste 10.2 n° 16 (mesures : rôles de lecture
    des performances) et joueur lui-même, ``None`` pour les autres."""

    club = membership.club
    season = resolve_season(club, season_id)
    aggregate = aggregate_of(compute_aggregates(club, season), membership.pk)
    roles = viewer_roles(club, viewer)
    is_self = getattr(viewer, "id", None) == membership.user_id
    sees_private = is_self or bool(roles & STAFF_AVAILABILITY_ROLES)
    sees_performance = is_self or bool(roles & PERFORMANCE_VIEW_ALL_ROLES)

    top = aggregate.ratings[:RECENT_FORM_SIZE]
    labels = _event_labels(club, [event_id for _date, event_id, kind, _note in top if kind == Event.Kind.MATCH])
    recent_form = [
        {
            "date": event_date,
            "event_type": kind,
            "label": labels.get(event_id, "Match") if kind == Event.Kind.MATCH else "Séance",
            "rating": str(note),
        }
        for event_date, event_id, kind, note in top
    ]

    fitness = None
    if sees_private:
        summary = medical_services.get_fitness_summary(membership)
        fitness = {
            "status": summary["fitness_status"],
            "label": HealthRecord.FitnessStatus(summary["fitness_status"]).label,
            "return_date": summary["fitness_return_date"],
        }

    performance_tests = None
    if sees_performance:
        performance_tests = performance.get_player_overview(membership=membership, request=request)["tests"]

    return {
        "membership_id": membership.pk,
        "season_id": season.pk if season else None,
        "season_label": season.label if season else None,
        "overall_rating": None,
        "stats": stats_block(aggregate),
        "radar": {
            "axes": [
                {"key": key, "label": label, "value": _rating(aggregate.radar.get(key))}
                for key, label, _field in RADAR_AXES
            ]
        },
        "recent_form": recent_form,
        "attendance": {
            "sessions_expected": aggregate.sessions_expected,
            "sessions_present": aggregate.sessions_present,
            "late": aggregate.late,
            "excused": aggregate.excused,
            "absent": aggregate.absent,
            "rate": aggregate.attendance_rate,
            "late_counts_as_absent": services._club_settings(club).late_arrival_counts_absent,
        },
        "discipline": _discipline(club, membership, season, sees_private=sees_private),
        "fitness": fitness,
        "performance": performance_tests,
    }


# ---------------------------------------------------------------------------
# Comparaison de 2 à 4 joueurs
# ---------------------------------------------------------------------------


def _is_minor(birth_date) -> bool:
    if birth_date is None:
        return False
    today = datetime.date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age < ADULT_AGE


def _public_consultable(membership: Membership) -> bool:
    user = membership.user
    return (
        membership.status == Membership.Status.ACTIVE
        and user.is_active
        and not user.is_superuser
        and user.card_publication_consent_at is not None
        and not _is_minor(user.birth_date)
    )


def compare_players(*, club, ids: list[int], request=None) -> dict:
    """Comparaison de 2 à 4 joueurs dans l'ordre demandé. Joueur du club
    actif : statistiques et radar. Joueur d'un autre club : DONNÉES PUBLIQUES
    seulement (identité de carte, club, statistiques de sa saison, jamais le
    radar), et seulement s'il a consenti à la publication de sa carte, n'est
    pas mineur et est inscrit. Tout autre cas (introuvable, parti, sans
    consentement) reçoit la même réponse « plus consultable » : aucune fuite
    d'existence."""

    found = {
        membership.pk: membership
        for membership in Membership.all_objects.filter(pk__in=ids).select_related("user", "club")
    }
    consultable: dict[int, Membership] = {}
    for membership_id, membership in found.items():
        if membership.club_id == club.pk or _public_consultable(membership):
            consultable[membership_id] = membership

    clubs: dict[int, tuple] = {}
    for membership in consultable.values():
        if membership.club_id not in clubs:
            season = resolve_season(membership.club)
            clubs[membership.club_id] = (season, compute_aggregates(membership.club, season))

    results = []
    for membership_id in ids:
        membership = consultable.get(membership_id)
        if membership is None:
            results.append(
                {"membership_id": membership_id, "consultable": False, "detail": "Ce joueur n'est plus consultable."}
            )
            continue
        own = membership.club_id == club.pk
        season, aggregates = clubs[membership.club_id]
        aggregate = aggregate_of(aggregates, membership.pk)
        row = _identity(membership, request)
        del row["position_detail"]
        row.update(
            {
                "consultable": True,
                "scope": "club" if own else "public",
                "club": _club_brief(membership.club, request),
                "season_id": season.pk if season else None,
                "season_label": season.label if season else None,
                "overall_rating": None,
                "stats": stats_block(aggregate),
                "radar": (
                    {
                        "axes": [
                            {"key": key, "label": label, "value": _rating(aggregate.radar.get(key))}
                            for key, label, _field in RADAR_AXES
                        ]
                    }
                    if own
                    else None
                ),
            }
        )
        results.append(row)
    return {"count": len(results), "results": results}
