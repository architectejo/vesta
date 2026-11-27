"""Serializers DRF de l'app sport (tache 3.6, suite des taches 3.2-3.4).

Aucun calcul metier ici (CLAUDE.md section 5) : chaque fonction ne fait
que mettre en forme ce que ``apps.sport.services`` a deja calcule --
notamment le motif de blocage d'un joueur (:func:`describe_reason_for_viewer`,
10.2 n16), jamais reconstruit ici (voir docstring de la tache).

Convention reprise de ``apps.treasury.serializers`` : des fonctions
``serialize_*`` pour la sortie (la plupart des objets combinent plusieurs
relations et des donnees calculees, peu adaptes a un simple
``ModelSerializer``), des classes ``rest_framework.serializers.Serializer``
pour valider la forme des entrees (les regles elles-memes restent dans
``apps.sport.services``, qui refait ses propres controles -- defense en
profondeur, meme principe que le reste du projet).
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import serializers

from apps.audit.services import GHOST_ACTOR_DISPLAY_NAME
from apps.clubs.models import Membership, MembershipRole
from apps.core.roles import get_active_roles
from apps.sport.permissions import MATCH_MANAGER_ROLES
from apps.sport import services
from apps.sport.models import (
    Attendance,
    Formation,
    Incident,
    Match,
    MatchComposition,
    Session,
    TacticalPlan,
    TacticalPlanAnnotation,
    TeamAssignment,
)

__all__ = [
    "SessionCreateSerializer",
    "SessionUpdateSerializer",
    "MatchCreateSerializer",
    "MatchUpdateSerializer",
    "AttendanceMarkSerializer",
    "AttendanceCorrectionSerializer",
    "AttendanceExcuseSerializer",
    "TeamAssignSerializer",
    "TeamFormationSetSerializer",
    "TeamPlayerPlacementSerializer",
    "UnlockSerializer",
    "MatchCompositionCreateSerializer",
    "ScoreSerializer",
    "GoalCreateSerializer",
    "IncidentCreateSerializer",
    "EvaluationCreateSerializer",
    "TacticalPlanCreateSerializer",
    "TacticalPlanSettingsSerializer",
    "TacticalPlanDuplicateSerializer",
    "PlacementCreateSerializer",
    "PlacementUpdateSerializer",
    "AnnotationCreateSerializer",
    "serialize_membership_brief",
    "serialize_reason",
    "serialize_event_common",
    "serialize_session_list_item",
    "serialize_session_detail",
    "serialize_match_list_item",
    "serialize_match_detail",
    "serialize_unassigned",
    "serialize_incident",
    "serialize_suspension",
    "serialize_evaluation",
    "serialize_tactical_plan_list_item",
    "serialize_tactical_plan_detail",
    "serialize_placement",
    "serialize_annotation",
    "serialize_next_event",
    "serialize_locker_room",
]


# ---------------------------------------------------------------------------
# Utilitaires communs (Ghost Mode CDC 5.4 ; photo publique CDC 6.7)
# ---------------------------------------------------------------------------


def _user_name(user) -> str:
    return f"{user.first_name} {user.last_name}".strip()


def _actor(user, *, viewer) -> dict | None:
    """Auteur d'une ecriture vu par ``viewer`` : un Superuser (jamais joueur,
    donc intervenu en Ghost Mode) apparait « Systeme Vesta » cote club
    (CDC 5.4 ; CLAUDE.md Ghost Mode ; meme convention que
    ``apps.treasury.serializers._actor``). L'identite reelle reste dans le
    journal d'activite, jamais ici."""

    if user is None:
        return None
    if getattr(user, "is_superuser", False) and not getattr(viewer, "is_superuser", False):
        return {"id": None, "name": GHOST_ACTOR_DISPLAY_NAME}
    return {"id": user.pk, "name": _user_name(user)}


def _photo_url(user, *, request):
    if request is None or not user.photo:
        return None
    return request.build_absolute_uri(user.photo.url)


def serialize_membership_brief(membership, *, request=None) -> dict:
    """Identite minimale d'un joueur (jamais de donnee financiere ni
    medicale ici -- reprise volontairement etroite de
    ``apps.clubs.serializers.PlayerPublicCardSerializer``)."""

    user = membership.user
    return {
        "membership_id": membership.pk,
        "name": _user_name(user),
        "jersey_number": membership.jersey_number,
        "position": membership.position,
        "position_label": membership.get_position_display() if membership.position else "",
        "photo": _photo_url(user, request=request),
    }


