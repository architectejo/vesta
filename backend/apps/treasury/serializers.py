"""Serializers DRF de l'app treasury."""

from django.urls import reverse
from rest_framework import serializers

from apps.audit.services import GHOST_ACTOR_DISPLAY_NAME
from apps.treasury import services
from apps.treasury.models import (
    ContributionType,
    Expense,
    ExpenseCategory,
    PaymentReversal,
    SocialAssistanceEvent,
    SocialAssistanceRequest,
    SocialAssistanceScale,
)


class ContributionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContributionType
        fields = (
            "id", "name", "nature", "amount", "periodicity", "due_day", "due_month",
            "deadline", "is_membership_fee", "scope", "status", "archived_at",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "status", "archived_at", "created_at", "updated_at")


class MyBalanceSerializer(serializers.Serializer):
    """Serialisation seule du resume calcule par
    ``services.get_balance_summary`` (aucun calcul ici, CLAUDE.md §5).

    Attend ``{"membership": Membership, "summary": BalanceSummary}``.
    """

    def to_representation(self, instance):
        membership = instance["membership"]
        summary = instance["summary"]
        return {
            "membership_id": membership.pk,
            "club_id": membership.club_id,
            "currency": summary.currency,
            "balance": str(summary.balance),
            "amount_due": str(summary.amount_due),
            "is_in_good_standing": summary.is_in_good_standing,
            "reason": summary.reason,
        }


class ContributionTypeInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    nature = serializers.ChoiceField(choices=ContributionType.Nature.choices, required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    periodicity = serializers.ChoiceField(choices=ContributionType.Periodicity.choices, required=False)
    due_day = serializers.IntegerField(required=False, allow_null=True)
    due_month = serializers.IntegerField(required=False, allow_null=True)
    deadline = serializers.DateField(required=False, allow_null=True)
    is_membership_fee = serializers.BooleanField(required=False)
    scope = serializers.ChoiceField(choices=ContributionType.Scope.choices, required=False)


class ContributionTypeCreateSerializer(ContributionTypeInputSerializer):
    name = serializers.CharField(max_length=120)
    nature = serializers.ChoiceField(choices=ContributionType.Nature.choices)
    periodicity = serializers.ChoiceField(choices=ContributionType.Periodicity.choices)


# ---------------------------------------------------------------------------
# Depenses et assistance sociale (tache 2.2). Serialisation seule : les
# regles (eligibilite, blocage, retard de justification) sont calculees par
# ``apps.treasury.services`` et transmises dans le contexte.
# ---------------------------------------------------------------------------


def _money(value):
    return None if value is None else f"{value:.2f}"


def _user_name(user):
    if user is None:
        return None
    return f"{user.first_name} {user.last_name}".strip()


class ExpenseCategorySerializer(serializers.ModelSerializer):
    ceiling = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseCategory
        fields = (
            "id", "name", "ceiling", "receipt_required", "good_standing_only", "status",
            "archived_at", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_ceiling(self, obj):
        return _money(obj.ceiling)


class ExpenseCategoryInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    ceiling = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    receipt_required = serializers.BooleanField(required=False)
    good_standing_only = serializers.BooleanField(required=False)


class ExpenseCategoryCreateSerializer(ExpenseCategoryInputSerializer):
    name = serializers.CharField(max_length=120)


class ExpenseSerializer(serializers.Serializer):
    """Detail d'une depense. Contexte attendu : ``today`` (date du club,
    fournie par ``services.get_club_today``)."""

    def to_representation(self, expense: Expense):
        today = self.context["today"]
        derogation = getattr(expense, "derogation", None) if hasattr(expense, "derogation") else None
        return {
            "id": expense.pk,
            "category": {"id": expense.category_id, "name": expense.category.name},
            "amount": _money(expense.amount),
            "currency": expense.currency,
            "beneficiary_name": expense.beneficiary_name,
            "beneficiary_membership_id": expense.beneficiary_membership_id,
            "reason": expense.reason,
            "expense_date": expense.expense_date,
            "status": expense.status,
            "status_label": expense.get_status_display(),
            "created_by": {"id": expense.created_by_id, "name": _user_name(expense.created_by)},
            "created_at": expense.created_at,
            "refused_at": expense.refused_at,
            "refusal_reason": expense.refusal_reason,
            "released_at": expense.released_at,
            "released_by": (
                {"id": expense.released_by_id, "name": _user_name(expense.released_by)}
                if expense.released_by_id
                else None
            ),
            "justification_deadline": expense.justification_deadline,
            "is_overdue": services.is_expense_overdue(expense, today),
            "justified_at": expense.justified_at,
            "unjustified_at": expense.unjustified_at,
            "social_assistance_request_id": expense.social_assistance_request_id,
            "derogation": (
                {
                    "reason": derogation.reason,
                    "granted_at": derogation.granted_at,
                    "granted_by": _user_name(derogation.granted_by),
                }
                if derogation is not None
                else None
            ),
            "attachments": [
                {
                    "id": attachment.pk,
                    "kind": attachment.kind,
                    "kind_label": attachment.get_kind_display(),
                    "uploaded_at": attachment.uploaded_at,
                    "download_url": reverse("treasury:expense-attachment-download", args=[attachment.pk]),
                }
                for attachment in expense.attachments.all().order_by("uploaded_at", "pk")
            ],
        }


class ExpenseCreateSerializer(serializers.Serializer):
    category_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    beneficiary_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    beneficiary_membership_id = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(allow_blank=True)
    expense_date = serializers.DateField()
    attachment = serializers.FileField(required=False, allow_null=True)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class PinSerializer(serializers.Serializer):
    pin = serializers.CharField(max_length=12)


class DerogationSerializer(PinSerializer):
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class ReceiptUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class SocialAssistanceScaleSerializer(serializers.Serializer):
    def to_representation(self, scale: SocialAssistanceScale):
        return {
            "id": scale.pk,
            "event_type": scale.event_type,
            "event_type_label": scale.get_event_type_display(),
            "amount": _money(scale.amount),
            "processing_days": scale.processing_days,
            "expense_category": {"id": scale.expense_category_id, "name": scale.expense_category.name},
            "status": scale.status,
            "archived_at": scale.archived_at,
        }


class SocialAssistanceScaleInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    processing_days = serializers.IntegerField(required=False)
    expense_category_id = serializers.IntegerField(required=False)


class SocialAssistanceScaleCreateSerializer(SocialAssistanceScaleInputSerializer):
    event_type = serializers.ChoiceField(choices=SocialAssistanceEvent.choices)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    processing_days = serializers.IntegerField()
    expense_category_id = serializers.IntegerField()


def serialize_eligibility(eligibility) -> dict:
    """Serialise un ``services.SocialAssistanceEligibility`` (aucun calcul)."""

    return {
        "eligible": eligibility.eligible,
        "was_in_good_standing_at_event": eligibility.was_in_good_standing_at_event,
        "amount_due_at_event": _money(eligibility.amount_due_at_event),
        "amount_to_regularize": _money(eligibility.amount_to_regularize),
        "can_be_approved": eligibility.can_be_approved,
        "currency": eligibility.currency,
        "reason": eligibility.reason,
    }


class SocialAssistancePreviewQuerySerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=SocialAssistanceEvent.choices)
    event_date = serializers.DateField()


class SocialAssistanceRequestCreateSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=SocialAssistanceEvent.choices)
    event_date = serializers.DateField()
    description = serializers.CharField(allow_blank=True)
    attachment = serializers.FileField()


