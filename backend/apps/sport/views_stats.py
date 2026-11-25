"""Vues des statistiques de séance (docs/ecrans/sport-statistiques-seance.md,
parties A et B). Lecture seule : permission -> service -> réponse. Tout le
calcul et tout le filtrage par rôle vivent dans ``apps.sport.session_stats``.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.permissions import IsActiveClubMember
from apps.core.tenant import get_active_club
from apps.sport import services, session_stats
from apps.sport.models import Session
from apps.sport.permissions import CanViewAttendanceRanking
from apps.sport.views import _GATE, _SESSION_NOT_FOUND, _not_found, _sport_error


class SessionStatsView(APIView):
    """``GET /sport/sessions/{id}/stats/`` : présence (tout membre actif),
    « Notes du Coach » (staff, bureau, Directeur sportif), ``my_evaluation``
    (le joueur), mesures de la séance (partie C)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            session = Session.objects.select_related("event").get(pk=pk)
        except Session.DoesNotExist:
            return _not_found(_SESSION_NOT_FOUND)
        return Response(session_stats.get_session_stats(session, viewer=request.user, request=request))


class SessionStatsHistoryView(APIView):
    """``GET /sport/sessions/stats/history/?period=last10|season``."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        try:
            data = session_stats.get_stats_history(
                get_active_club(), viewer=request.user, period=request.query_params.get("period")
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(data)


class AttendanceRankingView(APIView):
    """``GET /sport/attendance/ranking/?period=...`` : assiduité nominative,
    réservée aux rôles de la spec (A3)."""

    permission_classes = _GATE + [CanViewAttendanceRanking]

    def get(self, request):
        try:
            data = session_stats.get_attendance_ranking(
                get_active_club(), period=request.query_params.get("period"), request=request
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(data)


class MyAttendanceView(APIView):
    """``GET /sport/attendance/me/?period=...`` : l'assiduité du joueur connecté."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        try:
            data = session_stats.get_my_attendance(
                get_active_club(), viewer=request.user, period=request.query_params.get("period")
            )
        except services.SportError as exc:
            return _sport_error(exc)
        if data is None:
            return Response(
                {"detail": "Aucune fiche joueur n'est associée à ce compte dans ce club."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(data)
