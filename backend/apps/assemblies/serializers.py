"""Serializers DRF de l'app assemblies (CDC 4.15 ; assemblees-page-ag.md).

Chaque AG expose ses droits calcules cote API (``can_manage``,
``can_sign_president``, ``can_sign_vice_president``) : « l'interface
n'affiche un bouton que si le droit correspondant est present, elle ne
deduit jamais un droit du libelle d'un role » (assemblees-page-ag.md §2).
"""

from __future__ import annotations

import os

from django.urls import reverse
from rest_framework import serializers

from apps.assemblies.models import AgendaItem, ArchivedDocument, Assembly, AssemblyAttendance, Decision, Minutes
from apps.assemblies.permissions import ASSEMBLY_CONVENER_ROLES
from apps.assemblies.services import get_quorum
from apps.clubs.models import MembershipRole
from apps.core.roles import get_active_roles
from apps.core.validators import validate_image_or_pdf, validate_upload_size


def _user_name(user) -> str:
    if user is None:
        return ""
    return f"{user.first_name} {user.last_name}".strip()


class AgendaItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgendaItem
        fields = ["id", "order", "title", "description"]
        read_only_fields = fields


class AgendaItemInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160, allow_blank=False)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class ConveneAssemblyInputSerializer(serializers.Serializer):
    assembly_type = serializers.ChoiceField(choices=Assembly.AssemblyType.choices)
    scheduled_date = serializers.DateField()
    scheduled_time = serializers.TimeField()
    location = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    agenda_items = AgendaItemInputSerializer(many=True)

    def validate_agenda_items(self, value):
        if not value:
            raise serializers.ValidationError("Ajoutez au moins un point a l'ordre du jour.")
        return value


class DecisionSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Decision
        fields = [
            "id",
            "agenda_item_id",
            "votes_for",
            "votes_against",
            "votes_abstain",
            "outcome",
            "linked_object_type",
            "linked_object_id",
            "recorded_by_name",
            "recorded_at",
        ]
        read_only_fields = fields

    def get_recorded_by_name(self, obj: Decision) -> str:
        return _user_name(obj.recorded_by)


class DecisionInputSerializer(serializers.Serializer):
    votes_for = serializers.IntegerField(min_value=0)
    votes_against = serializers.IntegerField(min_value=0)
    votes_abstain = serializers.IntegerField(min_value=0)
    outcome = serializers.CharField(allow_blank=False)
    linked_object_type = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    linked_object_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class AttendanceSerializer(serializers.ModelSerializer):
    membership_id = serializers.IntegerField(source="membership.id")
    first_name = serializers.CharField(source="membership.user.first_name")
    last_name = serializers.CharField(source="membership.user.last_name")
    jersey_number = serializers.IntegerField(source="membership.jersey_number")

    class Meta:
        model = AssemblyAttendance
        fields = ["membership_id", "first_name", "last_name", "jersey_number", "present", "checked_in_at"]
        read_only_fields = fields


class AttendanceMarkInputSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()


class QuorumSerializer(serializers.Serializer):
    present = serializers.IntegerField()
    total = serializers.IntegerField()
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    threshold = serializers.DecimalField(max_digits=5, decimal_places=2)
    reached = serializers.BooleanField()


class MinutesSerializer(serializers.ModelSerializer):
    president_signed_by_name = serializers.SerializerMethodField()
    vp_signed_by_name = serializers.SerializerMethodField()
    is_complete = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = Minutes
        fields = [
            "content",
            "president_signed_by_name",
            "president_signed_at",
            "vp_signed_by_name",
            "vp_signed_at",
            "vp_vacant_at_signature",
            "vp_role_held_by_president",
            "is_complete",
            "generated_at",
            "pdf_url",
        ]
        read_only_fields = fields

    def get_president_signed_by_name(self, obj: Minutes) -> str:
        return _user_name(obj.president_signed_by)

    def get_vp_signed_by_name(self, obj: Minutes) -> str:
        return _user_name(obj.vp_signed_by)

    def get_is_complete(self, obj: Minutes) -> bool:
        return obj.is_complete

    def get_pdf_url(self, obj: Minutes) -> str | None:
        if not obj.pdf_file or not obj.generated_at:
            return None
        return reverse("assemblies:minutes-pdf-download", kwargs={"pk": obj.assembly_id})


class MinutesDraftInputSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=True)


class QuorumThresholdInputSerializer(serializers.Serializer):
    percentage = serializers.IntegerField(min_value=1, max_value=100)