class SocialAssistanceRequestSerializer(serializers.Serializer):
    """Demande d'assistance. Contexte facultatif : ``eligibility`` (dict
    identifiant de demande -> eligibilite courante, calculee par les
    services pour le Président ou le VP)."""

    def to_representation(self, request_obj: SocialAssistanceRequest):
        expense = getattr(request_obj, "expense", None) if hasattr(request_obj, "expense") else None
        current = (self.context.get("eligibility") or {}).get(request_obj.pk)
        return {
            "id": request_obj.pk,
            "membership_id": request_obj.membership_id,
            "player_name": _user_name(request_obj.membership.user),
            "event_type": request_obj.event_type,
            "event_type_label": request_obj.get_event_type_display(),
            "event_date": request_obj.event_date,
            "description": request_obj.description,
            "planned_amount": _money(request_obj.planned_amount),
            "currency": request_obj.currency,
            "processing_days": request_obj.processing_days,
            "eligible_at_submission": request_obj.eligible_at_submission,
            "amount_to_regularize_at_submission": _money(request_obj.amount_to_regularize),
            "status": request_obj.status,
            "status_label": request_obj.get_status_display(),
            "submitted_at": request_obj.submitted_at,
            "decided_at": request_obj.decided_at,
            "rejection_reason": request_obj.rejection_reason,
            "expense": (
                {"id": expense.pk, "status": expense.status, "status_label": expense.get_status_display()}
                if expense is not None
                else None
            ),
            "attachment_url": reverse("treasury:social-assistance-attachment-download", args=[request_obj.pk]),
            "current_eligibility": serialize_eligibility(current) if current is not None else None,
        }


# ---------------------------------------------------------------------------
# Enregistrement des paiements et Caisse Terrain Express (tache 2.4).
# Validation de forme seulement : montants, dates, roles et sessions sont
# controles par ``apps.treasury.services`` (messages en français).
# ---------------------------------------------------------------------------


class PaymentPreviewInputSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    contribution_type_id = serializers.IntegerField()
    # Chaîne : ``services.to_money`` refuse les flottants et arrondit à 2
    # décimales avec un message en français.
    amount = serializers.CharField(max_length=32)
    paid_on = serializers.DateField()


class PaymentCreateSerializer(PaymentPreviewInputSerializer):
    method = serializers.ChoiceField(choices=sorted(services.TREASURER_ENTRY_METHODS))
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    attachment = serializers.FileField(required=False, allow_null=True)
    pin = serializers.CharField(max_length=12)


class CashSessionOpenSerializer(PinSerializer):
    pass


class CashPaymentPreviewSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    amount = serializers.CharField(max_length=32)
    contribution_type_id = serializers.IntegerField(required=False, allow_null=True)


class CashPaymentCreateSerializer(CashPaymentPreviewSerializer):
    client_uuid = serializers.UUIDField()
    client_recorded_at = serializers.DateTimeField()


def serialize_summary(summary) -> dict:
    """Sérialise un ``services.BalanceSummary`` (aucun calcul)."""

    return {
        "balance": _money(summary.balance),
        "amount_due": _money(summary.amount_due),
        "is_in_good_standing": summary.is_in_good_standing,
        "reason": summary.reason,
        "currency": summary.currency,
    }


def serialize_preview(preview) -> dict:
    """Sérialise un ``services.PaymentPreview`` calculé par le serveur."""

    return {
        "membership_id": preview.membership.pk,
        "contribution_type": {"id": preview.contribution_type.pk, "name": preview.contribution_type.name},
        "amount": _money(preview.amount),
        "currency": preview.currency,
        "paid_on": preview.paid_on,
        "is_free_type": preview.is_free_type,
        "allocations": [
            {
                "period": line.period,
                "amount": _money(line.amount),
                "period_amount": _money(line.period_amount),
                "covered_after": _money(line.covered_after),
                "status": line.status,
            }
            for line in preview.lines
        ],
        "unallocated_amount": _money(preview.unallocated_amount),
        "current": serialize_summary(preview.current),
        "after": serialize_summary(preview.after),
    }


