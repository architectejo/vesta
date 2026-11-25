"""Regles metier de l'app sport (taches 3.2-3.4, complement tache 3.7).

Sources : CDC 4.7-4.11 ; docs/lot0/schema-donnees.md §5 ; 10.2 n° 6, 7,
8, 9, 16, 25, 29, 31, 32, 38 ; CLAUDE.md regle n° 5 et n° 6.

Perimetre construit a ce stade (taches 3.2 a 3.4)
--------------------------------------------------
- Eligibilite d'un joueur (dette/suspension/inaptitude/attente
  d'adhesion) et filtrage du motif affiche selon le role du lecteur
  (:func:`get_playability`, :func:`describe_reason_for_viewer`).
- Verrouillage a minuit des seances/matchs, deverrouillage Superuser
  journalise (:func:`is_event_locked`, :func:`ensure_event_writable`,
  :func:`unlock_event`).
- Seances : creation, pointage (arrivee, correction d'heure, absence
  excusee), repartition automatique/manuelle en equipe A/B avec la
  zone « Non repartis » a deux categories (10.2 n° 29, n° 38).
- Matchs : creation, composition (avec regularisation sur place),
  publication, feuille de match (score, buts/passes, modifiables apres
  coup), incidents/discipline avec suspension automatique (5e jaune,
  rouge direct) et levee automatique (commande cron, tache 3.4).
- Evaluations (fenetre de 48 h, moyenne calculee a la lecture).
- Plan tactique (creation, duplication, publication, placements avec le
  meme controle d'eligibilite, annotations du tableau noir).

Complement tache 3.7 (specs d'ecran deja validees, services manquants
identifies au rapport de la tache 3.6)
------------------------------------------------------------------------
- « Modifier la seance » (:func:`update_session`, sport-seance.md §4.2) et
  « Modifier le match » (:func:`update_match`, sport-feuille-de-match.md
  §4.7) : memes champs que la creation, verrouilles a minuit comme toute
  autre ecriture sur l'evenement.
- « Parametres du plan » (:func:`update_tactical_plan_settings`,
  sport-plan-tactique.md §4.3) : nom/formation/effectif/match rattache,
  bloque si le plan est deja publie -- voir la docstring de la fonction
  pour la limite assumee sur le repositionnement automatique des joueurs
  deja places (aucune geometrie de formation cote serveur).
- Pointage simple d'un match, sans repartition A/B
  (:func:`mark_match_arrival`, sport-feuille-de-match.md §7 point ouvert
  2) : ``TeamAssignment`` reste reservee aux seances (schema §5.4).

Conventions
-----------
- Le club vient toujours de l'objet manipule (evenement, match, plan) --
  jamais d'un parametre transmis tel quel par le client (CLAUDE.md
  regle n° 9).
- Toute lecture/ecriture passe par ``all_objects`` avec un filtre
  explicite par club (meme convention que ``apps.treasury.services`) :
  ces services sont appeles aussi bien depuis une requete HTTP (club actif
  positionne) que depuis une commande cron ou un test.
- Toute creation/modification/suppression est journalisee (CLAUDE.md
  regle n° 6), via ``apps.core.services.log_action``.
- Le controle d'eligibilite est fait ICI, jamais seulement cote vue ou
  interface (CLAUDE.md regle n° 5) : aucun appel de service ne peut
  contourner un blocage, y compris un appel direct a l'API ou un script.

Extension validee par le client le 30/09/2026 (hors CDC ecrit a ce jour,
comparable par sa nature aux extensions actees au 10.2 comme le n° 24 --
a documenter au CDC, signale au compte rendu de cette tache)
------------------------------------------------------------------------
- Formation par equipe de seance (:func:`set_team_formation`) : chaque
  equipe (A, B) a sa propre formation, independante de l'autre, choisie
  dans la meme bibliotheque que le plan tactique (``apps.sport.models.
  Formation``, alias partage avec ``TacticalPlan.Formation``).
- Statut terrain/banc et position d'un joueur deja reparti
  (:func:`place_team_player`) : au plus 11 joueurs « sur le terrain » par
  equipe ; deposer un 12e joueur sur une case occupee echange les deux
  joueurs ; deposer sur une case vide au-dela de 11 est refuse. Memes
  garde d'ecriture (:func:`ensure_event_writable`) et controle
  d'eligibilite (:func:`get_playability`) que :func:`assign_team`.

Point d'integration en attente (Lot 4, ``apps.medical``)
---------------------------------------------------------
``apps.medical`` est un squelette vide au moment de cette tache : aucune
regle d'aptitude medicale n'est donc appliquee (:func:`_get_medical_unfitness`
ne bloque jamais un joueur pour ce motif tant que le Lot 4 n'a pas
construit ``apps.medical.services.get_unfitness_reason``). Voir le
compte rendu de la tache 3.2 pour le contrat d'integration attendu.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.clubs.models import COACHING_STAFF_ROLES, ClubSettings, Membership, MembershipRole, Season
from apps.core.roles import get_active_roles, has_any_role
from apps.core.services import log_action
from apps.sport.models import (
    Attendance,
    Event,
    Incident,
    Match,
    MatchComposition,
    MatchGoal,
    MatchSheet,
    Session,
    Suspension,
    TacticalPlan,
    TacticalPlanAnnotation,
    TacticalPlanPlacement,
    TeamAssignment,
    Evaluation,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SportError",
    "SportValidationError",
    "SportPermissionError",
    "PlayerNotEligibleError",
    "EventLockedError",
    "Playability",
    "get_playability",
    "describe_reason_for_viewer",
    "is_event_locked",
    "ensure_event_writable",
    "unlock_event",
    "get_club_today",
    "get_next_upcoming_event",
    "create_session",
    "update_session",
    "mark_arrival",
    "correct_arrival_time",
    "mark_excused_absence",
    "assign_team",
    "set_team_formation",
    "place_team_player",
    "sync_pending_regularizations",
    "get_unassigned_players",
    "reason_visible_to_viewer",
    "UnassignedGroups",
    "create_match",
    "update_match",
    "mark_match_arrival",
    "mark_arrivals_bulk",
    "excuse_absences_bulk",
    "add_to_composition",
    "remove_from_composition",
    "publish_composition",
    "set_match_score",
    "add_goal",
    "update_goal",
    "delete_goal",
    "record_incident",
    "advance_suspensions_for_elapsed_matches",
    "submit_evaluation",
    "is_evaluation_locked",
    "evaluation_locks_at",
    "get_average_evaluation",
    "create_tactical_plan",
    "update_tactical_plan_settings",
    "duplicate_tactical_plan",
    "place_on_plan",
    "remove_from_plan",
    "update_plan_placement_number_and_position",
    "add_annotation",
    "delete_annotation",
    "publish_tactical_plan",
    "delete_tactical_plan",
]


class SportError(Exception):
    """Racine des erreurs métier de l'app sport."""


class SportValidationError(SportError):
    """Donnée ou état invalide (traduite en 400 par les vues)."""


class SportPermissionError(SportError, PermissionError):
    """Action refusée malgré un rôle a priori suffisant (ex. le Président
    tente de placer un retardataire, réservé au Coach/Capitaine — 10.2 n° 38)."""


