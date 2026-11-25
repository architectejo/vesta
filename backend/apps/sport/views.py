"""Vues DRF de l'app sport (tache 3.6, suite des taches 3.2-3.4).

Chaque vue orchestre uniquement : permission -> service -> serializer
(CLAUDE.md section 5). Aucune regle metier ici : l'eligibilite
(dette/suspension/inaptitude/attente d'adhesion), le verrouillage a
minuit, les suspensions automatiques et le motif filtre par role sont
deja calcules par ``apps.sport.services`` -- cette couche ne fait que
recuperer les objets (managers tenant-aware, CLAUDE.md regle n8),
verifier le role (``apps.sport.permissions``, deja pose par la tache
3.1/3.2) et serialiser (``apps.sport.serializers``).

Aucune action sportive n'exige de code PIN (CLAUDE.md regle n7 : la
liste des actions sensibles -- validation de paiement/depense,
derogation, signature parrain, signature PV, annulation -- ne couvre
aucune action de ce module ; verifie contre les 4 specs d'ecran
(sport-seance.md, sport-feuille-de-match.md, sport-plan-tactique.md,
sport-vestiaire.md), aucune n'en mentionne un).
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.models import COACHING_STAFF_ROLES, Membership, MembershipRole, Season
from apps.clubs.permissions import IsActiveClubMember, IsClubCoach
from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence, IsSuperuser
from apps.core.roles import has_any_role
from apps.core.services import resolve_active_membership
from apps.core.tenant import NoActiveClubError, get_active_club
from apps.sport import services
from apps.sport import serializers as serializers_mod
from apps.sport.models import (
    Attendance,
    Evaluation,
    Event,
    Incident,
    Match,
    MatchComposition,
    MatchGoal,
    Session,
    Suspension,
    TacticalPlan,
    TacticalPlanAnnotation,
    TacticalPlanPlacement,
)
from apps.sport.permissions import (
    CanAssignTeams,
    CanCorrectAttendanceTime,
    CanEditTacticalPlan,
    CanEvaluate,
    CanManageMatch,
    CanRecordAttendance,
    CanRecordIncident,
    EVALUATOR_ROLES,
    INCIDENT_FULL_VISIBILITY_ROLES,
)

_GATE = [IsAuthenticated, HasCompletedPasswordSetup, HasAcceptedLatestTerms, HasUsableLicence]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

_SESSION_NOT_FOUND = "Cette séance n'existe pas dans ce club."
_MATCH_NOT_FOUND = "Ce match n'existe pas dans ce club."
_EVENT_NOT_FOUND = "Cet événement n'existe pas dans ce club."
_MEMBER_NOT_FOUND = "Ce joueur n'existe pas dans ce club."
_ATTENDANCE_NOT_FOUND = "Ce pointage n'existe pas dans ce club."
_GOAL_NOT_FOUND = "Ce but n'existe pas dans ce club."
_PLAN_NOT_FOUND = "Ce plan tactique n'existe pas dans ce club."
_PLACEMENT_NOT_FOUND = "Cet emplacement n'existe pas dans ce club."
_ANNOTATION_NOT_FOUND = "Cette annotation n'existe pas dans ce club."
_SEASON_NOT_FOUND = "Saison introuvable dans ce club."


def _not_found(message):
    return Response({"detail": message}, status=status.HTTP_404_NOT_FOUND)


def _sport_error(exc: services.SportError):
    """Traduit une erreur metier de ``apps.sport.services`` en reponse HTTP
    en francais. Le texte n'est jamais reconstruit : ``str(exc)`` est deja
    le motif filtre par role quand il s'agit d'une eligibilite
    (:class:`~apps.sport.services.PlayerNotEligibleError`)."""

    if isinstance(exc, services.PlayerNotEligibleError):
        return Response({"detail": str(exc), "code": "player_not_eligible"}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, services.EventLockedError):
        return Response({"detail": str(exc), "code": "event_locked"}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, services.SportPermissionError):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _paginate(request, queryset):
    """Liste « N derniers + Voir plus » (CDC 3.3) : ``limit``/``offset``,
    meme convention que ``apps.treasury.views._paginate``."""

    try:
        limit = int(request.query_params.get("limit", DEFAULT_PAGE_SIZE))
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError):
        return None, None, None
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    count = queryset.count()
    items = list(queryset[offset : offset + limit])
    next_offset = offset + limit if offset + limit < count else None
    return items, count, next_offset


def _membership_or_404(membership_id):
    try:
        return Membership.objects.get(pk=membership_id), None
    except Membership.DoesNotExist:
        return None, _not_found(_MEMBER_NOT_FOUND)


def _resolve_season(data):
    """Saison d'un evenement cree : ``season_id`` explicite, sinon la
    saison courante du club (``Season.is_current``), sinon la plus
    recente. Decision technique (non documentee par le CDC/10.2, hors
    perimetre des specs d'ecran) : signalee au compte rendu."""

    season_id = data.get("season_id")
    if season_id is not None:
        try:
            return Season.objects.get(pk=season_id), None
        except Season.DoesNotExist:
            return None, _not_found(_SEASON_NOT_FOUND)
    season = Season.objects.filter(is_current=True).order_by("-start_date").first()
    if season is None:
        season = Season.objects.order_by("-start_date").first()
    if season is None:
        return None, Response(
            {"detail": "Aucune saison n'est configurée pour ce club."}, status=status.HTTP_400_BAD_REQUEST
        )
    return season, None


# ---------------------------------------------------------------------------
# Evenements (verrouillage a minuit, CDC 4.7)
# ---------------------------------------------------------------------------


class EventUnlockView(APIView):
    """Deverrouillage d'un evenement verrouille (CDC 4.7), reserve au
    Superuser, motif obligatoire (CLAUDE.md regle n6)."""

    permission_classes = _GATE + [IsSuperuser]

    def post(self, request, pk):
        if get_active_club() is None:
            return Response(
                {
                    "detail": "Le déverrouillage exige une session de support active : "
                    "ouvrez une session sur le club concerné (Ghost Mode)."
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            return _not_found(_EVENT_NOT_FOUND)
        serializer = serializers_mod.UnlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            event = services.unlock_event(event, superuser=request.user, reason=serializer.validated_data["reason"])
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_event_common(event, viewer=request.user))


class EventIncidentListCreateView(APIView):
    """Incidents disciplinaires d'un evenement (CDC 4.9). Lecture : tout
    membre actif, mais un simple joueur ne voit que les siens (matrice
    2.4, « L (les siens pour J) ») ; ecriture : Coach, Capitaine."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            return _not_found(_EVENT_NOT_FOUND)
        queryset = Incident.objects.filter(event=event).select_related("membership__user", "recorded_by").order_by(
            "-recorded_at", "-pk"
        )
        if not has_any_role(request.user, INCIDENT_FULL_VISIBILITY_ROLES):
            try:
                own_membership = resolve_active_membership(request.user, club=get_active_club())
            except NoActiveClubError:
                own_membership = None
            queryset = queryset.filter(membership=own_membership) if own_membership else queryset.none()
        items, count, next_offset = _paginate(request, queryset)
        if items is None:
            return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "count": count,
                "next_offset": next_offset,
                "results": [
                    serializers_mod.serialize_incident(item, viewer=request.user, request=request) for item in items
                ],
            }
        )

    def post(self, request, pk):
        if not CanRecordIncident().has_permission(request, self):
            return Response({"detail": CanRecordIncident.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            return _not_found(_EVENT_NOT_FOUND)
        serializer = serializers_mod.IncidentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, error = _membership_or_404(data["membership_id"])
        if error is not None:
            return error
        try:
            incident = services.record_incident(
                event=event,
                membership=membership,
                incident_type=data["incident_type"],
                cause=data["cause"],
                recorded_by=request.user,
                minute=data.get("minute"),
                cause_detail=data.get("cause_detail", ""),
                issued_by=data.get("issued_by", ""),
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(
            serializers_mod.serialize_incident(incident, viewer=request.user, request=request),
            status=status.HTTP_201_CREATED,
        )


class SuspensionListView(APIView):
    """Suspensions (CDC 4.9). La commande cron ``advance_suspensions``
    (tâche 3.4, deja ecrite) tient ``matches_served``/``lifted_at`` a jour
    -- cette vue ne fait que lire. Visibilite complete reservee au staff
    (``INCIDENT_FULL_VISIBILITY_ROLES``) ; un simple joueur ne voit que
    les siennes."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        queryset = Suspension.objects.select_related("membership__user").order_by("-created_at", "-pk")
        if not has_any_role(request.user, INCIDENT_FULL_VISIBILITY_ROLES):
            queryset = queryset.filter(membership__user=request.user)
        membership_id = request.query_params.get("membership_id")
        if membership_id:
            if not membership_id.isdigit():
                return Response({"detail": "Identifiant de joueur invalide."}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(membership_id=int(membership_id))
        if request.query_params.get("active") in ("1", "true"):
            queryset = queryset.filter(lifted_at__isnull=True)
        items, count, next_offset = _paginate(request, queryset)
        if items is None:
            return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "count": count,
                "next_offset": next_offset,
                "results": [serializers_mod.serialize_suspension(item) for item in items],
            }
        )


# ---------------------------------------------------------------------------
# Seances et pointage (CDC 4.7)
# ---------------------------------------------------------------------------


class SessionListCreateView(APIView):
    """Liste des séances (lecture : tout membre actif) et création
    (Coach seul -- ``Event.created_by`` : « Coach », CDC 4.7)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        queryset = Session.objects.select_related("event").order_by("-event__event_date", "-pk")
        items, count, next_offset = _paginate(request, queryset)
        if items is None:
            return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "count": count,
                "next_offset": next_offset,
                "results": [serializers_mod.serialize_session_list_item(item) for item in items],
            }
        )

    def post(self, request):
        if not IsClubCoach().has_permission(request, self):
            return Response({"detail": IsClubCoach.message}, status=status.HTTP_403_FORBIDDEN)
        serializer = serializers_mod.SessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        season, error = _resolve_season(data)
        if error is not None:
            return error
        try:
            session = services.create_session(
                club=get_active_club(),
                season=season,
                event_date=data["event_date"],
                gathering_time=data["gathering_time"],
                late_arrival_cutoff=data["late_arrival_cutoff"],
                created_by=request.user,
                location=data.get("location", ""),
                team_a_color=data.get("team_a_color"),
                team_b_color=data.get("team_b_color"),
                instructions=data.get("instructions", ""),
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(
            serializers_mod.serialize_session_detail(session, viewer=request.user, request=request),
            status=status.HTTP_201_CREATED,
        )


class SessionDetailView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            session = Session.objects.select_related("event").get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        return Response(serializers_mod.serialize_session_detail(session, viewer=request.user, request=request))

    def patch(self, request, pk):
        """« Modifier la séance » (sport-seance.md §4.2), réservée au Coach,
        le jour même (CDC 4.7, ``services.ensure_event_writable``)."""

        if not IsClubCoach().has_permission(request, self):
            return Response({"detail": IsClubCoach.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            session = Session.objects.select_related("event").get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        serializer = serializers_mod.SessionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            session = services.update_session(
                session=session,
                event_date=data["event_date"],
                gathering_time=data["gathering_time"],
                late_arrival_cutoff=data["late_arrival_cutoff"],
                updated_by=request.user,
                location=data.get("location", ""),
                team_a_color=data.get("team_a_color"),
                team_b_color=data.get("team_b_color"),
                instructions=data.get("instructions", ""),
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_session_detail(session, viewer=request.user, request=request))


class SessionUnassignedView(APIView):
    """Zone « Non répartis » seule (10.2 n29, n38), deja incluse dans le
    detail de la seance -- endpoint dedie pour l'interrogation periodique
    (6.5, sport-seance.md §3.2 point 4)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            session = Session.objects.get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        groups = services.get_unassigned_players(session, actor=request.user)
        return Response(serializers_mod.serialize_unassigned(groups, viewer=request.user, request=request))


class SessionAttendanceMarkView(APIView):
    """Bouton « Arrivé » (CDC 4.7) : Coach, Capitaine, Président."""

    permission_classes = _GATE + [CanRecordAttendance]

    def post(self, request, pk):
        try:
            session = Session.objects.select_related("event").get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        serializer = serializers_mod.AttendanceMarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, error = _membership_or_404(data["membership_id"])
        if error is not None:
            return error
        arrived_at = data.get("arrived_at") or timezone.now()
        try:
            attendance = services.mark_arrival(
                session=session,
                membership=membership,
                arrived_at=arrived_at,
                marked_by=request.user,
                client_uuid=data.get("client_uuid"),
                client_recorded_at=data.get("client_recorded_at"),
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(
            serializers_mod.serialize_attendance(attendance, viewer=request.user, request=request),
            status=status.HTTP_201_CREATED,
        )


class SessionAttendanceExcuseView(APIView):
    """« Marquer absent excusé » (CDC 4.7), reserve au Coach, le jour meme
    (meme modale que la correction d'heure)."""

    permission_classes = _GATE + [CanCorrectAttendanceTime]

    def post(self, request, pk):
        try:
            session = Session.objects.select_related("event").get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        serializer = serializers_mod.AttendanceExcuseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, error = _membership_or_404(data["membership_id"])
        if error is not None:
            return error
        try:
            attendance = services.mark_excused_absence(
                event=session.event, membership=membership, reason=data["reason"], marked_by=request.user
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_attendance(attendance, viewer=request.user, request=request))


def _bulk_attendance_response(request, event):
    """Corps commun des deux endpoints de pointage groupé. Une erreur de
    lot (verrou, droit, heure, taille) refuse tout ; sinon chaque joueur
    a son résultat (succès partiel, 200)."""

    serializer = serializers_mod.BulkAttendanceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        if data["action"] == "excuse":
            result = services.excuse_absences_bulk(
                event=event,
                items=data["items"],
                actor=request.user,
                reason_code=data["reason_code"],
                reason_detail=data.get("reason_detail", ""),
            )
        else:
            result = services.mark_arrivals_bulk(
                event=event, items=data["items"], actor=request.user, arrived_at=data.get("arrived_at")
            )
    except services.SportError as exc:
        return _sport_error(exc)
    return Response(serializers_mod.serialize_bulk_attendance_result(result, viewer=request.user, request=request))


class SessionAttendanceBulkView(APIView):
    """Pointage groupé d'une séance (CDC 4.7). Mêmes rôles que le pointage
    individuel ; ``excuse`` et ``arrived_at`` sont réservés au Coach et à son
    assistant (contrôlé par le service, 403)."""

    permission_classes = _GATE + [CanRecordAttendance]

    def post(self, request, pk):
        try:
            session = Session.objects.select_related("event").get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        return _bulk_attendance_response(request, session.event)


class MatchAttendanceBulkView(APIView):
    """Pointage groupé d'un match (CDC 4.8 : mêmes règles que les séances)."""

    permission_classes = _GATE + [CanRecordAttendance]

    def post(self, request, pk):
        try:
            match = Match.objects.select_related("event").get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        return _bulk_attendance_response(request, match.event)


class AttendanceCorrectionView(APIView):
    """Correction de l'heure d'arrivée (CDC 4.7), reservee au Coach."""

    permission_classes = _GATE + [CanCorrectAttendanceTime]

    def patch(self, request, pk):
        try:
            attendance = Attendance.objects.select_related("event", "membership").get(pk=pk)
        except Attendance.DoesNotExist:
            return _not_found(_ATTENDANCE_NOT_FOUND)
        serializer = serializers_mod.AttendanceCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attendance = services.correct_arrival_time(
                attendance=attendance, new_arrived_at=serializer.validated_data["arrived_at"], actor=request.user
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_attendance(attendance, viewer=request.user, request=request))


class TeamAssignmentView(APIView):
    """Répartition A/B (CDC 4.7 ; 10.2 n7, n29, n38) : Coach, Capitaine,
    Président. Le controle reel d'eligibilite est fait par le service
    (aucun contournement possible, sport-seance.md §3.2 bis)."""

    permission_classes = _GATE + [CanAssignTeams]

    def post(self, request, pk):
        try:
            session = Session.objects.get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        serializer = serializers_mod.TeamAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, error = _membership_or_404(data["membership_id"])
        if error is not None:
            return error
        try:
            assignment = services.assign_team(
                session=session, membership=membership, team=data["team"], assigned_by=request.user
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_team_assignment(assignment, request=request))


class SessionTeamFormationView(APIView):
    """Choix de la formation d'une équipe de séance (extension client du
    30/09/2026, hors CDC écrit à ce jour -- voir
    ``apps.sport.services.set_team_formation`` et le compte rendu de cette
    tâche). Mêmes permissions que la répartition A/B (matrice 2.4, ligne
    « Séances et matchs » : Coach, Capitaine, Président) -- le service
    refait sa propre vérification de rôle en défense en profondeur."""

    permission_classes = _GATE + [CanAssignTeams]

    def post(self, request, pk):
        try:
            session = Session.objects.select_related("event").get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        serializer = serializers_mod.TeamFormationSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            session = services.set_team_formation(
                session=session, team=data["team"], formation=data["formation"], actor=request.user
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_session_detail(session, viewer=request.user, request=request))


class SessionTeamPlayerPlacementView(APIView):
    """Place, déplace ou renvoie au banc un joueur déjà réparti en équipe
    A/B (extension client du 30/09/2026, hors CDC écrit à ce jour -- voir
    ``apps.sport.services.place_team_player`` et le compte rendu de cette
    tâche). Aucun contournement possible pour un joueur non éligible (déjà
    appliqué par le service) ; mêmes permissions que la répartition A/B."""

    permission_classes = _GATE + [CanAssignTeams]

    def post(self, request, pk):
        try:
            session = Session.objects.select_related("event").get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        serializer = serializers_mod.TeamPlayerPlacementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, error = _membership_or_404(data["membership_id"])
        if error is not None:
            return error
        try:
            services.place_team_player(
                session=session,
                team=data["team"],
                membership=membership,
                x_coord=data.get("x_coord"),
                y_coord=data.get("y_coord"),
                actor=request.user,
            )
        except services.SportError as exc:
            return _sport_error(exc)
        session = Session.objects.select_related("event").get(pk=pk)
        return Response(serializers_mod.serialize_session_detail(session, viewer=request.user, request=request))


# ---------------------------------------------------------------------------
# Matchs et composition (CDC 4.8)
# ---------------------------------------------------------------------------


class MatchListCreateView(APIView):
    """Liste des matchs (lecture : tout membre actif) et création (Coach
    seul, CDC 4.8)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        queryset = Match.objects.select_related("event", "opponent_club").order_by("-event__event_date", "-pk")
        items, count, next_offset = _paginate(request, queryset)
        if items is None:
            return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "count": count,
                "next_offset": next_offset,
                "results": [serializers_mod.serialize_match_list_item(item) for item in items],
            }
        )

    def post(self, request):
        if not IsClubCoach().has_permission(request, self):
            return Response({"detail": IsClubCoach.message}, status=status.HTTP_403_FORBIDDEN)
        serializer = serializers_mod.MatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        season, error = _resolve_season(data)
        if error is not None:
            return error
        opponent_club = None
        if data.get("opponent_club_id"):
            try:
                from apps.clubs.models import Club

                opponent_club = Club.objects.get(pk=data["opponent_club_id"])
            except Club.DoesNotExist:
                return _not_found("Club adverse introuvable.")
        challenge_to_club = None
        if data.get("challenge_to_club_id"):
            try:
                from apps.clubs.models import Club

                challenge_to_club = Club.objects.get(pk=data["challenge_to_club_id"])
            except Club.DoesNotExist:
                return _not_found("Club destinataire du défi introuvable.")
        try:
            match = services.create_match(
                club=get_active_club(),
                season=season,
                event_date=data["event_date"],
                kickoff_time=data["kickoff_time"],
                match_type=data["match_type"],
                venue=data["venue"],
                created_by=request.user,
                opponent_club=opponent_club,
                opponent_name=data.get("opponent_name", ""),
                location=data.get("location", ""),
                challenge_status=data.get("challenge_status", Match.ChallengeStatus.NOT_APPLICABLE),
                challenge_to_club=challenge_to_club,
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(
            serializers_mod.serialize_match_detail(match, viewer=request.user, request=request),
            status=status.HTTP_201_CREATED,
        )


class MatchDetailView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            match = Match.objects.select_related("event", "opponent_club").get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        return Response(serializers_mod.serialize_match_detail(match, viewer=request.user, request=request))

    def patch(self, request, pk):
        """« Modifier le match » (sport-feuille-de-match.md §4.7), réservée
        au Coach, verrouillée à minuit comme la séance (CDC 4.7 ; §5,
        « Verrouillé (lendemain) »)."""

        if not CanManageMatch().has_permission(request, self):
            return Response({"detail": CanManageMatch.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            match = Match.objects.select_related("event", "opponent_club").get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        serializer = serializers_mod.MatchUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        opponent_club = None
        if data.get("opponent_club_id"):
            try:
                from apps.clubs.models import Club

                opponent_club = Club.objects.get(pk=data["opponent_club_id"])
            except Club.DoesNotExist:
                return _not_found("Club adverse introuvable.")
        try:
            match = services.update_match(
                match=match,
                event_date=data["event_date"],
                kickoff_time=data["kickoff_time"],
                match_type=data["match_type"],
                venue=data["venue"],
                updated_by=request.user,
                opponent_club=opponent_club,
                opponent_name=data.get("opponent_name", ""),
                location=data.get("location", ""),
                challenge_to_club_id=data.get("challenge_to_club_id"),
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_match_detail(match, viewer=request.user, request=request))


class MatchAttendanceMarkView(APIView):
    """Pointage simple d'un match (CDC 4.8), sans répartition A/B (position
    déjà actée, sport-feuille-de-match.md §7 point ouvert 2 :
    ``TeamAssignment`` reste réservée à ``Session``). Mêmes rôles que le
    pointage d'une séance (Coach, Capitaine, Président, matrice 2.4,
    ligne « Séances et matchs »)."""

    permission_classes = _GATE + [CanRecordAttendance]

    def post(self, request, pk):
        try:
            match = Match.objects.select_related("event").get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        serializer = serializers_mod.AttendanceMarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, error = _membership_or_404(data["membership_id"])
        if error is not None:
            return error
        arrived_at = data.get("arrived_at") or timezone.now()
        try:
            attendance = services.mark_match_arrival(
                match=match,
                membership=membership,
                arrived_at=arrived_at,
                marked_by=request.user,
                client_uuid=data.get("client_uuid"),
                client_recorded_at=data.get("client_recorded_at"),
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(
            serializers_mod.serialize_attendance(attendance, viewer=request.user, request=request),
            status=status.HTTP_201_CREATED,
        )


class MatchCompositionAddView(APIView):
    """Composition (CDC 4.8), reservee au Coach. Refuse un joueur en
    dette/suspendu/inapte/en attente, avec la raison (CLAUDE.md regle n5)."""

    permission_classes = _GATE + [CanManageMatch]

    def post(self, request, pk):
        try:
            match = Match.objects.get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        serializer = serializers_mod.MatchCompositionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, error = _membership_or_404(data["membership_id"])
        if error is not None:
            return error
        try:
            composition = services.add_to_composition(
                match=match,
                membership=membership,
                role=data["role"],
                position=data["position"],
                jersey_number=data["jersey_number"],
                added_by=request.user,
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(
            serializers_mod.serialize_composition(composition, viewer=request.user, request=request),
            status=status.HTTP_201_CREATED,
        )


class MatchCompositionRemoveView(APIView):
    permission_classes = _GATE + [CanManageMatch]

    def delete(self, request, pk, membership_id):
        try:
            match = Match.objects.get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        membership, error = _membership_or_404(membership_id)
        if error is not None:
            return error
        services.remove_from_composition(match=match, membership=membership, removed_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MatchCompositionPublishView(APIView):
    """Publication bloquee tant qu'un joueur compose n'est plus
    selectionnable (position provisoire, sport-feuille-de-match.md §3
    point 2 -- deja applique par le service)."""

    permission_classes = _GATE + [CanManageMatch]

    def post(self, request, pk):
        try:
            match = Match.objects.get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        try:
            match = services.publish_composition(match=match, published_by=request.user)
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_match_detail(match, viewer=request.user, request=request))


class MatchScoreView(APIView):
    permission_classes = _GATE + [CanManageMatch]

    def post(self, request, pk):
        try:
            match = Match.objects.select_related("event").get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        serializer = serializers_mod.ScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            services.set_match_score(
                match=match, score_home=data["score_home"], score_away=data["score_away"], filled_by=request.user
            )
        except services.SportError as exc:
            return _sport_error(exc)
        match = Match.objects.select_related("event").get(pk=pk)
        return Response(serializers_mod.serialize_match_detail(match, viewer=request.user, request=request))


class MatchPublishResultView(APIView):
    """Publication du résultat sur le fil, en un clic (CDC 4.8). Réservée aux
    rôles qui saisissent le score ; visibilité « Club » (10.2 n° 160)."""

    permission_classes = _GATE + [CanManageMatch]

    def post(self, request, pk):
        try:
            match = Match.objects.select_related("event").get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        try:
            services.publish_match_result(match=match, published_by=request.user)
        except services.SportError as exc:
            return _sport_error(exc)
        match = Match.objects.select_related("event").get(pk=pk)
        return Response(serializers_mod.serialize_match_detail(match, viewer=request.user, request=request))


class MatchGoalListCreateView(APIView):
    """Buts et passes decisives (CDC 4.8). Lecture : tout membre actif ;
    ecriture : Coach seul. Modifiables apres coup (jamais verrouilles a
    minuit, a la difference du pointage/des incidents)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            match = Match.objects.get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        sheet = getattr(match, "sheet", None)
        goals = sheet.goals.all().order_by("minute", "pk") if sheet is not None else []
        return Response([serializers_mod.serialize_goal(goal, request=request) for goal in goals])

    def post(self, request, pk):
        if not CanManageMatch().has_permission(request, self):
            return Response({"detail": CanManageMatch.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            match = Match.objects.get(pk=pk)
        except Match.DoesNotExist:
            return _not_found(_MATCH_NOT_FOUND)
        sheet = getattr(match, "sheet", None)
        if sheet is None:
            return Response(
                {"detail": "Saisissez d'abord le score du match."}, status=status.HTTP_400_BAD_REQUEST
            )
        serializer = serializers_mod.GoalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        scorer = assist = None
        if data.get("scorer_membership_id"):
            scorer, error = _membership_or_404(data["scorer_membership_id"])
            if error is not None:
                return error
        if data.get("assist_membership_id"):
            assist, error = _membership_or_404(data["assist_membership_id"])
            if error is not None:
                return error
        try:
            goal = services.add_goal(
                match_sheet=sheet,
                created_by=request.user,
                scorer_membership=scorer,
                assist_membership=assist,
                minute=data.get("minute"),
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_goal(goal, request=request), status=status.HTTP_201_CREATED)


class MatchGoalDetailView(APIView):
    permission_classes = _GATE + [CanManageMatch]

    def patch(self, request, pk):
        try:
            goal = MatchGoal.objects.get(pk=pk)
        except MatchGoal.DoesNotExist:
            return _not_found(_GOAL_NOT_FOUND)
        serializer = serializers_mod.GoalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        scorer = assist = None
        if data.get("scorer_membership_id"):
            scorer, error = _membership_or_404(data["scorer_membership_id"])
            if error is not None:
                return error
        if data.get("assist_membership_id"):
            assist, error = _membership_or_404(data["assist_membership_id"])
            if error is not None:
                return error
        try:
            goal = services.update_goal(
                goal=goal,
                updated_by=request.user,
                scorer_membership=scorer,
                assist_membership=assist,
                minute=data.get("minute"),
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_goal(goal, request=request))

    def delete(self, request, pk):
        try:
            goal = MatchGoal.objects.get(pk=pk)
        except MatchGoal.DoesNotExist:
            return _not_found(_GOAL_NOT_FOUND)
        services.delete_goal(goal=goal, deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Evaluations (CDC 4.10) : Coach, Président, Vice-président uniquement --
# aucun autre rôle n'a d'accès, pas même en lecture de ses propres notes
# (matrice 2.4, sport-seance.md §2 : « — » pour DS/Médecin/joueurs).
# ---------------------------------------------------------------------------


class EventEvaluationListCreateView(APIView):
    """Lecture : évaluateurs et Directeur sportif (« L ») voient tout ; tout
    autre joueur actif ne voit QUE ses propres notes (matrice 2.4, « P » ;
    CDC 4.10), commentaire seulement s'il est marqué visible. Écriture :
    Coach, Président, Vice-président."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [permission() for permission in _GATE + [CanEvaluate]]
        return [permission() for permission in _GATE + [IsActiveClubMember]]

    def get(self, request, pk):
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            return _not_found(_EVENT_NOT_FOUND)
        queryset = Evaluation.objects.filter(event=event).select_related("membership__user", "evaluator")
        sees_all = has_any_role(
            request.user, EVALUATOR_ROLES | {MembershipRole.Role.SPORTS_DIRECTOR}
        ) or getattr(request.user, "is_superuser", False)
        if not sees_all:
            queryset = queryset.filter(membership__user=request.user)
        membership_id = request.query_params.get("membership_id")
        if membership_id:
            if not membership_id.isdigit():
                return Response({"detail": "Identifiant de joueur invalide."}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(membership_id=int(membership_id))
        evaluations = list(queryset.order_by("membership_id", "-created_at"))
        unique_memberships = {item.membership_id: item.membership for item in evaluations}
        averages = {
            str(mid): str(services.get_average_evaluation(event, membership))
            for mid, membership in unique_memberships.items()
        }
        return Response(
            {
                "results": [
                    serializers_mod.serialize_evaluation(item, request=request, as_player=not sees_all)
                    for item in evaluations
                ],
                "averages": averages,
                "is_locked": services.is_evaluation_locked(event),
                "locks_at": services.evaluation_locks_at(event),
            }
        )

    def post(self, request, pk):
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            return _not_found(_EVENT_NOT_FOUND)
        serializer = serializers_mod.EvaluationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        membership, error = _membership_or_404(data.pop("membership_id"))
        if error is not None:
            return error
        overall_score = data.pop("overall_score")
        comment = data.pop("comment", "")
        comment_visible_to_player = data.pop("comment_visible_to_player", False)
        try:
            evaluation = services.submit_evaluation(
                event=event,
                membership=membership,
                evaluator=request.user,
                overall_score=overall_score,
                comment=comment,
                comment_visible_to_player=comment_visible_to_player,
                **data,
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(
            serializers_mod.serialize_evaluation(evaluation, request=request), status=status.HTTP_201_CREATED
        )


# ---------------------------------------------------------------------------
# Plan tactique (CDC 4.11)
# ---------------------------------------------------------------------------


class TacticalPlanListCreateView(APIView):
    """Liste (tout membre actif, brouillons reserves au Coach -- position
    provisoire, sport-plan-tactique.md §8 point ouvert 1) et creation
    (Coach seul)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        queryset = TacticalPlan.objects.select_related("match__event").order_by("-updated_at", "-pk")
        is_coach = has_any_role(request.user, COACHING_STAFF_ROLES)
        if not is_coach:
            queryset = queryset.filter(is_published=True)
        else:
            status_filter = request.query_params.get("status")
            if status_filter == "published":
                queryset = queryset.filter(is_published=True)
            elif status_filter == "draft":
                queryset = queryset.filter(is_published=False)
        items, count, next_offset = _paginate(request, queryset)
        if items is None:
            return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "count": count,
                "next_offset": next_offset,
                "results": [serializers_mod.serialize_tactical_plan_list_item(item) for item in items],
            }
        )

    def post(self, request):
        if not CanEditTacticalPlan().has_permission(request, self):
            return Response({"detail": CanEditTacticalPlan.message}, status=status.HTTP_403_FORBIDDEN)
        serializer = serializers_mod.TacticalPlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        match = None
        if data.get("match_id"):
            try:
                match = Match.objects.get(pk=data["match_id"])
            except Match.DoesNotExist:
                return _not_found(_MATCH_NOT_FOUND)
        try:
            plan = services.create_tactical_plan(
                club=get_active_club(),
                name=data["name"],
                formation=data["formation"],
                squad_size=data["squad_size"],
                created_by=request.user,
                match=match,
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(
            serializers_mod.serialize_tactical_plan_detail(plan, viewer=request.user, request=request),
            status=status.HTTP_201_CREATED,
        )


class TacticalPlanDetailView(APIView):
    """Détail (§4.1) : brouillon reservé au Coach (message standard sinon,
    sport-plan-tactique.md §2) ; suppression Coach seul."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            plan = TacticalPlan.objects.get(pk=pk)
        except TacticalPlan.DoesNotExist:
            return _not_found(_PLAN_NOT_FOUND)
        if not plan.is_published and not has_any_role(request.user, COACHING_STAFF_ROLES):
            return Response(
                {"detail": "Vous n'avez pas accès à cette action."}, status=status.HTTP_403_FORBIDDEN
            )
        return Response(serializers_mod.serialize_tactical_plan_detail(plan, viewer=request.user, request=request))

    def patch(self, request, pk):
        """« Paramètres du plan » (sport-plan-tactique.md §4.3), Coach
        seul. Un plan publié ne peut plus être modifié (déjà appliqué par
        le service, même règle que le placement/l'annotation)."""

        if not CanEditTacticalPlan().has_permission(request, self):
            return Response({"detail": CanEditTacticalPlan.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            plan = TacticalPlan.objects.get(pk=pk)
        except TacticalPlan.DoesNotExist:
            return _not_found(_PLAN_NOT_FOUND)
        serializer = serializers_mod.TacticalPlanSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        match = None
        if data.get("match_id"):
            try:
                match = Match.objects.get(pk=data["match_id"])
            except Match.DoesNotExist:
                return _not_found(_MATCH_NOT_FOUND)
        try:
            plan = services.update_tactical_plan_settings(
                plan=plan,
                name=data["name"],
                formation=data["formation"],
                squad_size=data["squad_size"],
                updated_by=request.user,
                match=match,
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_tactical_plan_detail(plan, viewer=request.user, request=request))

    def delete(self, request, pk):
        if not CanEditTacticalPlan().has_permission(request, self):
            return Response({"detail": CanEditTacticalPlan.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            plan = TacticalPlan.objects.get(pk=pk)
        except TacticalPlan.DoesNotExist:
            return _not_found(_PLAN_NOT_FOUND)
        services.delete_tactical_plan(plan=plan, deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TacticalPlanDuplicateView(APIView):
    permission_classes = _GATE + [CanEditTacticalPlan]

    def post(self, request, pk):
        try:
            plan = TacticalPlan.objects.get(pk=pk)
        except TacticalPlan.DoesNotExist:
            return _not_found(_PLAN_NOT_FOUND)
        serializer = serializers_mod.TacticalPlanDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        match = None
        if data.get("match_id"):
            try:
                match = Match.objects.get(pk=data["match_id"])
            except Match.DoesNotExist:
                return _not_found(_MATCH_NOT_FOUND)
        try:
            new_plan, skipped = services.duplicate_tactical_plan(
                plan=plan, name=data["name"], created_by=request.user, match=match
            )
        except services.SportError as exc:
            return _sport_error(exc)
        payload = serializers_mod.serialize_tactical_plan_detail(new_plan, viewer=request.user, request=request)
        payload["skipped_count"] = len(skipped)
        return Response(payload, status=status.HTTP_201_CREATED)


class TacticalPlanPublishView(APIView):
    """Publication impossible tant qu'un joueur place est devenu non
    eligible (deja applique par le service, sport-plan-tactique.md §4.8)."""

    permission_classes = _GATE + [CanEditTacticalPlan]

    def post(self, request, pk):
        try:
            plan = TacticalPlan.objects.get(pk=pk)
        except TacticalPlan.DoesNotExist:
            return _not_found(_PLAN_NOT_FOUND)
        try:
            plan = services.publish_tactical_plan(plan=plan, published_by=request.user)
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_tactical_plan_detail(plan, viewer=request.user, request=request))


class TacticalPlanPlacementCreateView(APIView):
    """Place ou deplace un joueur (CDC 4.11). Aucun contournement possible
    pour un joueur non eligible (deja applique par le service,
    sport-plan-tactique.md §5.3)."""

    permission_classes = _GATE + [CanEditTacticalPlan]

    def post(self, request, pk):
        try:
            plan = TacticalPlan.objects.get(pk=pk)
        except TacticalPlan.DoesNotExist:
            return _not_found(_PLAN_NOT_FOUND)
        serializer = serializers_mod.PlacementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, error = _membership_or_404(data["membership_id"])
        if error is not None:
            return error
        try:
            placement = services.place_on_plan(
                plan=plan,
                membership=membership,
                x_coord=data["x_coord"],
                y_coord=data["y_coord"],
                placed_by=request.user,
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(
            serializers_mod.serialize_placement(placement, viewer=request.user, request=request),
            status=status.HTTP_201_CREATED,
        )


class PlacementDetailView(APIView):
    """Modifier le numero et le poste (§4.5), ou retirer l'emplacement du
    terrain (Coach seul)."""

    permission_classes = _GATE + [CanEditTacticalPlan]

    def patch(self, request, pk):
        try:
            placement = TacticalPlanPlacement.objects.select_related("membership__user").get(pk=pk)
        except TacticalPlanPlacement.DoesNotExist:
            return _not_found(_PLACEMENT_NOT_FOUND)
        serializer = serializers_mod.PlacementUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Champ non transmis = inchangé (D4).
        changes = {key: data[key] for key in ("jersey_number", "position") if key in data}
        try:
            placement, warning = services.update_plan_placement_number_and_position(
                placement=placement, updated_by=request.user, **changes
            )
        except services.SportError as exc:
            return _sport_error(exc)
        payload = serializers_mod.serialize_placement(placement, viewer=request.user, request=request)
        payload["warning"] = warning
        return Response(payload)

    def delete(self, request, pk):
        try:
            placement = TacticalPlanPlacement.objects.get(pk=pk)
        except TacticalPlanPlacement.DoesNotExist:
            return _not_found(_PLACEMENT_NOT_FOUND)
        services.remove_from_plan(placement=placement, removed_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TacticalPlanAnnotationCreateView(APIView):
    """Tableau noir : flèches, zones, consignes (CDC 4.11, Coach seul)."""

    permission_classes = _GATE + [CanEditTacticalPlan]

    def post(self, request, pk):
        try:
            plan = TacticalPlan.objects.get(pk=pk)
        except TacticalPlan.DoesNotExist:
            return _not_found(_PLAN_NOT_FOUND)
        serializer = serializers_mod.AnnotationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target_membership = None
        if data.get("target_membership_id"):
            target_membership, error = _membership_or_404(data["target_membership_id"])
            if error is not None:
                return error
        try:
            annotation = services.add_annotation(
                plan=plan,
                annotation_type=data["annotation_type"],
                created_by=request.user,
                path_data=data.get("path_data", ""),
                text=data.get("text", ""),
                target_membership=target_membership,
                target_line=data.get("target_line", ""),
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(serializers_mod.serialize_annotation(annotation), status=status.HTTP_201_CREATED)


class AnnotationDetailView(APIView):
    permission_classes = _GATE + [CanEditTacticalPlan]

    def delete(self, request, pk):
        try:
            annotation = TacticalPlanAnnotation.objects.get(pk=pk)
        except TacticalPlanAnnotation.DoesNotExist:
            return _not_found(_ANNOTATION_NOT_FOUND)
        services.delete_annotation(annotation=annotation, deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Vestiaire du jour (sport-vestiaire.md) : lecture seule pure, aucune
# ecriture, aucune regle recalculee -- agrege la seance et/ou le match du
# jour du club actif.
# ---------------------------------------------------------------------------


class LockerRoomView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        club = get_active_club()
        today = services.get_club_today(club)
        session = (
            Session.objects.select_related("event").filter(event__event_date=today).order_by("-pk").first()
        )
        match = (
            Match.objects.select_related("event").filter(event__event_date=today).order_by("-pk").first()
        )
        try:
            viewer_membership = resolve_active_membership(request.user, club=club)
        except NoActiveClubError:
            viewer_membership = None
        return Response(
            serializers_mod.serialize_locker_room(
                club=club,
                session=session,
                match=match,
                viewer=request.user,
                viewer_membership=viewer_membership,
                request=request,
            )
        )