def serialize_payment(payment, *, summary=None) -> dict:
    """Paiement validé : montants, reçu, répartition enregistrée et, si
    fourni, la situation du joueur recalculée après le paiement."""

    session = payment.cash_session if payment.cash_session_id else None
    return {
        "id": payment.pk,
        "membership_id": payment.membership_id,
        "contribution_type": {"id": payment.contribution_type_id, "name": payment.contribution_type.name},
        "amount": _money(payment.amount),
        "currency": payment.currency,
        "method": payment.method,
        "method_label": payment.get_method_display(),
        "reference": payment.reference,
        "paid_on": payment.paid_on,
        "source": payment.source,
        "source_label": payment.get_source_display(),
        "receipt_number": payment.receipt_number,
        "receipt_available": bool(payment.receipt_file),
        "receipt_url": reverse("treasury:payment-receipt-download", args=[payment.pk]),
        "attachment_url": (
            reverse("treasury:payment-attachment-download", args=[payment.pk]) if payment.attachment else None
        ),
        "validated_at": payment.validated_at,
        "cash_session_id": str(session.public_id) if session else None,
        "client_uuid": str(payment.client_uuid) if payment.client_uuid else None,
        "client_recorded_at": payment.client_recorded_at,
        "allocations": [
            {"period": allocation.period, "amount": _money(allocation.amount)}
            # Tri en Python : compatible avec ``prefetch_related("allocations")``
            # (un ``order_by`` relancerait une requête par paiement).
            for allocation in sorted(payment.allocations.all(), key=lambda item: item.period)
        ],
        "player_status": serialize_summary(summary) if summary is not None else None,
    }


# ---------------------------------------------------------------------------
# Paiement en ligne, phase 1 : « Contribuer » et « J'ai payé » (tâche 2.5 ;
# CDC 4.6). Sérialisation seule : statut, lien et types proposés viennent
# de ``apps.treasury.services``.
# ---------------------------------------------------------------------------


class PaymentDeclarationCreateSerializer(serializers.Serializer):
    """Modale « J'ai payé » (fiche comptes-mon-profil §4.2) : JSON ou
    multipart. Montant en chaîne (``services.to_money`` refuse les
    flottants) ; référence contrôlée par le service (message en français)."""

    contribution_type_id = serializers.IntegerField()
    amount = serializers.CharField(max_length=32)
    reference = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    attachment = serializers.FileField(required=False, allow_null=True)


def serialize_contribute_info(info) -> dict:
    """Bouton « Contribuer » : ``payment_link_url`` vaut ``None`` si le club
    n'a pas configuré de lien (bouton masqué côté interface)."""

    return {
        "payment_link_configured": bool(info.payment_link_url),
        "payment_link_url": info.payment_link_url or None,
        "currency": info.currency,
        "contribution_types": [
            {
                "id": ctype.pk,
                "name": ctype.name,
                "nature": ctype.nature,
                "periodicity": ctype.periodicity,
                "amount": _money(ctype.amount),
            }
            for ctype in info.contribution_types
        ],
        "default_contribution_type_id": info.default_contribution_type_id,
    }


def serialize_declaration(payment, *, summary=None) -> dict:
    """Déclaration « J'ai payé » (et, une fois validée, paiement normal).
    Attend ``payment.transaction`` et ``payment.membership.user`` chargés."""

    txn = payment.transaction
    status_key = services.payment_status_key(payment)
    user = payment.membership.user
    data = serialize_payment(payment, summary=summary)
    data.update(
        {
            "status": status_key,
            "status_label": services.PAYMENT_STATUS_LABELS[status_key],
            "player": {"membership_id": payment.membership_id, "name": _user_name(user)},
            "submitted_at": payment.submitted_at,
            "rejected_at": payment.rejected_at,
            "rejection_reason": payment.rejection_reason,
            "transaction": {"provider": txn.provider, "status": txn.status, "external_ref": txn.external_ref},
        }
    )
    return data


