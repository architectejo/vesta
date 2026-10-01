"""Vues DRF de l'app medical (Lot 4, tache 4.2).

Chaque vue orchestre uniquement : permission -> service -> serializer
(CLAUDE.md section 5). Toute decision de visibilite (N0/N1/N2, medical.md
§2) est deja prise par ``apps.medical.services`` (qui leve
``MedicalPermissionError`` -> 403, ou renvoie deja le contenu filtre) et
``apps.medical.serializers`` (qui ne serialise que ce que le niveau
autorise) : aucune reconstruction ici.

Isolation multi-tenant (CLAUDE.md regle n8) : toute recuperation d'un
``Membership``/``Injury``/``HealthRecord`` passe par le manager
tenant-aware ou un filtre explicite sur le club actif -- un objet d'un
autre club renvoie 404, jamais 403 (pas de fuite d'existence).
"""

from __future__ import annotations

from django.http import FileResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.models import Membership, MembershipRole
from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence
from apps.core.roles import has_any_role
from apps.core.services import resolve_active_membership
from apps.core.tenant import NoActiveClubError, get_active_club
from apps.medical import serializers as serializers_mod
from apps.medical import services
from apps.medical.models import Injury, MedicalDocument
from apps.medical.permissions import CanAccessMedicalPage, CanReportInjury, IsClubDoctor

_GATE = [IsAuthenticated, HasCompletedPasswordSetup, HasAcceptedLatestTerms, HasUsableLicence]

_MEMBER_NOT_FOUND = "Ce joueur n'existe pas dans ce club."
_INJURY_NOT_FOUND = "Cet element n'existe plus."
_DOCUMENT_NOT_FOUND = "Ce document n'existe pas."

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _not_found(message):
    return Response({"detail": message}, status=status.HTTP_404_NOT_FOUND)


def _medical_error(exc: services.MedicalError):
    if isinstance(exc, services.ConsentMissingError):
        return Response({"detail": str(exc), "code": "consent_missing"}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, services.MedicalPermissionError):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, services.MedicalValidationError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _paginate(request, queryset):
    try:
        limit = int(request.query_params.get("limit", DEFAULT_PAGE_SIZE))
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError):
        limit, offset = DEFAULT_PAGE_SIZE, 0
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    items = list(queryset[offset : offset + limit])
    return items, offset + limit


def _membership_or_404(membership_id):
    try:
        return Membership.objects.get(pk=membership_id), None
    except Membership.DoesNotExist:
        return None, _not_found(_MEMBER_NOT_FOUND)


def _injury_or_404(pk, club):
    injury = Injury.all_objects.filter(pk=pk, club_id=club.id).first()
    if injury is None:
        return None, _not_found(_INJURY_NOT_FOUND)
    return injury, None


# ---------------------------------------------------------------------------
# Fiche de sante (medical.md §4.2, §4.5, §4.10)
# ---------------------------------------------------------------------------


class HealthRecordDetailView(APIView):
    """GET : Medecin (§4.2), joueur concerne (§4.10) ou President avec
    consentement actif (§4.6 « Consulter le dossier complet »).
    PATCH : « Modifier la fiche » (§4.5), reserve au Medecin."""

    permission_classes = _GATE

    def _resolve(self, request, membership):
        actor = request.user
        if has_any_role(actor, {MembershipRole.Role.DOCTOR}):
            return services.view_health_record_as_doctor(membership=membership, actor=actor)
        if actor.id == membership.user_id:
            return services.view_health_record_as_player(membership=membership, actor=actor)
        if has_any_role(actor, {MembershipRole.Role.PRESIDENT}):
            return services.view_health_record_as_president(membership=membership, actor=actor)
        raise services.MedicalPermissionError("Vous n'avez pas acces a cette fiche (CDC 2.4, 4.12).")

    def get(self, request, membership_id: int):
        membership, error = _membership_or_404(membership_id)
        if error:
            return error
        try:
            record = self._resolve(request, membership)
        except services.MedicalError as exc:
            return _medical_error(exc)
        return Response(serializers_mod.serialize_health_record_full(record))

    def patch(self, request, membership_id: int):
        membership, error = _membership_or_404(membership_id)
        if error:
            return error
        serializer = serializers_mod.HealthRecordUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = services.update_health_record(
                membership=membership, actor=request.user, data=serializer.validated_data
            )
        except services.MedicalError as exc:
            return _medical_error(exc)
        return Response(serializers_mod.serialize_health_record_full(record))


