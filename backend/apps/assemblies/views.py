"""Vues DRF de l'app assemblies (CDC 4.15 ; tache 4.5).

Orchestrent uniquement : permission -> service -> serializer (CLAUDE.md
section 5). Toute regle metier vit dans ``apps.assemblies.services``.
"""

from __future__ import annotations

import os

from django.http import FileResponse
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assemblies import serializers as ser
from apps.assemblies import services
from apps.assemblies.models import AgendaItem, ArchivedDocument, Assembly, AssemblyAttendance, Minutes
from apps.assemblies.permissions import (
    CanConveneAssembly,
    CanManageAssembly,
    CanReadArchive,
    CanWriteArchive,
)
from apps.clubs.models import Membership
from apps.clubs.permissions import IsActiveClubMember
from apps.core.private_files import private_file_response
from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence
from apps.core.tenant import get_active_club

_GATE = [IsAuthenticated, HasCompletedPasswordSetup, HasAcceptedLatestTerms, HasUsableLicence]

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50

_ASSEMBLY_NOT_FOUND = "Cette assemblée n'existe pas dans ce club."
_MEMBER_NOT_FOUND = "Ce joueur n'existe pas dans ce club."
_AGENDA_ITEM_NOT_FOUND = "Ce point d'ordre du jour n'existe pas dans cette assemblée."


def _not_found(message: str) -> Response:
    return Response({"detail": message}, status=status.HTTP_404_NOT_FOUND)


def _assembly_error_response(exc: services.AssemblyError) -> Response:
    if isinstance(exc, services.AssemblyLockedError):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, services.AssemblyPermissionError):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _paginate(request, queryset):
    try:
        limit = int(request.query_params.get("limit", DEFAULT_PAGE_SIZE))
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError):
        limit, offset = DEFAULT_PAGE_SIZE, 0
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    count = queryset.count()
    items = list(queryset[offset : offset + limit])
    next_offset = offset + limit if offset + limit < count else None
    return items, count, next_offset


def _get_assembly(pk):
    return Assembly.objects.select_related("club").prefetch_related("agenda_items", "decisions").get(pk=pk)