class AssemblySerializer(serializers.ModelSerializer):
    agenda_items = AgendaItemSerializer(many=True, read_only=True)
    decisions = DecisionSerializer(many=True, read_only=True)
    quorum = serializers.SerializerMethodField()
    minutes = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    can_convene = serializers.SerializerMethodField()
    can_sign_president = serializers.SerializerMethodField()
    can_sign_vice_president = serializers.SerializerMethodField()

    class Meta:
        model = Assembly
        fields = [
            "id",
            "assembly_type",
            "scheduled_date",
            "scheduled_time",
            "location",
            "status",
            "created_at",
            "agenda_items",
            "decisions",
            "quorum",
            "minutes",
            "can_manage",
            "can_convene",
            "can_sign_president",
            "can_sign_vice_president",
        ]
        read_only_fields = fields

    def get_quorum(self, obj: Assembly) -> dict:
        return QuorumSerializer(get_quorum(obj)).data

    def get_minutes(self, obj: Assembly) -> dict | None:
        minutes = Minutes.objects.filter(assembly=obj).first()
        if minutes is None:
            return None
        return MinutesSerializer(minutes).data

    def _roles(self, obj: Assembly) -> frozenset[str]:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None:
            return frozenset()
        return get_active_roles(user, club=obj.club)

    def get_can_manage(self, obj: Assembly) -> bool:
        roles = self._roles(obj)
        return bool(roles.intersection({MembershipRole.Role.PRESIDENT, MembershipRole.Role.VICE_PRESIDENT}))

    def get_can_convene(self, obj: Assembly) -> bool:
        return bool(self._roles(obj).intersection(ASSEMBLY_CONVENER_ROLES))

    def get_can_sign_president(self, obj: Assembly) -> bool:
        roles = self._roles(obj)
        if MembershipRole.Role.PRESIDENT not in roles:
            return False
        minutes = Minutes.objects.filter(assembly=obj).first()
        if minutes is None:
            return False
        return minutes.president_signed_by_id is None and not minutes.is_complete

    def get_can_sign_vice_president(self, obj: Assembly) -> bool:
        roles = self._roles(obj)
        # « Un joueur qui cumule President et un autre role signe une
        # seule fois, au titre de President » (assemblees-page-ag.md §2).
        if MembershipRole.Role.PRESIDENT in roles:
            return False
        if MembershipRole.Role.VICE_PRESIDENT not in roles:
            return False
        minutes = Minutes.objects.filter(assembly=obj).first()
        if minutes is None:
            return False
        return minutes.vp_signed_by_id is None and not minutes.is_complete


# ---------------------------------------------------------------------------
# Archive des documents officiels (CDC 4.15.1)
# ---------------------------------------------------------------------------

GHOST_DISPLAY_NAME = "Système Vesta"


def _display_author(user) -> str:
    """Un Superuser agissant dans un club apparait « Système Vesta » (CDC 5.4)."""

    if user is None:
        return ""
    if getattr(user, "is_superuser", False):
        return GHOST_DISPLAY_NAME
    return _user_name(user)


class ArchivedDocumentSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    withdrawn_by_name = serializers.SerializerMethodField()
    replaces_id = serializers.IntegerField(read_only=True)
    replaced_by_id = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ArchivedDocument
        fields = [
            "id",
            "category",
            "category_label",
            "title",
            "document_date",
            "status",
            "status_label",
            "uploaded_by_name",
            "uploaded_at",
            "withdrawn_by_name",
            "withdrawn_at",
            "withdrawn_reason",
            "replaces_id",
            "replaced_by_id",
            "file_name",
            "file_size",
            "download_url",
        ]
        read_only_fields = fields

    def get_uploaded_by_name(self, obj: ArchivedDocument) -> str:
        return _display_author(obj.uploaded_by)

    def get_withdrawn_by_name(self, obj: ArchivedDocument) -> str:
        return _display_author(obj.withdrawn_by)

    def get_replaced_by_id(self, obj: ArchivedDocument):
        return ArchivedDocument.all_objects.filter(replaces_id=obj.pk).values_list("pk", flat=True).first()

    def get_file_name(self, obj: ArchivedDocument) -> str:
        return os.path.basename(obj.file.name) if obj.file else ""

    def get_file_size(self, obj: ArchivedDocument):
        try:
            return obj.file.size
        except (OSError, ValueError):
            return None

    def get_download_url(self, obj: ArchivedDocument) -> str:
        return reverse("assemblies:archive-file", kwargs={"pk": obj.pk})


class ArchivedDocumentInputSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=ArchivedDocument.Category.choices)
    title = serializers.CharField(max_length=160, allow_blank=False)
    document_date = serializers.DateField()
    file = serializers.FileField(validators=[validate_upload_size, validate_image_or_pdf])


class ArchivedDocumentWithdrawInputSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, max_length=500)