def serialize_reason(membership, *, viewer, playability=None, viewer_roles=None) -> dict:
    """Motif de blocage filtre par role (10.2 n16, matrice 2.4) : point de
    filtrage UNIQUE deja applique par
    ``apps.sport.services.describe_reason_for_viewer`` -- cette fonction ne
    fait que serialiser son resultat, jamais le reconstruire (consigne
    explicite de la tache)."""

    playability = playability if playability is not None else services.get_playability(membership)
    return {
        "eligible": playability.eligible,
        # Le code de motif suit la même règle que le texte : jamais exposé
        # à qui ne voit que « Indisponible » (10.2 n° 16).
        "reason_code": (
            playability.reason_code
            if services.reason_visible_to_viewer(
                playability, viewer=viewer, membership=membership, viewer_roles=viewer_roles
            )
            else ("unavailable" if not playability.eligible else "")
        ),
        "reason": services.describe_reason_for_viewer(
            playability, viewer=viewer, membership=membership, viewer_roles=viewer_roles
        ),
    }


def serialize_eligibility_list(memberships, *, viewer, club) -> list[dict]:
    """Éligibilité groupée pour la modale « Composer l'équipe »
    (sport-feuille-de-match.md §4.1, §4.1 bis). Calcul groupé
    (:func:`apps.sport.services.get_playabilities`) et rôles du lecteur
    résolus UNE fois ; le motif reste filtré par
    :func:`apps.sport.services.describe_reason_for_viewer` (10.2 n° 16)."""

    playabilities = services.get_playabilities(club, memberships)
    roles = get_active_roles(viewer, club=club)
    return [
        {
            "membership_id": membership.pk,
            **serialize_reason(
                membership, viewer=viewer, playability=playabilities[membership.pk], viewer_roles=roles
            ),
        }
        for membership in memberships
    ]


# ---------------------------------------------------------------------------
# Evenement commun (verrouillage a minuit, CDC 4.7)
# ---------------------------------------------------------------------------


def serialize_event_common(event, *, viewer) -> dict:
    return {
        "id": event.pk,
        "kind": event.kind,
        "event_date": event.event_date,
        "season_id": event.season_id,
        "is_locked": services.is_event_locked(event),
        "unlocked_by": _actor(event.unlocked_by, viewer=viewer) if event.unlocked_by_id else None,
        "unlocked_at": event.unlocked_at,
        "unlock_reason": event.unlock_reason,
    }


class UnlockSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False)


# ---------------------------------------------------------------------------
# Seances et pointage (CDC 4.7)
# ---------------------------------------------------------------------------


class SessionCreateSerializer(serializers.Serializer):
    season_id = serializers.IntegerField(required=False, allow_null=True)
    event_date = serializers.DateField()
    gathering_time = serializers.TimeField()
    late_arrival_cutoff = serializers.TimeField()
    location = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    team_a_color = serializers.CharField(max_length=7, required=False, allow_null=True)
    team_b_color = serializers.CharField(max_length=7, required=False, allow_null=True)
    instructions = serializers.CharField(required=False, allow_blank=True, default="")


class SessionUpdateSerializer(serializers.Serializer):
    """« Modifier la séance » (sport-seance.md §4.2) : mêmes champs que la
    création, sans ``season_id`` (la saison de l'événement ne change pas
    depuis cette modale, qui ne la propose pas)."""

    event_date = serializers.DateField()
    gathering_time = serializers.TimeField()
    late_arrival_cutoff = serializers.TimeField()
    location = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    team_a_color = serializers.CharField(max_length=7, required=False, allow_null=True)
    team_b_color = serializers.CharField(max_length=7, required=False, allow_null=True)
    instructions = serializers.CharField(required=False, allow_blank=True, default="")


class AttendanceMarkSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    arrived_at = serializers.DateTimeField(required=False)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    client_recorded_at = serializers.DateTimeField(required=False, allow_null=True)


class BulkAttendanceItemSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    client_recorded_at = serializers.DateTimeField(required=False, allow_null=True)
    selection_rank = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class BulkAttendanceSerializer(serializers.Serializer):
    """Pointage groupé (sport-pointage-selection-multiple.md §7). Les
    limites métier (taille du lot, rôle, heure) sont contrôlées par le
    service, pour que la règle n'existe qu'à un endroit."""

    action = serializers.ChoiceField(choices=["arrive", "excuse"])
    arrived_at = serializers.DateTimeField(required=False, allow_null=True)
    reason_code = serializers.ChoiceField(choices=["injured", "travel", "other"], required=False)
    reason_detail = serializers.CharField(required=False, allow_blank=True, default="")
    items = BulkAttendanceItemSerializer(many=True, allow_empty=True)

    def validate(self, attrs):
        if attrs["action"] == "excuse" and not attrs.get("reason_code"):
            raise serializers.ValidationError({"reason_code": "Choisissez un motif."})
        return attrs


def serialize_bulk_attendance_result(result: dict, *, viewer, request=None) -> dict:
    return {
        "batch_id": result["batch_id"],
        "results": [
            {
                "membership_id": r["membership_id"],
                "outcome": r["outcome"],
                "message": r["message"],
                "attendance": serialize_attendance(r["attendance"], viewer=viewer, request=request)
                if r["attendance"] is not None
                else None,
            }
            for r in result["results"]
        ],
        "counts": result["counts"],
    }


def serialize_attendance_capabilities(event, *, viewer) -> dict:
    """Droits de pointage groupé du lecteur (l'interface ne déduit jamais
    un droit d'un rôle). Faux dès que l'événement est verrouillé."""

    from apps.sport.permissions import ATTENDANCE_RECORDER_ROLES, ATTENDANCE_TIME_CORRECTOR_ROLES

    unlocked = getattr(viewer, "is_superuser", False) or not services.is_event_locked(event)
    roles = get_active_roles(viewer, club=event.club)
    is_super = bool(getattr(viewer, "is_superuser", False))
    return {
        "can_bulk_mark": bool(unlocked and (is_super or roles & ATTENDANCE_RECORDER_ROLES)),
        "can_bulk_excuse": bool(unlocked and (is_super or roles & ATTENDANCE_TIME_CORRECTOR_ROLES)),
        "can_set_arrival_time": bool(unlocked and (is_super or roles & ATTENDANCE_TIME_CORRECTOR_ROLES)),
    }


class AttendanceCorrectionSerializer(serializers.Serializer):
    arrived_at = serializers.DateTimeField()


class AttendanceExcuseSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    reason = serializers.CharField(allow_blank=True, default="")


class TeamAssignSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    team = serializers.ChoiceField(choices=TeamAssignment.Team.choices)


class TeamFormationSetSerializer(serializers.Serializer):
    """Choix de la formation d'une équipe de séance (extension client du
    30/09/2026, voir :func:`apps.sport.services.set_team_formation`)."""

    team = serializers.ChoiceField(choices=TeamAssignment.Team.choices)
    formation = serializers.ChoiceField(choices=Formation.choices)


class TeamPlayerPlacementSerializer(serializers.Serializer):
    """Place, déplace ou renvoie au banc un joueur déjà réparti en équipe
    A/B (extension client du 30/09/2026, voir
    :func:`apps.sport.services.place_team_player`). ``x_coord``/``y_coord``
    omis ou nuls tous les deux renvoient le joueur au banc ; fournir un
    seul des deux est refusé (cohérence avec la contrainte du modèle)."""

    team = serializers.ChoiceField(choices=TeamAssignment.Team.choices)
    membership_id = serializers.IntegerField()
    x_coord = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, allow_null=True, default=None
    )
    y_coord = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, allow_null=True, default=None
    )

    def validate(self, attrs):
        x_coord, y_coord = attrs.get("x_coord"), attrs.get("y_coord")
        if (x_coord is None) != (y_coord is None):
            raise serializers.ValidationError(
                "Fournissez les deux coordonnées (x et y), ou aucune des deux pour renvoyer le joueur au banc."
            )
        return attrs