class FitnessUpdateView(APIView):
    """« Modifier l'aptitude » (medical.md §4.4), reserve au Medecin."""

    permission_classes = _GATE + [IsClubDoctor]

    def patch(self, request, membership_id: int):
        membership, error = _membership_or_404(membership_id)
        if error:
            return error
        serializer = serializers_mod.FitnessUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            record = services.update_fitness(
                membership=membership,
                actor=request.user,
                status=data["fitness_status"],
                return_date=data.get("fitness_return_date"),
            )
        except services.MedicalError as exc:
            return _medical_error(exc)
        return Response(serializers_mod.serialize_health_record_full(record))


# ---------------------------------------------------------------------------
# Mon profil : declaration, consentement (medical.md §4.10, §4.11)
# ---------------------------------------------------------------------------


class MySelfDeclarationView(APIView):
    """« Mettre a jour ma declaration » (medical.md §4.10), reserve au joueur lui-meme."""

    permission_classes = _GATE

    def patch(self, request):
        try:
            membership = resolve_active_membership(request.user)
        except NoActiveClubError:
            return Response({"detail": "Aucun club actif."}, status=status.HTTP_403_FORBIDDEN)
        serializer = serializers_mod.SelfDeclarationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            record = services.update_self_declaration(
                membership=membership,
                actor=request.user,
                text=data.get("self_declaration", ""),
                consent_given=data.get("consent_given", False),
            )
        except services.MedicalError as exc:
            return _medical_error(exc)
        return Response(serializers_mod.serialize_health_record_full(record))


class MyProcessingConsentView(APIView):
    """Consentement au traitement des donnees de sante (CDC 4.12, 7.5),
    donne a la premiere connexion ou depuis « Ma fiche de sante »."""

    permission_classes = _GATE

    def post(self, request):
        try:
            membership = resolve_active_membership(request.user)
        except NoActiveClubError:
            return Response({"detail": "Aucun club actif."}, status=status.HTTP_403_FORBIDDEN)
        record = services.give_processing_consent(membership=membership, actor=request.user)
        return Response({"consent_given_at": record.consent_given_at})


class MyPresidentAccessView(APIView):
    """« Consentement medical » (medical.md §4.11) : etat, octroi, revocation."""

    permission_classes = _GATE

    def get(self, request):
        try:
            membership = resolve_active_membership(request.user)
        except NoActiveClubError:
            return Response({"detail": "Aucun club actif."}, status=status.HTTP_403_FORBIDDEN)
        record = services.get_health_record(membership)
        return Response(serializers_mod.serialize_consent_status(record))

    def post(self, request):
        try:
            membership = resolve_active_membership(request.user)
        except NoActiveClubError:
            return Response({"detail": "Aucun club actif."}, status=status.HTTP_403_FORBIDDEN)
        record = services.grant_president_access(membership=membership, actor=request.user)
        return Response(serializers_mod.serialize_consent_status(record))

    def delete(self, request):
        try:
            membership = resolve_active_membership(request.user)
        except NoActiveClubError:
            return Response({"detail": "Aucun club actif."}, status=status.HTTP_403_FORBIDDEN)
        record = services.revoke_president_access(membership=membership, actor=request.user)
        return Response(serializers_mod.serialize_consent_status(record))


# ---------------------------------------------------------------------------
# Blessures (medical.md §4.1, §4.3, §4.7-§4.9)
# ---------------------------------------------------------------------------


