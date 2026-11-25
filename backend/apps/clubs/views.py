"""Vues DRF de l'app clubs (CDC 2.2-2.4 ; tache 1.5).

Orchestrent uniquement : permission -> service -> serializer (CLAUDE.md
section 5). Toute regle metier (qui peut nommer qui, cardinalite,
libelle effectif du Medecin, atomicite de la passation de presidence)
vit dans ``apps.clubs.services``/``apps.clubs.models``.

Chaque vue declare explicitement ses permissions (``DEFAULT_PERMISSION_CLASSES``
n'est jamais fusionne avec ``permission_classes`` par DRF : le declarer
sur une vue REMPLACE la liste par defaut, voir config/settings/base.py) :
``IsAuthenticated``, ``HasCompletedPasswordSetup``, ``HasAcceptedLatestTerms``,
``HasUsableLicence`` (gardes-fous poses taches 1.3/1.8) sont donc repetes
explicitement sur chaque vue accessible a un membre de club -- a l'exception
des vues reservees
au Superuser, qui suivent le meme choix deja fait par
``apps.accounts.views.SuperuserPasswordResetView`` (``IsAuthenticated``,
``IsSuperuser`` seulement : un Superuser n'a ni mot de passe initial de
joueur, ni parcours de CGU joueur a accepter).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.http import FileResponse
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.serializers import TermsVersionSerializer, UserSummarySerializer
from apps.clubs import board_dashboard, club_creation
from apps.clubs import profile_services
from apps.clubs import serializers
from apps.clubs import services as clubs_services
from apps.clubs.models import ClubSettings, ImportBatch, Membership, MembershipApplication, MembershipRole
from apps.clubs.permissions import (
    CanAddOrImportPlayers,
    CanRecordMembershipFeePayment,
    IsActiveClubMember,
    IsClubCoach,
    IsClubHeadCoach,
    IsClubPresident,
    IsPresidentOrVicePresident,
    can_access_membership_application_file,
)
from apps.clubs.throttling import ClubCreationRateThrottle, ClubCreationSettingsRateThrottle
from apps.core.permissions import (
    HasAcceptedLatestTerms,
    HasCompletedPasswordSetup,
    HasUsableLicence,
    IsSuperuser,
)
from apps.core.roles import has_any_role
from apps.core.tenant import TenantMismatchError, get_active_club
from apps.sport import player_stats
from apps.treasury.permissions import CanImportContributions
from apps.treasury.services import (
    ClientUuidConflictError,
    LedgerFrozenError,
    LedgerKeyError,
    TreasuryError,
    TreasuryValidationError,
)

_CLUB_MEMBER_GATE = [
    IsAuthenticated,
    HasCompletedPasswordSetup,
    HasAcceptedLatestTerms,
    HasUsableLicence,
]


def _serialize_club_identity_summary(club, request) -> dict:
    """Identite publique minimale du club (memes champs que
    ``apps.accounts.views._serialize_club``, duplique volontairement : ce
    module ne doit pas importer une fonction prefixee ``_`` d'une autre
    app).

    ``logo`` en URL ABSOLUE (``request.build_absolute_uri``, bug
    remarques.md) -- voir la docstring de
    ``apps.accounts.views._serialize_club`` pour le detail du probleme
    (chemin relatif qui pointe vers le mauvais serveur des que
    interface/API sont sur des origines differentes)."""

    return {
        "id": club.id,
        "slug": club.slug,
        "name": club.name,
        "logo": request.build_absolute_uri(club.logo.url) if club.logo else None,
        "primary_color": club.primary_color,
        "secondary_color": club.secondary_color,
        "city": club.city,
        "country": club.country,
    }


def _validation_error_response(exc: DjangoValidationError) -> Response:
    return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)


def _treasury_error_response(exc: TreasuryError) -> Response:
    """Traduit une erreur de tresorerie (interface `finance-engine`, non
    modifiee) en reponse HTTP francaise claire."""

    if isinstance(exc, ClientUuidConflictError):
        return Response({"detail": str(exc), "code": "client_uuid_conflict"}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, LedgerFrozenError):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, LedgerKeyError):
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class RoleListView(APIView):
    """Liste des roles actifs du club actif (matrice 2.4, colonnes « L »)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request):
        # `objects` (tenant-aware) : deja scope au club actif du contexte
        # courant (CLAUDE.md regle n8) -- jamais `all_objects` ici.
        roles = MembershipRole.objects.filter(revoked_at__isnull=True).select_related("membership")
        return Response(serializers.MembershipRoleSerializer(roles, many=True).data)