def serialize_attendance(attendance: Attendance, *, viewer, request=None) -> dict:
    return {
        "id": attendance.pk,
        "membership_id": attendance.membership_id,
        "player": serialize_membership_brief(attendance.membership, request=request),
        "status": attendance.status,
        "status_label": attendance.get_status_display(),
        "arrived_at": attendance.arrived_at,
        "excused_reason": attendance.excused_reason,
        "marked_by": _actor(attendance.marked_by, viewer=viewer),
        "client_uuid": str(attendance.client_uuid) if attendance.client_uuid else None,
    }


def serialize_team_assignment(assignment: TeamAssignment, *, request=None) -> dict:
    return {
        "id": assignment.pk,
        "membership_id": assignment.membership_id,
        "player": serialize_membership_brief(assignment.membership, request=request),
        "team": assignment.team,
        "arrival_order": assignment.arrival_order,
        "is_on_field": assignment.is_on_field,
        "x_coord": str(assignment.x_coord) if assignment.x_coord is not None else None,
        "y_coord": str(assignment.y_coord) if assignment.y_coord is not None else None,
    }


def serialize_unassigned(groups: services.UnassignedGroups, *, viewer, request=None) -> dict:
    """Zone « Non repartis » (10.2 n29, n38) : deux sous-zones distinctes,
    jamais fusionnees (sport-seance.md §3.2)."""

    return {
        "to_place_manually": [
            {
                **serialize_membership_brief(membership, request=request),
                "attendance_status": attendance.status,
            }
            for membership, attendance in groups.to_place_manually
        ],
        "cannot_play": [
            {
                **serialize_membership_brief(membership, request=request),
                **serialize_reason(membership, viewer=viewer, playability=playability),
            }
            for membership, playability in groups.cannot_play
        ],
    }


def _attendance_counts(event, *, club) -> dict:
    active_total = Membership.objects.filter(status=Membership.Status.ACTIVE).count()
    present = Attendance.objects.filter(event=event, status=Attendance.Status.PRESENT).count()
    late = Attendance.objects.filter(event=event, status=Attendance.Status.LATE_ABSENT).count()
    excused = Attendance.objects.filter(event=event, status=Attendance.Status.EXCUSED_ABSENT).count()
    return {
        "present": present,
        "late": late,
        "excused": excused,
        "not_marked": max(active_total - present - late - excused, 0),
    }


def serialize_session_list_item(session: Session) -> dict:
    event = session.event
    return {
        "id": event.pk,
        "event_date": event.event_date,
        "gathering_time": session.gathering_time,
        "late_arrival_cutoff": session.late_arrival_cutoff,
        "location": session.location,
        "is_locked": services.is_event_locked(event),
    }


def serialize_session_detail(session: Session, *, viewer, request=None) -> dict:
    event = session.event
    club_settings = event.club.settings
    unassigned = services.get_unassigned_players(session, actor=viewer)
    attendances = Attendance.objects.filter(event=event).select_related("membership__user", "marked_by")
    assignments = TeamAssignment.objects.filter(session=session).select_related("membership__user").order_by(
        "arrival_order"
    )
    return {
        **serialize_event_common(event, viewer=viewer),
        "gathering_time": session.gathering_time,
        "late_arrival_cutoff": session.late_arrival_cutoff,
        "location": session.location,
        "team_a_color": session.team_a_color,
        "team_b_color": session.team_b_color,
        "team_a_formation": session.team_a_formation,
        "team_b_formation": session.team_b_formation,
        "instructions": session.instructions,
        "late_arrival_counts_absent": club_settings.late_arrival_counts_absent,
        "counts": _attendance_counts(event, club=session.club),
        "capabilities": serialize_attendance_capabilities(event, viewer=viewer),
        "attendances": [serialize_attendance(item, viewer=viewer, request=request) for item in attendances],
        "team_a": [
            serialize_team_assignment(item, request=request)
            for item in assignments
            if item.team == TeamAssignment.Team.A
        ],
        "team_b": [
            serialize_team_assignment(item, request=request)
            for item in assignments
            if item.team == TeamAssignment.Team.B
        ],
        "unassigned": serialize_unassigned(unassigned, viewer=viewer, request=request),
    }


# ---------------------------------------------------------------------------
# Matchs et composition (CDC 4.8)
# ---------------------------------------------------------------------------


