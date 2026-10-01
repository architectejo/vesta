"""Vues DRF de l'app treasury."""

import datetime

from django.db.models import Q
from django.http import FileResponse, HttpResponse
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.permissions import IsActiveClubMember
from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence
from apps.core.services import resolve_active_membership
from apps.core.tenant import NoActiveClubError, get_active_club
from apps.accounts.services import InvalidPinError, PinError, PinLockedError
from apps.clubs.models import Membership
from apps.treasury import services
from apps.treasury.models import (
    ContributionType,
    Expense,
    ExpenseAttachment,
    ExpenseCategory,
    Payment,
    PaymentReversal,
    SocialAssistanceRequest,
    SocialAssistanceScale,
)
from apps.treasury import serializers as serializers_mod
from apps.treasury.permissions import (
    CanDecidePaymentReversal,
    CanDerogateExpenses,
    CanImportContributions,
    CanManageAssistanceScales,
    CanManageExpenseCategories,
    CanProcessAssistanceRequests,
    CanReadContributionGrid,
    CanReadContributionTypes,
    CanReadExpenses,
    CanReadTreasuryDashboard,
    CanRecordPayments,
    CanRequestPaymentReversal,
    CanSubmitExpenses,
    CanUploadExpenseReceipts,
    CanValidateExpenses,
    CanWriteContributionTypes,
    assistance_requests_visible_to,
    payments_visible_to,
)
from apps.treasury.serializers import (
    ContributionTypeCreateSerializer,
    ContributionTypeInputSerializer,
    ContributionTypeSerializer,
    DerogationSerializer,
    ExpenseCategoryCreateSerializer,
    ExpenseCategoryInputSerializer,
    ExpenseCategorySerializer,
    ExpenseCreateSerializer,
    ExpenseSerializer,
    MyBalanceSerializer,
    PinSerializer,
    ReasonSerializer,
    ReceiptUploadSerializer,
    SocialAssistancePreviewQuerySerializer,
    SocialAssistanceRequestCreateSerializer,
    SocialAssistanceRequestSerializer,
    SocialAssistanceScaleCreateSerializer,
    SocialAssistanceScaleInputSerializer,
    SocialAssistanceScaleSerializer,
    serialize_eligibility,
)


_GATE = [IsAuthenticated, HasCompletedPasswordSetup, HasAcceptedLatestTerms, HasUsableLicence]