# ---------------------------------------------------------------------------
# Tableau de bord Trésorerie (CDC 4.4.6 ; fiche tresorerie-tableau-de-bord
# §3, §4.4). Sérialisation seule : indicateurs et statuts calculés par
# ``apps.treasury.services``.
# ---------------------------------------------------------------------------


def serialize_dashboard_summary(summary) -> dict:
    return {
        "period": summary.period.strftime("%Y-%m"),
        "currency": summary.currency,
        "collected": _money(summary.collected),
        "collection_rate": _money(summary.collection_rate),
        "matured_due_total": _money(summary.matured_due_total),
        "matured_due_covered": _money(summary.matured_due_covered),
        "total_debts": _money(summary.total_debts),
        "members_in_debt": summary.members_in_debt,
        "available_cash": _money(summary.available_cash),
    }


def _actor(user, reader):
    """Auteur d'une écriture vu par ``reader`` : un Superuser (jamais joueur,
    donc intervenu en Ghost Mode) apparaît « Système Vesta » côté club
    (CDC 5.4 ; même libellé que ``apps.audit.services``)."""

    if user is None:
        return None
    if getattr(user, "is_superuser", False) and not getattr(reader, "is_superuser", False):
        return {"id": None, "name": GHOST_ACTOR_DISPLAY_NAME}
    return {"id": user.pk, "name": _user_name(user)}


def _photo_url(user, request):
    """URL absolue de la photo de profil (fichier public, pas un justificatif).
    L'interface et l'API sont servies sur des hôtes distincts : un chemin
    relatif ``/media/...`` pointerait vers le serveur de l'interface."""

    if not user.photo:
        return None
    return request.build_absolute_uri(user.photo.url)


def _payment_player(membership, *, request) -> dict:
    user = membership.user
    return {
        "membership_id": membership.pk,
        "name": _user_name(user),
        "jersey_number": membership.jersey_number,
        "photo": _photo_url(user, request),
    }


def serialize_payment_list_item(payment, *, request) -> dict:
    """Ligne « Derniers paiements ». Attend ``membership__user``,
    ``contribution_type``, ``transaction`` et ``reversal`` chargés."""

    status_key = services.payment_status_key(payment)
    reversal = getattr(payment, "reversal", None)  # RelatedObjectDoesNotExist est une AttributeError
    return {
        "id": payment.pk,
        "player": _payment_player(payment.membership, request=request),
        "contribution_type": {"id": payment.contribution_type_id, "name": payment.contribution_type.name},
        "amount": _money(payment.amount),
        "currency": payment.currency,
        "paid_on": payment.paid_on,
        "method": payment.method,
        "method_label": payment.get_method_display(),
        "source": payment.source,
        "source_label": payment.get_source_display(),
        "status": status_key,
        "status_label": services.PAYMENT_STATUS_LABELS[status_key],
        "reversal_pending": reversal is not None and reversal.status == PaymentReversal.Status.PENDING_APPROVAL,
    }


def serialize_payment_detail(payment, *, reader, request) -> dict:
    """Modale « Détail du paiement » (fiche §4.4) : champs du paiement,
    répartition enregistrée, auteurs et annulation éventuelle."""

    data = serialize_payment(payment)
    data.update(serialize_payment_list_item(payment, request=request))
    reversal = getattr(payment, "reversal", None)  # RelatedObjectDoesNotExist est une AttributeError
    data.update(
        {
            "submitted_by": _actor(payment.submitted_by, reader),
            "submitted_at": payment.submitted_at,
            "validated_by": _actor(payment.validated_by, reader),
            "rejected_at": payment.rejected_at,
            "rejection_reason": payment.rejection_reason,
            "reversal": (
                {
                    "id": reversal.pk,
                    "status": reversal.status,
                    "status_label": reversal.get_status_display(),
                    "reason": reversal.reason,
                    "reason_kind": reversal.reason_kind,
                    "requested_by": _actor(reversal.requested_by, reader),
                    "requested_at": reversal.requested_at,
                    "approved_by": _actor(reversal.approved_by, reader),
                    "approved_at": reversal.approved_at,
                    "rejected_by": _actor(reversal.rejected_by, reader),
                    "rejected_at": reversal.rejected_at,
                    "rejection_reason": reversal.rejection_reason,
                }
                if reversal is not None
                else None
            ),
        }
    )
    return data


class ReversalRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=True, required=False, default="")


class ReversalRejectSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(allow_blank=True, required=False, default="")


def serialize_cash_session(session, *, state: str, payments_count: int, payments_total, currency: str, timezone: str):
    """Session de caisse : jamais de PIN ni d'empreinte de PIN, seulement
    l'identifiant public et les horodatages (10.2 n° 22)."""

    return {
        "id": str(session.public_id),
        "status": state,
        "is_open": state == "open",
        "opened_at": session.opened_at,
        "expires_at": session.expires_at,
        "closed_at": session.closed_at,
        "club_timezone": timezone,
        "payments_count": payments_count,
        "payments_total": _money(payments_total),
        "currency": currency,
    }


def serialize_cash_player(result, *, request) -> dict:
    """Résultat de recherche de la caisse : champs nécessaires uniquement
    (jamais d'email ni de téléphone)."""

    membership = result.membership
    user = membership.user
    return {
        "membership_id": membership.pk,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "jersey_number": membership.jersey_number,
        "photo": _photo_url(user, request),
        "membership_status": membership.status,
        "membership_status_label": membership.get_status_display(),
        "default_contribution_type_id": result.default_contribution_type_id,
        **serialize_summary(result.summary),
    }


# ---------------------------------------------------------------------------
# Grille des cotisations et import historique (tâche 2.6 ; CDC 4.4.7,
# 4.4.8). Sérialisation seule : états, montants, soldes et interprétation
# des cellules sont calculés par ``apps.treasury.services``.
# ---------------------------------------------------------------------------


def serialize_grid_type(ctype) -> dict:
    return {
        "id": ctype.pk,
        "name": ctype.name,
        "nature": ctype.nature,
        "nature_label": ctype.get_nature_display(),
        "periodicity": ctype.periodicity,
        "periodicity_label": ctype.get_periodicity_display(),
        "amount": _money(ctype.amount),
        "scope": ctype.scope,
        "status": ctype.status,
        "is_free": ctype.nature == ContributionType.Nature.FREE,
    }


def serialize_grid_cell(cell) -> dict:
    return {
        "period": cell.period,
        "month": cell.period.month,
        "amount_due": _money(cell.amount_due),
        "allocated": _money(cell.allocated),
        "state": cell.state,
        "state_label": services.GRID_STATE_LABELS[cell.state],
        "overdue_amount": _money(cell.overdue_amount),
    }


def _grid_player(membership, *, request) -> dict:
    user = membership.user
    return {
        "membership_id": membership.pk,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "name": _user_name(user),
        "jersey_number": membership.jersey_number,
        "photo": _photo_url(user, request),
        "membership_status": membership.status,
        "membership_status_label": membership.get_status_display(),
    }


def serialize_grid_row(row, *, request, summary=None) -> dict:
    return {
        **_grid_player(row.membership, request=request),
        "cells": [serialize_grid_cell(cell) for cell in row.cells],
        "total": _money(row.total),
        "overdue_amount": _money(row.overdue_amount),
        "has_unpaid": row.has_unpaid,
        "player_status": serialize_summary(summary) if summary is not None else None,
    }


def serialize_grid_months(grid) -> list:
    return [
        {
            "period": period,
            "month": period.month,
            "label": services.FRENCH_MONTHS_SHORT[period.month - 1],
            "long_label": services.french_month_label(period),
        }
        for period in grid.periods
    ]