class MatchCreateSerializer(serializers.Serializer):
    season_id = serializers.IntegerField(required=False, allow_null=True)
    event_date = serializers.DateField()
    kickoff_time = serializers.TimeField()
    match_type = serializers.ChoiceField(choices=Match.MatchType.choices)
    venue = serializers.ChoiceField(choices=Match.Venue.choices)
    location = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    opponent_club_id = serializers.IntegerField(required=False, allow_null=True)
    opponent_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    challenge_status = serializers.ChoiceField(choices=Match.ChallengeStatus.choices, required=False)
    challenge_to_club_id = serializers.IntegerField(required=False, allow_null=True)


class MatchUpdateSerializer(serializers.Serializer):
    """« Modifier le match » (sport-feuille-de-match.md §4.7) : champs de
    « Créer un match », sans le défi (ni ``challenge_status`` ni
    ``challenge_to_club_id`` : un défi ne se modifie pas depuis cette
    modale). L'adversaire reste transmis ; le service l'ignore lui-même
    si le défi est déjà accepté (§4.7 : « adversaire non modifiable »)."""

    event_date = serializers.DateField()
    kickoff_time = serializers.TimeField()
    match_type = serializers.ChoiceField(choices=Match.MatchType.choices)
    venue = serializers.ChoiceField(choices=Match.Venue.choices)
    location = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    opponent_club_id = serializers.IntegerField(required=False, allow_null=True)
    opponent_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    # Accepté uniquement pour être contrôlé (jamais son propre club) ; un défi
    # ne se modifie pas depuis cette modale.
    challenge_to_club_id = serializers.IntegerField(required=False, allow_null=True)


class MatchCompositionCreateSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=MatchComposition.Role.choices)
    position = serializers.ChoiceField(choices=Membership.Position.choices)
    jersey_number = serializers.IntegerField(min_value=1, max_value=99)


class ScoreSerializer(serializers.Serializer):
    score_home = serializers.IntegerField(min_value=0, max_value=99)
    score_away = serializers.IntegerField(min_value=0, max_value=99)


class GoalCreateSerializer(serializers.Serializer):
    scorer_membership_id = serializers.IntegerField(required=False, allow_null=True)
    assist_membership_id = serializers.IntegerField(required=False, allow_null=True)
    minute = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=130)


def _opponent_name(match: Match) -> str:
    return match.opponent_club.name if match.opponent_club_id else match.opponent_name


def serialize_composition(composition: MatchComposition, *, viewer, request=None) -> dict:
    playability = services.get_playability(composition.membership)
    data = {
        "id": composition.pk,
        "membership_id": composition.membership_id,
        "player": serialize_membership_brief(composition.membership, request=request),
        "role": composition.role,
        "role_label": composition.get_role_display(),
        "position": composition.position,
        "position_label": composition.get_position_display(),
        "jersey_number": composition.jersey_number,
    }
    if not playability.eligible:
        data["no_longer_eligible"] = serialize_reason(composition.membership, viewer=viewer, playability=playability)
    else:
        data["no_longer_eligible"] = None
    return data


def serialize_goal(goal, *, request=None) -> dict:
    return {
        "id": goal.pk,
        "scorer": (
            serialize_membership_brief(goal.scorer_membership, request=request) if goal.scorer_membership_id else None
        ),
        "assist": (
            serialize_membership_brief(goal.assist_membership, request=request) if goal.assist_membership_id else None
        ),
        "minute": goal.minute,
        "updated_at": goal.updated_at,
    }


def serialize_match_sheet(sheet) -> dict | None:
    if sheet is None:
        return None
    return {
        "score_home": sheet.score_home,
        "score_away": sheet.score_away,
        "filled_at": sheet.filled_at,
        "goals": [serialize_goal(goal) for goal in sheet.goals.all().order_by("minute", "pk")],
    }


def serialize_match_list_item(match: Match) -> dict:
    event = match.event
    return {
        "id": event.pk,
        "event_date": event.event_date,
        "kickoff_time": match.kickoff_time,
        "opponent": _opponent_name(match),
        "match_type": match.match_type,
        "venue": match.venue,
        "is_composition_published": match.is_composition_published,
        "is_locked": services.is_event_locked(event),
    }


