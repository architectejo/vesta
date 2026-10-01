"""Vues DRF de l'app logistics (CDC 4.13 ; fiche d'écran logistique.md).

Orchestration uniquement (permission -> service -> serializer, CLAUDE.md
section 5) : toute règle métier vit dans ``apps.logistics.services``.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.models import Membership
from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence
from apps.core.services import resolve_active_membership
from apps.core.tenant import NoActiveClubError, get_active_club
from apps.logistics import serializers as ser
from apps.logistics import services
from apps.logistics.models import Article, Inventory, InventoryLine, StockMovement
from apps.logistics.permissions import (
    CanManageMaterial,
    CanReadMaterial,
    CanRecordEquipmentOut,
    CanRecordEquipmentReturn,
)
from apps.sport.models import Match

_GATE = [IsAuthenticated, HasCompletedPasswordSetup, HasAcceptedLatestTerms, HasUsableLicence]


def _error(exc) -> Response:
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _active_membership(request):
    try:
        return resolve_active_membership(request.user, club=get_active_club())
    except NoActiveClubError:
        return None


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


class ArticleListCreateView(APIView):
    def get_permissions(self):
        classes = list(_GATE) + [CanReadMaterial]
        if self.request.method == "POST":
            classes = list(_GATE) + [CanManageMaterial]
        return [c() for c in classes]

    def get(self, request):
        club = get_active_club()
        queryset = Article.objects.select_related("created_by")
        include_archived = request.query_params.get("include_archived") == "true"
        if not include_archived:
            queryset = queryset.filter(status=Article.Status.ACTIVE)
        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)
        condition = request.query_params.get("condition")
        if condition:
            queryset = queryset.filter(reference_condition=condition)
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        queryset = queryset.order_by("category", "name")
        data = [ser.serialize_article(article) for article in queryset]
        return Response({"count": len(data), "results": data})

    def post(self, request):
        serializer = ser.ArticleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            article = services.create_article(club=get_active_club(), actor=request.user, **serializer.validated_data)
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(ser.serialize_article(article), status=status.HTTP_201_CREATED)


class ArticleDetailView(APIView):
    def get_permissions(self):
        classes = list(_GATE) + [CanReadMaterial]
        if self.request.method in ("PATCH", "POST"):
            classes = list(_GATE) + [CanManageMaterial]
        return [c() for c in classes]

    def _get(self, pk):
        return Article.objects.select_related("created_by").filter(pk=pk).first()

    def get(self, request, pk: int):
        article = self._get(pk)
        if article is None:
            return Response({"detail": "Cet article n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ser.serialize_article(article))

    def patch(self, request, pk: int):
        article = self._get(pk)
        if article is None:
            return Response({"detail": "Cet article n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.ArticleInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        article = services.update_article(article=article, actor=request.user, **serializer.validated_data)
        return Response(ser.serialize_article(article))

    def post(self, request, pk: int):
        article = self._get(pk)
        if article is None:
            return Response({"detail": "Cet article n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        action = request.data.get("action")
        try:
            if action == "archive":
                article = services.archive_article(article=article, actor=request.user)
            elif action == "reactivate":
                article = services.reactivate_article(article=article, actor=request.user)
            else:
                return Response({"detail": "Action inconnue."}, status=status.HTTP_400_BAD_REQUEST)
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(ser.serialize_article(article))


# ---------------------------------------------------------------------------
# Registre des mouvements
# ---------------------------------------------------------------------------


class MovementListCreateView(APIView):
    def get_permissions(self):
        classes = list(_GATE) + [CanReadMaterial]
        if self.request.method == "POST":
            classes = list(_GATE) + [CanManageMaterial]
        return [c() for c in classes]

    def get(self, request):
        queryset = StockMovement.objects.select_related("article", "membership__user").order_by(
            "-movement_date", "-created_at"
        )
        article_id = request.query_params.get("article")
        if article_id:
            queryset = queryset.filter(article_id=article_id)
        movement_type = request.query_params.get("movement_type")
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        sense = request.query_params.get("sense")
        if sense == "in":
            queryset = queryset.filter(movement_type__in=StockMovement.IN_TYPES)
        elif sense == "out":
            queryset = queryset.filter(movement_type__in=StockMovement.OUT_TYPES)
        match_id = request.query_params.get("match")
        if match_id:
            queryset = queryset.filter(match_id=match_id)
        expense_id = request.query_params.get("expense")
        if expense_id:
            queryset = queryset.filter(expense_id=expense_id)
        data = [ser.serialize_movement(movement, viewer=request.user) for movement in queryset[:200]]
        return Response({"count": len(data), "results": data})

    def post(self, request):
        serializer = ser.MovementInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        club = get_active_club()
        article = Article.objects.filter(pk=payload["article_id"]).first()
        if article is None:
            return Response({"detail": "Choisissez un article."}, status=status.HTTP_400_BAD_REQUEST)
        membership = None
        if payload.get("membership_id"):
            membership = Membership.objects.filter(pk=payload["membership_id"]).first()
        match = None
        if payload.get("match_id"):
            match = Match.objects.filter(pk=payload["match_id"]).first()
        expense = None
        if payload.get("expense_id"):
            from apps.treasury.models import Expense

            expense = Expense.objects.filter(pk=payload["expense_id"]).first()
        try:
            movement = services.record_movement(
                club=club,
                actor=request.user,
                movement_type=payload["movement_type"],
                article=article,
                quantity=payload["quantity"],
                movement_date=payload["movement_date"],
                reason=payload.get("reason", ""),
                membership=membership,
                match=match,
                expense=expense,
            )
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(
            {
                "movement": ser.serialize_movement(movement, viewer=request.user),
                "in_stock": services.theoretical_quantity(article),
            },
            status=status.HTTP_201_CREATED,
        )


class MovementDetailView(APIView):
    permission_classes = _GATE + [CanReadMaterial]

    def get(self, request, pk: int):
        movement = StockMovement.objects.select_related("article", "membership__user").filter(pk=pk).first()
        if movement is None:
            return Response({"detail": "Ce mouvement n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ser.serialize_movement(movement, viewer=request.user))


# ---------------------------------------------------------------------------
# Équipements d'un match
# ---------------------------------------------------------------------------


class MatchEquipmentView(APIView):
    permission_classes = _GATE + [CanReadMaterial]

    def get(self, request, match_id: int):
        match = Match.objects.filter(pk=match_id).first()
        if match is None:
            return Response({"detail": "Ce match n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"lines": ser.serialize_match_equipment_summary(match)})


class MatchEquipmentOutView(APIView):
    permission_classes = _GATE + [CanRecordEquipmentOut]

    def post(self, request, match_id: int):
        match = Match.objects.filter(pk=match_id).first()
        if match is None:
            return Response({"detail": "Ce match n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.MatchEquipmentOutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        articles = {a.pk: a for a in Article.objects.filter(pk__in=[l["article_id"] for l in serializer.validated_data["lines"]])}
        lines = []
        for line in serializer.validated_data["lines"]:
            article = articles.get(line["article_id"])
            if article is None:
                return Response({"detail": "Choisissez un article."}, status=status.HTTP_400_BAD_REQUEST)
            lines.append({"article": article, "quantity": line["quantity"]})
        try:
            services.record_match_equipment_out(club=get_active_club(), actor=request.user, match=match, lines=lines)
        except services.LogisticsError as exc:
            return _error(exc)
        return Response({"lines": ser.serialize_match_equipment_summary(match)}, status=status.HTTP_201_CREATED)


class MatchEquipmentReturnView(APIView):
    permission_classes = _GATE + [CanRecordEquipmentReturn]

    def post(self, request, match_id: int):
        match = Match.objects.filter(pk=match_id).first()
        if match is None:
            return Response({"detail": "Ce match n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.MatchEquipmentReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        articles = {
            a.pk: a
            for a in Article.all_objects.filter(
                club=get_active_club(), pk__in=[l["article_id"] for l in serializer.validated_data["lines"]]
            )
        }
        lines = []
        for line in serializer.validated_data["lines"]:
            article = articles.get(line["article_id"])
            if article is None:
                return Response({"detail": "Choisissez un article."}, status=status.HTTP_400_BAD_REQUEST)
            lines.append({"article": article, "quantity_returned": line["quantity_returned"]})
        try:
            services.record_match_equipment_return(
                club=get_active_club(),
                actor=request.user,
                match=match,
                lines=lines,
                observation=serializer.validated_data.get("observation", ""),
            )
        except services.LogisticsError as exc:
            return _error(exc)
        return Response({"lines": ser.serialize_match_equipment_summary(match)})


# ---------------------------------------------------------------------------
# Inventaire trimestriel
# ---------------------------------------------------------------------------


class MaterialOverviewView(APIView):
    permission_classes = _GATE + [CanReadMaterial]

    def get(self, request):
        overview = services.get_material_overview(get_active_club())
        return Response(ser.serialize_material_overview(overview))


class InventoryOpenView(APIView):
    permission_classes = _GATE + [CanManageMaterial]

    def post(self, request):
        try:
            inventory = services.open_inventory(club=get_active_club(), actor=request.user)
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(ser.serialize_inventory(inventory), status=status.HTTP_201_CREATED)


class InventoryDetailView(APIView):
    permission_classes = _GATE + [CanReadMaterial]

    def get(self, request, pk: int):
        inventory = Inventory.objects.filter(pk=pk).first()
        if inventory is None:
            return Response({"detail": "Cet inventaire n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ser.serialize_inventory(inventory, with_lines=True))


class InventoryCountView(APIView):
    permission_classes = _GATE + [CanManageMaterial]

    def post(self, request, pk: int):
        inventory = Inventory.objects.filter(pk=pk).first()
        if inventory is None:
            return Response({"detail": "Cet inventaire n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.CountInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        articles = {
            a.pk: a
            for a in Article.objects.filter(pk__in=[c["article_id"] for c in serializer.validated_data["counts"]])
        }
        counts = []
        for entry in serializer.validated_data["counts"]:
            article = articles.get(entry["article_id"])
            if article is None:
                return Response({"detail": "Article invalide pour cet inventaire."}, status=status.HTTP_400_BAD_REQUEST)
            counts.append({"article": article, "physical_quantity": entry["physical_quantity"]})
        try:
            lines = services.record_counts(inventory=inventory, actor=request.user, counts=counts)
        except services.LogisticsError as exc:
            return _error(exc)
        to_justify = sum(1 for line in lines if line.discrepancy != 0 and line.justified_at is None)
        return Response(
            {"lines_counted": len(lines), "to_justify": to_justify, "inventory": ser.serialize_inventory(inventory, with_lines=True)}
        )


class InventoryLineJustifyView(APIView):
    permission_classes = _GATE + [CanManageMaterial]

    def post(self, request, pk: int):
        line = InventoryLine.objects.select_related("inventory", "article").filter(pk=pk).first()
        if line is None:
            return Response({"detail": "Cette ligne n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.JustifyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            line = services.justify_discrepancy(
                line=line, actor=request.user, reason=serializer.validated_data["discrepancy_reason"]
            )
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(ser.serialize_inventory_line(line))


class InventoryCloseView(APIView):
    permission_classes = _GATE + [CanManageMaterial]

    def post(self, request, pk: int):
        inventory = Inventory.objects.filter(pk=pk).first()
        if inventory is None:
            return Response({"detail": "Cet inventaire n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        try:
            inventory = services.close_inventory(inventory=inventory, actor=request.user)
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(ser.serialize_inventory(inventory))
