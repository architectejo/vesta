"""Serializers DRF de l'app audit (CDC 5.1, 5.4 ; tache 1.8).

L'ecran de consultation/filtrage complet du journal (CDC 5.5) reste hors
perimetre de cette tache (tache frontend/ulterieure) : seule la
representation d'UNE entree est fournie ici, prete a etre reutilisee par
ce futur ecran comme par tout autre module qui exposerait un jour
l'acteur d'une action a un club (voir
``apps.audit.services.get_actor_display_name``, le point de masquage
Ghost Mode centralise -- CDC 5.4).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.audit.services import (
    ALERT_ACTION_TYPES,
    GHOST_ACTOR_DISPLAY_NAME,
    get_actor_display_name,
    is_medical_entry,
)


class AuditLogSerializer(serializers.ModelSerializer):
    """Representation d'une entree de journal (CDC 5.1).

    ``actor_display`` ET ``actor_id`` appliquent tous les deux le meme
    masquage Ghost Mode (CDC 5.4) : « Systeme Vesta » / ``None`` si
    ``acted_as_ghost`` est vrai et que le lecteur courant
    (``self.context["request"].user``) n'est pas lui-meme un Superuser --
    voir ``apps.audit.services.get_actor_display_name`` pour la regle
    complete, reutilisee ici (pas de condition dupliquee a la main) pour
    decider si ``actor_id`` doit etre masque. L'identite reelle du
    Superuser n'est donc exposee par NI L'UN NI L'AUTRE champ a un lecteur
    non-Superuser (CDC 5.4 : « l'identite reelle du Superuser ne doit
    jamais transpirer cote club ») -- seule l'entree `AuditLog` en base
    (jamais ce serializer) conserve l'identite reelle (CDC 5.4 : « le
    journal conserve l'identite reelle »). Pour un lecteur Superuser (CDC
    2.4 : « Le journal d'activite [...] n'est visible que par les
    Superusers »), aucun masquage ne s'applique et ``actor_id`` reste
    l'identifiant reel.
    """

    actor_display = serializers.SerializerMethodField()
    actor_id = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "club_id",
            "actor_id",
            "actor_display",
            "acted_as_ghost",
            "action_type",
            "object_type",
            "object_id",
            "before",
            "after",
            "ip_address",
            "user_agent",
            "device",
            "created_at",
        ]
        read_only_fields = fields

    def _reader(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_actor_display(self, obj: AuditLog) -> str:
        return get_actor_display_name(obj, reader=self._reader())

    def get_actor_id(self, obj: AuditLog):
        reader = self._reader()
        if get_actor_display_name(obj, reader=reader) == GHOST_ACTOR_DISPLAY_NAME:
            return None
        return obj.actor_id


class AuditLogListSerializer(AuditLogSerializer):
    """Ligne du tableau Journal (ecran superuser §3.4) : sans avant/apres
    ni contexte technique (reserves a la modale de detail)."""

    club_name = serializers.SerializerMethodField()
    club_timezone = serializers.SerializerMethodField()
    is_alert = serializers.SerializerMethodField()

    class Meta(AuditLogSerializer.Meta):
        fields = [
            "id",
            "created_at",
            "club_id",
            "club_name",
            "club_timezone",
            "actor_id",
            "actor_display",
            "acted_as_ghost",
            "support_session_id",
            "action_type",
            "object_type",
            "object_id",
            "is_alert",
        ]
        read_only_fields = fields

    def get_club_name(self, obj: AuditLog):
        return obj.club.name if obj.club_id else None

    def get_club_timezone(self, obj: AuditLog):
        if not obj.club_id:
            return None
        club_settings = getattr(obj.club, "settings", None)
        return getattr(club_settings, "timezone", None)

    def get_is_alert(self, obj: AuditLog) -> bool:
        return obj.action_type in ALERT_ACTION_TYPES


class AuditLogDetailSerializer(AuditLogListSerializer):
    """Modale « Entree du journal » (§4.6). Pour une entree ``medical.*``,
    ``before``/``after`` ne sont jamais renvoyes (10.2 n137, position
    prudente) ; ``medical_content_withheld`` vaut alors vrai et
    l'interface affiche « Contenu medical non copie dans le journal. »."""

    support_session = serializers.SerializerMethodField()
    medical_content_withheld = serializers.SerializerMethodField()
    before = serializers.SerializerMethodField()
    after = serializers.SerializerMethodField()

    class Meta(AuditLogListSerializer.Meta):
        fields = AuditLogListSerializer.Meta.fields + [
            "support_session",
            "before",
            "after",
            "medical_content_withheld",
            "ip_address",
            "user_agent",
            "device",
        ]
        read_only_fields = fields

    def get_support_session(self, obj: AuditLog):
        if not obj.support_session_id:
            return None
        if not str(obj.support_session_id).isdigit():
            return {"id": obj.support_session_id, "reason": None}
        from apps.licences.models import SupportSession

        session = SupportSession.objects.filter(pk=int(obj.support_session_id)).first()
        return {"id": obj.support_session_id, "reason": session.reason if session else None}

    def get_medical_content_withheld(self, obj: AuditLog) -> bool:
        return is_medical_entry(obj)

    def get_before(self, obj: AuditLog):
        return None if is_medical_entry(obj) else obj.before

    def get_after(self, obj: AuditLog):
        return None if is_medical_entry(obj) else obj.after
