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
from apps.logistics import register as register_module
from apps.logistics.models import Article, Decommission, Holder, Inventory, InventoryLine, StockMovement
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


_INVALID_PARAM = {"detail": "Paramètre invalide."}
MOVEMENTS_DEFAULT_LIMIT = 50
MOVEMENTS_MAX_LIMIT = 200


class _InvalidParam(Exception):
    pass


def _int_query_param(request, name: str):
    """Paramètre de requête numérique facultatif ; non numérique -> 400."""

    raw = request.query_params.get(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise _InvalidParam(name) from None


def _find_holder(pk):
    return Holder.objects.select_related("membership__user").filter(pk=pk).first()


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
        articles = services.filter_articles_by_search(
            queryset.order_by("category", "name"), request.query_params.get("search") or ""
        )
        stocks = services.bulk_stock_by_holder()
        holders_by_id = services.club_holders_by_id()
        pending = services.pending_decommission_by_article()
        loaned = services.loaned_for_match_by_article()
        data = [
            ser.serialize_article(
                article,
                holder_stocks=stocks.get(article.pk, {}),
                holders_by_id=holders_by_id,
                pending_decommission=pending.get(article.pk, 0),
                loaned_for_match=loaned.get(article.pk, 0),
            )
            for article in articles
        ]
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
        return Response(ser.serialize_article(article, detail=True))

    def patch(self, request, pk: int):
        article = self._get(pk)
        if article is None:
            return Response({"detail": "Cet article n'existe pas dans ce club."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.ArticleInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            article = services.update_article(article=article, actor=request.user, **serializer.validated_data)
        except services.LogisticsError as exc:
            return _error(exc)
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
        queryset = StockMovement.objects.select_related("article", "membership__user", "holder__membership__user").order_by(
            "-movement_date", "-created_at"
        )
        try:
            article_id = _int_query_param(request, "article")
            match_id = _int_query_param(request, "match")
            expense_id = _int_query_param(request, "expense")
            limit = _int_query_param(request, "limit")
            offset = _int_query_param(request, "offset") or 0
            holder_param = request.query_params.get("holder") or ""
            holder_id = None if holder_param in ("", "none") else _int_query_param(request, "holder")
            types = [t.strip() for t in (request.query_params.get("types") or "").split(",") if t.strip()]
            if any(t not in StockMovement.MovementType.values for t in types):
                raise _InvalidParam("types")
            if offset < 0 or (limit is not None and limit < 1):
                raise _InvalidParam("limit")
        except _InvalidParam:
            return Response(_INVALID_PARAM, status=status.HTTP_400_BAD_REQUEST)
        limit = min(limit or MOVEMENTS_DEFAULT_LIMIT, MOVEMENTS_MAX_LIMIT)
        if article_id is not None:
            queryset = queryset.filter(article_id=article_id)
        if holder_param == "none":
            queryset = queryset.filter(holder__isnull=True)
        elif holder_id is not None:
            queryset = queryset.filter(holder_id=holder_id)
        if types:
            queryset = queryset.filter(movement_type__in=types)
        movement_type = request.query_params.get("movement_type")
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        sense = request.query_params.get("sense")
        if sense == "in":
            queryset = queryset.filter(movement_type__in=StockMovement.IN_TYPES)
        elif sense == "out":
            queryset = queryset.filter(movement_type__in=StockMovement.OUT_TYPES)
        if match_id is not None:
            queryset = queryset.filter(match_id=match_id)
        if expense_id is not None:
            queryset = queryset.filter(expense_id=expense_id)
        total = queryset.count()
        page = queryset.order_by("-movement_date", "-created_at", "-pk")[offset : offset + limit]
        data = [ser.serialize_movement(movement, viewer=request.user) for movement in page]
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "next_offset": offset + limit if offset + limit < total else None,
                "results": data,
            }
        )

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
            membership = Membership.objects.filter(pk=payload["membership_id"], club=club).first()
            if membership is None:
                return Response({"detail": "Ce joueur n'appartient pas au club actif."}, status=status.HTTP_400_BAD_REQUEST)
        match = None
        if payload.get("match_id"):
            match = Match.objects.filter(pk=payload["match_id"]).first()
            if match is None:
                return Response({"detail": "Ce match n'existe pas dans ce club."}, status=status.HTTP_400_BAD_REQUEST)
        holder = None
        if payload.get("holder_id") is not None:
            holder = _find_holder(payload["holder_id"])
            if holder is None:
                return Response({"detail": "Ce détenteur n'existe pas dans ce club."}, status=status.HTTP_400_BAD_REQUEST)
        provenance = payload.get("provenance") or None
        donor_membership = None
        if provenance and provenance.get("donor_membership_id"):
            donor_membership = Membership.objects.filter(pk=provenance["donor_membership_id"], club=club).first()
            if donor_membership is None:
                return Response({"detail": "Ce donateur n'appartient pas au club actif."}, status=status.HTTP_400_BAD_REQUEST)
        expense = None
        if payload.get("expense_id"):
            from apps.treasury.models import Expense

            expense = Expense.objects.filter(pk=payload["expense_id"]).first()
            if expense is None:
                return Response({"detail": "Cette dépense n'existe pas dans ce club."}, status=status.HTTP_400_BAD_REQUEST)
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
                holder=holder,
                provenance=provenance,
                donor_membership=donor_membership,
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


class LinkableExpenseSearchView(APIView):
    """Recherche des dépenses rattachables à un achat (10.2 n° 167) : Intendant
    seul ; dépenses libérées du club ; ni bénéficiaire, ni motif, ni justificatif."""

    permission_classes = _GATE + [CanManageMaterial]

    def get(self, request):
        results = services.linkable_expenses(club=get_active_club(), query=request.query_params.get("q") or "")
        return Response({"count": len(results), "results": results})


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
            entry = {"article": article, "quantity": line["quantity"]}
            if "holder_id" in line:
                holder = _find_holder(line["holder_id"]) if line["holder_id"] is not None else None
                if line["holder_id"] is not None and holder is None:
                    return Response({"detail": "Ce détenteur n'existe pas dans ce club."}, status=status.HTTP_400_BAD_REQUEST)
                entry["holder"] = holder
            lines.append(entry)
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
        articles = services.articles_by_ids(
            club=get_active_club(), article_ids=[l["article_id"] for l in serializer.validated_data["lines"]]
        )
        lines = []
        for line in serializer.validated_data["lines"]:
            article = articles.get(line["article_id"])
            if article is None:
                return Response({"detail": "Choisissez un article."}, status=status.HTTP_400_BAD_REQUEST)
            entry = {"article": article, "quantity_returned": line["quantity_returned"]}
            if "holder_id" in line:
                holder = _find_holder(line["holder_id"]) if line["holder_id"] is not None else None
                if line["holder_id"] is not None and holder is None:
                    return Response({"detail": "Ce détenteur n'existe pas dans ce club."}, status=status.HTTP_400_BAD_REQUEST)
                entry["holder"] = holder
            lines.append(entry)
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


# ---------------------------------------------------------------------------
# Détenteurs (registre de l'intendance §3)
# ---------------------------------------------------------------------------


_HOLDER_NOT_FOUND = {"detail": "Ce détenteur n'existe pas dans ce club."}


class HolderListCreateView(APIView):
    def get_permissions(self):
        classes = list(_GATE) + [CanReadMaterial]
        if self.request.method == "POST":
            classes = list(_GATE) + [CanManageMaterial]
        return [c() for c in classes]

    def get(self, request):
        overview = services.holders_overview(include_archived=request.query_params.get("include_archived") == "true")
        results = [
            ser.serialize_holder(row["holder"], stock_total=row["stock_total"], articles_count=row["articles_count"])
            for row in overview["holders"]
        ]
        return Response({"count": len(results), "results": results, "unlocated": overview["unlocated"]})

    def post(self, request):
        serializer = ser.HolderInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        club = get_active_club()
        membership = None
        if payload["kind"] == Holder.Kind.MEMBER and payload.get("membership_id"):
            membership = Membership.objects.filter(pk=payload["membership_id"], club=club).first()
            if membership is None:
                return Response({"detail": "Ce joueur n'appartient pas au club actif."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            holder = services.create_holder(
                club=club,
                actor=request.user,
                kind=payload["kind"],
                membership=membership,
                label=payload.get("label", ""),
            )
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(ser.serialize_holder(holder), status=status.HTTP_201_CREATED)


class HolderDetailView(APIView):
    def get_permissions(self):
        classes = list(_GATE) + [CanReadMaterial]
        if self.request.method == "PATCH":
            classes = list(_GATE) + [CanManageMaterial]
        return [c() for c in classes]

    def get(self, request, pk: int):
        holder = _find_holder(pk)
        if holder is None:
            return Response(_HOLDER_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(ser.serialize_holder_detail(holder, viewer=request.user))

    def patch(self, request, pk: int):
        holder = _find_holder(pk)
        if holder is None:
            return Response(_HOLDER_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.HolderUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            holder = services.update_holder(holder=holder, actor=request.user, label=serializer.validated_data["label"])
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(ser.serialize_holder_detail(holder, viewer=request.user))


class HolderArchiveView(APIView):
    permission_classes = _GATE + [CanManageMaterial]

    def post(self, request, pk: int):
        holder = _find_holder(pk)
        if holder is None:
            return Response(_HOLDER_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        try:
            holder = services.archive_holder(holder=holder, actor=request.user)
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(ser.serialize_holder(holder))


class TransferCreateView(APIView):
    permission_classes = _GATE + [CanManageMaterial]

    def post(self, request):
        serializer = ser.TransferInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        article = Article.objects.filter(pk=payload["article_id"]).first()
        if article is None:
            return Response({"detail": "Choisissez un article."}, status=status.HTTP_400_BAD_REQUEST)
        source = None
        if payload["from_holder_id"] is not None:
            source = _find_holder(payload["from_holder_id"])
            if source is None:
                return Response(_HOLDER_NOT_FOUND, status=status.HTTP_400_BAD_REQUEST)
        destination = None
        if payload["to_holder_id"] is not None:
            destination = _find_holder(payload["to_holder_id"])
            if destination is None:
                return Response(_HOLDER_NOT_FOUND, status=status.HTTP_400_BAD_REQUEST)
        try:
            out_movement, in_movement = services.record_transfer(
                club=get_active_club(),
                actor=request.user,
                article=article,
                source=source,
                destination=destination,
                quantity=payload["quantity"],
                movement_date=payload["movement_date"],
                reason=payload.get("reason", ""),
            )
        except services.LogisticsError as exc:
            return _error(exc)
        out_movement = StockMovement.objects.select_related("article", "holder__membership__user").get(pk=out_movement.pk)
        in_movement = StockMovement.objects.select_related("article", "holder__membership__user").get(pk=in_movement.pk)
        article_data = ser.serialize_article(article)
        return Response(
            {
                "transfer_group": str(out_movement.transfer_group),
                "out_movement": ser.serialize_movement(out_movement, viewer=request.user),
                "in_movement": ser.serialize_movement(in_movement, viewer=request.user),
                "in_stock": article_data["in_stock"],
                "stock_by_holder": article_data["stock_by_holder"],
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Déclassement (registre de l'intendance §7)
# ---------------------------------------------------------------------------


_DECOMMISSION_NOT_FOUND = {"detail": "Ce déclassement n'existe pas dans ce club."}


def _find_decommission(pk):
    return (
        Decommission.objects.select_related("article", "holder__membership__user", "noted_by", "executed_by", "cancelled_by")
        .filter(pk=pk)
        .first()
    )


class DecommissionListCreateView(APIView):
    def get_permissions(self):
        classes = list(_GATE) + [CanReadMaterial]
        if self.request.method == "POST":
            classes = list(_GATE) + [CanManageMaterial]
        return [c() for c in classes]

    def get(self, request):
        queryset = Decommission.objects.select_related(
            "article", "holder__membership__user", "noted_by", "executed_by", "cancelled_by"
        ).order_by("-noted_on", "-pk")
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        try:
            article_id = _int_query_param(request, "article")
        except _InvalidParam:
            return Response(_INVALID_PARAM, status=status.HTTP_400_BAD_REQUEST)
        if article_id is not None:
            queryset = queryset.filter(article_id=article_id)
        data = [ser.serialize_decommission(d, viewer=request.user) for d in queryset[:200]]
        return Response(
            {
                "count": len(data),
                "pending_quantity": sum(services.pending_decommission_by_article().values()),
                "results": data,
            }
        )

    def post(self, request):
        serializer = ser.DecommissionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        article = Article.objects.filter(pk=payload["article_id"]).first()
        if article is None:
            return Response({"detail": "Choisissez un article."}, status=status.HTTP_400_BAD_REQUEST)
        holder = None
        if payload.get("holder_id") is not None:
            holder = _find_holder(payload["holder_id"])
            if holder is None:
                return Response(_HOLDER_NOT_FOUND, status=status.HTTP_400_BAD_REQUEST)
        try:
            decommission = services.flag_decommission(
                club=get_active_club(),
                actor=request.user,
                article=article,
                quantity=payload["quantity"],
                reason=payload["reason"],
                reason_note=payload.get("reason_note", ""),
                noted_on=payload["noted_on"],
                holder=holder,
            )
        except services.LogisticsError as exc:
            return _error(exc)
        decommission = _find_decommission(decommission.pk)
        return Response(ser.serialize_decommission(decommission, viewer=request.user), status=status.HTTP_201_CREATED)


class DecommissionDetailView(APIView):
    permission_classes = _GATE + [CanReadMaterial]

    def get(self, request, pk: int):
        decommission = _find_decommission(pk)
        if decommission is None:
            return Response(_DECOMMISSION_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(ser.serialize_decommission(decommission, viewer=request.user))


class DecommissionExecuteView(APIView):
    permission_classes = _GATE + [CanManageMaterial]

    def post(self, request, pk: int):
        decommission = _find_decommission(pk)
        if decommission is None:
            return Response(_DECOMMISSION_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.DecommissionExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            services.execute_decommission(
                decommission=decommission,
                actor=request.user,
                exit_date=payload["exit_date"],
                destination=payload.get("destination", ""),
                confirm=payload.get("confirm", False),
            )
        except services.LogisticsError as exc:
            return _error(exc)
        decommission = _find_decommission(pk)
        return Response(
            {
                "decommission": ser.serialize_decommission(decommission, viewer=request.user),
                "in_stock": services.theoretical_quantity(decommission.article),
            }
        )


class DecommissionCancelView(APIView):
    permission_classes = _GATE + [CanManageMaterial]

    def post(self, request, pk: int):
        decommission = _find_decommission(pk)
        if decommission is None:
            return Response(_DECOMMISSION_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        serializer = ser.DecommissionCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.cancel_decommission(
                decommission=decommission, actor=request.user, reason=serializer.validated_data["reason"]
            )
        except services.LogisticsError as exc:
            return _error(exc)
        return Response(ser.serialize_decommission(_find_decommission(pk), viewer=request.user))


# ---------------------------------------------------------------------------
# Registre de l'intendance (page, PDF, CSV)
# ---------------------------------------------------------------------------


class _RegisterBase(APIView):
    """Lecteurs de la matrice 2.4 (position provisoire, question Q22)."""

    permission_classes = _GATE + [CanReadMaterial]

    def _parse(self, request):
        """Renvoie ``(kwargs, None)`` ou ``(None, Response d'erreur)``."""

        params = request.query_params
        category = params.get("category") or ""
        if category and category not in Article.Category.values:
            return None, Response({"detail": "Nature inconnue."}, status=status.HTTP_400_BAD_REQUEST)
        holder_filter = None
        raw = params.get("holder")
        if raw == "none":
            holder_filter = "none"
        elif raw:
            holder_filter = _find_holder(raw) if raw.isdigit() else None
            if holder_filter is None:
                return None, Response(_HOLDER_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return {
            "search": (params.get("search") or "").strip(),
            "category": category,
            "holder_filter": holder_filter,
            "include_exits": params.get("include_exits") == "true",
        }, None

    def _export_log(self, request, club, fmt, kwargs):
        from apps.core.services import log_action

        log_action(
            actor=request.user,
            club=club,
            action_type="logistics.register.exported",
            obj=club,
            after={
                "format": fmt,
                "filters": register_module.register_filters_snapshot(
                    search=kwargs["search"],
                    category=kwargs["category"],
                    holder_filter=kwargs["holder_filter"],
                    include_exits=kwargs["include_exits"],
                ),
            },
        )


class RegisterView(_RegisterBase):
    def get(self, request):
        kwargs, error = self._parse(request)
        if error is not None:
            return error
        return Response(register_module.build_register(get_active_club(), **kwargs))


class RegisterPdfView(_RegisterBase):
    def get(self, request):
        from django.http import HttpResponse

        kwargs, error = self._parse(request)
        if error is not None:
            return error
        club = get_active_club()
        data = register_module.build_register(club, **kwargs)
        try:
            content = register_module.render_register_pdf(club, data, actor=request.user)
        except Exception:
            return Response(
                {"detail": "Le registre n'a pas pu être généré. Réessayez."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        self._export_log(request, club, "pdf", kwargs)
        response = HttpResponse(content, content_type="application/pdf")
        filename = "registre-intendance-" + club.slug + "-" + data["as_of"].isoformat() + ".pdf"
        response["Content-Disposition"] = 'attachment; filename="' + filename + '"'
        return response


class RegisterCsvView(_RegisterBase):
    def get(self, request):
        from django.http import HttpResponse

        kwargs, error = self._parse(request)
        if error is not None:
            return error
        club = get_active_club()
        data = register_module.build_register(club, **kwargs)
        content = register_module.render_register_csv(data)
        self._export_log(request, club, "csv", kwargs)
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        filename = "registre-intendance-" + club.slug + "-" + data["as_of"].isoformat() + ".csv"
        response["Content-Disposition"] = 'attachment; filename="' + filename + '"'
        return response