class PlayerNotEligibleError(SportValidationError):
    """Joueur en dette, suspendu, inapte ou en attente d'adhésion : jamais
    composable ni plaçable, y compris manuellement (CLAUDE.md règle n° 5)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class EventLockedError(SportValidationError):
    """Événement verrouillé (jour même uniquement, CDC 4.7), hors Superuser."""


# ---------------------------------------------------------------------------
# Fuseau horaire du club (même convention que apps.treasury.services)
# ---------------------------------------------------------------------------


def _club_settings(club) -> ClubSettings:
    club_settings = ClubSettings.objects.filter(club_id=club.id).first()
    if club_settings is None:
        raise SportValidationError(
            "Les paramètres du club (fuseau horaire, réglages sportifs) ne sont pas configurés."
        )
    return club_settings


def _club_tz(club_settings: ClubSettings) -> ZoneInfo:
    try:
        return ZoneInfo(club_settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise SportValidationError("Le fuseau horaire du club est invalide.") from None


def _club_today(club, *, now: Optional[datetime] = None) -> date:
    now = now or timezone.now()
    return now.astimezone(_club_tz(_club_settings(club))).date()


def get_club_today(club, *, now: Optional[datetime] = None) -> date:
    """Date du jour dans le fuseau du club (CDC 4.7), exposee publiquement
    pour les vues (ex. determiner « l'evenement du jour » du vestiaire,
    sport-vestiaire.md §2) -- meme convention que
    ``apps.treasury.services.get_club_today``."""

    return _club_today(club, now=now)


def get_next_upcoming_event(club, *, after: Optional[date] = None):
    """Prochain évènement à venir du club (séance ou match), c'est-à-dire
    celui dont ``event.event_date`` est strictement postérieure à
    ``after`` (date du jour du club par défaut, :func:`get_club_today`),
    trié par date croissante. Renvoie l'instance ``Session`` ou ``Match``
    elle-même (jamais l'``Event`` nu : l'appelant a besoin de
    ``gathering_time``/``kickoff_time``), ou ``None`` s'il n'y en a pas.

    Utilisée UNIQUEMENT pour la précision « Prochain rendez-vous » de
    l'état vide du vestiaire quand aucun évènement n'a lieu aujourd'hui
    (sport-vestiaire.md §6, ligne « Aucun événement aujourd'hui » ; même
    source pour club-accueil.md §4 point 5, carte « Prochain
    rendez-vous ») -- jamais appelée quand un évènement du jour existe
    déjà, pour ne pas alourdir ce cas (demande explicite de la tâche).

    Critère de départage non tranché par le CDC écrit à ce jour : si une
    séance et un match tombent le même jour futur le plus proche, la
    séance l'emporte -- choix arbitraire documenté ici, décision par
    défaut signalée au compte rendu, à confirmer par le client si le cas
    se présente en pratique."""

    reference_date = after if after is not None else _club_today(club)

    next_session = (
        Session.all_objects.select_related("event")
        .filter(club_id=club.id, event__event_date__gt=reference_date)
        .order_by("event__event_date", "event_id")
        .first()
    )
    next_match = (
        Match.all_objects.select_related("event")
        .filter(club_id=club.id, event__event_date__gt=reference_date)
        .order_by("event__event_date", "event_id")
        .first()
    )

    candidates = [c for c in (next_session, next_match) if c is not None]
    if not candidates:
        return None
    earliest_date = min(c.event.event_date for c in candidates)
    for candidate in candidates:
        if candidate.event.event_date == earliest_date:
            # Séance prioritaire sur un match à date égale (voir
            # docstring ci-dessus) : ``candidates`` est construit dans
            # l'ordre [séance, match], donc le premier trouvé ici est
            # toujours la séance quand les deux partagent cette date.
            return candidate
    return None  # pragma: no cover - inatteignable (earliest_date vient de candidates)


def _combine_local(event_date: date, time_value, club_settings: ClubSettings) -> datetime:
    return datetime.combine(event_date, time_value, tzinfo=_club_tz(club_settings))


# ---------------------------------------------------------------------------
# Éligibilité (CLAUDE.md règle n° 5 ; CDC 4.7-4.9, 4.11 ; 10.2 n° 16, n° 29)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Playability:
    """Résultat du contrôle d'éligibilité d'un joueur (composition,
    répartition A/B, plan tactique). ``detail`` est le texte complet
    (Coach/Président/VP/joueur lui-même) ; voir
    :func:`describe_reason_for_viewer` pour le filtrage par rôle."""

    eligible: bool
    reason_code: str  # "" | "pending_membership" | "suspension" | "unfit" | "debt"
    detail: str
    amount_due: Optional[Decimal] = None
    suspension_matches_remaining: Optional[int] = None
    fitness_return_date: Optional[date] = None


def _get_medical_unfitness(membership: Membership, *, at_date=None):
    """Point d'intégration en attente (Lot 4, ``apps.medical``).

    ``apps.medical`` est un squelette vide à ce jour (tâche 3.2) :
    aucune règle d'aptitude n'est donc inventée ici. Contrat attendu de
    ``apps.medical.services.get_unfitness_reason(membership, at_date=None)``
    (à construire au Lot 4) : renvoie ``None`` si le joueur est apte, ou
    un tuple ``(raison_lisible, date_de_retour_ou_None)`` sinon — voir le
    compte rendu de la tâche 3.2."""

    try:
        from apps.medical import services as medical_services
    except ImportError:  # pragma: no cover - apps.medical toujours présente au Lot 3
        return None

    hook = getattr(medical_services, "get_unfitness_reason", None)
    if hook is None:
        return None
    return hook(membership, at_date=at_date)


def get_playability(membership: Membership, *, at_date: Optional[date] = None) -> Playability:
    """Un joueur en dette, suspendu, inapte ou en attente d'adhésion ne
    peut être ni composé, ni réparti en A/B, ni placé sur un plan
    tactique (CLAUDE.md règle n° 5 ; CDC 4.7-4.9, 4.11 ; 10.2 n° 29).

    Ordre de priorité choisi quand plusieurs motifs coexistent (aucune
    combinaison n'est documentée par le CDC/schéma : un seul motif est
    toujours affiché) : attente d'adhésion, suspension, inaptitude,
    dette — du plus structurel au plus circonstanciel. Ce choix
    d'implémentation est signalé au compte rendu."""

    if membership.status == Membership.Status.PENDING:
        return Playability(False, "pending_membership", "En attente d'adhésion.")

    active_suspension = (
        Suspension.all_objects.filter(club_id=membership.club_id, membership_id=membership.pk, lifted_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if active_suspension is not None and active_suspension.is_active:
        remaining = active_suspension.matches_total - active_suspension.matches_served
        return Playability(
            False,
            "suspension",
            f"Suspendu : encore {remaining} match(s).",
            suspension_matches_remaining=remaining,
        )

    unfitness = _get_medical_unfitness(membership, at_date=at_date)
    if unfitness is not None:
        reason_text, return_date = unfitness
        return Playability(False, "unfit", reason_text, fitness_return_date=return_date)

    from apps.treasury.services import is_in_good_standing

    in_good_standing, amount_due, _reason = is_in_good_standing(membership, at_date=at_date)
    if not in_good_standing:
        currency = _club_settings(membership.club).currency
        return Playability(
            False, "debt", f"En dette : {amount_due:.2f} {currency}.", amount_due=amount_due
        )

    return Playability(True, "", "")


# 10.2 n° 16, matrice 2.4 (sport-seance.md §3.2 ter) : qui voit le motif
# financier (dette) et qui voit le motif « non financier » complet
# (suspension, inaptitude, attente d'adhésion). Position provisoire pour
# le Capitaine (voir sport-seance.md §7, point ouvert 3) : « Indisponible »
# seul, sans motif — appliquée telle quelle ici.
_FINANCIAL_DETAIL_ROLES = frozenset(
    {MembershipRole.Role.PRESIDENT, MembershipRole.Role.VICE_PRESIDENT, *COACHING_STAFF_ROLES}
)
_FULL_DETAIL_ROLES = _FINANCIAL_DETAIL_ROLES | frozenset(
    {MembershipRole.Role.SPORTS_DIRECTOR, MembershipRole.Role.DOCTOR}
)


def reason_visible_to_viewer(playability: Playability, *, viewer, membership: Membership) -> bool:
    """Le lecteur a-t-il droit au motif réel de blocage (10.2 n° 16) ?

    Le joueur voit toujours le sien. Dette et attente d'adhésion (motifs
    administratifs/financiers) : Président, VP, Coach. Suspension et
    inaptitude : ces rôles + Directeur sportif + Médecin. Tous les autres
    (coéquipiers, Capitaine) : « Indisponible » seul, sans code de motif."""

    if playability.eligible:
        return True
    if getattr(viewer, "id", None) == membership.user_id:
        return True
    roles = get_active_roles(viewer, club=membership.club)
    if playability.reason_code in ("debt", "pending_membership"):
        return bool(roles & _FINANCIAL_DETAIL_ROLES)
    return bool(roles & _FULL_DETAIL_ROLES)


def describe_reason_for_viewer(playability: Playability, *, viewer, membership: Membership) -> str:
    """Texte de blocage filtré selon le rôle du lecteur (10.2 n° 16 ;
    sport-seance.md §3.2 ter). Point de filtrage UNIQUE : jamais
    reconstruit ailleurs (l'interface affiche ce texte tel quel)."""

    if playability.eligible:
        return ""
    if reason_visible_to_viewer(playability, viewer=viewer, membership=membership):
        return playability.detail
    return "Indisponible"


# ---------------------------------------------------------------------------
# Verrouillage à minuit (CDC 4.7 ; schema §5.1)
# ---------------------------------------------------------------------------


def is_event_locked(event: Event, *, now: Optional[datetime] = None) -> bool:
    if event.unlocked_by_id:
        return False
    return event.event_date < _club_today(event.club, now=now)


def ensure_event_writable(event: Event, *, actor) -> None:
    """Lève :class:`EventLockedError` si l'événement est verrouillé, sauf
    pour un Superuser (CDC 4.7). Appelée par tout service qui écrit sur
    ``Attendance``/``TeamAssignment``/``Incident`` (schema §5.1)."""

    if getattr(actor, "is_superuser", False):
        return
    if is_event_locked(event):
        raise EventLockedError(
            "Cet événement est verrouillé : il n'est modifiable que le jour même (CDC 4.7). "
            "Seul le Superuser peut le déverrouiller."
        )


def unlock_event(event: Event, *, superuser, reason: str) -> Event:
    """Déverrouillage réservé au Superuser, motif obligatoire, journalisé
    (CDC 4.7 ; CLAUDE.md règle n° 6)."""

    if not getattr(superuser, "is_superuser", False):
        raise SportPermissionError("Seul le Superuser peut déverrouiller un événement verrouillé.")
    reason = (reason or "").strip()
    if not reason:
        raise SportValidationError(
            "Un motif écrit est requis pour déverrouiller un événement (CLAUDE.md règle n° 6)."
        )
    before = {
        "unlocked_by": event.unlocked_by_id,
        "unlock_reason": event.unlock_reason,
    }
    event.unlocked_by = superuser
    event.unlocked_at = timezone.now()
    event.unlock_reason = reason
    event.save()
    log_action(
        actor=superuser,
        club=event.club,
        action_type="sport.event_unlocked",
        obj=event,
        before=before,
        after={"unlocked_by": superuser.id, "unlock_reason": reason},
    )
    return event


# ---------------------------------------------------------------------------
# Séances et pointage (CDC 4.7)
# ---------------------------------------------------------------------------


def _notify_event_created(*, club, target, message: str) -> None:
    """CDC 4.17 « Séance ou match créé » : tous les joueurs du club (adhésions
    actives, club de l'événement uniquement), in-app, un envoi par joueur."""

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    memberships = Membership.all_objects.filter(club=club, status=Membership.Status.ACTIVE).select_related("user")
    for membership in memberships:
        create_notification(
            recipient=membership.user,
            event_type=Notification.EventType.EVENT_CREATED,
            message=message,
            club=club,
            target=target,
        )


def create_session(
    *,
    club,
    season: Season,
    event_date: date,
    gathering_time,
    late_arrival_cutoff,
    created_by,
    location: str = "",
    team_a_color: Optional[str] = None,
    team_b_color: Optional[str] = None,
    instructions: str = "",
) -> Session:
    club_settings = _club_settings(club)
    event = Event(club=club, kind=Event.Kind.SESSION, event_date=event_date, season=season, created_by=created_by)
    event.save()
    session = Session(
        event=event,
        club=club,
        gathering_time=gathering_time,
        late_arrival_cutoff=late_arrival_cutoff,
        location=location,
        team_a_color=team_a_color or club_settings.default_jersey_color_a,
        team_b_color=team_b_color or club_settings.default_jersey_color_b,
        instructions=instructions,
    )
    session.save()
    log_action(
        actor=created_by,
        club=club,
        action_type="sport.session_created",
        obj=session,
        after={"event_date": event_date.isoformat(), "gathering_time": str(gathering_time)},
    )
    place = f", {location}" if location else ""
    _notify_event_created(
        club=club,
        target=session,
        message=f"Une séance est programmée le {event_date.strftime('%d/%m/%Y')} à {str(gathering_time)[:5]}{place}.",
    )
    return session


def update_session(
    *,
    session: Session,
    event_date: date,
    gathering_time,
    late_arrival_cutoff,
    updated_by,
    location: str = "",
    team_a_color: Optional[str] = None,
    team_b_color: Optional[str] = None,
    instructions: str = "",
) -> Session:
    """Modifie une séance existante (sport-seance.md §4.2 : « Mêmes champs
    que Créer une séance. Un changement de couleur de maillot met à jour
    les terrains. »). Réservée au Coach, modifiable uniquement le jour
    même (CDC 4.7) : même verrouillage que toute écriture sur l'événement
    (:func:`ensure_event_writable`) -- la page « passe en lecture seule
    pour tous » à minuit (sport-seance.md §2), y compris pour ce menu."""

    event = session.event
    ensure_event_writable(event, actor=updated_by)

    club_settings = _club_settings(session.club)
    before = {
        "event_date": event.event_date.isoformat(),
        "gathering_time": str(session.gathering_time),
        "late_arrival_cutoff": str(session.late_arrival_cutoff),
        "location": session.location,
        "team_a_color": session.team_a_color,
        "team_b_color": session.team_b_color,
        "instructions": session.instructions,
    }

    event.event_date = event_date
    event.save()

    session.gathering_time = gathering_time
    session.late_arrival_cutoff = late_arrival_cutoff
    session.location = location
    session.team_a_color = team_a_color or club_settings.default_jersey_color_a
    session.team_b_color = team_b_color or club_settings.default_jersey_color_b
    session.instructions = instructions
    session.save()

    log_action(
        actor=updated_by,
        club=session.club,
        action_type="sport.session_updated",
        obj=session,
        before=before,
        after={
            "event_date": event_date.isoformat(),
            "gathering_time": str(gathering_time),
            "late_arrival_cutoff": str(late_arrival_cutoff),
            "location": location,
            "team_a_color": session.team_a_color,
            "team_b_color": session.team_b_color,
            "instructions": instructions,
        },
    )
    return session


def _next_arrival_order(session: Session) -> int:
    last = TeamAssignment.all_objects.filter(club=session.club_id, session=session).aggregate(Max("arrival_order"))[
        "arrival_order__max"
    ]
    return (last or 0) + 1


def _auto_assign_if_present(session: Session, membership: Membership, *, assigned_by) -> Optional[TeamAssignment]:
    if TeamAssignment.all_objects.filter(club=session.club_id, session=session, membership=membership).exists():
        return None
    order = _next_arrival_order(session)
    team = TeamAssignment.Team.A if order % 2 == 1 else TeamAssignment.Team.B
    assignment = TeamAssignment(
        club=session.club, session=session, membership=membership, team=team, arrival_order=order, assigned_by=assigned_by
    )
    assignment.save()
    log_action(
        actor=assigned_by,
        club=session.club,
        action_type="sport.team_assignment_auto",
        obj=assignment,
        after={"team": team},
    )
    return assignment


def _upsert_attendance(
    *,
    event: Event,
    membership: Membership,
    status: str,
    arrived_at,
    marked_by,
    client_uuid=None,
    client_recorded_at=None,
    audit_extra: Optional[dict] = None,
) -> tuple[Attendance, bool]:
    attendance = Attendance.all_objects.filter(club=event.club_id, event=event, membership=membership).first()
    created = attendance is None
    if created:
        attendance = Attendance(club=event.club, event=event, membership=membership)
    before = (
        None
        if created
        else {
            "status": attendance.status,
            "arrived_at": attendance.arrived_at.isoformat() if attendance.arrived_at else None,
        }
    )
    attendance.status = status
    attendance.arrived_at = arrived_at
    attendance.marked_by = marked_by
    attendance.excused_reason = ""
    if client_uuid is not None:
        attendance.client_uuid = client_uuid
        attendance.client_recorded_at = client_recorded_at
    attendance.save()
    log_action(
        actor=marked_by,
        club=event.club,
        action_type="sport.attendance_marked" if created else "sport.attendance_corrected",
        obj=attendance,
        before=before,
        after={
            "status": status,
            "arrived_at": arrived_at.isoformat() if arrived_at else None,
            # Pointage groupé : batch_id, taille du lot, etc. (une entrée
            # par joueur, règle 6).
            **(audit_extra or {}),
        },
    )
    return attendance, created


CLIENT_UUID_OTHER_PLAYER_MESSAGE = "Cet identifiant de pointage est déjà utilisé pour un autre joueur."


def _existing_attendance_for_client_uuid(event: Event, membership: Membership, client_uuid) -> Optional[Attendance]:
    """Déduplication d'un renvoi hors connexion (6.6) : renvoie le pointage
    déjà enregistré pour CE joueur et CET événement. Un identifiant déjà
    utilisé pour un autre joueur (ou un autre événement) est refusé, jamais
    rendu avec les données d'un autre."""

    existing = Attendance.all_objects.filter(club=event.club_id, client_uuid=client_uuid).first()
    if existing is None:
        return None
    if existing.membership_id != membership.pk or existing.event_id != event.pk:
        raise SportValidationError(CLIENT_UUID_OTHER_PLAYER_MESSAGE)
    return existing


def mark_arrival(
    *,
    session: Session,
    membership: Membership,
    arrived_at: datetime,
    marked_by,
    client_uuid=None,
    client_recorded_at=None,
    audit_extra: Optional[dict] = None,
) -> Attendance:
    """Pointage d'une arrivée (CDC 4.7). Présent avant l'heure limite,
    sinon « en retard, compté absent » (10.2 n° 6, n° 25) — le comptage
    « absent » lui-même est une question d'affichage/statistiques
    (``ClubSettings.late_arrival_counts_absent``), pas de ce statut de
    données, qui reste ``late_absent`` dans tous les cas."""

    event = session.event
    ensure_event_writable(event, actor=marked_by)

    if client_uuid is not None:
        existing = _existing_attendance_for_client_uuid(event, membership, client_uuid)
        if existing is not None:
            return existing

    club_settings = _club_settings(session.club)
    cutoff_dt = _combine_local(event.event_date, session.late_arrival_cutoff, club_settings)
    status = Attendance.Status.PRESENT if arrived_at <= cutoff_dt else Attendance.Status.LATE_ABSENT

    attendance, _created = _upsert_attendance(
        event=event,
        membership=membership,
        status=status,
        arrived_at=arrived_at,
        marked_by=marked_by,
        client_uuid=client_uuid,
        client_recorded_at=client_recorded_at,
        audit_extra=audit_extra,
    )

    if status == Attendance.Status.PRESENT:
        playability = get_playability(membership)
        if playability.eligible:
            _auto_assign_if_present(session, membership, assigned_by=marked_by)
    return attendance


def correct_arrival_time(*, attendance: Attendance, new_arrived_at: datetime, actor) -> Attendance:
    """Correction de l'heure d'arrivée, réservée au Coach, le jour même
    (CDC 4.7 — « Le Coach peut corriger l'heure le jour même »)."""

    event = attendance.event
    ensure_event_writable(event, actor=actor)
    if not getattr(actor, "is_superuser", False) and not has_any_role(
        actor, COACHING_STAFF_ROLES, club=attendance.club
    ):
        raise SportPermissionError("Seul le Coach (ou son assistant) corrige l'heure d'arrivée.")

    session = event.session
    club_settings = _club_settings(attendance.club)
    cutoff_dt = _combine_local(event.event_date, session.late_arrival_cutoff, club_settings)
    new_status = Attendance.Status.PRESENT if new_arrived_at <= cutoff_dt else Attendance.Status.LATE_ABSENT

    before_status = attendance.status
    before = {
        "status": attendance.status,
        "arrived_at": attendance.arrived_at.isoformat() if attendance.arrived_at else None,
    }
    attendance.arrived_at = new_arrived_at
    attendance.status = new_status
    attendance.marked_by = actor
    attendance.save()
    log_action(
        actor=actor,
        club=attendance.club,
        action_type="sport.attendance_corrected",
        obj=attendance,
        before=before,
        after={"status": new_status, "arrived_at": new_arrived_at.isoformat()},
    )

    if before_status == Attendance.Status.PRESENT and new_status == Attendance.Status.LATE_ABSENT:
        TeamAssignment.all_objects.filter(
            club=attendance.club_id, session=session, membership=attendance.membership
        ).delete()
    elif before_status != Attendance.Status.PRESENT and new_status == Attendance.Status.PRESENT:
        playability = get_playability(attendance.membership)
        if playability.eligible:
            _auto_assign_if_present(session, attendance.membership, assigned_by=actor)
    return attendance


def mark_excused_absence(
    *, event: Event, membership: Membership, reason: str, marked_by, audit_extra: Optional[dict] = None
) -> Attendance:
    """Absence excusée (blessé, voyage, autre) : reste une absence, mais
    distinguée dans les statistiques (CDC 4.7)."""

    ensure_event_writable(event, actor=marked_by)
    attendance, _created = _upsert_attendance(
        event=event,
        membership=membership,
        status=Attendance.Status.EXCUSED_ABSENT,
        arrived_at=None,
        marked_by=marked_by,
        audit_extra=audit_extra,
    )
    attendance.excused_reason = reason
    attendance.save()
    session = getattr(event, "session", None)
    if session is not None:
        TeamAssignment.all_objects.filter(club=event.club_id, session=session, membership=membership).delete()
    return attendance


# ---------------------------------------------------------------------------
# Répartition en équipes A/B (CDC 4.7 ; 10.2 n° 7, n° 29, n° 38)
# ---------------------------------------------------------------------------

# 10.2 n° 38 : réservé au Coach et au Capitaine pour placer un
# retardataire — le Président a « É » sur la répartition (matrice 2.4)
# mais seulement pour déplacer un joueur déjà réparti (sport-seance.md
# §2, position provisoire, point ouvert 1).
_LATE_PLACERS = frozenset({*COACHING_STAFF_ROLES, MembershipRole.Role.CAPTAIN})


def assign_team(*, session: Session, membership: Membership, team: str, assigned_by) -> TeamAssignment:
    """Place ou déplace un joueur en équipe A/B (CDC 4.7 ; 10.2 n° 7, n° 29,
    n° 38). Contrôle réel d'éligibilité fait ICI (CLAUDE.md règle n° 5 ;
    sport-seance.md §3.2 bis) : aucun appelant ne peut contourner ce refus."""

    event = session.event
    ensure_event_writable(event, actor=assigned_by)

    attendance = Attendance.all_objects.filter(club=session.club_id, event=event, membership=membership).first()
    if attendance is None or attendance.status not in (Attendance.Status.PRESENT, Attendance.Status.LATE_ABSENT):
        raise SportValidationError("Ce joueur doit être pointé présent ou en retard avant d'être réparti.")

    playability = get_playability(membership)
    if not playability.eligible:
        raise PlayerNotEligibleError(playability.detail)

    existing = TeamAssignment.all_objects.filter(club=session.club_id, session=session, membership=membership).first()

    if existing is None and attendance.status == Attendance.Status.LATE_ABSENT:
        if not getattr(assigned_by, "is_superuser", False) and not has_any_role(
            assigned_by, _LATE_PLACERS, club=session.club
        ):
            raise SportPermissionError("Seuls le Coach (ou son assistant) et le Capitaine placent un retardataire.")

    if existing is not None:
        before = {"team": existing.team}
        existing.team = team
        existing.assigned_by = assigned_by
        existing.save()
        assignment = existing
        action_type = "sport.team_assignment_updated"
    else:
        before = None
        assignment = TeamAssignment(
            club=session.club,
            session=session,
            membership=membership,
            team=team,
            arrival_order=_next_arrival_order(session),
            assigned_by=assigned_by,
        )
        assignment.save()
        action_type = "sport.team_assignment_created"

    log_action(actor=assigned_by, club=session.club, action_type=action_type, obj=assignment, before=before, after={"team": team})
    return assignment


def sync_pending_regularizations(session: Session, *, actor) -> None:
    """Applique la régularisation en direct (sport-seance.md §3.2, point 4) :
    un joueur pointé présent, redevenu éligible entre-temps, rejoint
    automatiquement l'équipe que lui donne la règle d'alternance, sans
    attendre une nouvelle saisie de pointage. Appelée avant toute lecture
    de la zone « Non répartis »/des équipes (interrogation périodique,
    6.5)."""

    assigned_ids = TeamAssignment.all_objects.filter(club=session.club_id, session=session).values_list(
        "membership_id", flat=True
    )
    pending_present = Attendance.all_objects.filter(
        club=session.club_id, event=session.event_id, status=Attendance.Status.PRESENT
    ).exclude(membership_id__in=list(assigned_ids))
    for attendance in pending_present:
        if get_playability(attendance.membership).eligible:
            _auto_assign_if_present(session, attendance.membership, assigned_by=actor)


@dataclass(frozen=True)
class UnassignedGroups:
    """Zone « Non répartis » (10.2 n° 29, n° 38) : jamais un champ stocké,
    toujours recalculée à la lecture (schema §5.4)."""

    to_place_manually: list
    cannot_play: list


def get_unassigned_players(session: Session, *, actor) -> UnassignedGroups:
    sync_pending_regularizations(session, actor=actor)

    assigned_ids = TeamAssignment.all_objects.filter(club=session.club_id, session=session).values_list(
        "membership_id", flat=True
    )
    pointed = (
        Attendance.all_objects.filter(
            club=session.club_id,
            event=session.event_id,
            status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE_ABSENT],
        )
        .exclude(membership_id__in=list(assigned_ids))
        .select_related("membership")
    )

    to_place_manually: list = []
    cannot_play: list = []
    for attendance in pointed:
        playability = get_playability(attendance.membership)
        if not playability.eligible:
            # Un joueur à la fois en retard et non sélectionnable
            # n'apparaît que dans « Ne peuvent pas jouer » (sport-seance.md
            # §3.2, point 3) : le blocage l'emporte toujours.
            cannot_play.append((attendance.membership, playability))
        else:
            to_place_manually.append((attendance.membership, attendance))
    return UnassignedGroups(to_place_manually=to_place_manually, cannot_play=cannot_play)


# ---------------------------------------------------------------------------
# Terrain A/B : formation par équipe et placement (extension client du
# 30/09/2026, hors CDC écrit à ce jour -- voir docstring du module et le
# compte rendu de cette tâche)
# ---------------------------------------------------------------------------

# Mêmes rôles que la répartition A/B (matrice 2.4, ligne « Séances et
# matchs : pointage, répartition A/B » : Pdt, Coach, Cap ont « É »),
# dupliqué ici a dessein plutôt qu'importé depuis ``apps.sport.permissions``
# -- même convention de défense en profondeur que ``_LATE_PLACERS``
# ci-dessus : ces deux nouveaux services n'ont pas encore de classe de
# permission DRF dédiée (aucune vue n'est construite dans cette tâche).
_TEAM_FORMATION_AND_PLACEMENT_ROLES = frozenset(
    {MembershipRole.Role.PRESIDENT, *COACHING_STAFF_ROLES, MembershipRole.Role.CAPTAIN}
)

_MAX_PLAYERS_ON_FIELD = 11


def _ensure_team_formation_permission(actor, *, club) -> None:
    if getattr(actor, "is_superuser", False):
        return
    if not has_any_role(actor, _TEAM_FORMATION_AND_PLACEMENT_ROLES, club=club):
        raise SportPermissionError(
            "Réservé au Président, au Coach (ou son assistant) ou au Capitaine."
        )


def set_team_formation(*, session: Session, team: str, formation: str, actor) -> Session:
    """Choisit la formation d'une équipe (A ou B) de la séance,
    indépendamment de l'autre équipe (extension client du 30/09/2026).
    Réutilise la bibliothèque ``apps.sport.models.Formation`` déjà
    utilisée par le plan tactique (CDC 4.11), sans dupliquer le
    TextChoices. Même garde d'écriture que :func:`assign_team`
    (:func:`ensure_event_writable`) et mêmes permissions (matrice 2.4,
    ligne « Séances et matchs : pointage, répartition A/B »)."""

    if team not in (TeamAssignment.Team.A, TeamAssignment.Team.B):
        raise SportValidationError("Équipe invalide : choisissez A ou B.")

    event = session.event
    ensure_event_writable(event, actor=actor)
    _ensure_team_formation_permission(actor, club=session.club)

    field_name = "team_a_formation" if team == TeamAssignment.Team.A else "team_b_formation"
    before = {field_name: getattr(session, field_name)}
    setattr(session, field_name, formation)
    session.save(update_fields=[field_name])

    log_action(
        actor=actor,
        club=session.club,
        action_type="sport.session_team_formation_set",
        obj=session,
        before=before,
        after={field_name: formation},
    )
    return session


def place_team_player(
    *,
    session: Session,
    team: str,
    membership: Membership,
    x_coord: Optional[Decimal],
    y_coord: Optional[Decimal],
    actor,
) -> TeamAssignment:
    """Place, déplace ou renvoie sur le banc un joueur déjà réparti en
    équipe A/B (extension client du 30/09/2026, hors CDC écrit à ce jour
    -- voir le compte rendu). Distinct du plan tactique (CDC 4.11,
    ``TacticalPlanPlacement``, délibérément non réutilisé/dupliqué ici :
    une séance d'entraînement n'est pas un plan de match).

    Règles (client, cf. tâche) :
    - le joueur doit déjà porter une ``TeamAssignment`` pour cette
      équipe, posée au préalable par :func:`assign_team` ;
    - même contrôle d'éligibilité que partout ailleurs (CLAUDE.md
      règle n° 5 ; :func:`get_playability`) -- appliqué avant tout
      placement sur le terrain (pas avant un renvoi au banc, qui ne
      retire jamais un joueur de rien) ;
    - au plus 11 joueurs « sur le terrain » par équipe : déposer un
      joueur sur une case déjà occupée par un coéquipier échange les
      deux joueurs (l'occupant repasse sur le banc) ; déposer sur une
      case vide alors que 11 joueurs sont déjà sur le terrain est
      refusé explicitement (pas de dépassement silencieux) ;
    - ``x_coord``/``y_coord`` tous deux ``None`` renvoie le joueur sur
      le banc, sans contrôle de plafond dans ce sens.

    Verrouillage (``select_for_update``) sur les lignes de l'équipe
    pendant le calcul du plafond/de l'échange : sans effet sous SQLite
    (no-op silencieux, développement), réellement pris en compte sous
    MySQL/MariaDB (production) -- même limite documentée ailleurs dans
    le projet (ex. ``apps.treasury.services``), signalée au compte rendu.
    """

    event = session.event
    ensure_event_writable(event, actor=actor)
    _ensure_team_formation_permission(actor, club=session.club)

    assignment = TeamAssignment.all_objects.filter(
        club=session.club_id, session=session, team=team, membership=membership
    ).first()
    if assignment is None:
        raise SportValidationError(
            "Ce joueur doit d'abord être réparti dans cette équipe avant d'être placé sur le terrain."
        )

    to_bench = x_coord is None and y_coord is None
    if not to_bench and (x_coord is None or y_coord is None):
        raise SportValidationError(
            "Fournissez les deux coordonnées (x et y), ou aucune des deux pour renvoyer le joueur au banc."
        )

    if to_bench:
        before = {
            "is_on_field": assignment.is_on_field,
            "x": str(assignment.x_coord) if assignment.x_coord is not None else None,
            "y": str(assignment.y_coord) if assignment.y_coord is not None else None,
        }
        assignment.is_on_field = False
        assignment.x_coord = None
        assignment.y_coord = None
        assignment.save()
        log_action(
            actor=actor,
            club=session.club,
            action_type="sport.team_assignment_benched",
            obj=assignment,
            before=before,
            after={"is_on_field": False},
        )
        return assignment

    playability = get_playability(membership)
    if not playability.eligible:
        raise PlayerNotEligibleError(playability.detail)

    before = {
        "is_on_field": assignment.is_on_field,
        "x": str(assignment.x_coord) if assignment.x_coord is not None else None,
        "y": str(assignment.y_coord) if assignment.y_coord is not None else None,
    }

    with transaction.atomic():
        team_assignments = list(
            TeamAssignment.all_objects.select_for_update()
            .filter(club=session.club_id, session=session, team=team)
        )
        assignment = next(a for a in team_assignments if a.pk == assignment.pk)

        occupant = next(
            (
                a
                for a in team_assignments
                if a.pk != assignment.pk and a.is_on_field and a.x_coord == x_coord and a.y_coord == y_coord
            ),
            None,
        )
        on_field_count_excluding_self = sum(
            1 for a in team_assignments if a.is_on_field and a.pk != assignment.pk
        )

        if occupant is not None:
            occupant_before = {
                "is_on_field": occupant.is_on_field,
                "x": str(occupant.x_coord),
                "y": str(occupant.y_coord),
            }
            occupant.is_on_field = False
            occupant.x_coord = None
            occupant.y_coord = None
            occupant.save()
            log_action(
                actor=actor,
                club=session.club,
                action_type="sport.team_assignment_benched",
                obj=occupant,
                before=occupant_before,
                after={"is_on_field": False},
                # Échange : cette écriture accompagne celle de ``assignment``
                # ci-dessous, journalisée séparément (une ligne par ligne
                # modifiée, CLAUDE.md règle n° 6).
            )
        elif on_field_count_excluding_self >= _MAX_PLAYERS_ON_FIELD:
            raise SportValidationError(
                "Cette équipe compte déjà 11 joueurs sur le terrain : déposez ce joueur sur un "
                "coéquipier pour échanger les places, ou renvoyez-en un au banc d'abord."
            )

        assignment.is_on_field = True
        assignment.x_coord = x_coord
        assignment.y_coord = y_coord
        assignment.save()

    log_action(
        actor=actor,
        club=session.club,
        action_type="sport.team_assignment_placed",
        obj=assignment,
        before=before,
        after={"is_on_field": True, "x": str(x_coord), "y": str(y_coord)},
    )
    return assignment


# ---------------------------------------------------------------------------
# Matchs et composition (CDC 4.8)
# ---------------------------------------------------------------------------


def create_match(
    *,
    club,
    season: Season,
    event_date: date,
    kickoff_time,
    match_type: str,
    venue: str,
    created_by,
    opponent_club=None,
    opponent_name: str = "",
    location: str = "",
    challenge_status: str = Match.ChallengeStatus.NOT_APPLICABLE,
    challenge_to_club=None,
) -> Match:
    if opponent_club is None and not (opponent_name or "").strip():
        raise SportValidationError("Indiquez un club adverse Vesta ou le nom d'une équipe extérieure.")
    if opponent_club is not None and opponent_club.pk == club.pk:
        raise SportValidationError("Votre propre club ne peut pas être l'adversaire d'un match.")
    if challenge_to_club is not None and challenge_to_club.pk == club.pk:
        raise SportValidationError("Vous ne pouvez pas lancer un défi à votre propre club.")
    if challenge_status != Match.ChallengeStatus.NOT_APPLICABLE and challenge_to_club is None:
        raise SportValidationError("Un défi doit désigner le club destinataire.")
    if challenge_to_club is not None or challenge_status != Match.ChallengeStatus.NOT_APPLICABLE:
        # Un défi est toujours créé « Proposé » : il n'est jamais accepté ou
        # refusé à la création, faute de consentement du club adverse.
        challenge_status = Match.ChallengeStatus.PROPOSED
    with transaction.atomic():
        match = _create_match_atomic(
            club=club, season=season, event_date=event_date, kickoff_time=kickoff_time, match_type=match_type,
            venue=venue, created_by=created_by, opponent_club=opponent_club, opponent_name=opponent_name,
            location=location, challenge_status=challenge_status, challenge_to_club=challenge_to_club,
        )
    place = f", {location}" if location else ""
    _notify_event_created(
        club=club,
        target=match,
        message=(
            f"Un match contre {_opponent_label(match)} est programmé le "
            f"{event_date.strftime('%d/%m/%Y')} à {str(kickoff_time)[:5]}{place}."
        ),
    )
    return match


def _create_match_atomic(
    *, club, season, event_date, kickoff_time, match_type, venue, created_by, opponent_club, opponent_name,
    location, challenge_status, challenge_to_club,
) -> Match:
    event = Event(club=club, kind=Event.Kind.MATCH, event_date=event_date, season=season, created_by=created_by)
    event.save()
    match = Match(
        event=event,
        club=club,
        opponent_club=opponent_club,
        opponent_name=opponent_name,
        match_type=match_type,
        venue=venue,
        kickoff_time=kickoff_time,
        location=location,
        challenge_status=challenge_status,
        challenge_to_club=challenge_to_club,
    )
    match.save()
    log_action(actor=created_by, club=club, action_type="sport.match_created", obj=match, after={"event_date": event_date.isoformat()})
    return match


def update_match(
    *,
    match: Match,
    event_date: date,
    kickoff_time,
    match_type: str,
    venue: str,
    updated_by,
    opponent_club=None,
    opponent_name: str = "",
    location: str = "",
    challenge_to_club_id: int | None = None,
) -> Match:
    """Modifie un match existant (sport-feuille-de-match.md §4.7 : « Champs
    de Créer un match, adversaire non modifiable pour un défi accepté »).
    Verrouillée à minuit comme la séance (§5, « Verrouillé (lendemain) :
    lecture seule, sauf buts et passes modifiables après coup »).

    Comme à la création, le propre club ne peut être ni l'adversaire ni le
    destinataire d'un défi ; ``challenge_to_club_id`` ne sert qu'à ce
    contrôle (un défi ne se modifie pas depuis cette modale)."""

    event = match.event
    ensure_event_writable(event, actor=updated_by)

    if opponent_club is not None and opponent_club.pk == match.club_id:
        raise SportValidationError("Votre propre club ne peut pas être l'adversaire d'un match.")
    if challenge_to_club_id is not None and challenge_to_club_id == match.club_id:
        raise SportValidationError("Vous ne pouvez pas lancer un défi à votre propre club.")

    if match.challenge_status == Match.ChallengeStatus.ACCEPTED:
        # L'adversaire d'un défi accepté n'est jamais modifiable ici, quoi
        # que le client envoie pour ces deux champs (§4.7) : on ignore la
        # valeur transmise plutôt que de refuser toute la requête, pour ne
        # pas dépendre de ce que l'interface choisit de renvoyer pour un
        # champ qu'elle désactive.
        opponent_club = match.opponent_club
        opponent_name = match.opponent_name

    before = {
        "event_date": event.event_date.isoformat(),
        "kickoff_time": str(match.kickoff_time),
        "match_type": match.match_type,
        "venue": match.venue,
        "location": match.location,
        "opponent_club": match.opponent_club_id,
        "opponent_name": match.opponent_name,
    }

    event.event_date = event_date
    event.save()

    match.kickoff_time = kickoff_time
    match.match_type = match_type
    match.venue = venue
    match.location = location
    match.opponent_club = opponent_club
    match.opponent_name = opponent_name
    match.save()

    log_action(
        actor=updated_by,
        club=match.club,
        action_type="sport.match_updated",
        obj=match,
        before=before,
        after={
            "event_date": event_date.isoformat(),
            "kickoff_time": str(kickoff_time),
            "match_type": match_type,
            "venue": venue,
            "location": location,
        },
    )
    return match


def mark_match_arrival(
    *,
    match: Match,
    membership: Membership,
    arrived_at: datetime,
    marked_by,
    client_uuid=None,
    client_recorded_at=None,
    audit_extra: Optional[dict] = None,
) -> Attendance:
    """Pointage simple d'un match (CDC 4.8 : « mêmes règles que les
    séances » pour la présence, sans répartition A/B -- position déjà
    actée par `ui-designer`, sport-feuille-de-match.md §7 point ouvert 2 :
    ``TeamAssignment`` ne se rattache qu'à une ``Session`` (schéma §5.4),
    jamais à un ``Match``). Contrairement à :func:`mark_arrival`, ce
    service ne crée donc jamais d'affectation d'équipe.

    **Heure limite utilisée** : ``Match`` ne porte aucun champ
    ``late_arrival_cutoff`` -- absent de `docs/lot0/schema-donnees.md`
    §5.5, à la différence de ``Session`` §5.2 (lecture volontaire du
    schéma, pas un oubli à corriger sans validation du client). En
    l'absence de ce champ, ce service utilise ``match.kickoff_time``
    lui-même comme heure limite : présent si arrivé au plus tard au coup
    d'envoi, sinon « en retard, compté absent » (comptage configurable par
    club, ``ClubSettings.late_arrival_counts_absent``, comme pour les
    séances -- 10.2 n° 6, n° 25). Décision par défaut signalée au compte
    rendu : à confirmer par le client (un champ dédié, par exemple une
    marge avant le coup d'envoi, pourrait être préféré)."""

    event = match.event
    ensure_event_writable(event, actor=marked_by)

    if client_uuid is not None:
        existing = _existing_attendance_for_client_uuid(event, membership, client_uuid)
        if existing is not None:
            return existing

    club_settings = _club_settings(match.club)
    cutoff_dt = _combine_local(event.event_date, match.kickoff_time, club_settings)
    status = Attendance.Status.PRESENT if arrived_at <= cutoff_dt else Attendance.Status.LATE_ABSENT

    attendance, _created = _upsert_attendance(
        event=event,
        membership=membership,
        status=status,
        arrived_at=arrived_at,
        marked_by=marked_by,
        client_uuid=client_uuid,
        client_recorded_at=client_recorded_at,
        audit_extra=audit_extra,
    )
    return attendance


# ---------------------------------------------------------------------------
# Pointage groupé (sport-pointage-selection-multiple.md ; décisions du
# 15/11/2026). Une seule source de vérité : chaque joueur passe par
# mark_arrival / mark_match_arrival / mark_excused_absence.
# ---------------------------------------------------------------------------

BULK_ATTENDANCE_MAX_ITEMS = 100

EXCUSE_REASON_LABELS = {"injured": "Blessé", "travel": "Voyage", "other": "Autre"}


def _is_coaching_staff(actor, club) -> bool:
    return bool(getattr(actor, "is_superuser", False)) or has_any_role(actor, COACHING_STAFF_ROLES, club=club)


def _bulk_prepare(event: Event, items, actor):
    """Contrôles communs d'un lot : taille, verrou (une seule fois),
    chargement des joueurs du club (étanchéité), ordre de sélection."""

    items = list(items or [])
    if not items:
        raise SportValidationError("Cochez au moins un joueur.")
    if len(items) > BULK_ATTENDANCE_MAX_ITEMS:
        raise SportValidationError(
            f"Un envoi ne peut pas dépasser {BULK_ATTENDANCE_MAX_ITEMS} joueurs. Envoyez plusieurs lots."
        )
    if not getattr(actor, "is_superuser", False) and is_event_locked(event):
        raise EventLockedError(
            "Cette séance est verrouillée depuis minuit. Seul le support peut la corriger, "
            "à la demande du Président."
        )
    # Ordre de sélection (selection_rank), puis ordre d'envoi ; tri stable.
    indexed = sorted(
        enumerate(items),
        key=lambda pair: (pair[1].get("selection_rank") is None, pair[1].get("selection_rank") or 0, pair[0]),
    )
    ordered = [item for _i, item in indexed]
    ids = {item["membership_id"] for item in ordered}
    members = {m.pk: m for m in Membership.all_objects.filter(club=event.club_id, pk__in=ids).select_related("user")}
    return ordered, members


def _bulk_result(membership_id, outcome, message, attendance=None) -> dict:
    return {"membership_id": membership_id, "outcome": outcome, "message": message, "attendance": attendance}


def _local_hhmm(event: Event, moment) -> str:
    tz = _club_tz(_club_settings(event.club))
    return moment.astimezone(tz).strftime("%H:%M")


def _bulk_counts(results) -> dict:
    return {key: sum(1 for r in results if r["outcome"] == key) for key in ("created", "skipped", "refused")}


def _validate_common_arrival(event: Event, arrived_at, actor) -> None:
    """Heure commune : Coach/Assistant seulement, dans la journée de
    l'événement (fuseau du club), pas dans le futur."""

    if not _is_coaching_staff(actor, event.club):
        raise SportPermissionError("Seuls le Coach et son assistant peuvent indiquer une heure d'arrivée commune.")
    tz = _club_tz(_club_settings(event.club))
    if arrived_at > timezone.now():
        raise SportValidationError("L'heure ne peut pas être dans le futur.")
    if arrived_at.astimezone(tz).date() != event.event_date:
        raise SportValidationError("L'heure doit être comprise dans la journée de la séance.")


def mark_arrivals_bulk(*, event: Event, items, actor, arrived_at=None, batch_id=None) -> dict:
    """Pointage d'arrivée groupé (une entrée de journal par joueur, avec
    ``batch_id``). Jamais de statut forcé : le statut Présent/En retard est
    calculé par le service unitaire à partir de l'heure. Chaque joueur est
    traité dans sa propre transaction ; un échec n'arrête pas les autres.
    Un joueur déjà pointé n'est pas écrasé (outcome « skipped »).

    Refus du lot entier (exceptions) : SportValidationError (lot vide ou
    trop grand, heure invalide), EventLockedError (verrou de minuit),
    SportPermissionError (heure commune sans être Coach/Assistant)."""

    batch_id = batch_id or str(uuid.uuid4())
    ordered, members = _bulk_prepare(event, items, actor)
    custom_time = arrived_at is not None
    if custom_time:
        _validate_common_arrival(event, arrived_at, actor)
    when = arrived_at or timezone.now()
    club_settings = _club_settings(event.club)
    extra = {"batch_id": batch_id, "batch_size": len(ordered)}
    if custom_time:
        extra["common_time_entered_by_coach"] = True

    session = match = None
    if event.kind == Event.Kind.SESSION:
        session = Session.all_objects.filter(club=event.club_id, event=event).first()
    elif event.kind == Event.Kind.MATCH:
        match = Match.all_objects.filter(club=event.club_id, event=event).first()
    if session is None and match is None:
        raise SportValidationError("Cet événement ne peut pas être pointé.")

    results = []
    for item in ordered:
        mid = item["membership_id"]
        membership = members.get(mid)
        if membership is None:
            results.append(_bulk_result(mid, "refused", "Ce joueur n'existe pas dans ce club."))
            continue
        existing = Attendance.all_objects.filter(club=event.club_id, event=event, membership=membership).first()
        client_uuid = item.get("client_uuid")
        if existing is None and client_uuid is not None:
            try:
                existing = _existing_attendance_for_client_uuid(event, membership, client_uuid)
            except SportValidationError as exc:
                results.append(_bulk_result(mid, "refused", str(exc)))
                continue
        if existing is not None:
            if existing.arrived_at is not None:
                message = f"Déjà pointé à {_local_hhmm(event, existing.arrived_at)}."
            else:
                message = "Déjà pointé (absence excusée)."
            results.append(_bulk_result(mid, "skipped", message, existing))
            continue
        try:
            with transaction.atomic():
                kwargs = dict(
                    membership=membership,
                    arrived_at=when,
                    marked_by=actor,
                    client_uuid=client_uuid,
                    client_recorded_at=item.get("client_recorded_at"),
                    audit_extra=extra,
                )
                if session is not None:
                    attendance = mark_arrival(session=session, **kwargs)
                else:
                    attendance = mark_match_arrival(match=match, **kwargs)
        except SportError as exc:
            results.append(_bulk_result(mid, "refused", str(exc)))
            continue
        except Exception:  # noqa: BLE001 - un joueur en échec ne bloque jamais les autres
            logger.exception("Pointage groupé : échec inattendu pour le joueur %s", mid)
            results.append(_bulk_result(mid, "refused", "Pointage non enregistré. Réessayez."))
            continue
        hhmm = _local_hhmm(event, attendance.arrived_at)
        if attendance.status == Attendance.Status.PRESENT:
            message = f"Pointé à {hhmm}."
        elif club_settings.late_arrival_counts_absent:
            message = f"Pointé en retard à {hhmm} (compté absent selon la règle du club)."
        else:
            message = f"Pointé en retard à {hhmm}."
        results.append(_bulk_result(mid, "created", message, attendance))
    return {"batch_id": batch_id, "results": results, "counts": _bulk_counts(results)}


def excuse_absences_bulk(*, event: Event, items, actor, reason_code: str, reason_detail: str = "", batch_id=None) -> dict:
    """Absences excusées groupées : Coach/Assistant seulement (vérifié ici,
    pas seulement dans la vue). Seulement des joueurs non pointés."""

    if not _is_coaching_staff(actor, event.club):
        raise SportPermissionError("Seuls le Coach et son assistant marquent des absences excusées.")
    if reason_code not in EXCUSE_REASON_LABELS:
        raise SportValidationError("Choisissez un motif.")
    reason_detail = (reason_detail or "").strip()
    if len(reason_detail) > 200:
        raise SportValidationError("La précision ne doit pas dépasser 200 caractères.")
    batch_id = batch_id or str(uuid.uuid4())
    ordered, members = _bulk_prepare(event, items, actor)
    reason = EXCUSE_REASON_LABELS[reason_code] + (f" : {reason_detail}" if reason_detail else "")
    extra = {"batch_id": batch_id, "batch_size": len(ordered), "reason_code": reason_code}

    results = []
    for item in ordered:
        mid = item["membership_id"]
        membership = members.get(mid)
        if membership is None:
            results.append(_bulk_result(mid, "refused", "Ce joueur n'existe pas dans ce club."))
            continue
        existing = Attendance.all_objects.filter(club=event.club_id, event=event, membership=membership).first()
        if existing is not None:
            results.append(
                _bulk_result(
                    mid, "skipped", "Déjà pointé : une absence excusée ne s'applique qu'à un joueur non pointé.", existing
                )
            )
            continue
        try:
            with transaction.atomic():
                attendance = mark_excused_absence(
                    event=event, membership=membership, reason=reason, marked_by=actor, audit_extra=extra
                )
        except SportError as exc:
            results.append(_bulk_result(mid, "refused", str(exc)))
            continue
        except Exception:  # noqa: BLE001
            logger.exception("Absence excusée groupée : échec inattendu pour le joueur %s", mid)
            results.append(_bulk_result(mid, "refused", "Absence non enregistrée. Réessayez."))
            continue
        results.append(_bulk_result(mid, "created", "Absence excusée enregistrée.", attendance))
    return {"batch_id": batch_id, "results": results, "counts": _bulk_counts(results)}


def add_to_composition(
    *, match: Match, membership: Membership, role: str, position: str, jersey_number: int, added_by
) -> MatchComposition:
    """Composition d'un match (CDC 4.8). Refuse un joueur en dette,
    suspendu, inapte ou en attente d'adhésion, avec la raison (CLAUDE.md
    règle n° 5 ; CDC 9.2, critère du Lot 3). Régularisation sur place :
    rappeler ce même service une fois le paiement validé rend le joueur
    de nouveau composable, sans latence perceptible (la vérification est
    faite à chaque appel, jamais mise en cache)."""

    playability = get_playability(membership)
    if not playability.eligible:
        raise PlayerNotEligibleError(playability.detail)

    existing = MatchComposition.all_objects.filter(club=match.club_id, match=match, membership=membership).first()
    taken = MatchComposition.all_objects.filter(club=match.club_id, match=match, jersey_number=jersey_number)
    if existing is not None:
        taken = taken.exclude(pk=existing.pk)
    if taken.exists():
        raise SportValidationError(f"Le numéro {jersey_number} est déjà attribué à un autre joueur pour ce match.")
    if existing is not None:
        before = {"role": existing.role, "position": existing.position, "jersey_number": existing.jersey_number}
        existing.role, existing.position, existing.jersey_number, existing.added_by = role, position, jersey_number, added_by
        existing.save()
        composition = existing
        action_type = "sport.composition_updated"
    else:
        before = None
        composition = MatchComposition(
            club=match.club, match=match, membership=membership, role=role, position=position,
            jersey_number=jersey_number, added_by=added_by,
        )
        composition.save()
        action_type = "sport.composition_added"

    log_action(
        actor=added_by, club=match.club, action_type=action_type, obj=composition, before=before,
        after={"role": role, "position": position, "jersey_number": jersey_number},
    )
    return composition


def remove_from_composition(*, match: Match, membership: Membership, removed_by) -> None:
    composition = MatchComposition.all_objects.filter(club=match.club_id, match=match, membership=membership).first()
    if composition is None:
        return
    log_action(
        actor=removed_by, club=match.club, action_type="sport.composition_removed", obj=composition,
        before={"role": composition.role, "jersey_number": composition.jersey_number},
    )
    composition.delete()


def _opponent_label(match: Match) -> str:
    return match.opponent_club.name if match.opponent_club_id else match.opponent_name


def _notify_composition_published(match: Match, compositions) -> None:
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    for composition in compositions:
        role_label = "titulaire" if composition.role == MatchComposition.Role.STARTER else "remplaçant"
        create_notification(
            recipient=composition.membership.user,
            event_type=Notification.EventType.COMPOSITION_OR_PLAN_PUBLISHED,
            message=f"La composition du match contre {_opponent_label(match)} a été publiée. Vous êtes {role_label}.",
            club=match.club,
            target=match,
        )


def publish_composition(*, match: Match, published_by) -> Match:
    """Publication bloquée tant que la composition compte un joueur non
    sélectionnable (position provisoire, sport-feuille-de-match.md §3,
    point 2)."""

    compositions = list(MatchComposition.all_objects.filter(club=match.club_id, match=match).select_related("membership"))
    ineligible = [c.membership for c in compositions if not get_playability(c.membership).eligible]
    if ineligible:
        raise SportValidationError(
            "Retirez d'abord les joueurs qui ne peuvent plus jouer avant de publier la composition."
        )
    match.is_composition_published = True
    match.composition_published_at = timezone.now()
    match.save()
    log_action(actor=published_by, club=match.club, action_type="sport.composition_published", obj=match, after={"is_composition_published": True})
    _notify_composition_published(match, compositions)
    return match


# ---------------------------------------------------------------------------
# Feuille de match : score et buts (CDC 4.8 -- jamais soumis au
# verrouillage à minuit, à la différence du pointage/de la répartition/
# des incidents : « le Coach peut modifier les buts et les passes
# décisives après coup »)
# ---------------------------------------------------------------------------


def _result_post_body(match: Match, sheet: MatchSheet) -> str:
    scorers = []
    for goal in sheet.goals.select_related("scorer_membership__user").order_by("minute", "pk"):
        if goal.scorer_membership_id:
            user = goal.scorer_membership.user
            label = f"{user.first_name} {user.last_name}".strip()
            scorers.append(f"{label} {goal.minute}'" if goal.minute is not None else label)
    body = f"Résultat : {match.club.name} {sheet.score_home} - {sheet.score_away} {_opponent_label(match)}."
    if scorers:
        body += " Buteurs : " + ", ".join(scorers) + "."
    return body


def _refresh_result_post(*, match: Match, sheet: MatchSheet, actor, before_score: Optional[dict]) -> None:
    """Met à jour le post « résultat » déjà publié (même publication, pas de
    doublon, visibilité inchangée) et journalise la mise à jour. Sans effet
    si le résultat n'a pas été publié ou si le texte ne change pas."""

    from apps.social.models import Post

    post_id = Match.all_objects.filter(pk=match.pk, club=match.club_id).values_list("result_post_id", flat=True).first()
    if post_id is None:
        return
    post = Post.all_objects.filter(pk=post_id, club=match.club_id, deleted_at__isnull=True).first()
    if post is None:
        return
    body = _result_post_body(match, sheet)
    if body == post.body:
        return
    before_body = post.body
    post.body = body
    post.save(update_fields=["body"])
    after_score = {"score_home": sheet.score_home, "score_away": sheet.score_away}
    log_action(
        actor=actor,
        club=match.club,
        action_type="sport.match_result_post_updated",
        obj=match,
        before={**(before_score or after_score), "body": before_body},
        after={**after_score, "body": body, "post_id": post.pk},
    )


def set_match_score(*, match: Match, score_home: int, score_away: int, filled_by) -> MatchSheet:
    """Saisie du score (CDC 4.8). Verrouillé après minuit (fuseau du club ;
    décision du client du 16/11/2026), sauf Superuser en session de support.
    Les buts et passes, eux, restent modifiables après coup. Si le résultat
    a déjà été publié, le post existant est mis à jour."""

    if not getattr(filled_by, "is_superuser", False) and is_event_locked(match.event):
        raise EventLockedError(
            "Ce match est verrouillé depuis minuit : son score ne peut plus être modifié. "
            "Seul le support peut le corriger, à la demande du Président."
        )
    sheet = MatchSheet.all_objects.filter(club=match.club_id, match=match).first()
    if sheet is None:
        sheet = MatchSheet(club=match.club, match=match, score_home=score_home, score_away=score_away, filled_by=filled_by, filled_at=timezone.now())
        sheet.save()
        before = None
        action_type = "sport.match_score_set"
    else:
        before = {"score_home": sheet.score_home, "score_away": sheet.score_away}
        sheet.score_home, sheet.score_away = score_home, score_away
        sheet.save()
        action_type = "sport.match_score_updated"
    log_action(actor=filled_by, club=match.club, action_type=action_type, obj=sheet, before=before, after={"score_home": score_home, "score_away": score_away})
    _refresh_result_post(match=match, sheet=sheet, actor=filled_by, before_score=before)
    return sheet


def is_match_finished(match: Match, *, now: Optional[datetime] = None) -> bool:
    """Vrai si l'heure du coup d'envoi est passée (fuseau du club)."""

    now = now or timezone.now()
    local_now = now.astimezone(_club_tz(_club_settings(match.club)))
    event_date = match.event.event_date
    if event_date != local_now.date():
        return event_date < local_now.date()
    return local_now.time() >= match.kickoff_time


def publish_match_result(*, match: Match, published_by, now: Optional[datetime] = None) -> Match:
    """Publie le résultat sur le fil du club en un clic (CDC 4.8).

    Exige un score saisi et un match terminé ; une seule publication par
    match. Visibilité « Club » (10.2 n° 160 : jamais public sans consentement).
    """

    from apps.social.services import create_auto_result_post

    with transaction.atomic():
        locked = (
            Match.all_objects.select_for_update()
            .select_related("event", "club", "opponent_club")
            .get(pk=match.pk, club=match.club_id)
        )
        if locked.result_post_id is not None:
            raise SportValidationError("Le résultat de ce match a déjà été publié sur le fil.")
        sheet = MatchSheet.all_objects.filter(club=locked.club_id, match=locked).first()
        if sheet is None:
            raise SportValidationError("Saisissez d'abord le score du match avant de publier le résultat.")
        if not is_match_finished(locked, now=now):
            raise SportValidationError("Le match n'est pas encore terminé : le résultat ne peut pas être publié.")

        body = _result_post_body(locked, sheet)

        post = create_auto_result_post(club=locked.club, actor=published_by, body=body)
        locked.result_post = post
        locked.save(update_fields=["result_post"])
        log_action(
            actor=published_by,
            club=locked.club,
            action_type="sport.match_result_published",
            obj=locked,
            after={"post_id": post.pk, "visibility": post.visibility},
        )
    return locked


def _refresh_result_post_for_sheet(sheet: MatchSheet, *, actor) -> None:
    _refresh_result_post(
        match=sheet.match, sheet=sheet, actor=actor,
        before_score={"score_home": sheet.score_home, "score_away": sheet.score_away},
    )


def _check_scorer_assist(scorer_membership, assist_membership) -> None:
    if scorer_membership is not None and assist_membership is not None and scorer_membership.pk == assist_membership.pk:
        raise SportValidationError("Le passeur décisif doit être différent du buteur.")


def add_goal(*, match_sheet: MatchSheet, created_by, scorer_membership=None, assist_membership=None, minute=None) -> MatchGoal:
    _check_scorer_assist(scorer_membership, assist_membership)
    goal = MatchGoal(
        club=match_sheet.club, match_sheet=match_sheet, scorer_membership=scorer_membership,
        assist_membership=assist_membership, minute=minute, created_by=created_by,
    )
    goal.save()
    log_action(
        actor=created_by, club=match_sheet.club, action_type="sport.goal_added", obj=goal,
        after={"scorer": getattr(scorer_membership, "pk", None), "minute": minute},
    )
    _refresh_result_post_for_sheet(match_sheet, actor=created_by)
    return goal


def update_goal(*, goal: MatchGoal, updated_by, scorer_membership=None, assist_membership=None, minute=None) -> MatchGoal:
    _check_scorer_assist(scorer_membership, assist_membership)
    before = {
        "scorer": goal.scorer_membership_id, "assist": goal.assist_membership_id, "minute": goal.minute,
    }
    goal.scorer_membership = scorer_membership
    goal.assist_membership = assist_membership
    goal.minute = minute
    goal.updated_at = timezone.now()
    goal.save()
    log_action(
        actor=updated_by, club=goal.club, action_type="sport.goal_updated", obj=goal, before=before,
        after={"scorer": goal.scorer_membership_id, "assist": goal.assist_membership_id, "minute": minute},
    )
    _refresh_result_post_for_sheet(goal.match_sheet, actor=updated_by)
    return goal


def delete_goal(*, goal: MatchGoal, deleted_by) -> None:
    log_action(
        actor=deleted_by, club=goal.club, action_type="sport.goal_deleted", obj=goal,
        before={"scorer": goal.scorer_membership_id, "minute": goal.minute},
    )
    sheet = goal.match_sheet
    goal.delete()
    _refresh_result_post_for_sheet(sheet, actor=deleted_by)


# ---------------------------------------------------------------------------
# Discipline et suspensions automatiques (CDC 4.9 ; tâche 3.4)
# ---------------------------------------------------------------------------


def _notify_incident(incident: Incident, suspension: Optional[Suspension]) -> None:
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    label = dict(Incident.IncidentType.choices)[incident.incident_type]
    message = f"{label} reçu le {timezone.localtime(incident.recorded_at):%d/%m/%Y}."
    if suspension is not None:
        message += f" Suspension automatique : {suspension.matches_total} match(s)."

    create_notification(
        recipient=incident.membership.user,
        event_type=Notification.EventType.CARD_OR_SUSPENSION,
        message=message,
        club=incident.club,
        target=incident,
    )

    coach_memberships = (
        Membership.all_objects.filter(
            club=incident.club, roles__role__in=COACHING_STAFF_ROLES, roles__revoked_at__isnull=True
        )
        .select_related("user")
        .distinct()
    )
    for coach_membership in coach_memberships:
        if coach_membership.user_id == incident.membership.user_id:
            continue
        create_notification(
            recipient=coach_membership.user,
            event_type=Notification.EventType.CARD_OR_SUSPENSION,
            message=message,
            club=incident.club,
            target=incident,
        )


def _create_suspension(*, membership, reason, triggering_incident, season, matches_total, starts_event, actor) -> Suspension:
    suspension = Suspension(
        club=membership.club, membership=membership, reason=reason, triggering_incident=triggering_incident,
        season=season, matches_total=matches_total, matches_served=0, starts_event=starts_event,
    )
    suspension.save()
    log_action(
        actor=actor, club=membership.club, action_type="sport.suspension_created", obj=suspension,
        after={"reason": reason, "matches_total": matches_total},
    )
    return suspension


def _maybe_create_suspension(incident: Incident) -> Optional[Suspension]:
    """Suspension automatique (CDC 4.9 ; 10.2 n° 8) : carton rouge direct,
    ou 5e carton jaune de la saison (seuil configurable par club,
    ``ClubSettings.yellow_card_suspension_threshold``, remis à zéro par
    saison puisque le comptage est scopé par ``Season``, 10.2 n° 8).
    Ne déclenche qu'AU seuil exact (le CDC ne documente que « le 5e » :
    un 10e jaune plus tard ne redéclenche pas une suspension à ce
    même mécanisme — décision signalée au compte rendu)."""

    club = incident.club
    club_settings = _club_settings(club)
    membership = incident.membership
    season = incident.event.season

    if incident.incident_type == Incident.IncidentType.RED_CARD:
        return _create_suspension(
            membership=membership, reason=Suspension.Reason.RED_CARD, triggering_incident=incident,
            season=season, matches_total=club_settings.red_card_suspension_matches, starts_event=incident.event,
            actor=incident.recorded_by,
        )

    if incident.incident_type == Incident.IncidentType.YELLOW_CARD:
        yellow_count = Incident.all_objects.filter(
            club=club, membership=membership, incident_type=Incident.IncidentType.YELLOW_CARD, event__season_id=season.pk,
        ).count()
        if yellow_count == club_settings.yellow_card_suspension_threshold:
            return _create_suspension(
                membership=membership, reason=Suspension.Reason.CUMULATIVE_YELLOW, triggering_incident=incident,
                season=season, matches_total=club_settings.yellow_card_suspension_matches, starts_event=incident.event,
                actor=incident.recorded_by,
            )
    return None


def record_incident(
    *, event: Event, membership: Membership, incident_type: str, cause: str, recorded_by,
    minute=None, cause_detail: str = "", issued_by: str = "",
) -> Incident:
    """Saisie d'un incident (CDC 4.9), verrouillée à minuit comme le
    pointage et la répartition A/B (schema §5.1 ; position provisoire de
    sport-feuille-de-match.md §7, point 3 pour les matchs)."""

    ensure_event_writable(event, actor=recorded_by)
    incident = Incident(
        club=event.club, event=event, membership=membership, incident_type=incident_type, cause=cause,
        cause_detail=cause_detail, issued_by=issued_by, minute=minute, recorded_by=recorded_by, recorded_at=timezone.now(),
    )
    incident.save()
    log_action(
        actor=recorded_by, club=event.club, action_type="sport.incident_recorded", obj=incident,
        after={"incident_type": incident_type, "cause": cause},
    )
    suspension = _maybe_create_suspension(incident)
    _notify_incident(incident, suspension)
    return incident


def advance_suspensions_for_elapsed_matches(*, club, now: Optional[datetime] = None) -> int:
    """Commande cron (tâche 3.4, CDC 4.9 : « la suspension est levée
    automatiquement après le nombre de matchs du club prévu »).

    Incrémente ``matches_served`` de chaque suspension active du club
    pour chaque ``Match`` écoulé (date passée dans le fuseau du club)
    postérieur au déclenchement, jamais deux fois pour le même match
    (idempotence via ``Suspension.credited_events`` -- ajout technique
    hors schéma, voir docstring du modèle). Aucune entrée de journal
    (pas d'acteur réel), même convention que
    ``apps.treasury.services.run_monthly_dues``/``process_licence_expirations``.
    """

    now = now or timezone.now()
    today = _club_today(club, now=now)
    credited_total = 0

    for suspension in Suspension.all_objects.filter(club=club, lifted_at__isnull=True).select_related("starts_event"):
        matches = list(
            Match.all_objects.filter(
                club=club, event__event_date__lt=today, event__event_date__gt=suspension.starts_event.event_date,
            )
            .exclude(event__in=suspension.credited_events.all())
            .order_by("event__event_date")
        )
        if not matches:
            continue
        changed = False
        for match in matches:
            if suspension.matches_served >= suspension.matches_total:
                break
            suspension.matches_served += 1
            suspension.credited_events.add(match.event)
            credited_total += 1
            changed = True
            if suspension.matches_served >= suspension.matches_total:
                suspension.lifted_at = now
        if changed:
            suspension.save(update_fields=["matches_served", "lifted_at"])
    return credited_total


# ---------------------------------------------------------------------------
# Évaluations des performances (CDC 4.10)
# ---------------------------------------------------------------------------


def _event_start_datetime(event: Event) -> datetime:
    club_settings = _club_settings(event.club)
    if event.kind == Event.Kind.SESSION:
        time_value = event.session.gathering_time
    else:
        time_value = event.match.kickoff_time
    return _combine_local(event.event_date, time_value, club_settings)


def evaluation_locks_at(event: Event) -> datetime:
    club_settings = _club_settings(event.club)
    return _event_start_datetime(event) + timedelta(hours=club_settings.evaluation_window_hours)


def is_evaluation_locked(event: Event, *, now: Optional[datetime] = None) -> bool:
    now = now or timezone.now()
    return now >= evaluation_locks_at(event)


_SCORE_FIELDS = ("technical_score", "physical_score", "tactical_score", "mental_score", "attitude_score")


def submit_evaluation(
    *, event: Event, membership: Membership, evaluator, overall_score: Decimal,
    comment: str = "", comment_visible_to_player: bool = False, **detail_scores: Any,
) -> Evaluation:
    """Une note par évaluateur (Coach, Président, VP), verrouillée 48 h
    après le début de l'événement (CDC 4.10 ; ``ClubSettings.evaluation_window_hours``).
    La moyenne retenue n'est jamais stockée (invariant J1) : voir
    :func:`get_average_evaluation`."""

    if is_evaluation_locked(event):
        raise SportValidationError("La fenêtre d'évaluation de 48 h est dépassée.")

    has_participation = Attendance.all_objects.filter(
        club=event.club_id, event=event, membership=membership,
        status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE_ABSENT],
    ).exists() or MatchComposition.all_objects.filter(club=event.club_id, match__event=event, membership=membership).exists()
    if not has_participation:
        raise SportValidationError("Seuls les joueurs présents à cet événement peuvent être évalués.")

    values = {"overall_score": overall_score, "comment": comment, "comment_visible_to_player": comment_visible_to_player}
    for field in _SCORE_FIELDS:
        values[field] = detail_scores.get(field)

    existing = Evaluation.all_objects.filter(club=event.club_id, event=event, membership=membership, evaluator=evaluator).first()
    if existing is not None:
        before = {"overall_score": str(existing.overall_score)}
        for field, value in values.items():
            setattr(existing, field, value)
        existing.save()
        evaluation = existing
        action_type = "sport.evaluation_updated"
    else:
        before = None
        evaluation = Evaluation(club=event.club, event=event, membership=membership, evaluator=evaluator, **values)
        evaluation.save()
        action_type = "sport.evaluation_created"

    log_action(actor=evaluator, club=event.club, action_type=action_type, obj=evaluation, before=before, after={"overall_score": str(overall_score)})
    return evaluation