def serialize_match_detail(match: Match, *, viewer, request=None) -> dict:
    event = match.event
    compositions = MatchComposition.objects.filter(match=match).select_related("membership__user").order_by(
        "role", "jersey_number"
    )
    sheet = getattr(match, "sheet", None)
    # Pointage simple du match (sport-feuille-de-match.md §3 point 3, §7
    # point ouvert 2 : sans répartition A/B -- voir
    # ``apps.sport.services.mark_match_arrival``), même forme que le
    # pointage d'une séance (``serialize_session_detail``).
    attendances = Attendance.objects.filter(event=event).select_related("membership__user", "marked_by")
    # Brouillon de composition : visible seulement par le staff (CDC 4.8 ;
    # sport-feuille-de-match.md §3 point 2). Position prudente : Coach
    # (et son assistant) + Superuser ; les autres rôles attendent la publication.
    can_see_composition = match.is_composition_published or bool(
        getattr(viewer, "is_superuser", False)
        or (get_active_roles(viewer, club=match.club) & MATCH_MANAGER_ROLES)
    )
    if not can_see_composition:
        compositions = compositions.none()
    return {
        **serialize_event_common(event, viewer=viewer),
        "kickoff_time": match.kickoff_time,
        "opponent": _opponent_name(match),
        "match_type": match.match_type,
        "venue": match.venue,
        "location": match.location,
        "challenge_status": match.challenge_status,
        "capabilities": serialize_attendance_capabilities(event, viewer=viewer),
        "is_composition_published": match.is_composition_published,
        "composition_published_at": match.composition_published_at,
        "result_published": match.result_post_id is not None,
        "attendances": [serialize_attendance(item, viewer=viewer, request=request) for item in attendances],
        "attendance_counts": _attendance_counts(event, club=match.club),
        "starters": [
            serialize_composition(item, viewer=viewer, request=request)
            for item in compositions
            if item.role == MatchComposition.Role.STARTER
        ],
        "substitutes": [
            serialize_composition(item, viewer=viewer, request=request)
            for item in compositions
            if item.role == MatchComposition.Role.SUBSTITUTE
        ],
        "sheet": serialize_match_sheet(sheet),
    }


# ---------------------------------------------------------------------------
# Discipline (CDC 4.9)
# ---------------------------------------------------------------------------


class IncidentCreateSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    incident_type = serializers.ChoiceField(choices=Incident.IncidentType.choices)
    cause = serializers.ChoiceField(choices=Incident.Cause.choices)
    cause_detail = serializers.CharField(required=False, allow_blank=True, default="")
    issued_by = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    minute = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=130)


def serialize_incident(incident: Incident, *, viewer, request=None) -> dict:
    return {
        "id": incident.pk,
        "event_id": incident.event_id,
        "player": serialize_membership_brief(incident.membership, request=request),
        "incident_type": incident.incident_type,
        "incident_type_label": incident.get_incident_type_display(),
        "cause": incident.cause,
        "cause_label": incident.get_cause_display(),
        "cause_detail": incident.cause_detail,
        "issued_by": incident.issued_by,
        "minute": incident.minute,
        "recorded_by": _actor(incident.recorded_by, viewer=viewer),
        "recorded_at": incident.recorded_at,
    }


def serialize_suspension(suspension) -> dict:
    return {
        "id": suspension.pk,
        "membership_id": suspension.membership_id,
        "reason": suspension.reason,
        "reason_label": suspension.get_reason_display(),
        "matches_total": suspension.matches_total,
        "matches_served": suspension.matches_served,
        "matches_remaining": max(suspension.matches_total - suspension.matches_served, 0),
        "is_active": suspension.is_active,
        "lifted_at": suspension.lifted_at,
        "created_at": suspension.created_at,
    }


# ---------------------------------------------------------------------------
# Evaluations (CDC 4.10)
# ---------------------------------------------------------------------------


class EvaluationCreateSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    overall_score = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=10)
    technical_score = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=10, required=False, allow_null=True)
    physical_score = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=10, required=False, allow_null=True)
    tactical_score = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=10, required=False, allow_null=True)
    mental_score = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=10, required=False, allow_null=True)
    attitude_score = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=10, required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    comment_visible_to_player = serializers.BooleanField(required=False, default=False)