def _error(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class MyBalanceView(APIView):
    permission_classes = _GATE

    def get(self, request):
        try:
            membership = resolve_active_membership(request.user, club=get_active_club())
        except NoActiveClubError:
            return Response({"detail": "Aucune adhésion active pour ce club."}, status=403)
        try:
            summary = services.get_balance_summary(membership)
        except services.TreasuryError as exc:
            return _error(exc)
        return Response(MyBalanceSerializer({"membership": membership, "summary": summary}).data)


_PAYMENT_NOT_FOUND = "Ce paiement n'existe pas dans ce club."


class _PaymentFileDownloadView(APIView):
    """Téléchargement authentifié d'un fichier privé de paiement (CDC 6.7 ;
    CLAUDE.md règle n° 10). Même principe que les vues de téléchargement de
    l'app clubs : fichier lu depuis le stockage privé, jamais d'URL publique.

    Lecture réservée à la ligne « Enregistrement des paiements » de la
    matrice 2.4 : Président, Vice-président, Trésorier, Trésorier adjoint,
    et le joueur pour ses propres paiements. Un paiement d'un autre club ou
    non visible par l'utilisateur répond 404 (jamais 403 : aucune fuite
    d'existence).
    """

    permission_classes = _GATE + [IsActiveClubMember]
    file_field: str = ""
    missing_message: str = ""
    filename_pattern: str = ""

    def get(self, request, pk: int):
        try:
            payment = payments_visible_to(request.user).get(pk=pk)
        except Payment.DoesNotExist:
            return Response({"detail": _PAYMENT_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        stored_file = getattr(payment, self.file_field)
        if not stored_file:
            return Response({"detail": self.missing_message}, status=status.HTTP_404_NOT_FOUND)

        extension = stored_file.name.rsplit(".", 1)[-1].lower() if "." in stored_file.name else ""
        if not (extension.isascii() and extension.isalnum() and len(extension) <= 5):
            extension = "bin"
        return FileResponse(
            stored_file.open("rb"),
            as_attachment=True,
            filename=self.filename_pattern.format(pk=payment.pk, ext=extension),
        )


class PaymentAttachmentDownloadView(_PaymentFileDownloadView):
    """Pièce jointe justificative d'un paiement (CDC 4.4.4)."""

    file_field = "attachment"
    missing_message = "Ce paiement n'a pas de pièce jointe."
    filename_pattern = "paiement-{pk}-justificatif.{ext}"


class PaymentReceiptDownloadView(_PaymentFileDownloadView):
    """Reçu numéroté d'un paiement validé (CDC 4.4.4)."""

    file_field = "receipt_file"
    missing_message = "Le reçu de ce paiement n'est pas encore disponible."
    filename_pattern = "paiement-{pk}-recu.{ext}"


class ContributionTypeListView(APIView):
    permission_classes = _GATE + [CanReadContributionTypes]

    def get(self, request):
        status_filter = request.query_params.get("status", ContributionType.Status.ACTIVE)
        if status_filter not in ContributionType.Status.values:
            return Response({"detail": "État de type de cotisation inconnu."}, status=400)
        types = ContributionType.objects.filter(status=status_filter).order_by("name")
        return Response(ContributionTypeSerializer(types, many=True).data)

    def post(self, request):
        if not CanWriteContributionTypes().has_permission(request, self):
            return Response({"detail": CanWriteContributionTypes.message}, status=403)
        serializer = ContributionTypeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ctype = services.create_contribution_type(
                club=get_active_club(), created_by=request.user, **serializer.validated_data
            )
        except services.TreasuryError as exc:
            return _error(exc)
        return Response(ContributionTypeSerializer(ctype).data, status=status.HTTP_201_CREATED)


class ContributionTypeDetailView(APIView):
    permission_classes = _GATE + [CanReadContributionTypes]

    def get_object(self, pk):
        return ContributionType.objects.get(pk=pk)

    def get(self, request, pk):
        try:
            return Response(ContributionTypeSerializer(self.get_object(pk)).data)
        except ContributionType.DoesNotExist:
            return Response({"detail": "Type de cotisation introuvable dans ce club."}, status=404)

    def patch(self, request, pk):
        if not CanWriteContributionTypes().has_permission(request, self):
            return Response({"detail": CanWriteContributionTypes.message}, status=403)
        serializer = ContributionTypeInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            ctype = services.update_contribution_type(
                contribution_type=self.get_object(pk), updated_by=request.user, **serializer.validated_data
            )
        except ContributionType.DoesNotExist:
            return Response({"detail": "Type de cotisation introuvable dans ce club."}, status=404)
        except services.TreasuryError as exc:
            return _error(exc)
        return Response(ContributionTypeSerializer(ctype).data)

    def post(self, request, pk):
        if request.data.get("action") != "archive":
            return Response({"detail": "Action inconnue."}, status=400)
        if not CanWriteContributionTypes().has_permission(request, self):
            return Response({"detail": CanWriteContributionTypes.message}, status=403)
        try:
            ctype = services.archive_contribution_type(
                contribution_type=self.get_object(pk), archived_by=request.user
            )
        except ContributionType.DoesNotExist:
            return Response({"detail": "Type de cotisation introuvable dans ce club."}, status=404)
        except services.TreasuryError as exc:
            return _error(exc)
        return Response(ContributionTypeSerializer(ctype).data)


# ---------------------------------------------------------------------------
# Capacites et devise (tache 2.2) : remplacent toute copie de la matrice 2.4
# cote interface.
# ---------------------------------------------------------------------------


class TreasuryCapabilitiesView(APIView):
    """Capacités trésorerie de l'utilisateur dans le club actif et devise du
    club. Lecture : tout membre actif (chacun ne voit que ses capacités)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        club = get_active_club()
        try:
            currency = services.get_club_currency(club)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(
            {"currency": currency, "capabilities": services.get_treasury_capabilities(request.user, club)}
        )


# ---------------------------------------------------------------------------
# Depenses (CDC 4.5.1, 4.5.2)
# ---------------------------------------------------------------------------

_EXPENSE_NOT_FOUND = "Cette dépense n'existe pas dans ce club."
_CATEGORY_NOT_FOUND = "Catégorie de dépense introuvable dans ce club."
_REQUEST_NOT_FOUND = "Cette demande d'assistance n'existe pas dans ce club."
_SCALE_NOT_FOUND = "Barème introuvable dans ce club."
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _treasury_error(exc):
    """Erreur métier de trésorerie -> réponse HTTP en français."""

    if isinstance(exc, services.TreasuryPermissionError):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    if isinstance(exc, services.ExpenseReleaseBlockedError):
        return Response(
            {"detail": str(exc), "code": "expense_release_blocked"}, status=status.HTTP_409_CONFLICT
        )
    if isinstance(exc, services.LedgerFrozenError):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, services.LedgerKeyError):
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _pin_error(exc: PinError):
    """Même traduction que ``apps.clubs.views._pin_error_response`` (CDC 7.2)."""

    if isinstance(exc, PinLockedError):
        return Response({"detail": str(exc), "locked_until": exc.locked_until}, status=status.HTTP_423_LOCKED)
    if isinstance(exc, InvalidPinError):
        return Response(
            {"detail": str(exc), "attempts_remaining": exc.attempts_remaining},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _not_found(message):
    return Response({"detail": message}, status=status.HTTP_404_NOT_FOUND)


def _paginate(request, queryset):
    """Liste « N derniers + Voir plus » (CDC 3.3) : ``limit``/``offset``."""

    try:
        limit = int(request.query_params.get("limit", DEFAULT_PAGE_SIZE))
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError):
        return None, None, None
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    count = queryset.count()
    items = list(queryset[offset:offset + limit])
    next_offset = offset + limit if offset + limit < count else None
    return items, count, next_offset


def _status_filter(request, choices):
    raw = request.query_params.get("status", "")
    if not raw:
        return []
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if any(value not in choices for value in values):
        return None
    return values


def _expense_queryset():
    return Expense.objects.select_related(
        "category", "created_by", "released_by", "derogation__granted_by"
    ).prefetch_related("attachments")


def _expense_response(expense, *, status_code=status.HTTP_200_OK):
    expense = _expense_queryset().get(pk=expense.pk)
    today = services.get_club_today(expense.club)
    return Response(ExpenseSerializer(expense, context={"today": today}).data, status=status_code)


class ExpenseCategoryListView(APIView):
    """Catégories de dépense. Lecture : Pdt, VP, Trés, Adj ; écriture : Pdt,
    Trés (matrice 2.4)."""

    permission_classes = _GATE + [CanReadExpenses]

    def get(self, request):
        status_filter = request.query_params.get("status", ExpenseCategory.Status.ACTIVE)
        if status_filter not in ExpenseCategory.Status.values:
            return Response({"detail": "État de catégorie inconnu."}, status=status.HTTP_400_BAD_REQUEST)
        categories = ExpenseCategory.objects.filter(status=status_filter).order_by("name")
        return Response(ExpenseCategorySerializer(categories, many=True).data)

    def post(self, request):
        if not CanManageExpenseCategories().has_permission(request, self):
            return Response({"detail": CanManageExpenseCategories.message}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExpenseCategoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            category = services.create_expense_category(
                club=get_active_club(), created_by=request.user, **serializer.validated_data
            )
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(ExpenseCategorySerializer(category).data, status=status.HTTP_201_CREATED)


class ExpenseCategoryDetailView(APIView):
    permission_classes = _GATE + [CanReadExpenses]

    def get(self, request, pk):
        try:
            return Response(ExpenseCategorySerializer(ExpenseCategory.objects.get(pk=pk)).data)
        except ExpenseCategory.DoesNotExist:
            return _not_found(_CATEGORY_NOT_FOUND)

    def patch(self, request, pk):
        if not CanManageExpenseCategories().has_permission(request, self):
            return Response({"detail": CanManageExpenseCategories.message}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExpenseCategoryInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            category = services.update_expense_category(
                category=ExpenseCategory.objects.get(pk=pk), updated_by=request.user, **serializer.validated_data
            )
        except ExpenseCategory.DoesNotExist:
            return _not_found(_CATEGORY_NOT_FOUND)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(ExpenseCategorySerializer(category).data)

    def post(self, request, pk):
        if request.data.get("action") != "archive":
            return Response({"detail": "Action inconnue."}, status=status.HTTP_400_BAD_REQUEST)
        if not CanManageExpenseCategories().has_permission(request, self):
            return Response({"detail": CanManageExpenseCategories.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            category = services.archive_expense_category(
                category=ExpenseCategory.objects.get(pk=pk), archived_by=request.user
            )
        except ExpenseCategory.DoesNotExist:
            return _not_found(_CATEGORY_NOT_FOUND)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(ExpenseCategorySerializer(category).data)


class ExpenseListView(APIView):
    """Dépenses du club. Lecture : Pdt, VP, Trés, Adj ; saisie : Trés, Adj
    (matrice 2.4). Filtres ``status`` (valeurs séparées par des virgules),
    ``category`` ; pagination ``limit``/``offset``."""

    permission_classes = _GATE + [CanReadExpenses]

    def get(self, request):
        statuses = _status_filter(request, Expense.Status.values)
        if statuses is None:
            return Response({"detail": "État de dépense inconnu."}, status=status.HTTP_400_BAD_REQUEST)
        queryset = _expense_queryset().order_by("-created_at", "-pk")
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        category = request.query_params.get("category")
        if category:
            if not category.isdigit():
                return Response({"detail": "Catégorie invalide."}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(category_id=int(category))
        items, count, next_offset = _paginate(request, queryset)
        if items is None:
            return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
        today = services.get_club_today(get_active_club())
        return Response(
            {
                "count": count,
                "next_offset": next_offset,
                "results": ExpenseSerializer(items, many=True, context={"today": today}).data,
            }
        )

    def post(self, request):
        if not CanSubmitExpenses().has_permission(request, self):
            return Response({"detail": CanSubmitExpenses.message}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExpenseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            category = ExpenseCategory.objects.get(pk=data["category_id"])
        except ExpenseCategory.DoesNotExist:
            return _not_found(_CATEGORY_NOT_FOUND)
        beneficiary = None
        if data.get("beneficiary_membership_id"):
            try:
                beneficiary = Membership.objects.get(pk=data["beneficiary_membership_id"])
            except Membership.DoesNotExist:
                return _not_found("Joueur bénéficiaire introuvable dans ce club.")
        try:
            expense = services.create_expense(
                club=get_active_club(),
                created_by=request.user,
                category=category,
                amount=data["amount"],
                beneficiary_name=data.get("beneficiary_name", ""),
                beneficiary_membership=beneficiary,
                reason=data["reason"],
                expense_date=data["expense_date"],
                attachment=data.get("attachment"),
            )
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return _expense_response(expense, status_code=status.HTTP_201_CREATED)


class ExpenseSummaryView(APIView):
    """Blocage des libérations et caisse disponible (CDC 4.4.6, 4.5.2)."""

    permission_classes = _GATE + [CanReadExpenses]

    def get(self, request):
        club = get_active_club()
        try:
            check = services.can_release_expense(club)
            cash = services.get_available_cash(club)
            currency = services.get_club_currency(club)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(
            {
                "can_release": check.allowed,
                "reason": check.reason,
                "blocking_expense_ids": list(check.blocking_expense_ids),
                "available_cash": f"{cash:.2f}",
                "currency": currency,
            }
        )


class ExpenseDetailView(APIView):
    permission_classes = _GATE + [CanReadExpenses]

    def get(self, request, pk):
        try:
            expense = _expense_queryset().get(pk=pk)
        except Expense.DoesNotExist:
            return _not_found(_EXPENSE_NOT_FOUND)
        return _expense_response(expense)


class _ExpenseActionView(APIView):
    """Base des actions sur une dépense : l'objet est cherché dans le club
    actif (404 sinon, jamais 403)."""

    permission_classes = _GATE + [CanReadExpenses]
    action_permission = None
    input_serializer = None

    def post(self, request, pk):
        permission = self.action_permission()
        if not permission.has_permission(request, self):
            return Response({"detail": permission.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            expense = Expense.objects.get(pk=pk)
        except Expense.DoesNotExist:
            return _not_found(_EXPENSE_NOT_FOUND)
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            expense = self.perform(request, expense, serializer.validated_data)
        except PinError as exc:
            return _pin_error(exc)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return _expense_response(expense)

    def perform(self, request, expense, data):  # pragma: no cover - abstrait
        raise NotImplementedError


class ExpenseRefuseView(_ExpenseActionView):
    """Refus motivé (Pdt ou VP), sans PIN."""

    action_permission = CanValidateExpenses
    input_serializer = ReasonSerializer

    def perform(self, request, expense, data):
        return services.refuse_expense(expense=expense, refused_by=request.user, reason=data["reason"])


class ExpenseReleaseView(_ExpenseActionView):
    """Validation et libération (Pdt ou VP), code PIN exigé (CDC 7.2)."""

    action_permission = CanValidateExpenses
    input_serializer = PinSerializer

    def perform(self, request, expense, data):
        return services.release_expense(expense=expense, released_by=request.user, pin=data["pin"])


class ExpenseDerogationView(_ExpenseActionView):
    """Libération par dérogation (Président seul), motif + PIN."""

    action_permission = CanDerogateExpenses
    input_serializer = DerogationSerializer

    def perform(self, request, expense, data):
        return services.release_expense_with_derogation(
            expense=expense, president=request.user, reason=data["reason"], pin=data["pin"]
        )


class ExpenseReceiptUploadView(_ExpenseActionView):
    """Téléversement du justificatif (Trés ou Adj) : Libérée ou Non
    justifiée -> Justifiée."""

    action_permission = CanUploadExpenseReceipts
    input_serializer = ReceiptUploadSerializer

    def perform(self, request, expense, data):
        return services.justify_expense(expense=expense, uploaded_by=request.user, file=data["file"])


def _file_response(stored_file, filename_pattern, pk):
    extension = stored_file.name.rsplit(".", 1)[-1].lower() if "." in stored_file.name else ""
    if not (extension.isascii() and extension.isalnum() and len(extension) <= 5):
        extension = "bin"
    return FileResponse(
        stored_file.open("rb"), as_attachment=True, filename=filename_pattern.format(pk=pk, ext=extension)
    )


class ExpenseAttachmentDownloadView(APIView):
    """Téléchargement authentifié d'une pièce de dépense (CDC 6.7 ; CLAUDE.md
    règle n° 10). Lecteurs des dépenses uniquement ; autre club = 404."""

    permission_classes = _GATE + [CanReadExpenses]

    def get(self, request, pk: int):
        try:
            attachment = ExpenseAttachment.objects.get(pk=pk)
        except ExpenseAttachment.DoesNotExist:
            return _not_found("Cette pièce jointe n'existe pas dans ce club.")
        return _file_response(attachment.file, "depense-{pk}-piece.{ext}", attachment.expense_id)


# ---------------------------------------------------------------------------
# Assistance sociale (CDC 4.5.3)
# ---------------------------------------------------------------------------


class SocialAssistanceScaleListView(APIView):
    """Barème du club : lecture par tout membre actif (montant et délai
    affichés avant l'envoi) ; écriture Pdt ou Trés (Q11, provisoire)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        status_filter = request.query_params.get("status", SocialAssistanceScale.Status.ACTIVE)
        if status_filter not in SocialAssistanceScale.Status.values:
            return Response({"detail": "État de barème inconnu."}, status=status.HTTP_400_BAD_REQUEST)
        scales = (
            SocialAssistanceScale.objects.filter(status=status_filter)
            .select_related("expense_category")
            .order_by("event_type", "pk")
        )
        return Response(SocialAssistanceScaleSerializer(scales, many=True).data)

    def post(self, request):
        if not CanManageAssistanceScales().has_permission(request, self):
            return Response({"detail": CanManageAssistanceScales.message}, status=status.HTTP_403_FORBIDDEN)
        serializer = SocialAssistanceScaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        try:
            category = ExpenseCategory.objects.get(pk=data.pop("expense_category_id"))
        except ExpenseCategory.DoesNotExist:
            return _not_found(_CATEGORY_NOT_FOUND)
        try:
            scale = services.create_social_assistance_scale(
                club=get_active_club(), created_by=request.user, expense_category=category, **data
            )
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(SocialAssistanceScaleSerializer(scale).data, status=status.HTTP_201_CREATED)


class SocialAssistanceScaleDetailView(APIView):
    permission_classes = _GATE + [CanManageAssistanceScales]

    def patch(self, request, pk):
        serializer = SocialAssistanceScaleInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data)
        try:
            scale = SocialAssistanceScale.objects.get(pk=pk)
            if "expense_category_id" in changes:
                changes["expense_category"] = ExpenseCategory.objects.get(pk=changes.pop("expense_category_id"))
            scale = services.update_social_assistance_scale(scale=scale, updated_by=request.user, **changes)
        except SocialAssistanceScale.DoesNotExist:
            return _not_found(_SCALE_NOT_FOUND)
        except ExpenseCategory.DoesNotExist:
            return _not_found(_CATEGORY_NOT_FOUND)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(SocialAssistanceScaleSerializer(scale).data)

    def post(self, request, pk):
        if request.data.get("action") != "archive":
            return Response({"detail": "Action inconnue."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            scale = services.archive_social_assistance_scale(
                scale=SocialAssistanceScale.objects.get(pk=pk), archived_by=request.user
            )
        except SocialAssistanceScale.DoesNotExist:
            return _not_found(_SCALE_NOT_FOUND)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(SocialAssistanceScaleSerializer(scale).data)


def _own_membership(request):
    return resolve_active_membership(request.user, club=get_active_club())


class SocialAssistancePreviewView(APIView):
    """Aperçu affiché avant l'envoi : éligibilité, montant du barème et délai
    (CDC 4.5.3). Chaque joueur pour lui-même."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        query = SocialAssistancePreviewQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            preview = services.get_social_assistance_preview(
                membership=_own_membership(request),
                event_type=query.validated_data["event_type"],
                event_date=query.validated_data["event_date"],
            )
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        scale = preview.scale
        return Response(
            {
                "scale_configured": scale is not None,
                "planned_amount": f"{scale.amount:.2f}" if scale else None,
                "processing_days": scale.processing_days if scale else None,
                "eligibility": serialize_eligibility(preview.eligibility),
            }
        )


def _request_queryset(user):
    return assistance_requests_visible_to(user).select_related("expense")


def _eligibility_context(request, requests):
    """Éligibilité courante (10.2 n° 37), calculée par les services, pour le
    Président ou le VP qui traitent les demandes encore en attente."""

    if not CanProcessAssistanceRequests().has_permission(request, None):
        return {}
    return {
        item.pk: services.get_social_assistance_eligibility(item.membership, item.event_date)
        for item in requests
        if item.status == SocialAssistanceRequest.Status.SUBMITTED
    }


class SocialAssistanceRequestListView(APIView):
    """Demandes d'assistance. Tout joueur envoie et suit ses propres demandes
    (matrice 2.4 « P ») ; le Président et le VP voient celles du club pour
    les traiter. ``mine=1`` limite aux demandes de l'utilisateur."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        statuses = _status_filter(request, SocialAssistanceRequest.Status.values)
        if statuses is None:
            return Response({"detail": "État de demande inconnu."}, status=status.HTTP_400_BAD_REQUEST)
        queryset = _request_queryset(request.user).order_by("-submitted_at", "-pk")
        if request.query_params.get("mine") in ("1", "true"):
            queryset = queryset.filter(membership__user=request.user)
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        items, count, next_offset = _paginate(request, queryset)
        if items is None:
            return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            context = {"eligibility": _eligibility_context(request, items)}
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(
            {
                "count": count,
                "next_offset": next_offset,
                "results": SocialAssistanceRequestSerializer(items, many=True, context=context).data,
            }
        )

    def post(self, request):
        serializer = SocialAssistanceRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            request_obj = services.submit_social_assistance_request(
                membership=_own_membership(request), submitted_by=request.user, **serializer.validated_data
            )
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        request_obj = _request_queryset(request.user).get(pk=request_obj.pk)
        return Response(SocialAssistanceRequestSerializer(request_obj).data, status=status.HTTP_201_CREATED)


class SocialAssistanceRequestDetailView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            request_obj = _request_queryset(request.user).get(pk=pk)
        except SocialAssistanceRequest.DoesNotExist:
            return _not_found(_REQUEST_NOT_FOUND)
        try:
            context = {"eligibility": _eligibility_context(request, [request_obj])}
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(SocialAssistanceRequestSerializer(request_obj, context=context).data)


class _AssistanceDecisionView(APIView):
    permission_classes = _GATE + [CanProcessAssistanceRequests]

    def post(self, request, pk):
        try:
            request_obj = SocialAssistanceRequest.objects.get(pk=pk)
        except SocialAssistanceRequest.DoesNotExist:
            return _not_found(_REQUEST_NOT_FOUND)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform(request, request_obj, serializer.validated_data)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        request_obj = _request_queryset(request.user).get(pk=pk)
        return Response(SocialAssistanceRequestSerializer(request_obj).data)

    def perform(self, request, request_obj, data):  # pragma: no cover - abstrait
        raise NotImplementedError


class SocialAssistanceApproveView(_AssistanceDecisionView):
    """Approbation (Pdt ou VP) : crée la dépense « En attente » de la
    catégorie du barème. Refusée si le joueur est toujours en dette (10.2
    n° 37)."""

    def perform(self, request, request_obj, data):
        services.approve_social_assistance_request(request_obj=request_obj, approved_by=request.user)


class SocialAssistanceRejectView(_AssistanceDecisionView):
    """Refus motivé (Pdt ou VP)."""

    def perform(self, request, request_obj, data):
        services.reject_social_assistance_request(
            request_obj=request_obj, rejected_by=request.user, reason=data["reason"]
        )


class SocialAssistanceAttachmentDownloadView(APIView):
    """Pièce justificative d'une demande : le joueur concerné, le Président
    et le VP ; toute autre personne ou autre club = 404."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk: int):
        try:
            request_obj = assistance_requests_visible_to(request.user).get(pk=pk)
        except SocialAssistanceRequest.DoesNotExist:
            return _not_found(_REQUEST_NOT_FOUND)
        return _file_response(request_obj.attachment, "assistance-{pk}-justificatif.{ext}", request_obj.pk)


# ---------------------------------------------------------------------------
# Enregistrement des paiements (CDC 4.4.3, 4.4.4) et Caisse Terrain Express
# (CDC 4.4.5, 6.6 ; 10.2 n° 22) -- tâche 2.4. Trésorier et adjoint
# uniquement (matrice 2.4, ligne « Enregistrement des paiements », É).
# ---------------------------------------------------------------------------

_MEMBER_NOT_FOUND = "Ce joueur n'existe pas dans ce club."
_TYPE_NOT_FOUND = "Type de cotisation introuvable dans ce club."


def _payment_error(exc):
    """Erreurs métier des paiements et de la caisse, avec un ``code`` stable
    pour la file de synchronisation hors connexion (6.6)."""

    if isinstance(exc, services.PaymentLinkNotConfiguredError):
        return Response(
            {"detail": str(exc), "code": "payment_link_not_configured"}, status=status.HTTP_400_BAD_REQUEST
        )
    if isinstance(exc, services.DeclarationAlreadyProcessedError):
        return Response(
            {"detail": str(exc), "code": "declaration_already_processed"}, status=status.HTTP_409_CONFLICT
        )
    if isinstance(exc, services.CashSessionNotFoundError):
        return Response({"detail": str(exc), "code": "cash_session_not_found"}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, services.ClientUuidConflictError):
        return Response({"detail": str(exc), "code": "client_uuid_conflict"}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, services.CashSessionNotValidError):
        return Response({"detail": str(exc), "code": "cash_session_not_valid"}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, services.LedgerFrozenError):
        return Response({"detail": str(exc), "code": "ledger_frozen"}, status=status.HTTP_409_CONFLICT)
    return _treasury_error(exc)


def _member_and_type(data, *, type_required=True):
    """Adhésion et type cherchés dans le club actif (managers tenant-aware).
    Renvoie ``(membership, contribution_type, error_response)``."""

    try:
        membership = Membership.objects.select_related("club").get(pk=data["membership_id"])
    except Membership.DoesNotExist:
        return None, None, _not_found(_MEMBER_NOT_FOUND)
    ctype_id = data.get("contribution_type_id")
    if ctype_id is None:
        if type_required:
            return None, None, Response(
                {"detail": "Choisissez le type de cotisation."}, status=status.HTTP_400_BAD_REQUEST
            )
        return membership, None, None
    try:
        ctype = ContributionType.objects.get(pk=ctype_id)
    except ContributionType.DoesNotExist:
        return None, None, _not_found(_TYPE_NOT_FOUND)
    return membership, ctype, None


def _payment_response(payment, *, status_code):
    payment = Payment.objects.select_related("contribution_type", "cash_session", "membership").get(pk=payment.pk)
    summary = services.get_balance_summary(payment.membership)
    return Response(serializers_mod.serialize_payment(payment, summary=summary), status=status_code)


class PaymentPreviewView(APIView):
    """Aperçu de la répartition 4.4.3 et du nouveau solde, sans écriture."""

    permission_classes = _GATE + [CanRecordPayments]

    def post(self, request):
        serializer = serializers_mod.PaymentPreviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, ctype, error = _member_and_type(data)
        if error is not None:
            return error
        try:
            preview = services.preview_payment_allocation(
                membership=membership,
                contribution_type=ctype,
                amount=data["amount"],
                paid_on=data["paid_on"],
                requested_by=request.user,
            )
        except services.TreasuryError as exc:
            return _payment_error(exc)
        return Response(serializers_mod.serialize_preview(preview))


class PaymentCreateView(APIView):
    """POST : modale « Enregistrer un paiement » (CDC 4.4.4) : JSON ou
    multipart (pièce jointe facultative), code PIN vérifié par le serveur ;
    Trés, Adj.
    GET : « Derniers paiements » du tableau de bord (CDC 4.4.6) ; Pdt, VP,
    Trés, Adj. Voir :func:`_payment_list`."""

    permission_classes = _GATE + [CanRecordPayments]

    def get_permissions(self):
        if self.request.method == "GET":
            return [permission() for permission in _GATE + [CanReadTreasuryDashboard]]
        return super().get_permissions()

    def get(self, request):
        return _payment_list(request)

    def post(self, request):
        serializer = serializers_mod.PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, ctype, error = _member_and_type(data)
        if error is not None:
            return error
        try:
            payment = services.record_payment(
                membership=membership,
                contribution_type=ctype,
                amount=data["amount"],
                method=data["method"],
                paid_on=data["paid_on"],
                reference=data.get("reference", ""),
                attachment=data.get("attachment"),
                recorded_by=request.user,
                pin=data["pin"],
            )
        except PinError as exc:
            return _pin_error(exc)
        except services.TreasuryError as exc:
            return _payment_error(exc)
        return _payment_response(payment, status_code=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Tableau de bord Trésorerie (CDC 4.4.6 ; fiche tresorerie-tableau-de-bord
# §3, §4.4) : indicateurs, derniers paiements, détail d'un paiement et
# circuit d'annulation (CDC 4.4.4). Un paiement d'un autre club répond 404.
# ---------------------------------------------------------------------------

_PAYMENT_LIST_STATUS_FILTERS = {
    "to_validate": Q(transaction__status="pending") | Q(transaction__status="initiated"),
    "validated": Q(transaction__status="succeeded") & ~Q(reversal__status="approved"),
    "cancelled": Q(transaction__status="succeeded", reversal__status="approved"),
    "refused": Q(transaction__status="failed"),
}
_PAYMENT_LIST_DEFAULT_STATUSES = ("to_validate", "validated", "cancelled")
_REVERSAL_NOT_FOUND = "Aucune demande d'annulation pour ce paiement."


def _parse_month(raw):
    """``YYYY-MM`` -> premier jour du mois ; ``None`` si absent ; ``False``
    si illisible."""

    if not raw:
        return None
    try:
        year, month = (int(part) for part in raw.split("-"))
        return datetime.date(year, month, 1)
    except (TypeError, ValueError):
        return False


def _dashboard_payment_queryset(request):
    # Filtre explicite sur le club actif en plus du manager tenant-aware
    # (CLAUDE.md règle n° 8).
    return (
        payments_visible_to(request.user)
        .filter(club=get_active_club())
        .select_related(
            "membership__user",
            "contribution_type",
            "transaction",
            "reversal__requested_by",
            "reversal__approved_by",
            "reversal__rejected_by",
            "submitted_by",
            "validated_by",
            "cash_session",
        )
        .prefetch_related("allocations")
    )


def _payment_list(request):
    statuses = _status_filter(request, _PAYMENT_LIST_STATUS_FILTERS)
    if statuses is None:
        return Response({"detail": "État de paiement inconnu."}, status=status.HTTP_400_BAD_REQUEST)
    condition = Q()
    for key in statuses or _PAYMENT_LIST_DEFAULT_STATUSES:
        condition |= _PAYMENT_LIST_STATUS_FILTERS[key]
    queryset = _dashboard_payment_queryset(request).filter(condition)
    reversal = request.query_params.get("reversal")
    if reversal:
        if reversal != PaymentReversal.Status.PENDING_APPROVAL:
            return Response({"detail": "Filtre d'annulation inconnu."}, status=status.HTTP_400_BAD_REQUEST)
        queryset = queryset.filter(reversal__status=reversal)
    queryset = queryset.order_by("-paid_on", "-submitted_at", "-pk")
    items, count, next_offset = _paginate(request, queryset)
    if items is None:
        return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {
            "count": count,
            "next_offset": next_offset,
            "results": [serializers_mod.serialize_payment_list_item(item, request=request) for item in items],
        }
    )


def _payment_detail_response(request, pk, *, status_code=status.HTTP_200_OK):
    try:
        payment = _dashboard_payment_queryset(request).get(pk=pk)
    except Payment.DoesNotExist:
        return _not_found(_PAYMENT_NOT_FOUND)
    return Response(serializers_mod.serialize_payment_detail(payment, reader=request.user, request=request), status=status_code)


class TreasuryDashboardSummaryView(APIView):
    """Indicateurs du tableau de bord (CDC 4.4.6). ``?month=YYYY-MM``
    (défaut : mois en cours, fuseau du club)."""

    permission_classes = _GATE + [CanReadTreasuryDashboard]

    def get(self, request):
        period = _parse_month(request.query_params.get("month"))
        if period is False:
            return Response(
                {"detail": "Mois invalide : utilisez le format AAAA-MM."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            summary = services.get_treasury_dashboard_summary(get_active_club(), period=period)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(serializers_mod.serialize_dashboard_summary(summary))


class PaymentDetailView(APIView):
    """Modale « Détail du paiement » (fiche §4.4)."""

    permission_classes = _GATE + [CanReadTreasuryDashboard]

    def get(self, request, pk):
        return _payment_detail_response(request, pk)


class _PaymentReversalActionView(APIView):
    """Base du circuit d'annulation : rôle vérifié d'abord (403), puis
    paiement cherché dans le club actif (404, jamais de fuite d'existence)."""

    permission_classes = _GATE + [CanReadTreasuryDashboard]
    action_permission = None
    input_serializer = None
    success_status = status.HTTP_200_OK

    def post(self, request, pk):
        permission = self.action_permission()
        if not permission.has_permission(request, self):
            return Response({"detail": permission.message}, status=status.HTTP_403_FORBIDDEN)
        try:
            payment = Payment.objects.filter(club=get_active_club()).get(pk=pk)
        except Payment.DoesNotExist:
            return _not_found(_PAYMENT_NOT_FOUND)
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform(request, payment, serializer.validated_data)
        except PaymentReversal.DoesNotExist:
            return _not_found(_REVERSAL_NOT_FOUND)
        except PinError as exc:
            return _pin_error(exc)
        except services.TreasuryError as exc:
            return _payment_error(exc)
        return _payment_detail_response(request, pk, status_code=self.success_status)

    @staticmethod
    def _reversal(payment):
        return PaymentReversal.objects.get(payment=payment)

    def perform(self, request, payment, data):  # pragma: no cover - abstrait
        raise NotImplementedError


class PaymentReversalRequestView(_PaymentReversalActionView):
    """« Demander l'annulation » : Trés, Adj ; motif obligatoire ; sans PIN."""

    action_permission = CanRequestPaymentReversal
    input_serializer = serializers_mod.ReversalRequestSerializer
    success_status = status.HTTP_201_CREATED

    def perform(self, request, payment, data):
        services.request_payment_reversal(payment=payment, reason=data["reason"], requested_by=request.user)


class PaymentReversalApproveView(_PaymentReversalActionView):
    """« Valider l'annulation » : Président, code PIN (CDC 4.4.4, 7.2)."""

    action_permission = CanDecidePaymentReversal
    input_serializer = PinSerializer

    def perform(self, request, payment, data):
        services.approve_payment_reversal(reversal=self._reversal(payment), approved_by=request.user, pin=data["pin"])


class PaymentReversalRejectView(_PaymentReversalActionView):
    """« Refuser » : Président, motif obligatoire (exigé par le service), sans PIN."""

    action_permission = CanDecidePaymentReversal
    input_serializer = serializers_mod.ReversalRejectSerializer

    def perform(self, request, payment, data):
        services.reject_payment_reversal(
            reversal=self._reversal(payment), rejected_by=request.user, rejection_reason=data["rejection_reason"]
        )


def _cash_session_response(session, *, status_code=status.HTTP_200_OK):
    count, total = services.cash_session_totals(session)
    settings_obj = session.club.settings
    return Response(
        {
            "session": serializers_mod.serialize_cash_session(
                session,
                state=services.cash_session_state(session),
                payments_count=count,
                payments_total=total,
                currency=settings_obj.currency,
                timezone=settings_obj.timezone,
            )
        },
        status=status_code,
    )


class CashSessionOpenView(APIView):
    """Ouverture d'une session de caisse : EN LIGNE, PIN vérifié une fois
    par le serveur. 201 si créée, 200 si une session valide existait déjà.
    La réponse ne contient jamais le PIN ni aucun secret dérivé."""

    permission_classes = _GATE + [CanRecordPayments]

    def post(self, request):
        serializer = serializers_mod.CashSessionOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session, created = services.open_cash_session(
                club=get_active_club(), user=request.user, pin=serializer.validated_data["pin"]
            )
        except PinError as exc:
            return _pin_error(exc)
        except services.TreasuryError as exc:
            return _payment_error(exc)
        return _cash_session_response(
            session, status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class CashSessionCurrentView(APIView):
    """Session de caisse valide de l'utilisateur (sur n'importe lequel de
    ses appareils), ou ``{"session": null}``."""

    permission_classes = _GATE + [CanRecordPayments]

    def get(self, request):
        try:
            session = services.get_current_cash_session(club=get_active_club(), user=request.user)
            if session is None:
                return Response({"session": None})
            return _cash_session_response(session)
        except services.TreasuryError as exc:
            return _payment_error(exc)


class CashSessionCloseView(APIView):
    """Fermeture manuelle (idempotente) par l'auteur de la session."""

    permission_classes = _GATE + [CanRecordPayments]

    def post(self, request, public_id):
        try:
            session = services.close_cash_session(club=get_active_club(), user=request.user, public_id=public_id)
            return _cash_session_response(session)
        except services.TreasuryError as exc:
            return _payment_error(exc)


class CashSessionPlayerSearchView(APIView):
    """Recherche par nom ou numéro (``?q=``), au plus 20 joueurs, avec photo,
    solde et statut calculés à la lecture (jamais mis en cache)."""

    permission_classes = _GATE + [CanRecordPayments]

    def get(self, request, public_id):
        try:
            results = services.search_cash_session_players(
                club=get_active_club(),
                user=request.user,
                public_id=public_id,
                query=request.query_params.get("q", ""),
            )
        except services.TreasuryError as exc:
            return _payment_error(exc)
        return Response(
            {"results": [serializers_mod.serialize_cash_player(result, request=request) for result in results]},
            headers={"Cache-Control": "no-store"},
        )


class CashSessionPaymentPreviewView(APIView):
    """Aperçu d'un encaissement de caisse (répartition, nouveau statut)."""

    permission_classes = _GATE + [CanRecordPayments]

    def post(self, request, public_id):
        serializer = serializers_mod.CashPaymentPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, ctype, error = _member_and_type(data, type_required=False)
        if error is not None:
            return error
        try:
            preview = services.preview_cash_payment(
                club=get_active_club(),
                user=request.user,
                public_id=public_id,
                membership=membership,
                amount=data["amount"],
                contribution_type=ctype,
            )
        except services.TreasuryError as exc:
            return _payment_error(exc)
        return Response(serializers_mod.serialize_preview(preview))


class CashSessionPaymentView(APIView):
    """Encaissement en espèces d'une session de caisse, en ligne ou
    synchronisé après une saisie hors connexion : aucun PIN. 201 si créé,
    200 si la même saisie (``client_uuid``) avait déjà été reçue."""

    permission_classes = _GATE + [CanRecordPayments]

    def post(self, request, public_id):
        serializer = serializers_mod.CashPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, ctype, error = _member_and_type(data, type_required=False)
        if error is not None:
            return error
        try:
            payment, created = services.record_cash_payment(
                club=get_active_club(),
                user=request.user,
                public_id=public_id,
                membership=membership,
                amount=data["amount"],
                contribution_type=ctype,
                client_uuid=data["client_uuid"],
                client_recorded_at=data["client_recorded_at"],
            )
        except services.TreasuryError as exc:
            return _payment_error(exc)
        return _payment_response(payment, status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Paiement en ligne, phase 1 (CDC 4.6 ; tâche 2.5) : bouton « Contribuer »,
# déclaration « J'ai payé » par le joueur (matrice 2.4, « P »), validation
# par PIN ou refus motivé par le Trésorier ou l'adjoint (« É »). Une
# déclaration d'un autre club, ou non visible par l'utilisateur, répond 404.
# ---------------------------------------------------------------------------

_DECLARATION_NOT_FOUND = "Cette déclaration n'existe pas dans ce club."
_DECLARATION_STATUS_FILTERS = {
    "to_validate": {"transaction__status": "pending"},
    "validated": {"transaction__status": "succeeded"},
    "refused": {"transaction__status": "failed"},
    "cancelled": {"transaction__status": "succeeded", "reversal__status": "approved"},
}


def _declaration_queryset(queryset):
    return (
        queryset.filter(source=Payment.Source.PLAYER_DECLARATION)
        .select_related("membership__user", "contribution_type", "transaction", "reversal", "cash_session")
        .prefetch_related("allocations")
    )


def _declaration_response(payment, *, status_code=status.HTTP_200_OK, with_summary=False):
    # Filtre explicite sur le club actif (CLAUDE.md regle n8 : jamais de
    # ``Model.objects.all()`` sur une table privee dans une vue).
    payment = _declaration_queryset(Payment.objects.filter(club=get_active_club())).get(pk=payment.pk)
    summary = services.get_balance_summary(payment.membership) if with_summary else None
    return Response(serializers_mod.serialize_declaration(payment, summary=summary), status=status_code)


class ContributeView(APIView):
    """Bouton « Contribuer » et modale « J'ai payé » : lien de paiement du
    club actif (``null`` si non configuré : bouton masqué), types proposés
    au joueur et type par défaut. Tout membre actif, pour lui-même."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        try:
            info = services.get_contribute_info(_own_membership(request))
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(serializers_mod.serialize_contribute_info(info), headers={"Cache-Control": "no-store"})


class PaymentDeclarationListView(APIView):
    """GET : déclarations visibles (Pdt, VP, Trés, Adj : tout le club ;
    autres : les siennes), filtres ``status`` (``to_validate``,
    ``validated``, ``refused``, ``cancelled``, séparés par des virgules) et
    ``mine=1`` ; pagination ``limit``/``offset``.
    POST : « J'ai payé » par le joueur pour lui-même (JSON ou multipart)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        statuses = _status_filter(request, _DECLARATION_STATUS_FILTERS)
        if statuses is None:
            return Response({"detail": "État de déclaration inconnu."}, status=status.HTTP_400_BAD_REQUEST)
        queryset = _declaration_queryset(payments_visible_to(request.user)).order_by("-submitted_at", "-pk")
        if request.query_params.get("mine") in ("1", "true"):
            queryset = queryset.filter(membership__user=request.user)
        if statuses:
            condition = None
            for key in statuses:
                clause = Q(**_DECLARATION_STATUS_FILTERS[key])
                if key == "validated":
                    clause &= ~Q(reversal__status="approved")
                condition = clause if condition is None else condition | clause
            queryset = queryset.filter(condition)
        items, count, next_offset = _paginate(request, queryset)
        if items is None:
            return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "count": count,
                "next_offset": next_offset,
                "results": [serializers_mod.serialize_declaration(item) for item in items],
            }
        )

    def post(self, request):
        serializer = serializers_mod.PaymentDeclarationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            ctype = ContributionType.objects.get(pk=data["contribution_type_id"])
        except ContributionType.DoesNotExist:
            return _not_found(_TYPE_NOT_FOUND)
        try:
            payment = services.declare_payment(
                membership=_own_membership(request),
                declared_by=request.user,
                contribution_type=ctype,
                amount=data["amount"],
                reference=data.get("reference", ""),
                attachment=data.get("attachment"),
            )
        except services.TreasuryError as exc:
            return _payment_error(exc)
        return _declaration_response(payment, status_code=status.HTTP_201_CREATED)


class PaymentDeclarationDetailView(APIView):
    """Détail d'une déclaration (modale « Déclaration à valider » ou
    « Détail du paiement ») ; même visibilité que la liste."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            payment = _declaration_queryset(payments_visible_to(request.user)).get(pk=pk)
        except Payment.DoesNotExist:
            return _not_found(_DECLARATION_NOT_FOUND)
        return Response(serializers_mod.serialize_declaration(payment))


class _DeclarationActionView(APIView):
    """Actions du Trésorier ou de l'adjoint sur une déclaration du club
    actif (403 pour les autres rôles, 404 hors club ou hors déclaration)."""

    permission_classes = _GATE + [CanRecordPayments]
    input_serializer = None

    def post(self, request, pk):
        try:
            payment = Payment.objects.filter(source=Payment.Source.PLAYER_DECLARATION).get(pk=pk)
        except Payment.DoesNotExist:
            return _not_found(_DECLARATION_NOT_FOUND)
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return self.perform(request, payment, serializer.validated_data)
        except PinError as exc:
            return _pin_error(exc)
        except services.TreasuryError as exc:
            return _payment_error(exc)

    def perform(self, request, payment, data):  # pragma: no cover - abstrait
        raise NotImplementedError


class _EmptySerializer(drf_serializers.Serializer):
    pass


class PaymentDeclarationPreviewView(_DeclarationActionView):
    """Aperçu de la répartition 4.4.3 et du nouveau solde, sans écriture."""

    input_serializer = _EmptySerializer

    def perform(self, request, payment, data):
        preview = services.preview_declared_payment(payment=payment, requested_by=request.user)
        return Response(serializers_mod.serialize_preview(preview))


class PaymentDeclarationValidateView(_DeclarationActionView):
    """Validation par code PIN (CDC 4.6, 7.2) : paiement normal, reçu."""

    input_serializer = PinSerializer

    def perform(self, request, payment, data):
        payment = services.validate_declared_payment(payment=payment, validated_by=request.user, pin=data["pin"])
        return _declaration_response(payment, with_summary=True)


class PaymentDeclarationRejectView(_DeclarationActionView):
    """Refus motivé (sans PIN) : la déclaration reste tracée, joueur prévenu."""

    input_serializer = ReasonSerializer

    def perform(self, request, payment, data):
        payment = services.reject_declared_payment(payment=payment, rejected_by=request.user, reason=data["reason"])
        return _declaration_response(payment)


# ---------------------------------------------------------------------------
# Grille des cotisations (CDC 4.4.7) et import des cotisations historiques
# (CDC 4.4.8) -- tâche 2.6. Lecture de la grille : Pdt, VP, Trés, Adj
# (matrice 2.4) ; import : Trés et Adj. Un type ou un joueur d'un autre club
# répond 404 (managers tenant-aware, aucune fuite d'existence).
# ---------------------------------------------------------------------------

GRID_DEFAULT_PAGE_SIZE = 50
GRID_MAX_PAGE_SIZE = 100


def _grid_type_or_404(type_id):
    try:
        return ContributionType.objects.get(pk=type_id), None
    except ContributionType.DoesNotExist:
        return None, _not_found(_TYPE_NOT_FOUND)


def _grid_query(request):
    """Paramètres ``q``, ``unpaid``, ``ordering`` communs à la grille et à
    l'export. Renvoie ``(q, unpaid, ordering, error_response)``."""

    ordering = request.query_params.get("ordering", "name") or "name"
    if ordering not in services.GRID_ORDERINGS:
        return None, None, None, Response(
            {"detail": "Tri inconnu : nom ou total."}, status=status.HTTP_400_BAD_REQUEST
        )
    unpaid = request.query_params.get("unpaid", "") in ("1", "true")
    return request.query_params.get("q", ""), unpaid, ordering, None


class GridContributionTypesView(APIView):
    """Puces « Type » de la grille : types actifs, types archivés et type par
    défaut (premier type mensuel obligatoire), devise du club."""

    permission_classes = _GATE + [CanReadContributionGrid]

    def get(self, request):
        club = get_active_club()
        try:
            currency = services.get_club_currency(club)
            active, archived, default_id = services.get_grid_contribution_types(club)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        return Response(
            {
                "currency": currency,
                "default_type_id": default_id,
                "active": [serializers_mod.serialize_grid_type(ctype) for ctype in active],
                "archived": [serializers_mod.serialize_grid_type(ctype) for ctype in archived],
            }
        )


class ContributionGridView(APIView):
    """Grille d'un type pour une année (CDC 4.4.7) : 50 lignes par page
    (``limit``/``offset``), tri ``ordering`` (``name``, ``-name``,
    ``total``, ``-total``), recherche ``q`` (nom ou numéro), filtre
    ``unpaid=1`` (« Avec impayés »). Chaque ligne porte la situation du
    joueur calculée par ``services.get_balance_summaries``."""

    permission_classes = _GATE + [CanReadContributionGrid]

    def get(self, request, type_id, year):
        ctype, error = _grid_type_or_404(type_id)
        if error is not None:
            return error
        query, unpaid, ordering, error = _grid_query(request)
        if error is not None:
            return error
        try:
            limit = int(request.query_params.get("limit", GRID_DEFAULT_PAGE_SIZE))
            offset = int(request.query_params.get("offset", 0))
        except (TypeError, ValueError):
            return Response({"detail": "Pagination invalide."}, status=status.HTTP_400_BAD_REQUEST)
        limit = max(1, min(limit, GRID_MAX_PAGE_SIZE))
        offset = max(0, offset)
        try:
            grid = services.build_contribution_grid(contribution_type=ctype, year=year, requested_by=request.user)
            rows = services.filter_grid_rows(grid, query=query, unpaid_only=unpaid, ordering=ordering)
            page = rows[offset:offset + limit]
            summaries = services.get_balance_summaries(
                ctype.club, [row.membership.pk for row in page], at_date=grid.today
            )
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        count = len(rows)
        return Response(
            {
                "contribution_type": serializers_mod.serialize_grid_type(ctype),
                "year": grid.year,
                "currency": grid.currency,
                "today": grid.today,
                "months": serializers_mod.serialize_grid_months(grid),
                "states": services.GRID_STATE_LABELS,
                "rows_total": len(grid.rows),
                "count": count,
                "limit": limit,
                "offset": offset,
                "next_offset": offset + limit if offset + limit < count else None,
                "results": [
                    serializers_mod.serialize_grid_row(row, request=request, summary=summaries.get(row.membership.pk))
                    for row in page
                ],
            },
            headers={"Cache-Control": "no-store"},
        )


class ContributionGridExportView(APIView):
    """Export CSV du type et de l'année affichés (CDC 4.4.7) ; mêmes filtres
    facultatifs que la grille, toutes les lignes (sans pagination). Nom de
    fichier généré à partir du type, jamais de nom de club."""

    permission_classes = _GATE + [CanReadContributionGrid]

    def get(self, request, type_id, year):
        ctype, error = _grid_type_or_404(type_id)
        if error is not None:
            return error
        query, unpaid, ordering, error = _grid_query(request)
        if error is not None:
            return error
        try:
            grid = services.build_contribution_grid(contribution_type=ctype, year=year, requested_by=request.user)
            rows = services.filter_grid_rows(grid, query=query, unpaid_only=unpaid, ordering=ordering)
            filename, content = services.export_contribution_grid_csv(grid, rows)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "no-store"
        return response


class ContributionGridMonthView(APIView):
    """Modale « Détail du mois » : montant dû, montant affecté, état et
    paiements ayant alimenté ce mois (part affectée, étalement 4.4.3)."""

    permission_classes = _GATE + [CanReadContributionGrid]

    def get(self, request, type_id, year, membership_id, month):
        ctype, error = _grid_type_or_404(type_id)
        if error is not None:
            return error
        try:
            membership = Membership.objects.select_related("user").get(pk=membership_id)
        except Membership.DoesNotExist:
            return _not_found(_MEMBER_NOT_FOUND)
        try:
            detail = services.get_grid_month_detail(
                contribution_type=ctype, membership=membership, year=year, month=month, requested_by=request.user
            )
            capabilities = services.get_treasury_capabilities(request.user, ctype.club)
        except services.TreasuryError as exc:
            return _treasury_error(exc)
        can_record = (
            capabilities["can_record_payments"]
            and ctype.status == ContributionType.Status.ACTIVE
            and membership.status != Membership.Status.DEPARTED
        )
        return Response(
            serializers_mod.serialize_month_detail(detail, can_record_payment=can_record, request=request),
            headers={"Cache-Control": "no-store"},
        )


def _import_error(exc):
    if isinstance(exc, services.ContributionImportError):
        return Response({"detail": str(exc), "code": "import_file_invalid"}, status=status.HTTP_400_BAD_REQUEST)
    return _payment_error(exc)


class _ContributionImportBaseView(APIView):
    permission_classes = _GATE + [CanImportContributions]
    parser_classes = [MultiPartParser, FormParser]
    input_serializer = serializers_mod.ContributionImportInputSerializer
    success_status = status.HTTP_200_OK

    def post(self, request):
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ctype, error = _grid_type_or_404(data["contribution_type_id"])
        if error is not None:
            return error
        try:
            report = self.perform(request, ctype, data)
        except PinError as exc:
            return _pin_error(exc)
        except services.TreasuryError as exc:
            return _import_error(exc)
        return Response(serializers_mod.serialize_import_report(report, request=request), status=self.success_status)

    def perform(self, request, ctype, data):  # pragma: no cover - abstrait
        raise NotImplementedError


class ContributionImportPreviewView(_ContributionImportBaseView):
    """Aperçu de l'import (CDC 4.4.8) : grille résultante, lignes en échec,
    paiements et montants dus prévus. **Aucune écriture.**"""

    def perform(self, request, ctype, data):
        return services.preview_contribution_import(
            contribution_type=ctype, year=data["year"], csv_file=data["file"], requested_by=request.user
        )


class ContributionImportView(_ContributionImportBaseView):
    """Import définitif (CDC 4.4.8), confirmé par code PIN (CDC 7.2) ;
    renvoie le rapport (lignes importées, lignes en échec avec le détail)."""

    input_serializer = serializers_mod.ContributionImportCreateSerializer
    success_status = status.HTTP_201_CREATED

    def perform(self, request, ctype, data):
        return services.import_contributions(
            contribution_type=ctype,
            year=data["year"],
            csv_file=data["file"],
            imported_by=request.user,
            pin=data["pin"],
        )