def get_average_evaluation(event: Event, membership: Membership) -> Optional[Decimal]:
    from django.db.models import Avg

    result = Evaluation.all_objects.filter(club=event.club_id, event=event, membership=membership).aggregate(
        Avg("overall_score")
    )["overall_score__avg"]
    if result is None:
        return None
    return Decimal(str(result)).quantize(Decimal("0.1"))


# ---------------------------------------------------------------------------
# Plan tactique (CDC 4.11 ; 10.2 n° 16, n° 31, n° 32)
# ---------------------------------------------------------------------------


def create_tactical_plan(*, club, name: str, formation: str, squad_size: int, created_by, match: Optional[Match] = None) -> TacticalPlan:
    plan = TacticalPlan(club=club, name=name, formation=formation, squad_size=squad_size, match=match, created_by=created_by)
    plan.save()
    log_action(actor=created_by, club=club, action_type="sport.tactical_plan_created", obj=plan, after={"name": name, "formation": formation})
    return plan


def update_tactical_plan_settings(
    *, plan: TacticalPlan, name: str, formation: str, squad_size: int, updated_by, match: Optional[Match] = None
) -> TacticalPlan:
    """Modifie les paramètres d'un plan existant : nom, formation,
    effectif, match rattaché (sport-plan-tactique.md §4.3, « Mêmes champs
    que le §4.2, préremplis »). Un plan publié ne peut plus être modifié
    ici (même règle que :func:`place_on_plan`/:func:`add_annotation`,
    §4.8/§5.3) : il faut d'abord le dupliquer.

    **Repositionnement automatique des joueurs déjà placés** : le
    bandeau du §4.3 annonce qu'un changement de formation ou d'effectif
    « replace [les joueurs] sur les nouveaux emplacements, selon leur
    poste » et renvoie sur le banc ceux qui n'ont plus de place. Ce
    service ne déplace **aucun** emplacement existant : la géométrie des
    emplacements par formation (cercles en pointillés par poste, §5.1)
    n'existe que côté client (`PitchBoard`) -- aucune bibliothèque de
    coordonnées par formation n'est documentée côté serveur
    (`schema-donnees.md` §5.11 ne stocke que des coordonnées libres 0-100
    par emplacement, jamais un gabarit par formation). Les emplacements
    existants restent donc inchangés en base après ce changement ; c'est
    au client de renvoyer les nouveaux placements, chaque geste restant un
    écrit immédiat via :func:`place_on_plan`/:func:`remove_from_plan`
    (§5.2, comme pour toute autre modification du tableau noir). Point
    signalé au compte rendu de la tâche : à confirmer avec `ui-designer`/
    `frontend-dev`."""

    if plan.is_published:
        raise SportValidationError("Un plan publié ne peut plus être modifié : dupliquez-le d'abord.")

    if squad_size != 11 and formation != TacticalPlan.Formation.CUSTOM:
        # Même règle que ``TacticalPlan.clean()`` (invoqué par ``save()``
        # via ``TenantModel``), vérifiée ici en amont pour renvoyer une
        # erreur métier lisible (400) plutôt qu'une ``ValidationError``
        # Django non traduite par la vue (même limite, non corrigée ici,
        # que :func:`create_tactical_plan` -- signalée au compte rendu).
        raise SportValidationError(
            "À effectif réduit (7 ou 8 joueurs), seule la formation « Personnalisée » est "
            "disponible pour l'instant (bibliothèque à confirmer par le client)."
        )

    before = {
        "name": plan.name,
        "formation": plan.formation,
        "squad_size": plan.squad_size,
        "match_id": plan.match_id,
    }

    plan.name = name
    plan.formation = formation
    plan.squad_size = squad_size
    plan.match = match
    plan.save()

    log_action(
        actor=updated_by,
        club=plan.club,
        action_type="sport.tactical_plan_settings_updated",
        obj=plan,
        before=before,
        after={
            "name": name,
            "formation": formation,
            "squad_size": squad_size,
            "match_id": match.pk if match is not None else None,
        },
    )
    return plan