def serialize_evaluation(evaluation, *, request=None, as_player: bool = False) -> dict:
    """``as_player`` : le joueur évalué voit ses notes, mais le commentaire
    seulement si l'évaluateur l'a rendu visible, et jamais l'identité de l'évaluateur (CDC 4.10)."""

    return {
        "id": evaluation.pk,
        "membership_id": evaluation.membership_id,
        "player": serialize_membership_brief(evaluation.membership, request=request),
        "evaluator_id": None if as_player else evaluation.evaluator_id,
        "overall_score": str(evaluation.overall_score),
        "technical_score": str(evaluation.technical_score) if evaluation.technical_score is not None else None,
        "physical_score": str(evaluation.physical_score) if evaluation.physical_score is not None else None,
        "tactical_score": str(evaluation.tactical_score) if evaluation.tactical_score is not None else None,
        "mental_score": str(evaluation.mental_score) if evaluation.mental_score is not None else None,
        "attitude_score": str(evaluation.attitude_score) if evaluation.attitude_score is not None else None,
        "comment": evaluation.comment if (not as_player or evaluation.comment_visible_to_player) else "",
        "comment_visible_to_player": evaluation.comment_visible_to_player,
        "created_at": evaluation.created_at,
    }


# ---------------------------------------------------------------------------
# Plan tactique (CDC 4.11)
# ---------------------------------------------------------------------------


class TacticalPlanCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    formation = serializers.ChoiceField(choices=TacticalPlan.Formation.choices)
    squad_size = serializers.ChoiceField(choices=[size for size, _ in TacticalPlan.SQUAD_SIZE_CHOICES])
    match_id = serializers.IntegerField(required=False, allow_null=True)


class TacticalPlanSettingsSerializer(serializers.Serializer):
    """« Paramètres du plan » (sport-plan-tactique.md §4.3) : mêmes champs
    que la création, préremplis."""

    name = serializers.CharField(max_length=120)
    formation = serializers.ChoiceField(choices=TacticalPlan.Formation.choices)
    squad_size = serializers.ChoiceField(choices=[size for size, _ in TacticalPlan.SQUAD_SIZE_CHOICES])
    match_id = serializers.IntegerField(required=False, allow_null=True)


class TacticalPlanDuplicateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    match_id = serializers.IntegerField(required=False, allow_null=True)


class PlacementCreateSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    x_coord = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    y_coord = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)


class PlacementUpdateSerializer(serializers.Serializer):
    jersey_number = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=99)
    position = serializers.ChoiceField(choices=Membership.Position.choices, required=False, allow_blank=True)


class AnnotationCreateSerializer(serializers.Serializer):
    annotation_type = serializers.ChoiceField(choices=TacticalPlanAnnotation.AnnotationType.choices)
    path_data = serializers.CharField(required=False, allow_blank=True, default="")
    text = serializers.CharField(required=False, allow_blank=True, default="")
    target_membership_id = serializers.IntegerField(required=False, allow_null=True)
    target_line = serializers.ChoiceField(
        choices=TacticalPlanAnnotation.TargetLine.choices, required=False, allow_blank=True, default=""
    )


def serialize_placement(placement, *, viewer, request=None) -> dict:
    data = {
        "id": placement.pk,
        "membership_id": placement.membership_id,
        "player": serialize_membership_brief(placement.membership, request=request) if placement.membership_id else None,
        "x_coord": str(placement.x_coord),
        "y_coord": str(placement.y_coord),
        "jersey_number_override": placement.jersey_number_override,
        "position_override": placement.position_override,
    }
    if placement.membership_id:
        playability = services.get_playability(placement.membership)
        data["no_longer_eligible"] = None if playability.eligible else serialize_reason(
            placement.membership, viewer=viewer, playability=playability
        )
    else:
        data["no_longer_eligible"] = None
    return data


def serialize_annotation(annotation) -> dict:
    return {
        "id": annotation.pk,
        "annotation_type": annotation.annotation_type,
        "path_data": annotation.path_data,
        "text": annotation.text,
        "target_membership_id": annotation.target_membership_id,
        "target_line": annotation.target_line,
    }


def serialize_tactical_plan_list_item(plan: TacticalPlan) -> dict:
    return {
        "id": plan.pk,
        "name": plan.name,
        "formation": plan.formation,
        "squad_size": plan.squad_size,
        "match_id": plan.match_id,
        "is_published": plan.is_published,
        "published_at": plan.published_at,
        "updated_at": plan.updated_at,
    }


