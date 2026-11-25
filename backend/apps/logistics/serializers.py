"""Serializers DRF de l'app logistics (CDC 4.13 ; fiche d'écran logistique.md).

Fonctions ``serialize_*`` plutôt que des ``ModelSerializer`` complets pour
les représentations en lecture (même convention qu'``apps.sport.serializers``) :
le stock théorique, les compteurs d'inventaire et le masquage Ghost Mode ne
sont jamais de simples champs de modèle.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.audit.services import GHOST_ACTOR_DISPLAY_NAME, get_actor_display_name
from apps.logistics import services
from apps.logistics.models import Article, Decommission, Holder, Inventory, InventoryLine, StockMovement

__all__ = [
    "ArticleInputSerializer",
    "MovementInputSerializer",
    "ProvenanceInputSerializer",
    "MatchEquipmentOutSerializer",
    "MatchEquipmentReturnSerializer",
    "CountInputSerializer",
    "JustifyInputSerializer",
    "HolderInputSerializer",
    "HolderUpdateSerializer",
    "TransferInputSerializer",
    "DecommissionInputSerializer",
    "DecommissionExecuteSerializer",
    "DecommissionCancelSerializer",
    "serialize_article",
    "serialize_movement",
    "serialize_provenance",
    "serialize_holder",
    "serialize_holder_detail",
    "serialize_decommission",
    "serialize_match_equipment_summary",
    "serialize_inventory",
    "serialize_inventory_line",
    "serialize_material_overview",
]


def _user_name(user) -> str:
    return f"{user.first_name} {user.last_name}".strip()


def _actor_display(*, object_type: str, object_id, action_type: str, viewer) -> dict:
    """Auteur d'une écriture ; « Système Vesta » en Ghost Mode (CDC 5.4),
    reconstitué depuis le journal d'activité (StockMovement/Inventory ne
    portent pas eux-mêmes ``acted_as_ghost``)."""

    entry = (
        AuditLog.objects.filter(object_type=object_type, object_id=str(object_id), action_type=action_type)
        .order_by("created_at")
        .first()
    )
    if entry is None:
        return {"id": None, "name": ""}
    name = get_actor_display_name(entry, reader=viewer)
    return {"id": None if name == GHOST_ACTOR_DISPLAY_NAME else entry.actor_id, "name": name}


# ---------------------------------------------------------------------------
# Entrées (formulaires)
# ---------------------------------------------------------------------------


class ArticleInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    category = serializers.ChoiceField(choices=Article.Category.choices)
    unit = serializers.CharField(max_length=20, required=False, allow_blank=True, default="pièce")
    reference_condition = serializers.ChoiceField(choices=Article.Condition.choices, required=False)


class ProvenanceInputSerializer(serializers.Serializer):
    origin_kind = serializers.ChoiceField(choices=StockMovement.OriginKind.choices, required=False, allow_blank=True)
    donor_membership_id = serializers.IntegerField(required=False, allow_null=True)
    donor_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    acquisition_date = serializers.DateField(required=False, allow_null=True)
    acquisition_date_unknown = serializers.BooleanField(required=False, default=False)
    acquisition_date_note = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    condition_at_entry = serializers.ChoiceField(choices=Article.Condition.choices, required=False, allow_blank=True)


_MANUAL_TYPE_CHOICES = [c for c in StockMovement.MovementType.choices if c[0] in StockMovement.MANUAL_TYPES]


class MovementInputSerializer(serializers.Serializer):
    movement_type = serializers.ChoiceField(choices=_MANUAL_TYPE_CHOICES)
    article_id = serializers.IntegerField()
    holder_id = serializers.IntegerField(required=False, allow_null=True)
    provenance = ProvenanceInputSerializer(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    movement_date = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    membership_id = serializers.IntegerField(required=False, allow_null=True)
    match_id = serializers.IntegerField(required=False, allow_null=True)
    expense_id = serializers.IntegerField(required=False, allow_null=True)


class MatchEquipmentLineSerializer(serializers.Serializer):
    article_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    holder_id = serializers.IntegerField(required=False, allow_null=True)


class MatchEquipmentOutSerializer(serializers.Serializer):
    lines = MatchEquipmentLineSerializer(many=True)


class MatchEquipmentReturnLineSerializer(serializers.Serializer):
    article_id = serializers.IntegerField()
    quantity_returned = serializers.IntegerField(min_value=0)
    holder_id = serializers.IntegerField(required=False, allow_null=True)


class MatchEquipmentReturnSerializer(serializers.Serializer):
    lines = MatchEquipmentReturnLineSerializer(many=True)
    observation = serializers.CharField(required=False, allow_blank=True, default="")


class CountLineSerializer(serializers.Serializer):
    article_id = serializers.IntegerField()
    physical_quantity = serializers.IntegerField(min_value=0)


class CountInputSerializer(serializers.Serializer):
    counts = CountLineSerializer(many=True)


class JustifyInputSerializer(serializers.Serializer):
    discrepancy_reason = serializers.ChoiceField(choices=InventoryLine.DiscrepancyReason.choices)


class HolderInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Holder.Kind.choices)
    membership_id = serializers.IntegerField(required=False, allow_null=True)
    label = serializers.CharField(required=False, allow_blank=True, default="")


class HolderUpdateSerializer(serializers.Serializer):
    label = serializers.CharField()


class TransferInputSerializer(serializers.Serializer):
    article_id = serializers.IntegerField()
    from_holder_id = serializers.IntegerField(allow_null=True)
    to_holder_id = serializers.IntegerField(allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    movement_date = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class DecommissionInputSerializer(serializers.Serializer):
    article_id = serializers.IntegerField()
    holder_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.ChoiceField(choices=Decommission.Reason.choices)
    reason_note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)
    noted_on = serializers.DateField()


class DecommissionExecuteSerializer(serializers.Serializer):
    exit_date = serializers.DateField()
    destination = serializers.CharField(required=False, allow_blank=True, default="", max_length=120)
    confirm = serializers.BooleanField(required=False, default=False)


class DecommissionCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


# ---------------------------------------------------------------------------
# Représentations en lecture
# ---------------------------------------------------------------------------


def _holder_ref(holder) -> dict | None:
    if holder is None:
        return None
    return {"id": holder.pk, "name": holder.display_name, "kind": holder.kind}


def _stock_rows_json(rows: list[dict]) -> list[dict]:
    return [
        {
            "holder_id": row["holder_id"],
            "holder": _holder_ref(row["holder"]),
            "holder_name": row["holder"].display_name if row["holder"] is not None else services.UNLOCATED_LABEL,
            "quantity": row["quantity"],
        }
        for row in rows
    ]


def serialize_article(
    article: Article,
    *,
    loaned_for_match: int = 0,
    holder_stocks: dict | None = None,
    holders_by_id: dict | None = None,
    pending_decommission: int | None = None,
    detail: bool = False,
) -> dict:
    if holder_stocks is None:
        holder_stocks = services.bulk_stock_by_holder().get(article.pk, {})
    if holders_by_id is None:
        holders_by_id = services.club_holders_by_id()
    if pending_decommission is None:
        pending_decommission = services.pending_decommission_by_article().get(article.pk, 0)
    rows = services.stock_rows_for(holder_stocks, holders_by_id)
    positive = [r for r in rows if r["quantity"] > 0]
    data = {
        "id": article.pk,
        "name": article.name,
        "category": article.category,
        "category_display": article.get_category_display(),
        "unit": article.unit,
        "reference_condition": article.reference_condition,
        "reference_condition_display": article.get_reference_condition_display(),
        "status": article.status,
        "in_stock": sum(holder_stocks.values()),
        "loaned_for_match": loaned_for_match,
        "stock_by_holder": _stock_rows_json(rows),
        "pending_decommission": pending_decommission,
        "suggested_holder": _holder_ref(positive[0]["holder"]) if positive else None,
        "created_at": article.created_at,
        "created_by": {"id": article.created_by_id, "name": _user_name(article.created_by)},
    }
    if detail:
        data["provenances"] = [serialize_provenance(m) for m in services.recent_provenances(article)]
    return data


def serialize_provenance(movement: StockMovement) -> dict | None:
    """Provenance d'une entrée ; ``None`` pour un mouvement qui n'est pas une entrée de stock."""

    if movement.movement_type not in StockMovement.PROVENANCE_TYPES:
        return None
    donor = None
    if movement.donor_membership_id:
        donor = {"membership_id": movement.donor_membership_id, "name": _user_name(movement.donor_membership.user)}
    elif movement.donor_name:
        donor = {"membership_id": None, "name": movement.donor_name}
    if movement.acquisition_date_unknown:
        acquisition_date = None
    else:
        acquisition_date = movement.acquisition_date or movement.movement_date
    return {
        "movement_id": movement.pk,
        "quantity": movement.quantity,
        "movement_type": movement.movement_type,
        "origin_kind": movement.origin_kind,
        "origin_kind_display": movement.get_origin_kind_display() if movement.origin_kind else "Origine non renseignée",
        "donor": donor,
        "acquisition_date": acquisition_date,
        "acquisition_date_unknown": movement.acquisition_date_unknown,
        "acquisition_date_note": movement.acquisition_date_note,
        "condition_at_entry": movement.condition_at_entry,
        "condition_at_entry_display": (
            movement.get_condition_at_entry_display() if movement.condition_at_entry else "Non renseigné"
        ),
        "holder": _holder_ref(movement.holder),
        "movement_date": movement.movement_date,
    }


def _movement_audit_key(movement: StockMovement) -> tuple[str, object, str]:
    """Entrée du journal qui porte l'auteur d'un mouvement (un transfert ou un
    déclassement n'a pas son propre « stock_movement.created »)."""

    if movement.movement_type == StockMovement.MovementType.OUT_TRANSFER:
        return "StockMovement", movement.pk, "logistics.transfer.created"
    if movement.movement_type == StockMovement.MovementType.IN_TRANSFER:
        out_id = (
            StockMovement.objects.filter(
                transfer_group=movement.transfer_group, movement_type=StockMovement.MovementType.OUT_TRANSFER
            )
            .values_list("pk", flat=True)
            .first()
        )
        return "StockMovement", out_id, "logistics.transfer.created"
    if movement.movement_type == StockMovement.MovementType.OUT_DECOMMISSION:
        return "Decommission", movement.decommission_id, "logistics.decommission.executed"
    return "StockMovement", movement.pk, "logistics.stock_movement.created"


def serialize_movement(movement: StockMovement, *, viewer) -> dict:
    object_type, object_id, action_type = _movement_audit_key(movement)
    return {
        "id": movement.pk,
        "article": {"id": movement.article_id, "name": movement.article.name, "unit": movement.article.unit},
        "movement_type": movement.movement_type,
        "movement_type_display": movement.get_movement_type_display(),
        "quantity": movement.quantity,
        "signed_quantity": movement.signed_quantity,
        "movement_date": movement.movement_date,
        "reason": movement.reason,
        "membership": (
            {"id": movement.membership_id, "name": _user_name(movement.membership.user)}
            if movement.membership_id
            else None
        ),
        "match_id": movement.match_id,
        "expense_id": movement.expense_id,
        "holder": _holder_ref(movement.holder),
        "provenance": serialize_provenance(movement),
        "transfer_group": str(movement.transfer_group) if movement.transfer_group else None,
        "decommission_id": movement.decommission_id,
        "recorded_by": _actor_display(
            object_type=object_type, object_id=object_id, action_type=action_type, viewer=viewer
        ),
        "created_at": movement.created_at,
    }


def serialize_holder(holder: Holder, *, stock_total: int = 0, articles_count: int = 0) -> dict:
    return {
        "id": holder.pk,
        "kind": holder.kind,
        "kind_display": holder.get_kind_display(),
        "name": holder.display_name,
        "membership_id": holder.membership_id,
        "label": holder.label,
        "status": holder.status,
        "has_left_club": holder.has_left_club,
        "stock_total": stock_total,
        "articles_count": articles_count,
        "created_at": holder.created_at,
    }


def serialize_holder_detail(holder: Holder, *, viewer) -> dict:
    holdings = services.holder_holdings(holder)
    data = serialize_holder(holder, stock_total=sum(h["quantity"] for h in holdings), articles_count=len(holdings))
    data["articles"] = [
        {
            "article_id": h["article"].pk,
            "name": h["article"].name,
            "category": h["article"].category,
            "category_display": h["article"].get_category_display(),
            "unit": h["article"].unit,
            "quantity": h["quantity"],
            "pending_decommission": h["pending_decommission"],
        }
        for h in holdings
    ]
    recent = (
        StockMovement.objects.filter(holder=holder)
        .select_related("article", "membership__user", "holder__membership__user", "donor_membership__user")
        .order_by("-movement_date", "-created_at", "-pk")[:5]
    )
    data["recent_movements"] = [serialize_movement(m, viewer=viewer) for m in recent]
    return data


def serialize_decommission(decommission: Decommission, *, viewer) -> dict:
    article = decommission.article

    def person(user, action_type):
        if user is None:
            return None
        return _actor_display(
            object_type="Decommission", object_id=decommission.pk, action_type=action_type, viewer=viewer
        )

    return {
        "id": decommission.pk,
        "article": {"id": article.pk, "name": article.name, "unit": article.unit, "category": article.category},
        "holder": _holder_ref(decommission.holder),
        "quantity": decommission.quantity,
        "reason": decommission.reason,
        "reason_display": decommission.get_reason_display(),
        "reason_note": decommission.reason_note,
        "noted_on": decommission.noted_on,
        "noted_by": person(decommission.noted_by, "logistics.decommission.flagged"),
        "status": decommission.status,
        "status_display": decommission.get_status_display(),
        "exit_date": decommission.exit_date,
        "exit_destination": decommission.exit_destination,
        "exit_movement_id": decommission.exit_movement_id,
        "executed_by": person(decommission.executed_by, "logistics.decommission.executed"),
        "cancelled_at": decommission.cancelled_at,
        "cancelled_by": person(decommission.cancelled_by, "logistics.decommission.cancelled"),
        "cancel_reason": decommission.cancel_reason,
        "created_at": decommission.created_at,
    }


def serialize_match_equipment_summary(match) -> list[dict]:
    lines = services.match_equipment_summary(match)
    result = []
    for line in lines:
        article = line["article"]
        result.append(
            {
                "article_id": line["article_id"],
                "article_name": article.name if article else None,
                "out_quantity": line["out_quantity"],
                "returned_quantity": line["returned_quantity"],
                "remaining_quantity": line["remaining_quantity"],
                "status": line["status"],
                "holder": _holder_ref(line.get("holder")),
            }
        )
    return result


def serialize_inventory_line(line: InventoryLine) -> dict:
    if line.discrepancy == 0:
        status = "no_gap"
    elif line.justified_at is not None:
        status = "justified"
    else:
        status = "to_justify"
    return {
        "id": line.pk,
        "article_id": line.article_id,
        "article_name": line.article.name,
        "theoretical_quantity": line.theoretical_quantity,
        "physical_quantity": line.physical_quantity,
        "discrepancy": line.discrepancy,
        "discrepancy_reason": line.discrepancy_reason,
        "status": status,
        "justified_by_id": line.justified_by_id,
        "justified_at": line.justified_at,
    }


def serialize_inventory(inventory: Inventory, *, with_lines: bool = False) -> dict:
    data = {
        "id": inventory.pk,
        "quarter_label": inventory.quarter_label,
        "quarter_label_display": services.quarter_label_ordinal(inventory.quarter_label),
        "status": inventory.status,
        "opened_at": inventory.opened_at,
        "opened_by": {"id": inventory.opened_by_id, "name": _user_name(inventory.opened_by)},
        "closed_at": inventory.closed_at,
        "closed_by": (
            {"id": inventory.closed_by_id, "name": _user_name(inventory.closed_by)}
            if inventory.closed_by_id
            else None
        ),
    }
    if with_lines:
        data["lines"] = [serialize_inventory_line(line) for line in InventoryLine.objects.filter(inventory=inventory).select_related("article")]
    return data


def serialize_material_overview(overview: dict) -> dict:
    open_inventory = overview["open_inventory"]
    last_closed = overview["last_closed_inventory"]
    return {
        "current_quarter_label": overview["current_quarter_label"],
        "current_quarter_label_display": services.quarter_label_ordinal(overview["current_quarter_label"]),
        "open_inventory": serialize_inventory(open_inventory) if open_inventory else None,
        "blocking_inventory": overview["blocking"],
        "to_count": overview["to_count"],
        "to_justify": overview["to_justify"],
        "counted": overview["counted"],
        "total_active_articles": overview["total_active_articles"],
        "can_open": overview["can_open"],
        "openable_quarter_label": overview["openable_quarter_label"],
        "openable_quarter_label_display": (
            services.quarter_label_ordinal(overview["openable_quarter_label"])
            if overview["openable_quarter_label"]
            else None
        ),
        "last_closed_inventory": serialize_inventory(last_closed) if last_closed else None,
    }
