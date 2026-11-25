"""Mecanisme generique de verification des roles de club (CDC 2.2-2.4).

Tache 1.5 : point d'entree **unique** pour repondre a la question « cet
utilisateur porte-t-il tel role (ou l'un de tels roles) dans le club
actif ? », cumul de roles inclus (CDC 2.2 : « Un joueur peut cumuler
plusieurs roles [...] Ses droits sont alors l'union des droits de ses
roles »). Reutilisable par toute app qui declare ses propres classes de
permission par-dessus ce mecanisme (CLAUDE.md section 7) : `apps.clubs`
(tache 1.5) en est le premier consommateur ; `treasury`/`sport`/
`medical`/... suivront plus tard, chacune avec ses propres classes de
permission specifiques a sa colonne de la matrice 2.4.

Volontairement independant de DRF pour les fonctions de bas niveau
(:func:`get_active_roles`, :func:`has_any_role`) : elles sont aussi
utilisees par `apps.clubs.services` (defense en profondeur, cote
service, en plus du controle cote vue -- meme principe que
`apps.accounts.services.reset_password_by_superuser`, qui revalide
`is_superuser` malgre la classe de permission `IsSuperuser` sur la vue).
"""

from __future__ import annotations

from typing import Iterable, Optional

from rest_framework.permissions import BasePermission


def get_active_roles(user, club=None) -> frozenset[str]:
    """Renvoie l'ensemble des codes de role ACTIFS (non revoques) de
    ``user`` pour ``club``.

    ``club`` omis : le club actif du contexte courant (CLAUDE.md regle
    n9). Renvoie un ensemble vide -- jamais une exception -- pour tout
    utilisateur sans adhesion active dans ce club (y compris un
    Superuser, qui n'a jamais de fiche joueur, CLAUDE.md regle n1) :
    l'appelant (permission DRF ou service) traduit cet ensemble vide en
    refus, sans avoir a gerer une exception pour un cas parfaitement
    normal (« ce joueur n'a simplement aucun role »).
    """

    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()
    if getattr(user, "is_superuser", False):
        return frozenset()

    # Imports tardifs : evitent tout import circulaire au chargement des
    # apps (apps.core est charge avant apps.clubs ; apps.core.services
    # importe deja apps.clubs.models de la meme facon).
    from apps.clubs.models import MembershipRole
    from apps.core.services import resolve_active_membership
    from apps.core.tenant import NoActiveClubError, get_active_club

    resolved_club = club if club is not None else get_active_club()
    if resolved_club is None:
        return frozenset()

    try:
        membership = resolve_active_membership(user, club=resolved_club)
    except NoActiveClubError:
        return frozenset()

    role_codes = MembershipRole.all_objects.filter(
        membership=membership, revoked_at__isnull=True
    ).values_list("role", flat=True)
    return frozenset(role_codes)


def is_ghost_read_access(request) -> bool:
    """Vrai pour une requête de LECTURE d'un Superuser pendant une session de
    support valide (Ghost Mode, CDC 4.18, 5.4) : le club actif est alors celui
    de la session (posé par ``TenantJWTAuthentication``). Position prudente :
    lecture seule (aucune écriture), jamais hors session de support."""

    from apps.core.ghost_context import get_ghost_context
    from apps.core.tenant import get_active_club

    user = getattr(request, "user", None)
    if not (getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False)):
        return False
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        return False
    return get_ghost_context() is not None and get_active_club() is not None


def has_any_role(user, roles: Iterable[str], club=None) -> bool:
    """Vrai si ``user`` porte au moins un des ``roles`` (union, CDC 2.2)."""

    active = get_active_roles(user, club=club)
    return bool(active.intersection(roles))


class HasClubRole(BasePermission):
    """Classe de base DRF : reserve aux porteurs d'au moins un role donne.

    Ne pas instancier directement : chaque sous-classe fixe
    ``required_roles`` (voir ``apps.clubs.permissions`` pour des
    exemples concrets, un par colonne pertinente de la matrice 2.4).
    Le controle porte sur le club actif du contexte courant -- jamais un
    club transmis tel quel par le client (CLAUDE.md regle n9).
    """

    required_roles: frozenset[str] = frozenset()
    message = "Vous n'avez pas le rôle requis pour cette action."
    #: Lecture ouverte au Superuser en session de support. Faux pour le
    #: module médical (aucun accès au contenu médical, 10.2 n° 137).
    ghost_readable: bool = True

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return False
        if self.ghost_readable and is_ghost_read_access(request):
            return True
        return has_any_role(user, self.required_roles)

    @classmethod
    def for_roles(cls, *roles: str, message: Optional[str] = None) -> type["HasClubRole"]:
        """Fabrique une sous-classe figee sur un ensemble de roles precis.

        Pratique pour un cas ponctuel ; les classes nommees et
        documentees de ``apps.clubs.permissions`` restent preferables
        pour tout endpoint durable (message d'erreur specifique, nom
        explicite dans les traces).
        """

        attrs: dict = {"required_roles": frozenset(roles)}
        if message is not None:
            attrs["message"] = message
        return type(f"HasClubRole_{'_'.join(sorted(roles))}", (cls,), attrs)