def place_on_plan(*, plan: TacticalPlan, membership: Membership, x_coord: Decimal, y_coord: Decimal, placed_by) -> TacticalPlanPlacement:
    """Place un joueur sur le tableau noir (CDC 4.11). Même contrôle
    d'éligibilité que la composition (schema §5.11, CLAUDE.md règle n° 5) :
    aucun geste, y compris manuel, ne permet de contourner ce refus
    (sport-plan-tactique.md §5.3)."""

    if plan.is_published:
        raise SportValidationError("Un plan publié ne peut plus être modifié : dupliquez-le d'abord.")

    playability = get_playability(membership)
    if not playability.eligible:
        raise PlayerNotEligibleError(playability.detail)

    existing = TacticalPlanPlacement.all_objects.filter(club=plan.club_id, plan=plan, membership=membership).first()
    if existing is not None:
        before = {"x": str(existing.x_coord), "y": str(existing.y_coord)}
        existing.x_coord, existing.y_coord = x_coord, y_coord
        existing.save()
        placement = existing
        action_type = "sport.tactical_plan_placement_moved"
    else:
        before = None
        placement = TacticalPlanPlacement(club=plan.club, plan=plan, membership=membership, x_coord=x_coord, y_coord=y_coord)
        placement.save()
        action_type = "sport.tactical_plan_placement_created"

    log_action(actor=placed_by, club=plan.club, action_type=action_type, obj=placement, before=before, after={"x": str(x_coord), "y": str(y_coord)})
    return placement