class AssemblyListCreateView(APIView):
    """Liste des AG (« A venir » / « Passees », assemblees-page-ag.md §3) et
    convocation (assistant §4.1)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        queryset = Assembly.objects.all()
        status_filter = request.query_params.get("status")
        if status_filter == "scheduled":
            queryset = queryset.filter(status=Assembly.Status.SCHEDULED)
        elif status_filter == "held":
            queryset = queryset.filter(status__in=[Assembly.Status.HELD, Assembly.Status.CANCELLED])
        items, count, next_offset = _paginate(request, queryset)
        data = ser.AssemblySerializer(items, many=True, context={"request": request}).data
        return Response({"results": data, "count": count, "next_offset": next_offset})

    def post(self, request):
        if not CanConveneAssembly().has_permission(request, self):
            return Response(
                {"detail": CanConveneAssembly.message}, status=status.HTTP_403_FORBIDDEN
            )
        serializer = ser.ConveneAssemblyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            assembly = services.convene_assembly(
                club=get_active_club(),
                actor=request.user,
                assembly_type=data["assembly_type"],
                scheduled_date=data["scheduled_date"],
                scheduled_time=data["scheduled_time"],
                location=data.get("location", ""),
                agenda_items=data["agenda_items"],
            )
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)

        return Response(
            ser.AssemblySerializer(assembly, context={"request": request}).data, status=status.HTTP_201_CREATED
        )


class AssemblyDetailView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            assembly = _get_assembly(pk)
        except Assembly.DoesNotExist:
            return _not_found(_ASSEMBLY_NOT_FOUND)
        return Response(ser.AssemblySerializer(assembly, context={"request": request}).data)


class AssemblyAttendanceListMarkView(APIView):
    """Onglet « Presences » (assemblees-page-ag.md §4.2) : liste filtrable
    et pointage (President, VP, uniquement le jour de l'AG -- verifie par
    le service)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            assembly = _get_assembly(pk)
        except Assembly.DoesNotExist:
            return _not_found(_ASSEMBLY_NOT_FOUND)

        total = services.get_active_membership_count(assembly.club, at_date=assembly.scheduled_date)
        present_ids = set(
            AssemblyAttendance.objects.filter(assembly=assembly, present=True).values_list("membership_id", flat=True)
        )
        memberships = Membership.objects.filter(
            club=assembly.club, status=Membership.Status.ACTIVE, joined_on__lte=assembly.scheduled_date
        ).select_related("user")

        view_filter = request.query_params.get("filter", "unchecked")
        search = (request.query_params.get("q") or "").strip().lower()

        def matches_search(m: Membership) -> bool:
            if not search:
                return True
            full_name = f"{m.user.first_name} {m.user.last_name}".lower()
            jersey = str(m.jersey_number or "")
            return search in full_name or search == jersey

        results = []
        for membership in memberships:
            if not matches_search(membership):
                continue
            is_present = membership.id in present_ids
            if view_filter == "present" and not is_present:
                continue
            if view_filter == "unchecked" and is_present:
                continue
            results.append(
                {
                    "membership_id": membership.id,
                    "first_name": membership.user.first_name,
                    "last_name": membership.user.last_name,
                    "jersey_number": membership.jersey_number,
                    "present": is_present,
                }
            )

        return Response(
            {
                "results": results,
                "counts": {
                    "all": total,
                    "present": len(present_ids),
                    "unchecked": total - len(present_ids),
                },
            }
        )

    def post(self, request, pk):
        if not CanManageAssembly().has_permission(request, self):
            return Response({"detail": CanManageAssembly.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            assembly = _get_assembly(pk)
        except Assembly.DoesNotExist:
            return _not_found(_ASSEMBLY_NOT_FOUND)

        serializer = ser.AttendanceMarkInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = Membership.objects.get(pk=serializer.validated_data["membership_id"])
        except Membership.DoesNotExist:
            return _not_found(_MEMBER_NOT_FOUND)

        try:
            attendance = services.mark_attendance(assembly=assembly, actor=request.user, membership=membership)
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)

        return Response(ser.AttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)


class AssemblyAttendanceRemoveView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def delete(self, request, pk, membership_id):
        if not CanManageAssembly().has_permission(request, self):
            return Response({"detail": CanManageAssembly.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            assembly = _get_assembly(pk)
        except Assembly.DoesNotExist:
            return _not_found(_ASSEMBLY_NOT_FOUND)
        try:
            membership = Membership.objects.get(pk=membership_id)
        except Membership.DoesNotExist:
            return _not_found(_MEMBER_NOT_FOUND)

        try:
            services.remove_attendance(assembly=assembly, actor=request.user, membership=membership)
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)

        return Response(status=status.HTTP_204_NO_CONTENT)


class AssemblyDecisionView(APIView):
    """Saisie du vote d'un point (assemblees-page-ag.md §4.3). Jamais
    bloquant sur le quorum ni sur le total des votes."""

    permission_classes = _GATE + [IsActiveClubMember]

    def put(self, request, pk, agenda_item_id):
        if not CanManageAssembly().has_permission(request, self):
            return Response({"detail": CanManageAssembly.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            assembly = _get_assembly(pk)
        except Assembly.DoesNotExist:
            return _not_found(_ASSEMBLY_NOT_FOUND)
        try:
            agenda_item = AgendaItem.objects.get(pk=agenda_item_id, assembly=assembly)
        except AgendaItem.DoesNotExist:
            return _not_found(_AGENDA_ITEM_NOT_FOUND)

        serializer = ser.DecisionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            decision = services.record_decision(
                assembly=assembly,
                agenda_item=agenda_item,
                actor=request.user,
                votes_for=data["votes_for"],
                votes_against=data["votes_against"],
                votes_abstain=data["votes_abstain"],
                outcome=data["outcome"],
                linked_object_type=data.get("linked_object_type", ""),
                linked_object_id=data.get("linked_object_id"),
            )
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)

        return Response(ser.DecisionSerializer(decision).data, status=status.HTTP_200_OK)


class AssemblyMinutesView(APIView):
    """Redaction du PV (assemblees-page-ag.md §4.4)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def put(self, request, pk):
        if not CanManageAssembly().has_permission(request, self):
            return Response({"detail": CanManageAssembly.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            assembly = _get_assembly(pk)
        except Assembly.DoesNotExist:
            return _not_found(_ASSEMBLY_NOT_FOUND)

        serializer = ser.MinutesDraftInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            minutes = services.draft_minutes(
                assembly=assembly, actor=request.user, content=serializer.validated_data["content"]
            )
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)

        return Response(ser.MinutesSerializer(minutes).data, status=status.HTTP_200_OK)


class AssemblyMinutesSignView(APIView):
    """Signature du PV (Président / Vice-président). Aucun code PIN : un `pin` reçu est ignoré."""

    permission_classes = _GATE + [IsActiveClubMember]

    def post(self, request, pk):
        try:
            assembly = _get_assembly(pk)
        except Assembly.DoesNotExist:
            return _not_found(_ASSEMBLY_NOT_FOUND)

        try:
            minutes = services.sign_minutes(assembly=assembly, actor=request.user)
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)

        return Response(ser.MinutesSerializer(minutes).data, status=status.HTTP_200_OK)


class AssemblyMinutesPdfDownloadView(APIView):
    """Telechargement authentifie du PV (CDC 6.7, 7.6 ; jamais public,
    assemblees-page-ag.md §4.6)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            minutes = Minutes.objects.select_related("assembly").get(assembly_id=pk)
        except Minutes.DoesNotExist:
            return _not_found("Le procès-verbal n'existe pas dans ce club.")

        if not minutes.pdf_file:
            return Response(
                {"detail": "Le procès-verbal n'a pas encore ete genere."}, status=status.HTTP_404_NOT_FOUND
            )

        # Reprend le nom de fichier reellement stocke a la generation
        # (`apps.assemblies.services._generate_minutes_pdf`, gabarit §3.1)
        # plutot que d'en recalculer un ici -- une seule source pour ce
        # format, jamais deux qui pourraient diverger.
        filename = os.path.basename(minutes.pdf_file.name) or f"pv-ag-{minutes.assembly_id}.pdf"

        return FileResponse(
            minutes.pdf_file.open("rb"),
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )


class QuorumThresholdView(APIView):
    """Reglage du seuil de quorum (assemblees-page-ag.md §4.5 ; 10.2 n° 18)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        club = get_active_club()
        club_settings = club.settings
        return Response({"percentage": str(club_settings.assembly_quorum_percentage)})

    def put(self, request):
        if not CanManageAssembly().has_permission(request, self):
            return Response({"detail": CanManageAssembly.message}, status=status.HTTP_403_FORBIDDEN)
        serializer = ser.QuorumThresholdInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            club_settings = services.update_quorum_threshold(
                club=get_active_club(), actor=request.user, percentage=serializer.validated_data["percentage"]
            )
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)

        return Response({"percentage": str(club_settings.assembly_quorum_percentage)})


# ---------------------------------------------------------------------------
# Archive des documents officiels (CDC 4.15.1)
# ---------------------------------------------------------------------------

_DOCUMENT_NOT_FOUND = "Ce document n'existe pas dans l'archive de ce club."


class ArchivedDocumentListCreateView(APIView):
    """Liste (N derniers + « Voir plus », filtres categorie/annee) : Bureau.
    Depot : Secretaire, President, VP. Multipart : category, title,
    document_date, file."""

    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        extra = CanWriteArchive if self.request.method == "POST" else CanReadArchive
        return [permission() for permission in _GATE + [extra]]

    def get(self, request):
        try:
            queryset = services.filter_archived_documents(
                ArchivedDocument.objects.select_related("uploaded_by", "withdrawn_by"),
                category=request.query_params.get("category", ""),
                year=request.query_params.get("year", ""),
                include_withdrawn=request.query_params.get("include_withdrawn") in ("1", "true", "True"),
            )
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)
        items, count, next_offset = _paginate(request, queryset)
        data = ser.ArchivedDocumentSerializer(items, many=True).data
        return Response({"results": data, "count": count, "next_offset": next_offset})

    def post(self, request):
        serializer = ser.ArchivedDocumentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            document = services.archive_document(
                club=get_active_club(),
                actor=request.user,
                category=data["category"],
                title=data["title"],
                document_date=data["document_date"],
                file=data["file"],
            )
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)
        return Response(ser.ArchivedDocumentSerializer(document).data, status=status.HTTP_201_CREATED)


class ArchivedDocumentDetailView(APIView):
    permission_classes = _GATE + [CanReadArchive]

    def get(self, request, pk):
        try:
            document = ArchivedDocument.objects.select_related("uploaded_by", "withdrawn_by").get(pk=pk)
        except ArchivedDocument.DoesNotExist:
            return _not_found(_DOCUMENT_NOT_FOUND)
        services.record_archived_document_access(document=document, actor=request.user, downloaded=False)
        return Response(ser.ArchivedDocumentSerializer(document).data)


class ArchivedDocumentFileView(APIView):
    """Telechargement authentifie (regle n 10) : Bureau du club du document."""

    permission_classes = _GATE + [CanReadArchive]

    def get(self, request, pk):
        try:
            document = ArchivedDocument.objects.get(pk=pk)
        except ArchivedDocument.DoesNotExist:
            return _not_found(_DOCUMENT_NOT_FOUND)
        services.record_archived_document_access(document=document, actor=request.user, downloaded=True)
        # Type et extension deduits du contenu reel, jamais du nom stocke.
        return private_file_response(document.file, download_stem=f"archive-{document.pk}")


class ArchivedDocumentReplaceView(APIView):
    """Remplacement : l'ancien est retire et conserve, le nouveau le reference."""

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = _GATE + [CanWriteArchive]

    def post(self, request, pk):
        try:
            document = ArchivedDocument.objects.get(pk=pk)
        except ArchivedDocument.DoesNotExist:
            return _not_found(_DOCUMENT_NOT_FOUND)
        serializer = ser.ArchivedDocumentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            new_document = services.replace_archived_document(
                document=document,
                actor=request.user,
                category=data["category"],
                title=data["title"],
                document_date=data["document_date"],
                file=data["file"],
            )
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)
        return Response(ser.ArchivedDocumentSerializer(new_document).data, status=status.HTTP_201_CREATED)


class ArchivedDocumentWithdrawView(APIView):
    permission_classes = _GATE + [CanWriteArchive]

    def post(self, request, pk):
        try:
            document = ArchivedDocument.objects.get(pk=pk)
        except ArchivedDocument.DoesNotExist:
            return _not_found(_DOCUMENT_NOT_FOUND)
        serializer = ser.ArchivedDocumentWithdrawInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            document = services.withdraw_archived_document(
                document=document, actor=request.user, reason=serializer.validated_data["reason"]
            )
        except services.AssemblyError as exc:
            return _assembly_error_response(exc)
        return Response(ser.ArchivedDocumentSerializer(document).data)