def serialize_month_detail(detail, *, can_record_payment: bool, request) -> dict:
    cell = detail.cell
    payments = []
    for item in detail.payments:
        payment = item.payment
        spread = item.first_period != item.last_period
        payments.append(
            {
                "payment_id": payment.pk,
                "paid_on": payment.paid_on,
                "amount": _money(payment.amount),
                "allocated": _money(item.allocated),
                "receipt_number": payment.receipt_number,
                "receipt_url": reverse("treasury:payment-receipt-download", args=[payment.pk]),
                "method": payment.method,
                "method_label": payment.get_method_display(),
                "source": payment.source,
                "source_label": payment.get_source_display(),
                "reference": payment.reference,
                "spread_from": item.first_period,
                "spread_to": item.last_period,
                "spread_label": (
                    f"Paiement de {_money(payment.amount)} {payment.currency} du {payment.paid_on:%d/%m/%Y}, "
                    f"réparti de {services.french_month_label(item.first_period)} "
                    f"à {services.french_month_label(item.last_period)}."
                    if spread
                    else None
                ),
            }
        )
    return {
        "contribution_type": serialize_grid_type(detail.contribution_type),
        "player": _grid_player(detail.membership, request=request),
        "currency": detail.currency,
        "period": cell.period,
        "period_label": services.french_month_label(cell.period),
        "cell": serialize_grid_cell(cell),
        "payments": payments,
        "can_record_payment": can_record_payment,
    }


class ContributionImportInputSerializer(serializers.Serializer):
    """Modale d'import (CDC 4.4.8) : type, année et fichier CSV (multipart)."""

    contribution_type_id = serializers.IntegerField()
    year = serializers.IntegerField()
    file = serializers.FileField()


class ContributionImportCreateSerializer(ContributionImportInputSerializer):
    pin = serializers.CharField(max_length=12)


def _import_payment_line(line) -> dict:
    return {
        "period": line.period,
        "paid_on": line.paid_on,
        "amount": _money(line.amount),
        "origin": line.origin,
        "reference": line.reference,
    }


def serialize_import_report(report, *, request) -> dict:
    batch = report.import_batch
    return {
        "is_preview": report.is_preview,
        "import_batch_id": batch.pk if batch is not None else None,
        "contribution_type": serialize_grid_type(report.contribution_type),
        "year": report.year,
        "currency": report.currency,
        "months": [
            {"period": period, "month": period.month, "label": services.FRENCH_MONTHS_SHORT[period.month - 1]}
            for period in services.year_periods(report.year)
        ],
        "summary": {
            "rows_total": len(report.rows),
            "rows_succeeded": report.success_count,
            "rows_failed": report.failed_count,
            "payments_count": report.payments_count,
            "payments_total": _money(report.payments_total),
            "dues_count": report.dues_count,
            "already_imported_count": report.already_imported_count,
        },
        "ignored_columns": list(report.ignored_columns),
        "ignored_lines": list(report.ignored_lines),
        "rows": [
            {
                "line_number": row.line_number,
                "identity": row.identity,
                "status": row.status,
                "player": _grid_player(row.membership, request=request) if row.membership is not None else None,
                "errors": list(row.errors),
                "warnings": list(row.warnings),
                "payments": [_import_payment_line(line) for line in row.payments],
                "already_imported": [_import_payment_line(line) for line in row.already_imported],
                "dues": [
                    {"period": line.period, "amount": _money(line.amount), "due_date": line.due_date}
                    for line in row.dues
                ],
                "cells": [serialize_grid_cell(cell) for cell in row.grid_row.cells] if row.grid_row else [],
                "total": _money(row.grid_row.total) if row.grid_row else None,
                "balance_before": _money(row.balance_before),
                "balance_after": _money(row.balance_after),
                "player_status_after": serialize_summary(row.summary_after) if row.summary_after else None,
            }
            for row in report.rows
        ],
    }