def remove_from_plan(*, placement: TacticalPlanPlacement, removed_by) -> None:
    log_action(
        actor=removed_by, club=placement.club, action_type="sport.tactical_plan_placement_removed", obj=placement,
        before={"membership": placement.membership_id},
    )
    placement.delete()


_UNSET = object()


def update_plan_placement_number_and_position(
    *, placement: TacticalPlanPlacement, updated_by, jersey_number=_UNSET, position=_UNSET
) -> tuple[TacticalPlanPlacement, Optional[str]]:
    """Modifie le numéro/poste depuis le plan (CDC 4.11) : répercuté sur
    la fiche joueur. Un champ non transmis reste inchangé. Le numéro de
    maillot est unique dans le club (CDC 4.1, tableau des champs) : un
    doublon est refusé (le 10.2 n° 94 parle d'un simple avertissement :
    contradiction signalée, position la plus restrictive appliquée)."""

    if placement.membership_id is None:
        raise SportValidationError("Cet emplacement n'a aucun joueur placé.")

    membership = placement.membership
    if jersey_number is _UNSET:
        jersey_number = placement.jersey_number_override if placement.jersey_number_override is not None else membership.jersey_number
    if position is _UNSET or position is None:
        position = placement.position_override or membership.position
    if jersey_number is not None:
        duplicate = (
            Membership.all_objects.filter(club=membership.club_id, status=Membership.Status.ACTIVE, jersey_number=jersey_number)
            .exclude(pk=membership.pk)
            .select_related("user")
            .first()
        )
        if duplicate is not None:
            raise SportValidationError(
                f"Le numéro {jersey_number} est déjà porté par {duplicate.user.first_name} {duplicate.user.last_name} : "
                "choisissez un autre numéro."
            )

    before = {"jersey_number": membership.jersey_number, "position": membership.position}
    placement.jersey_number_override = jersey_number
    placement.position_override = position
    placement.save()
    membership.jersey_number = jersey_number
    membership.position = position
    membership.save()
    log_action(
        actor=updated_by, club=membership.club, action_type="sport.tactical_plan_number_position_updated", obj=membership,
        before=before, after={"jersey_number": jersey_number, "position": position},
    )
    return placement, None


