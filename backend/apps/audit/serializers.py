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
from apps.audit.services import GHOST_ACTOR_DISPLAY_NAME, get_actor_display_name


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
