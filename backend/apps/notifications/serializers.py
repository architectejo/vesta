"""Serializers DRF de l'app notifications (CDC 4.17 ; tache 1.7).

Prepare l'ecran de la tache 1.9 (icone cloche, modale Mon profil) --
hors perimetre de cette tache : seuls les endpoints sont livres ici.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.notifications.models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    """Une notification, telle qu'affichee dans la liste de l'icone cloche
    (CDC 3.4, 4.17). En lecture seule : la seule modification possible
    (marquer comme lue) passe par un endpoint dedie, pas par une mise a
    jour generique de ce serializer."""

    class Meta:
        model = Notification
        fields = [
            "id",
            "event_type",
            "title",
            "body",
            "link_object_type",
            "link_object_id",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Preference email globale (CDC 4.17). Seul ``email_enabled`` est
    modifiable par le titulaire du compte (onglet « Informations » de la
    modale Mon profil, tache 1.9)."""

    class Meta:
        model = NotificationPreference
        fields = ["email_enabled", "updated_at"]
        read_only_fields = ["updated_at"]