def add_annotation(
    *, plan: TacticalPlan, annotation_type: str, created_by, path_data: str = "", text: str = "",
    target_membership: Optional[Membership] = None, target_line: str = "",
) -> TacticalPlanAnnotation:
    if plan.is_published:
        raise SportValidationError("Un plan publié ne peut plus être modifié : dupliquez-le d'abord.")
    annotation = TacticalPlanAnnotation(
        club=plan.club, plan=plan, annotation_type=annotation_type, path_data=path_data, text=text,
        target_membership=target_membership, target_line=target_line, created_by=created_by,
    )
    annotation.save()
    log_action(actor=created_by, club=plan.club, action_type="sport.tactical_plan_annotation_added", obj=annotation, after={"annotation_type": annotation_type})
    return annotation


def delete_annotation(*, annotation: TacticalPlanAnnotation, deleted_by) -> None:
    log_action(actor=deleted_by, club=annotation.club, action_type="sport.tactical_plan_annotation_deleted", obj=annotation, before={"annotation_type": annotation.annotation_type})
    annotation.delete()


def duplicate_tactical_plan(*, plan: TacticalPlan, name: str, created_by, match: Optional[Match] = None) -> tuple[TacticalPlan, list]:
    """Duplique un plan (CDC 4.11) : les joueurs devenus non éligibles ne
    sont pas recopiés (sport-plan-tactique.md §4.7)."""

    new_plan = TacticalPlan(
        club=plan.club, name=name, formation=plan.formation, squad_size=plan.squad_size, match=match,
        duplicated_from=plan, created_by=created_by,
    )
    new_plan.save()

    skipped_memberships: list = []
    for placement in TacticalPlanPlacement.all_objects.filter(club=plan.club_id, plan=plan):
        if placement.membership_id is not None and not get_playability(placement.membership).eligible:
            skipped_memberships.append(placement.membership)
            continue
        TacticalPlanPlacement(
            club=new_plan.club, plan=new_plan, membership=placement.membership, x_coord=placement.x_coord,
            y_coord=placement.y_coord, jersey_number_override=placement.jersey_number_override,
            position_override=placement.position_override,
        ).save()

    skipped_ids = {m.pk for m in skipped_memberships}
    for annotation in TacticalPlanAnnotation.all_objects.filter(club=plan.club_id, plan=plan):
        if annotation.target_membership_id in skipped_ids:
            continue
        TacticalPlanAnnotation(
            club=new_plan.club, plan=new_plan, annotation_type=annotation.annotation_type, path_data=annotation.path_data,
            text=annotation.text, target_membership=annotation.target_membership, target_line=annotation.target_line,
            created_by=created_by,
        ).save()

    log_action(
        actor=created_by, club=plan.club, action_type="sport.tactical_plan_duplicated", obj=new_plan,
        after={"duplicated_from": plan.pk, "skipped_count": len(skipped_memberships)},
    )
    return new_plan, skipped_memberships