def serialize_tactical_plan_detail(plan: TacticalPlan, *, viewer, request=None) -> dict:
    placements = plan.placements.select_related("membership__user")
    annotations = plan.annotations.all()
    return {
        **serialize_tactical_plan_list_item(plan),
        "created_at": plan.created_at,
        "placements": [serialize_placement(item, viewer=viewer, request=request) for item in placements],
        "annotations": [serialize_annotation(item) for item in annotations],
    }


# ---------------------------------------------------------------------------
# Vestiaire du jour (lecture seule derivee, sport-vestiaire.md)
# ---------------------------------------------------------------------------


def serialize_next_event(candidate) -> dict:
    """Précision « Prochain rendez-vous » de l'état vide du vestiaire
    (sport-vestiaire.md §6 ; club-accueil.md §4 point 5), calculée par
    :func:`apps.sport.services.get_next_upcoming_event`. Forme
    volontairement minimale : type, date et heure (rassemblement pour une
    séance, coup d'envoi pour un match), plus le lieu et l'adversaire
    déjà publics sur le calendrier des séances/matchs -- jamais de
    pointage, de composition ni de liste de joueurs ici (aucune
    confidentialité supplémentaire exposée par rapport à ce que
    l'évènement du jour révèle déjà normalement)."""

    event = candidate.event
    if isinstance(candidate, Session):
        return {
            "type": "session",
            "id": event.pk,
            "event_date": event.event_date,
            "gathering_time": candidate.gathering_time,
            "location": candidate.location,
        }
    return {
        "type": "match",
        "id": event.pk,
        "event_date": event.event_date,
        "kickoff_time": candidate.kickoff_time,
        "opponent": _opponent_name(candidate),
        "location": candidate.location,
    }


def serialize_locker_room(*, club, session=None, match=None, viewer, viewer_membership, request=None) -> dict:
    """Agrege l'evenement du jour (seance et/ou match), le pointage et la
    repartition A/B deja calcules par les services -- vue de consultation
    pure (aucune ecriture, sport-vestiaire.md §1). Ne recalcule aucune
    regle d'eligibilite : ne fait que reutiliser
    ``services.get_playability``/``describe_reason_for_viewer``.

    ``club`` sert uniquement à calculer ``next_event`` quand l'évènement
    du jour est vide (voir ci-dessous) -- jamais utilisé pour filtrer
    ``session``/``match``, déjà résolus par l'appelant (CLAUDE.md règle
    n° 9 : le club actif ne se redéduit jamais ici)."""

    data: dict = {"session": None, "match": None, "next_event": None}
    if session is not None:
        data["session"] = serialize_session_detail(session, viewer=viewer, request=request)
    if match is not None:
        data["match"] = serialize_match_detail(match, viewer=viewer, request=request)

    if session is None and match is None:
        # Seul cas où l'on alourdit le payload (demande explicite de la
        # tâche) : « aucun événement aujourd'hui » est la situation
        # normale la plupart des jours pour un club qui ne s'entraîne pas
        # tous les jours (sport-vestiaire.md §6).
        next_candidate = services.get_next_upcoming_event(club)
        if next_candidate is not None:
            data["next_event"] = serialize_next_event(next_candidate)

    my_situation = None
    if viewer_membership is not None:
        event = session.event if session is not None else (match.event if match is not None else None)
        if event is not None:
            attendance = Attendance.objects.filter(event=event, membership=viewer_membership).first()
            assignment = None
            if session is not None:
                assignment = TeamAssignment.objects.filter(session=session, membership=viewer_membership).first()
            playability = services.get_playability(viewer_membership)
            my_situation = {
                "attendance": serialize_attendance(attendance, viewer=viewer, request=request) if attendance else None,
                "team": assignment.team if assignment is not None else None,
                "eligible": playability.eligible,
                # Le joueur voit toujours son propre motif complet (matrice 2.4,
                # colonne « P » -- ce sont ses propres donnees) : jamais filtre
                # par role ici, a la difference de ``serialize_reason``.
                "reason": playability.detail if not playability.eligible else "",
                "reason_code": playability.reason_code,
            }
    data["my_situation"] = my_situation
    return data