class RoleAppointmentView(APIView):
    """Nomination d'un membre du bureau, du Medecin, du Coach ou d'un
    recruteur (CDC 2.3). Reserve au President (matrice 2.4)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubPresident]

    def post(self, request):
        serializer = serializers.RoleAppointmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            target_membership = Membership.objects.get(pk=data["membership_id"])
        except Membership.DoesNotExist:
            return Response(
                {"detail": "Ce joueur n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            role = clubs_services.appoint_president_nominated_role(
                president_user=request.user,
                target_membership=target_membership,
                role=data["role"],
                is_qualified_professional=data.get("is_qualified_professional"),
            )
        except clubs_services.RoleManagementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipRoleSerializer(role).data, status=status.HTTP_201_CREATED)


class RoleRevocationView(APIView):
    """Revocation d'un role du bureau, du Medecin, du Coach ou d'un
    recruteur (CDC 2.3). Reserve au President (matrice 2.4)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubPresident]

    def post(self, request):
        serializer = serializers.RoleRevocationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            role = MembershipRole.objects.get(pk=data["role_id"])
        except MembershipRole.DoesNotExist:
            return Response({"detail": "Ce rôle n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            role = clubs_services.revoke_president_nominated_role(
                president_user=request.user, role=role, reason=data.get("reason", "")
            )
        except clubs_services.RoleManagementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipRoleSerializer(role).data, status=status.HTTP_200_OK)


class CaptainAppointmentView(APIView):
    """Choix du Capitaine parmi les joueurs (CDC 2.3). Reserve au Coach (matrice 2.4)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubCoach]

    def post(self, request):
        serializer = serializers.CaptainAppointmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            target_membership = Membership.objects.get(pk=data["membership_id"])
        except Membership.DoesNotExist:
            return Response(
                {"detail": "Ce joueur n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            role = clubs_services.appoint_captain(coach_user=request.user, target_membership=target_membership)
        except clubs_services.RoleManagementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipRoleSerializer(role).data, status=status.HTTP_201_CREATED)


class CaptainRevocationView(APIView):
    """Retrait du Capitaine (CDC 2.3 : « il peut le changer »). Reserve au Coach."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubCoach]

    def post(self, request):
        serializer = serializers.RoleRevocationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            role = MembershipRole.objects.get(pk=data["role_id"])
        except MembershipRole.DoesNotExist:
            return Response({"detail": "Ce rôle n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            role = clubs_services.revoke_captain(
                coach_user=request.user, role=role, reason=data.get("reason", "")
            )
        except clubs_services.RoleManagementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipRoleSerializer(role).data, status=status.HTTP_200_OK)


class AssistantCoachAppointmentView(APIView):
    """Nomination de l'Assistant du Coach (CDC 10.3 n179). Reserve au Coach
    (pas a l'assistant, pas au President) ; remplace l'assistant precedent."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubHeadCoach]

    def post(self, request):
        serializer = serializers.AssistantCoachAppointmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            target_membership = Membership.objects.get(pk=data["membership_id"])
        except Membership.DoesNotExist:
            return Response(
                {"detail": "Ce joueur n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            role = clubs_services.appoint_assistant_coach(
                coach_user=request.user, target_membership=target_membership
            )
        except clubs_services.RoleManagementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipRoleSerializer(role).data, status=status.HTTP_201_CREATED)


class AssistantCoachRevocationView(APIView):
    """Retrait de l'Assistant du Coach (CDC 10.3 n179). Reserve au Coach."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubHeadCoach]

    def post(self, request):
        serializer = serializers.RoleRevocationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            role = MembershipRole.objects.get(pk=data["role_id"])
        except MembershipRole.DoesNotExist:
            return Response({"detail": "Ce rôle n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            role = clubs_services.remove_assistant_coach(
                coach_user=request.user, role=role, reason=data.get("reason", "")
            )
        except clubs_services.RoleManagementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipRoleSerializer(role).data, status=status.HTTP_200_OK)


