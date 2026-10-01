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
from apps.logistics.models import Article, Inventory, InventoryLine, StockMovement

__all__ = [
    "ArticleInputSerializer",
    "MovementInputSerializer",
    "MatchEquipmentOutSerializer",
    "MatchEquipmentReturnSerializer",
    "CountInputSerializer",
    "JustifyInputSerializer",
    "serialize_article",
    "serialize_movement",
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


class MovementInputSerializer(serializers.Serializer):
    movement_type = serializers.ChoiceField(choices=StockMovement.MovementType.choices)
    article_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    movement_date = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    membership_id = serializers.IntegerField(required=False, allow_null=True)
    match_id = serializers.IntegerField(required=False, allow_null=True)
    expense_id = serializers.IntegerField(required=False, allow_null=True)


class MatchEquipmentLineSerializer(serializers.Serializer):
    article_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class MatchEquipmentOutSerializer(serializers.Serializer):
    lines = MatchEquipmentLineSerializer(many=True)


class MatchEquipmentReturnLineSerializer(serializers.Serializer):
    article_id = serializers.IntegerField()
    quantity_returned = serializers.IntegerField(min_value=0)


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


# ---------------------------------------------------------------------------
# Représentations en lecture
# ---------------------------------------------------------------------------


def serialize_article(article: Article, *, loaned_for_match: int = 0) -> dict:
    return {
        "id": article.pk,
        "name": article.name,
        "category": article.category,
        "category_display": article.get_category_display(),
        "unit": article.unit,
        "reference_condition": article.reference_condition,
        "reference_condition_display": article.get_reference_condition_display(),
        "status": article.status,
        "in_stock": services.theoretical_quantity(article),
        "loaned_for_match": loaned_for_match,
        "created_at": article.created_at,
        "created_by": {"id": article.created_by_id, "name": _user_name(article.created_by)},
    }


def serialize_movement(movement: StockMovement, *, viewer) -> dict:
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
        "recorded_by": _actor_display(
            object_type="StockMovement",
            object_id=movement.pk,
            action_type="logistics.stock_movement.created",
            viewer=viewer,
        ),
        "created_at": movement.created_at,
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
