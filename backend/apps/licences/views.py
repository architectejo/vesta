"""Vues DRF de l'app licences (CDC 2.5, 4.18, 5.4 ; tache 1.8).

Orchestrent uniquement : permission -> service -> serializer (CLAUDE.md
section 5). Toute regle metier (transitions, confirmation de resiliation,
Ghost Mode...) vit dans ``apps.licences.services``.

Reservees au Superuser (``IsSuperuser``, CDC 2.5) : l'ecran « Espace
Superuser » n'est jamais accessible a un membre de club.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.models import Club
from apps.core.permissions import IsSuperuser
from apps.licences import serializers, services
from apps.licences.models import Licence, LicenceEvent, SupportSession


class LicenceListView(APIView):
    """Tableau des licences (CDC 4.18), filtrable par club/statut."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def get(self, request):
        queryset = Licence.objects.select_related("club").order_by("-created_at")

        club_id = request.query_params.get("club_id")
        if club_id:
            queryset = queryset.filter(club_id=club_id)

        licence_status = request.query_params.get("status")
        if licence_status:
            queryset = queryset.filter(status=licence_status)

        return Response(serializers.LicenceSerializer(queryset, many=True).data, status=status.HTTP_200_OK)


class LicenceDetailView(APIView):
    """Detail d'une licence (CDC 4.18)."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def get(self, request, licence_id: int):
        licence = _get_licence_or_404(licence_id)
        if licence is None:
            return Response({"detail": "Cette licence n'existe pas."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializers.LicenceSerializer(licence).data, status=status.HTTP_200_OK)


class LicenceEventListView(APIView):
    """Historique d'une licence (CDC 2.5 « historique », 4.18)."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def get(self, request, licence_id: int):
        licence = _get_licence_or_404(licence_id)
        if licence is None:
            return Response({"detail": "Cette licence n'existe pas."}, status=status.HTTP_404_NOT_FOUND)

        events = LicenceEvent.objects.filter(licence=licence).order_by("-event_date")
        return Response(serializers.LicenceEventSerializer(events, many=True).data, status=status.HTTP_200_OK)


def _get_licence_or_404(licence_id: int):
    return Licence.objects.select_related("club").filter(pk=licence_id).first()


class _LicenceActionView(APIView):
    """Base commune des 5 actions du cycle de vie (CDC 2.5)."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def _licence_or_404(self, licence_id: int):
        return _get_licence_or_404(licence_id)


class LicenceActivateView(_LicenceActionView):
    def post(self, request, licence_id: int):
        licence = self._licence_or_404(licence_id)
        if licence is None:
            return Response({"detail": "Cette licence n'existe pas."}, status=status.HTTP_404_NOT_FOUND)

        serializer = serializers.LicenceActivateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            licence = services.activate_licence(
                superuser=request.user,
                licence=licence,
                start_date=data["start_date"],
                end_date=data["end_date"],
                note=data["note"],
            )
        except services.InvalidLicenceTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializers.LicenceSerializer(licence).data, status=status.HTTP_200_OK)


class LicenceExtendView(_LicenceActionView):
    def post(self, request, licence_id: int):
        licence = self._licence_or_404(licence_id)
        if licence is None:
            return Response({"detail": "Cette licence n'existe pas."}, status=status.HTTP_404_NOT_FOUND)

        serializer = serializers.LicenceExtendInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            licence = services.extend_licence(
                superuser=request.user,
                licence=licence,
                end_date=data["end_date"],
                start_date=data["start_date"],
                note=data["note"],
            )
        except services.InvalidLicenceTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializers.LicenceSerializer(licence).data, status=status.HTTP_200_OK)


class LicenceSuspendView(_LicenceActionView):
    def post(self, request, licence_id: int):
        licence = self._licence_or_404(licence_id)
        if licence is None:
            return Response({"detail": "Cette licence n'existe pas."}, status=status.HTTP_404_NOT_FOUND)

        serializer = serializers.LicenceSuspendInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            licence = services.suspend_licence(superuser=request.user, licence=licence, reason=data["reason"])
        except services.InvalidLicenceTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializers.LicenceSerializer(licence).data, status=status.HTTP_200_OK)


class LicenceResumeView(_LicenceActionView):
    def post(self, request, licence_id: int):
        licence = self._licence_or_404(licence_id)
        if licence is None:
            return Response({"detail": "Cette licence n'existe pas."}, status=status.HTTP_404_NOT_FOUND)

        serializer = serializers.LicenceResumeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            licence = services.resume_licence(superuser=request.user, licence=licence, note=data["note"])
        except services.InvalidLicenceTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializers.LicenceSerializer(licence).data, status=status.HTTP_200_OK)


class LicenceTerminateView(_LicenceActionView):
    """CDC 2.5, 4.18 ; 10.2 n26 : confirmation par saisie du nom exact du club."""

    def post(self, request, licence_id: int):
        licence = self._licence_or_404(licence_id)
        if licence is None:
            return Response({"detail": "Cette licence n'existe pas."}, status=status.HTTP_404_NOT_FOUND)

        serializer = serializers.LicenceTerminateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            licence = services.terminate_licence(
                superuser=request.user,
                licence=licence,
                reason=data["reason"],
                confirm_club_name=data["confirm_club_name"],
            )
        except services.LicenceTerminationConfirmationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except services.InvalidLicenceTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializers.LicenceSerializer(licence).data, status=status.HTTP_200_OK)


class SupportSessionListView(APIView):
    """Historique des sessions de support (CDC 4.18, 5.4), filtrable par club."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def get(self, request):
        queryset = SupportSession.objects.select_related("club").order_by("-started_at")

        club_id = request.query_params.get("club_id")
        if club_id:
            queryset = queryset.filter(club_id=club_id)

        return Response(serializers.SupportSessionSerializer(queryset, many=True).data, status=status.HTTP_200_OK)


class SupportSessionStartView(APIView):
    """« Intervenir sur ce club » (CDC 4.18) : motif obligatoire, 60 minutes au plus."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def post(self, request):
        serializer = serializers.SupportSessionStartInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        club = Club.objects.filter(pk=data["club_id"]).first()
        if club is None:
            return Response({"detail": "Ce club n'existe pas."}, status=status.HTTP_404_NOT_FOUND)

        try:
            session = services.start_support_session(superuser=request.user, club=club, reason=data["reason"])
        except services.SupportSessionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializers.SupportSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class SupportSessionEndView(APIView):
    """Fin anticipee d'une session de support (schema §13.1)."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def post(self, request, session_id: int):
        session = SupportSession.objects.select_related("club").filter(pk=session_id).first()
        if session is None:
            return Response({"detail": "Cette session de support n'existe pas."}, status=status.HTTP_404_NOT_FOUND)

        try:
            session = services.end_support_session(session=session, superuser=request.user)
        except services.SupportSessionPermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except services.SupportSessionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializers.SupportSessionSerializer(session).data, status=status.HTTP_200_OK)