def _notify_plan_published(plan: TacticalPlan, placements) -> None:
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    for placement in placements:
        create_notification(
            recipient=placement.membership.user,
            event_type=Notification.EventType.COMPOSITION_OR_PLAN_PUBLISHED,
            message=f"Le plan « {plan.name} » a été publié. Vous êtes placé.",
            club=plan.club,
            target=plan,
        )


def publish_tactical_plan(*, plan: TacticalPlan, published_by) -> TacticalPlan:
    """Publication impossible tant qu'un joueur placé est devenu non
    éligible (position provisoire, sport-plan-tactique.md §4.8)."""

    placements = list(
        TacticalPlanPlacement.all_objects.filter(club=plan.club_id, plan=plan, membership__isnull=False).select_related(
            "membership"
        )
    )
    ineligible = [p.membership for p in placements if not get_playability(p.membership).eligible]
    if ineligible:
        raise SportValidationError("Remplacez d'abord les joueurs qui ne peuvent plus jouer avant de publier le plan.")

    plan.is_published = True
    plan.published_at = timezone.now()
    plan.save()
    log_action(actor=published_by, club=plan.club, action_type="sport.tactical_plan_published", obj=plan, after={"is_published": True})
    _notify_plan_published(plan, placements)
    return plan


def delete_tactical_plan(*, plan: TacticalPlan, deleted_by) -> None:
    log_action(actor=deleted_by, club=plan.club, action_type="sport.tactical_plan_deleted", obj=plan, before={"name": plan.name})
    plan.delete()
