"""Contexte du club actif (multi-tenant, CLAUDE.md regles n8/n9 ; CDC 6.3).

Ce module expose le mecanisme de "club actif" de facon independante de
toute requete HTTP, pour qu'il soit testable des la tache 1.2 (avant que
l'authentification JWT ne soit branchee en tache 1.3). Le club actif :

- ne vient **jamais** d'un parametre transmis tel quel par le client, ni
  d'un ``tenant_id`` fige dans un jeton JWT (regle n9) ;
- se deduit **toujours** de l'adhesion (``Membership``) en cours de
  l'utilisateur authentifie (voir :func:`resolve_active_membership` dans
  ``apps.core.services``).

A partir de la tache 1.3, un middleware ou la couche d'authentification
DRF appellera :func:`set_active_club` (ou le gestionnaire de contexte
:func:`active_club`) au debut de chaque requete authentifiee, avec le
club resolu par :func:`apps.core.services.resolve_active_membership`,
puis :func:`reset_active_club` a la fin de la requete (y compris en cas
d'exception), pour ne jamais faire fuiter le club actif d'une requete a
l'autre.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, Optional

if TYPE_CHECKING:  # pragma: no cover - uniquement pour l'annotation de type
    from apps.clubs.models import Club


class NoActiveClubError(Exception):
    """Levee quand une operation tenant-aware est tentee sans club actif.

    CLAUDE.md regle n8 : « Toute donnee privee est filtree par club [...]
    Une requete sans club actif est refusee. »
    """


class TenantMismatchError(Exception):
    """Levee quand une ecriture directe porte un club different du club actif.

    Audit de securite du Lot 1 (ecart bloquant B4) : le manager
    tenant-aware (``TenantManager``/``TenantQuerySet``) ne filtre que les
    **lectures** -- rien n'empechait jusqu'ici de creer directement
    (``Model.objects.create(...)`` ou ``Model(...).save()``) une ligne
    dont ``club`` est en realite un autre club que celui actif dans le
    contexte courant. Cette exception ferme ce contournement en
    ecriture, appliquee par ``apps.core.models.TenantModel.save()``.

    Ne s'applique que si un club actif existe reellement dans le
    contexte courant (``get_active_club()`` non ``None``) : hors de
    toute requete HTTP (import de donnees, commande de gestion, contexte
    Superuser), aucune restriction n'est appliquee par cette exception --
    c'est deja le comportement voulu ailleurs (voir ``TenantManager``,
    qui ne filtre les lectures que dans ce meme cas).
    """


# Contexte par tache/thread (``contextvars`` fonctionne correctement en
# WSGI synchrone comme en ASGI/async, contrairement a un simple attribut
# de module ou un ``threading.local`` classique).
_active_club_var: "contextvars.ContextVar[Optional[Club]]" = contextvars.ContextVar(
    "vesta_active_club", default=None
)


def get_active_club() -> Optional["Club"]:
    """Renvoie le club actif du contexte courant, ou ``None`` si aucun."""

    return _active_club_var.get()


def set_active_club(club: Optional["Club"]) -> contextvars.Token:
    """Positionne le club actif du contexte courant.

    Renvoie un jeton a passer a :func:`reset_active_club` pour restaurer
    l'etat precedent. Utilise directement par les tests ; a partir de la
    tache 1.3, appele par le middleware/l'authentification pour la duree
    d'une requete HTTP reelle.
    """

    return _active_club_var.set(club)


def reset_active_club(token: contextvars.Token) -> None:
    """Restaure l'etat du club actif precedant :func:`set_active_club`."""

    _active_club_var.reset(token)


@contextmanager
def active_club(club: Optional["Club"]) -> Iterator[None]:
    """Gestionnaire de contexte pratique : ``with active_club(club): ...``.

    Garantit que le club actif est restaure (y compris en cas
    d'exception), ce qui evite qu'un club reste actif au-dela de la
    portee voulue -- essentiel pour les tests d'etancheite (un test qui
    leve ne doit jamais laisser un club actif pour le test suivant).
    """

    token = set_active_club(club)
    try:
        yield
    finally:
        reset_active_club(token)
