"""Vues DRF de l'app audit : consultation du journal par le Superuser
(CDC 4.18, 5.5 ; docs/ecrans/superuser-espace.md §3.4, §4.6).

Lecture seule : aucune methode d'ecriture n'est exposee (CDC 5.3).
Orchestration : permission -> service -> serializer.
"""

from __future__ import annotations

from datetime import date

from django.http import HttpResponse
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import serializers, services
from apps.audit.models import AuditLog
from apps.audit.permissions import IsSuperuser

_PERMISSIONS = [IsAuthenticated, IsSuperuser]


class AuditLogPagination(PageNumberPagination):
    """50 lignes par page (ecran §3.4)."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def _parse_int(value):
    return int(value) if value not in (None, "") else None


def _parse_date(value):
    return date.fromisoformat(value) if value else None


def _filtered_queryset(request):
    """Retourne (queryset, reponse_d_erreur)."""

    params = request.query_params
    try:
        club_id = _parse_int(params.get("club_id"))
        actor_id = _parse_int(params.get("actor_id"))
        date_from = _parse_date(params.get("date_from"))
        date_to = _parse_date(params.get("date_to"))
    except ValueError:
        return None, Response(
            {"detail": "Filtre invalide : vérifiez les identifiants et les dates (AAAA-MM-JJ)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if date_from and date_to and date_from > date_to:
        return None, Response(
            {"detail": "La date de début doit précéder la date de fin."}, status=status.HTTP_400_BAD_REQUEST
        )
    action_types = []
    for raw in params.getlist("action_type"):
        action_types.extend(part.strip() for part in raw.split(","))
    queryset = AuditLog.objects.select_related("club", "club__settings", "actor").order_by("-created_at", "-id")
    queryset = services.filter_audit_logs(
        queryset,
        club_id=club_id,
        actor_id=actor_id,
        action_types=action_types,
        date_from=date_from,
        date_to=date_to,
        alerts_only=params.get("alerts_only", "").lower() in ("1", "true", "oui"),
    )
    return queryset, None


class AuditLogListView(ListAPIView):
    """GET /api/v1/audit/logs/ : liste paginee et filtrable."""

    permission_classes = _PERMISSIONS
    serializer_class = serializers.AuditLogListSerializer
    pagination_class = AuditLogPagination

    def list(self, request, *args, **kwargs):
        queryset, error = _filtered_queryset(request)
        if error is not None:
            return error
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class AuditLogDetailView(APIView):
    """GET /api/v1/audit/logs/<id>/ : modale « Entree du journal »."""

    permission_classes = _PERMISSIONS

    def get(self, request, pk: int):
        entry = AuditLog.objects.select_related("club", "club__settings", "actor").filter(pk=pk).first()
        if entry is None:
            return Response({"detail": "Cette entrée n'existe pas."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializers.AuditLogDetailSerializer(entry, context={"request": request}).data)


class AuditLogExportView(APIView):
    """GET /api/v1/audit/logs/export/ : CSV des entrees filtrees (memes
    filtres que la liste), plafonne a EXPORT_MAX_ROWS lignes."""

    permission_classes = _PERMISSIONS
    EXPORT_MAX_ROWS = 50000

    def get(self, request):
        queryset, error = _filtered_queryset(request)
        if error is not None:
            return error
        filename, content = services.export_audit_logs_csv(queryset[: self.EXPORT_MAX_ROWS], reader=request.user)
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "no-store"
        return response


class AuditActionTypeListView(APIView):
    """GET /api/v1/audit/action-types/ : types d'action presents, pour le
    filtre a choix multiple."""

    permission_classes = _PERMISSIONS

    def get(self, request):
        types = list(AuditLog.objects.order_by("action_type").values_list("action_type", flat=True).distinct())
        return Response(
            {"results": [{"action_type": t, "is_alert": t in services.ALERT_ACTION_TYPES} for t in types]}
        )
