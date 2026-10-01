"""Agregation en lecture de « Mon profil » (tache 1.9, slice Lot 1).

Sources : `docs/ecrans/comptes-mon-profil.md` (specification complete,
Lot 0 -- ce module ne couvre QUE la tranche du Lot 1 : identite,
informations personnelles, rôles actifs, preference de notification
email). Explicitement HORS PERIMETRE ici (a construire par les lots
concernes, jamais improvise) : situation financiere (Lot 2), assistance
sociale (Lot 2), statistiques/carriere (sport, lot ulterieur),
sante/consentement medical (Lot 4), mercato (lot ulterieur).

Module SEPARE de ``apps.clubs.services`` (deja tres volumineux) : cette
agregation ne modifie jamais de donnees (lecture seule) et compose
plusieurs apps (``apps.accounts`` pour l'identite, ``apps.core.roles``
pour les roles, ``apps.notifications`` pour la preference email) --
nom explicite pour qu'un futur lecteur trouve immediatement ce qui est
propre a l'ecran « Mon profil » (CLAUDE.md section 5).

Renvoie un dictionnaire brut (meme choix que
``apps.accounts.services.search_accounts``) plutot qu'un objet de
plusieurs modeles : c'est une agregation de lecture, pas une entite.
"""

from __future__ import annotations

from typing import Any

from apps.clubs import services as clubs_services
from apps.clubs.models import Membership, MembershipRole
from apps.core.services import resolve_active_membership
from apps.notifications.services import get_or_create_preference

__all__ = ["get_my_profile"]


def get_my_profile(user, request) -> dict[str, Any]:
    """Profil personnel de ``user`` dans son club actif (CDC 4.1, 4.2, 4.17 ;
    2.4 « P » -- propres donnees).

    Le club actif est deduit de l'adhesion en cours de ``user``
    (CLAUDE.md regle n9, ``apps.core.services.resolve_active_membership``) --
    jamais transmis par le client.

    ``request`` sert uniquement a construire des URL absolues pour
    ``logo``/``photo`` (``request.build_absolute_uri``, bug remarques.md) :
    un chemin relatif (``MEDIA_URL``) pointe vers le mauvais serveur des
    que l'interface et l'API sont sur des origines differentes -- voir la
    docstring de ``apps.accounts.views._serialize_club``. Ni ``logo`` ni
    ``photo`` ne sont des fichiers prives ici (pas de justificatif ni de
    document medical) : pas de passage par une vue authentifiee.
    """

    membership: Membership = resolve_active_membership(user)
    club = membership.club

    roles = MembershipRole.objects.filter(membership=membership, revoked_at__isnull=True)
    preference = get_or_create_preference(user)

    return {
        "membership_id": membership.id,
        "club": {
            "id": club.id,
            "slug": club.slug,
            "name": club.name,
            "logo": request.build_absolute_uri(club.logo.url) if club.logo else None,
            "primary_color": club.primary_color,
            "secondary_color": club.secondary_color,
        },
        "identity": {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "photo": request.build_absolute_uri(user.photo.url) if user.photo else None,
            "email": user.email,
            "phone": user.phone,
            "birth_date": user.birth_date,
            "weight_kg": user.weight_kg,
            "height_cm": user.height_cm,
        },
        "position": membership.position,
        "position_label": membership.get_position_display() if membership.position else "",
        "position_detail": membership.position_detail,
        "jersey_number": membership.jersey_number,
        "membership_status": membership.status,
        "membership_status_label": membership.get_status_display(),
        "roles": [
            {"role": role.role, "label": clubs_services.get_effective_role_label(role)}
            for role in roles
        ],
        "email_notifications_enabled": preference.email_enabled,
    }
