"""Serializers DRF de l'app licences (CDC 2.5, 4.18 ; tache 1.8).

Aucune regle metier ici (CLAUDE.md section 5) : validation de forme
uniquement. Toute regle metier (transitions, confirmation de resiliation,
Ghost Mode...) vit dans ``apps.licences.services``.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.licences.models import Licence, LicenceEvent, SupportSession
from apps.licences.services import is_support_session_valid


class LicenceSerializer(serializers.ModelSerializer):
    """Tableau des licences (CDC 4.18 : « tableau des clubs avec dates, statut »)."""

    club_name = serializers.CharField(source="club.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Licence
        fields = [
            "id",
            "club_id",
            "club_name",
            "status",
            "status_label",
            "start_date",
            "end_date",
            "grace_period_days",
            "created_by_id",
            "created_at",
        ]
        read_only_fields = fields


class LicenceEventSerializer(serializers.ModelSerializer):
    """Historique d'une licence (CDC 2.5 « historique », CDC 4.18)."""

    event_type_label = serializers.CharField(source="get_event_type_display", read_only=True)

    class Meta:
        model = LicenceEvent
        fields = ["id", "licence_id", "event_type", "event_type_label", "event_date", "actor_id", "note"]
        read_only_fields = fields


class LicenceActivateInputSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False, allow_null=True, default=None)
    end_date = serializers.DateField(required=False, allow_null=True, default=None)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class LicenceExtendInputSerializer(serializers.Serializer):
    end_date = serializers.DateField()
    start_date = serializers.DateField(required=False, allow_null=True, default=None)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class LicenceSuspendInputSerializer(serializers.Serializer):
    reason = serializers.CharField()

    def validate_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Le motif de suspension est obligatoire.")
        return value


class LicenceResumeInputSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class LicenceTerminateInputSerializer(serializers.Serializer):
    """CDC 2.5, 4.18 ; 10.2 n26 : motif ET saisie du nom exact du club."""

    reason = serializers.CharField()
    confirm_club_name = serializers.CharField()

    def validate_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Le motif de résiliation est obligatoire.")
        return value


class SupportSessionSerializer(serializers.ModelSerializer):
    """Session de support en Ghost Mode (CDC 4.18, 5.4)."""

    club_name = serializers.CharField(source="club.name", read_only=True)
    is_valid = serializers.SerializerMethodField()

    class Meta:
        model = SupportSession
        fields = [
            "id",
            "club_id",
            "club_name",
            "superuser_id",
            "reason",
            "started_at",
            "expires_at",
            "ended_at",
            "is_valid",
        ]
        read_only_fields = fields

    def get_is_valid(self, obj: SupportSession) -> bool:
        return is_support_session_valid(obj)


class SupportSessionStartInputSerializer(serializers.Serializer):
    club_id = serializers.IntegerField()
    reason = serializers.CharField()

    def validate_reason(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Le motif de la session de support est obligatoire.")
        return value