class InjuryListCreateView(APIView):
    """POST : « Declarer une blessure » (§4.1), Coach/Capitaine/Medecin."""

    permission_classes = _GATE + [CanReportInjury]

    def post(self, request):
        serializer = serializers_mod.InjuryReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, error = _membership_or_404(data["membership_id"])
        if error:
            return error

        event = None
        event_id = data.get("event_id")
        if event_id is not None:
            from apps.sport.models import Event

            event = Event.objects.filter(pk=event_id).first()
            if event is None:
                return _not_found("Cet evenement n'existe pas dans ce club.")

        try:
            injury = services.report_injury(
                membership=membership,
                actor=request.user,
                circumstances=data["circumstances"],
                event=event,
                occurred_time=data.get("occurred_time"),
                occurred_minute=data.get("occurred_minute"),
            )
        except services.MedicalError as exc:
            return _medical_error(exc)
        return Response(serializers_mod.serialize_injury_detail(injury), status=status.HTTP_201_CREATED)


class InjuryDetailView(APIView):
    """GET : Medecin, joueur concerne, President avec consentement actif
    pour ce joueur (medical.md §4.3)."""

    permission_classes = _GATE

    def get(self, request, pk: int):
        club = get_active_club()
        injury, error = _injury_or_404(pk, club)
        if error:
            return error
        actor = request.user
        membership = injury.membership
        allowed = (
            has_any_role(actor, {MembershipRole.Role.DOCTOR})
            or actor.id == membership.user_id
            or (
                has_any_role(actor, {MembershipRole.Role.PRESIDENT})
                and services.has_full_record_access(viewer=actor, membership=membership)
            )
        )
        if not allowed:
            return Response(
                {"detail": "Vous n'avez pas acces a cette blessure (CDC 2.4, 4.12)."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if has_any_role(actor, {MembershipRole.Role.PRESIDENT}) and actor.id != membership.user_id:
            # schema §6 / medical.md §8 : « Ouverture du dossier complet (et
            # de chaque blessure) par le President » -- journalisee comme le
            # reste du dossier.
            services.log_action(
                actor=actor, club=club, action_type="medical.record.viewed_by_president", obj=injury
            )
        return Response(serializers_mod.serialize_injury_detail(injury))


class InjuryCompleteView(APIView):
    """« Completer la blessure »/« Modifier le bilan » (§4.7), Medecin."""

    permission_classes = _GATE + [IsClubDoctor]

    def patch(self, request, pk: int):
        club = get_active_club()
        injury, error = _injury_or_404(pk, club)
        if error:
            return error
        serializer = serializers_mod.InjuryCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            injury = services.complete_injury_report(
                injury=injury,
                actor=request.user,
                location_on_body=data.get("location_on_body", ""),
                severity=data.get("severity", ""),
                on_site_care=data.get("on_site_care", ""),
                referral=data.get("referral", ""),
                estimated_days_out=data.get("estimated_days_out"),
                return_date=data.get("fitness_return_date"),
            )
        except services.MedicalError as exc:
            return _medical_error(exc)
        return Response(serializers_mod.serialize_injury_detail(injury))


class InjuryFollowUpListCreateView(APIView):
    """« Ajouter un suivi » (§4.8), Medecin."""

    permission_classes = _GATE + [IsClubDoctor]

    def post(self, request, pk: int):
        club = get_active_club()
        injury, error = _injury_or_404(pk, club)
        if error:
            return error
        serializer = serializers_mod.InjuryFollowUpCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            followup = services.add_injury_followup(
                injury=injury,
                actor=request.user,
                entry_date=data["entry_date"],
                note=data["note"],
                new_return_date=data.get("fitness_return_date"),
            )
        except services.MedicalError as exc:
            return _medical_error(exc)
        return Response(serializers_mod.serialize_followup(followup), status=status.HTTP_201_CREATED)


class InjuryReturnView(APIView):
    """« Declarer le retour » (§4.9), Medecin."""

    permission_classes = _GATE + [IsClubDoctor]

    def post(self, request, pk: int):
        club = get_active_club()
        injury, error = _injury_or_404(pk, club)
        if error:
            return error
        serializer = serializers_mod.InjuryReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            injury = services.declare_injury_return(
                injury=injury, actor=request.user, return_date=serializer.validated_data["return_date"]
            )
        except services.MedicalError as exc:
            return _medical_error(exc)
        return Response(serializers_mod.serialize_injury_detail(injury))


# ---------------------------------------------------------------------------
# Page « Medical » (medical.md §3)
# ---------------------------------------------------------------------------


class InjuriesToCompleteView(APIView):
    """§3.1, Medecin uniquement."""

    permission_classes = _GATE + [IsClubDoctor]

    def get(self, request):
        club = get_active_club()
        items, next_offset = _paginate(request, services.list_injuries_to_complete(club))
        return Response({"results": [serializers_mod.serialize_injury_list_item(i) for i in items], "next_offset": next_offset})


class RecentInjuriesView(APIView):
    """§3.4, Medecin uniquement."""

    permission_classes = _GATE + [IsClubDoctor]

    def get(self, request):
        club = get_active_club()
        items = services.list_recent_injuries(club, limit=5)
        return Response({"results": [serializers_mod.serialize_injury_list_item(i) for i in items]})


class UnfitAndRestrictedView(APIView):
    """§3.2, Medecin/Coach/President. Journalise la consultation par le
    Coach/President (point ouvert 9)."""

    permission_classes = _GATE + [CanAccessMedicalPage]

    def get(self, request):
        club = get_active_club()
        actor = request.user
        is_doctor = has_any_role(actor, {MembershipRole.Role.DOCTOR})
        if not is_doctor:
            services.log_fitness_list_viewed(club=club, actor=actor)

        records = services.list_unfit_and_restricted(club)
        results = []
        for record in records:
            membership = record.membership
            full_access = is_doctor or (
                has_any_role(actor, {MembershipRole.Role.PRESIDENT})
                and services.can_president_read_full_record(record)
            )
            results.append(serializers_mod.serialize_fitness_list_item(record, viewer_is_full_access=full_access))
        return Response({"results": results})


# ---------------------------------------------------------------------------
# Documents medicaux (CDC 6.7 ; extension hors ecran valide, voir models.py)
# ---------------------------------------------------------------------------


class InjuryDocumentUploadView(APIView):
    """Televersement d'une piece jointe sur une blessure, reserve au
    Medecin (CDC 6.7)."""

    permission_classes = _GATE + [IsClubDoctor]

    def post(self, request, pk: int):
        club = get_active_club()
        injury, error = _injury_or_404(pk, club)
        if error:
            return error
        file = request.FILES.get("file")
        if file is None:
            return Response({"detail": "Choisissez un fichier."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            document = services.attach_document(
                actor=request.user, file=file, original_filename=file.name, injury=injury
            )
        except services.MedicalError as exc:
            return _medical_error(exc)
        return Response({"id": document.pk}, status=status.HTTP_201_CREATED)


class MedicalDocumentDownloadView(APIView):
    """Telechargement authentifie (CDC 6.7, 7.6) : jamais servi depuis
    ``public_html`` -- verifie le club (404 hors club) et le role (403,
    meme regle N2 que le dossier medical)."""

    permission_classes = _GATE

    def get(self, request, pk: int):
        club = get_active_club()
        document = MedicalDocument.all_objects.filter(pk=pk, club_id=club.id).first()
        if document is None:
            return _not_found(_DOCUMENT_NOT_FOUND)
        if not services.can_access_document(viewer=request.user, document=document):
            return Response(
                {"detail": "Vous n'avez pas acces a ce document (CDC 2.4, 6.7)."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=document.original_filename or document.file.name,
        )