class PresidencyHandoverView(APIView):
    """Passation directe de presidence (CDC 2.3). Reserve au President sortant."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubPresident]

    def post(self, request):
        serializer = serializers.PresidencyHandoverInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            to_membership = Membership.objects.get(pk=data["to_membership_id"])
        except Membership.DoesNotExist:
            return Response(
                {"detail": "Ce joueur n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            transfer = clubs_services.transfer_presidency_by_handover(
                outgoing_user=request.user,
                to_membership=to_membership,
                reason=data.get("reason", ""),
            )
        except clubs_services.RoleManagementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.PresidencyTransferSerializer(transfer).data, status=status.HTTP_201_CREATED)


class PresidencySuperuserOverrideView(APIView):
    """Passation de presidence forcee par le Superuser (CDC 2.3, 2.5).

    Motif ecrit obligatoire (validation de forme, serializer). Aucun club
    actif pour un Superuser (CLAUDE.md regle n1) : le club et les
    adhesions concernees sont donc identifies explicitement dans le
    corps de la requete, jamais deduits d'un contexte courant.
    """

    permission_classes = [IsAuthenticated, IsSuperuser]

    def post(self, request):
        serializer = serializers.PresidencySuperuserOverrideInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # `all_objects` (non filtre) : usage explicitement multi-club
        # legitime depuis l'espace Superuser, documente sur
        # `apps.core.models.TenantModel` -- jamais depuis une vue cote club.
        try:
            from_membership = Membership.all_objects.get(
                pk=data["from_membership_id"], club_id=data["club_id"]
            )
            to_membership = Membership.all_objects.get(pk=data["to_membership_id"], club_id=data["club_id"])
        except Membership.DoesNotExist:
            return Response(
                {"detail": "Adhésion introuvable pour ce club."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            transfer = clubs_services.transfer_presidency_by_superuser(
                superuser=request.user,
                from_membership=from_membership,
                to_membership=to_membership,
                reason=data["reason"],
            )
        except clubs_services.RoleManagementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.PresidencyTransferSerializer(transfer).data, status=status.HTTP_201_CREATED)


class BoardSeatsSettingsView(APIView):
    """Nombre de titulaires par role du bureau (10.2 n24).

    Lecture : tout membre actif du club (matrice 2.4, meme principe que
    « Identite du club », « L »). Ecriture : President uniquement (« É »).
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [permission() for permission in _CLUB_MEMBER_GATE + [IsActiveClubMember]]
        return [permission() for permission in _CLUB_MEMBER_GATE + [IsClubPresident]]

    def get(self, request):
        club = get_active_club()
        try:
            club_settings = ClubSettings.objects.get(pk=club.pk)
        except ClubSettings.DoesNotExist:
            return Response(
                {"detail": "Les paramètres de ce club ne sont pas encore configurés."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(serializers.ClubSettingsBoardSeatsSerializer(club_settings).data)

    def patch(self, request):
        club = get_active_club()
        try:
            club_settings = ClubSettings.objects.get(pk=club.pk)
        except ClubSettings.DoesNotExist:
            return Response(
                {"detail": "Les paramètres de ce club ne sont pas encore configurés."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = serializers.BoardSeatsInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            club_settings = clubs_services.update_board_seats_per_role(
                president_user=request.user,
                club_settings=club_settings,
                seats=serializer.validated_data["board_seats_per_role"],
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.ClubSettingsBoardSeatsSerializer(club_settings).data)


class PlayerImportView(APIView):
    """Import CSV des joueurs (CDC 4.1, tache 1.4). Reserve au President ou
    a un joueur recruteur designe (matrice 2.4, colonne « Ajout et import
    de joueurs »)."""

    permission_classes = _CLUB_MEMBER_GATE + [CanAddOrImportPlayers]

    def post(self, request):
        serializer = serializers.PlayerImportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        club = get_active_club()
        try:
            summary = clubs_services.import_players_from_csv(
                club=club,
                imported_by=request.user,
                csv_file=serializer.validated_data["file"],
            )
        except clubs_services.PlayerImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        response_serializer = serializers.ImportBatchSerializer(
            summary.batch, context={"rows": summary.rows}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


def _get_import_batch(pk: int) -> ImportBatch:
    # `objects` (tenant-aware) : deja scope au club actif du contexte
    # courant (CLAUDE.md regle n8) -- jamais `all_objects` ici. Un lot
    # d'un AUTRE club leve `DoesNotExist`, jamais une fuite d'existence
    # (404 dans les deux vues de telechargement ci-dessous).
    return ImportBatch.objects.get(pk=pk)


# Permission requise pour telecharger les fichiers d'un lot d'import,
# SELON SON TYPE (correction faille : audit de securite + revue manuelle,
# lot d'import de cotisations historiques auparavant telechargeable par
# le recruteur designe). Chaque type d'import correspond a une colonne
# differente de la matrice 2.4 :
# - ``PLAYERS`` (CDC 4.1) : « Ajout et import de joueurs » -- President
#   ou joueur recruteur designe, ``CanAddOrImportPlayers`` (inchange) ;
# - ``HISTORICAL_CONTRIBUTIONS`` (CDC 4.4.8) : lot cree par
#   `apps.treasury` (versements mensuels de tous les joueurs), ligne
#   « Enregistrement des paiements » -- Tresorier et Tresorier adjoint
#   uniquement. Reutilise directement
#   ``apps.treasury.permissions.CanImportContributions`` : aucune
#   dependance circulaire, `apps.treasury` n'important que
#   `apps.clubs.models` (jamais `apps.clubs.views`/`apps.clubs.permissions`)
#   et ce module important deja des symboles de `apps.treasury.services`
#   plus haut.
# Tout type non liste ici (lot futur non encore couvert) n'a AUCUN acces
# par defaut : voir ``_import_batch_access_error``, qui le traite comme
# un lot introuvable (404), jamais un 403 permissif par defaut qui
# confirmerait son existence a un role non habilite.
_IMPORT_BATCH_PERMISSION_BY_TYPE = {
    ImportBatch.ImportType.PLAYERS: CanAddOrImportPlayers,
    ImportBatch.ImportType.HISTORICAL_CONTRIBUTIONS: CanImportContributions,
}


def _import_batch_access_error(request, batch: ImportBatch) -> Response | None:
    """Verifie que ``request.user`` a le droit de telecharger les fichiers
    de ``batch``, selon son type (``_IMPORT_BATCH_PERMISSION_BY_TYPE``).

    Renvoie une ``Response`` d'erreur a propager telle quelle (404 si le
    type n'est pas couvert, 403 si le role du club actif est simplement
    insuffisant), ou ``None`` si l'acces est autorise. L'objet a deja ete
    recupere via le manager tenant-aware (``_get_import_batch``) : un lot
    d'un autre club leve `DoesNotExist` avant meme d'atteindre cette
    fonction (404 dans les deux vues de telechargement ci-dessous)."""

    permission_class = _IMPORT_BATCH_PERMISSION_BY_TYPE.get(batch.import_type)
    if permission_class is None:
        return Response({"detail": "Ce lot d'import n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

    permission = permission_class()
    if not permission.has_permission(request, None):
        return Response({"detail": permission.message}, status=status.HTTP_403_FORBIDDEN)
    return None


class ImportBatchSourceDownloadView(APIView):
    """Telechargement authentifie du fichier CSV source d'un lot d'import
    (CDC 6.7, 7.6 ; ecart bloquant B10, revue de conformite fin de Lot 1).
    Ouverte a tout membre actif du club au niveau de la vue : la
    permission effective depend du TYPE du lot (joueurs ou cotisations
    historiques), verifiee objet par objet dans
    ``_import_batch_access_error`` (matrice 2.4, voir
    ``_IMPORT_BATCH_PERMISSION_BY_TYPE``) -- meme construction que
    ``MembershipApplicationPdfDownloadView``/
    ``can_access_membership_application_file`` un peu plus bas dans ce
    fichier."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request, pk: int):
        try:
            batch = _get_import_batch(pk)
        except ImportBatch.DoesNotExist:
            return Response({"detail": "Ce lot d'import n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        access_error = _import_batch_access_error(request, batch)
        if access_error is not None:
            return access_error

        if not batch.source_file:
            return Response({"detail": "Le fichier source de ce lot n'est pas disponible."}, status=status.HTTP_404_NOT_FOUND)

        return _csv_download(batch.source_file, f"import-{batch.pk}-source.csv")


def _csv_download(stored_file, filename: str) -> FileResponse:
    """CSV genere ou depose par le club : type et nom fixes cote serveur
    (jamais ceux du client), en piece jointe, sans sniffing."""

    response = FileResponse(
        stored_file.open("rb"), as_attachment=True, filename=filename, content_type="text/csv; charset=utf-8"
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


class ImportBatchReportDownloadView(APIView):
    """Telechargement authentifie du rapport d'un lot d'import (CDC 6.7,
    7.6 ; ecart bloquant B10). Meme permission que
    :class:`ImportBatchSourceDownloadView` (verifiee selon le type du lot,
    voir ``_import_batch_access_error``)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request, pk: int):
        try:
            batch = _get_import_batch(pk)
        except ImportBatch.DoesNotExist:
            return Response({"detail": "Ce lot d'import n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        access_error = _import_batch_access_error(request, batch)
        if access_error is not None:
            return access_error

        if not batch.report_file:
            return Response({"detail": "Le rapport de ce lot n'est pas disponible."}, status=status.HTTP_404_NOT_FOUND)

        return _csv_download(batch.report_file, f"import-{batch.pk}-rapport.csv")


# ---------------------------------------------------------------------------
# Adhesion et parrainage (CDC 4.3 ; tache 1.4b)
# ---------------------------------------------------------------------------


class AddPlayerWithSponsorView(APIView):
    """Ajout manuel d'un nouveau joueur « En attente », parrain obligatoire
    (CDC 4.3 etape 1). Reserve au President ou a un joueur recruteur
    designe (matrice 2.4, meme colonne que l'import CSV)."""

    permission_classes = _CLUB_MEMBER_GATE + [CanAddOrImportPlayers]

    def post(self, request):
        serializer = serializers.AddPlayerWithSponsorInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        club = get_active_club()
        try:
            sponsor = Membership.objects.get(pk=data["sponsor_membership_id"])
        except Membership.DoesNotExist:
            return Response({"detail": "Ce parrain n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            membership, application = clubs_services.add_player_with_sponsor(
                club=club,
                email=data["email"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                added_by=request.user,
                sponsor=sponsor,
                position=data["position"],
                position_detail=data.get("position_detail", ""),
                jersey_number=data.get("jersey_number"),
                birth_date=data.get("birth_date"),
                weight_kg=data.get("weight_kg"),
                height_cm=data.get("height_cm"),
                phone=data.get("phone", ""),
                requested_contribution_type_label=data.get("requested_contribution_type_label", ""),
            )
        except clubs_services.MembershipApplicationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except clubs_services.PlayerImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(
            {
                "membership_id": membership.id,
                "application": serializers.MembershipApplicationSerializer(application).data,
            },
            status=status.HTTP_201_CREATED,
        )


def _get_application(pk: int) -> MembershipApplication:
    # `objects` (tenant-aware) : deja scope au club actif du contexte
    # courant (CLAUDE.md regle n8) -- jamais `all_objects` ici. Un dossier
    # d'un AUTRE club leve `DoesNotExist`, jamais une fuite d'existence.
    return MembershipApplication.objects.select_related("membership", "membership__sponsor").get(pk=pk)


class MembershipApplicationPdfDownloadView(APIView):
    """Telechargement authentifie de la fiche d'adhesion PDF (CDC 6.7, 7.6 ;
    ecart bloquant B10, revue de conformite fin de Lot 1). Reserve au
    President, a l'adherent concerne et au parrain du dossier -- memes
    identites que celles deja verifiees pour la signature/le refus du
    parrain, voir ``apps.clubs.permissions.can_access_membership_application_file``
    (aucune nouvelle matrice de permission)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request, pk: int):
        try:
            application = _get_application(pk)
        except MembershipApplication.DoesNotExist:
            return Response({"detail": "Ce dossier d'adhésion n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        if not can_access_membership_application_file(user=request.user, application=application):
            return Response(
                {"detail": "Vous n'êtes pas autorisé à consulter la fiche de ce dossier d'adhésion."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not application.application_pdf_file:
            return Response({"detail": "La fiche d'adhésion n'a pas encore été générée."}, status=status.HTTP_404_NOT_FOUND)

        response = FileResponse(
            application.application_pdf_file.open("rb"),
            as_attachment=True,
            filename=f"adhesion-{application.membership_id}.pdf",
            content_type="application/pdf",
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class MembershipFeePaymentView(APIView):
    """Paiement des frais d'adhesion d'un dossier (CDC 4.3 etape 2 ; 4.4.4).
    Reserve au Tresorier ou au Tresorier adjoint (matrice 2.4, confirme par
    `finance-engine`). Enchaine automatiquement la generation de la fiche
    PDF et la notification du parrain une fois le montant entierement
    paye (etapes 3-4), puis verifie le passage « Inscrit » (etape 5)."""

    permission_classes = _CLUB_MEMBER_GATE + [CanRecordMembershipFeePayment]

    def post(self, request):
        serializer = serializers.MembershipFeePaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            application = _get_application(data["application_id"])
        except MembershipApplication.DoesNotExist:
            return Response({"detail": "Ce dossier d'adhésion n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            application = clubs_services.record_membership_fee_payment_for_application(
                application=application,
                amount=data["amount"],
                method=data["method"],
                paid_on=data["paid_on"],
                validated_by=request.user,
                reference=data.get("reference", ""),
                attachment=data.get("attachment"),
                client_uuid=data.get("client_uuid"),
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except TreasuryError as exc:
            return _treasury_error_response(exc)
        except clubs_services.MembershipApplicationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        # 200 dans tous les cas (cet endpoint ne renvoyait deja pas 201) ;
        # un rejeu renvoie l'etat courant du dossier.
        return Response(serializers.MembershipApplicationSerializer(application).data)


class SponsorSignatureView(APIView):
    """Signature du parrain (CDC 4.3 etape 4). Ouvert a
    tout membre actif du club : c'est le service qui verifie que
    l'appelant est bien le parrain designe de ce dossier precis (action
    « P » -- propres donnees -- de la matrice 2.4)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def post(self, request):
        serializer = serializers.SponsorSignInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            application = _get_application(data["application_id"])
        except MembershipApplication.DoesNotExist:
            return Response({"detail": "Ce dossier d'adhésion n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            application = clubs_services.sign_sponsor_application(
                application=application, sponsor_user=request.user
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except clubs_services.MembershipApplicationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipApplicationSerializer(application).data)


class SponsorRefusalView(APIView):
    """Refus du parrain, motif obligatoire (CDC 4.3, cas limite). Meme
    controle d'identite que :class:`SponsorSignatureView`."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def post(self, request):
        serializer = serializers.SponsorRefuseInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            application = _get_application(data["application_id"])
        except MembershipApplication.DoesNotExist:
            return Response({"detail": "Ce dossier d'adhésion n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            application = clubs_services.refuse_sponsor_application(
                application=application, sponsor_user=request.user, reason=data["reason"]
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except clubs_services.MembershipApplicationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipApplicationSerializer(application).data)


class SponsorReassignmentView(APIView):
    """Le President designe un nouveau parrain apres un refus (CDC 4.3,
    cas limite). Reserve au President (matrice 2.4)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubPresident]

    def post(self, request):
        serializer = serializers.SponsorReassignInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            application = _get_application(data["application_id"])
        except MembershipApplication.DoesNotExist:
            return Response({"detail": "Ce dossier d'adhésion n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            new_sponsor = Membership.objects.get(pk=data["new_sponsor_membership_id"])
        except Membership.DoesNotExist:
            return Response({"detail": "Ce joueur n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            application = clubs_services.reassign_sponsor(
                application=application, president_user=request.user, new_sponsor=new_sponsor
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except clubs_services.MembershipApplicationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipApplicationSerializer(application).data)


# ---------------------------------------------------------------------------
# Assistant de creation de club (CDC 1.4, 4.1 ; tache 1.9 ; PUBLIC, non
# authentifie -- docs/ecrans/clubs-creation.md)
# ---------------------------------------------------------------------------


class PublicClubCreationSettingsView(APIView):
    """Parametres publics de l'etape 3 de l'assistant (spec §4.3), avant
    toute authentification (CDC 7.6 : limitation de requetes)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ClubCreationSettingsRateThrottle]

    def get(self, request):
        data = club_creation.get_public_creation_settings()
        return Response(serializers.PublicClubCreationSettingsSerializer(data).data)


class ClubCreationView(APIView):
    """Envoi final de l'assistant (spec §5) : cree le club, sa licence
    d'essai et son fondateur-President en une seule transaction. Point
    d'acces public (CDC 7.6 : limitation de requetes) -- meme raison que
    ``apps.accounts.views.LoginView`` pour l'exclusion explicite de
    l'authentification par defaut."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ClubCreationRateThrottle]

    def post(self, request):
        serializer = serializers.ClubCreationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = club_creation.create_club_with_founder(
                idempotency_key=data["idempotency_key"],
                name=data["name"],
                city=data["city"],
                country=data["country"],
                currency=data["currency"],
                timezone_name=data["timezone_name"],
                logo=data.get("logo"),
                primary_color=data.get("primary_color", ""),
                secondary_color=data.get("secondary_color", ""),
                email=data["email"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                position=data["position"],
                phone=data.get("phone", ""),
                position_detail=data.get("position_detail", ""),
                jersey_number=data.get("jersey_number"),
                birth_date=data.get("birth_date"),
                weight_kg=data.get("weight_kg"),
                height_cm=data.get("height_cm"),
                terms_version_id=data["terms_version_id"],
            )
        except club_creation.TermsVersionOutdatedError as exc:
            latest = exc.latest_terms_version
            return Response(
                {
                    "code": "terms_version_outdated",
                    "detail": str(exc),
                    "terms_version": TermsVersionSerializer(latest).data if latest is not None else None,
                },
                status=status.HTTP_409_CONFLICT,
            )
        except club_creation.EmailAlreadyUsedError as exc:
            return Response(
                {"code": "email_already_used", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        user = result.user
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSummarySerializer(user).data,
                "club": _serialize_club_identity_summary(result.club, request),
                "licence": {"status": result.licence.status, "end_date": result.licence.end_date},
                "must_change_password": user.must_change_password,
                "terms_acceptance_required": False,
            },
            status=status.HTTP_200_OK if result.idempotent_replay else status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Mon profil (CDC 4.1, 4.2, 4.17 ; comptes-mon-profil.md ; tache 1.9,
# slice Lot 1 -- voir apps.clubs.profile_services pour le detail du
# perimetre couvert/differe)
# ---------------------------------------------------------------------------


class MyProfileView(APIView):
    """Lecture agregee de « Mon profil » (slice Lot 1). Reserve a un
    membre actif du club, pour SES PROPRES donnees uniquement (2.4 « P ») :
    ``apps.core.services.resolve_active_membership`` ne resout jamais que
    l'adhesion de ``request.user`` lui-meme."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request):
        return Response(profile_services.get_my_profile(request.user, request))


# ---------------------------------------------------------------------------
# Identite du club (CDC 3.5 ; club-comite-bureau.md §4.1 ; tache 1.9)
# ---------------------------------------------------------------------------


class ClubIdentityView(APIView):
    """Carte « Identite du club » (club-comite-bureau.md §3, §4.1).

    Lecture : tout membre actif du club. Ecriture : President uniquement.
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [permission() for permission in _CLUB_MEMBER_GATE + [IsActiveClubMember]]
        return [permission() for permission in _CLUB_MEMBER_GATE + [IsClubPresident]]

    def get(self, request):
        club = get_active_club()
        is_president = has_any_role(request.user, {MembershipRole.Role.PRESIDENT}, club=club)
        return Response(
            serializers.ClubIdentitySerializer(
                club, context={"is_president": is_president, "request": request}
            ).data
        )

    def patch(self, request):
        club = get_active_club()
        serializer = serializers.ClubIdentityInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            club = clubs_services.update_club_identity(
                president_user=request.user, club=club, **serializer.validated_data
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except clubs_services.ClubIdentityError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(
            serializers.ClubIdentitySerializer(
                club, context={"is_president": True, "request": request}
            ).data
        )


# ---------------------------------------------------------------------------
# Liste / recherche des membres du club actif (club-comite-bureau.md §3.6
# "Effectif" ; PlayerSearch pour le champ Parrain §4.5 et le choix de
# titulaire de role §4.1/4.7 ; CDC 2.4, 4.2 ; CLAUDE.md regle n15 -- tache
# de complement au trou releve pendant l'implementation frontend 1.9)
# ---------------------------------------------------------------------------


class PlayerListView(APIView):
    """Liste/recherche des membres du club actif : memes champs que
    :class:`PlayerPublicCardSerializer` (identite, poste/numero, roles,
    statut d'adhesion), aucune donnee financiere ni medicale.

    Ouvert a tout membre actif du club (matrice 2.4, colonne « L » --
    besoin transverse : recherche de parrain (PlayerSearch, CLAUDE.md
    regle n15), effectif (club-comite-bureau.md §3.6), choix d'un
    titulaire de role/Capitaine/successeur a la presidence -- ce n'est
    pas reserve au President, exactement comme ``PlayerCardView`` et
    ``ClubIdentityView`` en lecture).

    Isolation multi-tenant : ``Membership.objects`` (manager tenant-aware,
    CLAUDE.md regle n8) -- jamais ``all_objects`` -- ne renvoie donc que
    les membres du club actif du contexte courant (CLAUDE.md regle n9).
    """

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    #: Limite de resultats sur une recherche texte : choix technique de
    #: securite/performance (pas une regle du CDC), documente au compte
    #: rendu de la tache. Sans recherche texte (ex. filtres seuls pour
    #: l'onglet « Effectif »), aucune limite n'est appliquee : le CDC
    #: prevoit explicitement une DataTable pour > 30 joueurs (§3.6).
    SEARCH_RESULT_LIMIT = 50

    def get(self, request):
        query_serializer = serializers.PlayerListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        # `objects` (tenant-aware) : deja scope au club actif du contexte
        # courant (CLAUDE.md regle n8) -- jamais `all_objects` ici.
        queryset = Membership.objects.select_related("user")

        search = params.get("search", "").strip()
        position = params.get("position", "")
        membership_status = params.get("status", "")
        role = params.get("role", "")

        if position:
            queryset = queryset.filter(position=position)
        if membership_status:
            # CDC 10.2 n16 (precise en 4.12) : le filtre "En attente" est
            # reserve aux roles autorises a voir ce motif (le President,
            # lui, decide implicitement via ce meme role) -- pas de fuite
            # par le filtre pour un coequipier non autorise (resultat vide,
            # jamais une erreur qui confirmerait l'existence du filtre).
            if membership_status == Membership.Status.PENDING and not has_any_role(
                request.user, clubs_services.PENDING_STATUS_VISIBLE_ROLES
            ):
                queryset = queryset.none()
            else:
                queryset = queryset.filter(status=membership_status)
        if role:
            queryset = queryset.filter(roles__role=role, roles__revoked_at__isnull=True)
        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search)
            )

        queryset = queryset.order_by("user__last_name", "user__first_name").distinct()

        if search:
            queryset = queryset[: self.SEARCH_RESULT_LIMIT]

        members = list(queryset)
        club = get_active_club()
        return Response(
            serializers.PlayerPublicCardSerializer(
                members,
                many=True,
                context={
                    "request": request,
                    "unavailable_ids": player_stats.unavailable_membership_ids(club, members),
                },
            ).data
        )


class PlayerCardView(APIView):
    """Fiche publique d'un joueur du club (club-comite-bureau.md §4.7) :
    identite, poste/numero, roles, statut d'adhesion. Aucune donnee
    financiere ni medicale. Ouvert a tout membre actif du club --
    l'isolation multi-tenant est garantie par le manager tenant-aware
    (``Membership.objects``, CLAUDE.md regle n8) : la fiche d'un joueur
    d'un AUTRE club repond 404, jamais 403 (aucune fuite d'existence)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request, membership_id: int):
        try:
            membership = Membership.objects.select_related("user").get(pk=membership_id)
        except Membership.DoesNotExist:
            return Response({"detail": "Ce joueur n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            serializers.PlayerPublicCardSerializer(
                membership,
                context={
                    "request": request,
                    "unavailable_ids": player_stats.unavailable_membership_ids(get_active_club(), [membership]),
                },
            ).data
        )


class MembershipApplicationCancellationView(APIView):
    """Annulation de l'adhesion par le President apres un refus du parrain
    (CDC 4.3, cas limite). Reserve au President (matrice 2.4)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubPresident]

    def post(self, request):
        serializer = serializers.MembershipApplicationCancelInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            application = _get_application(data["application_id"])
        except MembershipApplication.DoesNotExist:
            return Response({"detail": "Ce dossier d'adhésion n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)

        try:
            application = clubs_services.cancel_membership_application(
                application=application,
                president_user=request.user,
                reason=data["reason"],
                disposition=data["disposition"],
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except TreasuryError as exc:
            return _treasury_error_response(exc)
        except clubs_services.MembershipApplicationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return _validation_error_response(exc)

        return Response(serializers.MembershipApplicationSerializer(application).data)


def _applications_queryset():
    return MembershipApplication.objects.select_related(
        "membership", "membership__user", "membership__sponsor", "membership__sponsor__user",
        "membership_fee_payment",
    )


class MembershipApplicationByMembershipView(APIView):
    """Dossier d'adhesion d'un joueur (lecture ; CDC 4.3). Memes identites
    autorisees que le telechargement de la fiche (President, adherent,
    parrain) : aucune nouvelle matrice de permission."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request, membership_id: int):
        try:
            application = _applications_queryset().get(membership_id=membership_id)
        except MembershipApplication.DoesNotExist:
            return Response({"detail": "Ce joueur n'a pas de dossier d'adhésion dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        # Le Tresorier et son adjoint (matrice 2.4 : enregistrement des
        # paiements) doivent voir le dossier pour enregistrer les frais
        # d'adhesion ; la fiche PDF reste, elle, reservee aux trois identites.
        can_read = can_access_membership_application_file(
            user=request.user, application=application
        ) or has_any_role(
            request.user, {MembershipRole.Role.TREASURER, MembershipRole.Role.ASSISTANT_TREASURER}
        )
        if not can_read:
            return Response(
                {"detail": "Vous n'êtes pas autorisé à consulter ce dossier d'adhésion."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(serializers.MembershipApplicationSerializer(application, context={"request": request}).data)


class PendingSponsorSignaturesView(APIView):
    """Dossiers dont l'appelant est le parrain designe et dont la fiche est
    prete a signer (fiche generee, decision en attente ; CDC 4.3 etape 4).
    Donnees propres a l'appelant uniquement."""

    permission_classes = _CLUB_MEMBER_GATE + [IsActiveClubMember]

    def get(self, request):
        queryset = _applications_queryset().filter(
            membership__sponsor__user=request.user,
            sponsor_decision=MembershipApplication.SponsorDecision.PENDING,
            generated_at__isnull=False,
            resolved_at__isnull=True,
        ).order_by("generated_at")
        return Response(serializers.MembershipApplicationSerializer(queryset, many=True, context={"request": request}).data)


class PendingPresidentDecisionsView(APIView):
    """Dossiers que le President doit suivre (CDC 4.3, cas limites) :
    ``refused`` (decision a prendre : autre parrain ou annulation) et
    ``awaiting_sponsor`` (parrain sans reponse apres 7 jours : alerte
    seulement, aucune action supplementaire -- 10.3 n° 71)."""

    permission_classes = _CLUB_MEMBER_GATE + [IsClubPresident]

    def get(self, request):
        base = _applications_queryset().filter(resolved_at__isnull=True)
        ctx = {"request": request}
        refused = base.filter(sponsor_decision=MembershipApplication.SponsorDecision.REFUSED).order_by("id")
        awaiting = base.filter(
            sponsor_decision=MembershipApplication.SponsorDecision.PENDING, president_alerted_at__isnull=False
        ).order_by("president_alerted_at")
        return Response(
            {
                "refused": serializers.MembershipApplicationSerializer(refused, many=True, context=ctx).data,
                "awaiting_sponsor": serializers.MembershipApplicationSerializer(awaiting, many=True, context=ctx).data,
            }
        )


# ---------------------------------------------------------------------------
# Tableau de bord du Président et du Vice-président (lecture seule)
# ---------------------------------------------------------------------------


class BoardDashboardView(APIView):
    """Toutes les cartes du tableau de bord en un appel (fiche
    club-tableau-de-bord-bureau §10). Permission : Président ou Vice-président
    (matrice 2.4). Aucune écriture, aucune entrée de journal."""

    permission_classes = _CLUB_MEMBER_GATE + [IsPresidentOrVicePresident]

    def get(self, request):
        club = get_active_club()
        try:
            period = board_dashboard.period_from_query(club, request.query_params)
            data = board_dashboard.board_cards(club, period, request=request)
        except (TreasuryValidationError, board_dashboard.BoardDashboardError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except TenantMismatchError:
            return Response({"detail": "Club actif incohérent."}, status=status.HTTP_403_FORBIDDEN)
        return Response(data)


class BoardDashboardSectionView(APIView):
    """Détail d'une carte pour sa modale : ``?period=…&limit=&offset=&only=``."""

    permission_classes = _CLUB_MEMBER_GATE + [IsPresidentOrVicePresident]

    def get(self, request, section):
        club = get_active_club()
        if section not in board_dashboard.ALL_SECTIONS:
            return Response({"detail": "Section inconnue du tableau de bord."}, status=status.HTTP_404_NOT_FOUND)
        try:
            period = board_dashboard.period_from_query(club, request.query_params)
            limit, offset = board_dashboard.paging_from_query(request.query_params)
            data = board_dashboard.board_section(
                club,
                section,
                period,
                limit=limit,
                offset=offset,
                only=request.query_params.get("only") or None,
                request=request,
            )
        except (TreasuryValidationError, board_dashboard.BoardDashboardError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except TenantMismatchError:
            return Response({"detail": "Club actif incohérent."}, status=status.HTTP_403_FORBIDDEN)
        return Response(data)
