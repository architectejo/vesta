"""Contexte de la session de support en cours (Ghost Mode, CDC 5.4 ; tache 1.8).

Meme logique que ``apps.core.tenant`` (club actif) et
``apps.core.request_context`` (IP/user-agent) : un ``contextvars.ContextVar``
independant de tout mecanisme particulier qui le renseigne, pour rester
testable sans requete HTTP reelle et pour ne jamais fuiter d'une requete
a l'autre sur un meme thread/processus.

Ce module ne porte volontairement qu'un seul champ, l'identifiant de la
``apps.licences.models.SupportSession`` en cours (``support_session_id``,
sous forme texte -- meme convention que
``apps.audit.models.AuditLog.support_session_id``) :

- l'acteur REEL (``actor``) reste toujours celui explicitement passe par
  l'appelant a ``apps.core.services.log_action`` (jamais devine depuis un
  contexte global : CDC 5.4, « le journal conserve l'identite reelle du
  Superuser ») ;
- le club concerne passe par le mecanisme existant
  ``apps.core.tenant.set_active_club`` (positionne sur le SEUL club de la
  session de support, voir ``apps.core.authentication.TenantJWTAuthentication``
  et ``apps.licences.services``) -- ce module n'a donc pas besoin de porter
  le club une deuxieme fois.

Seuls ``acted_as_ghost``/``support_session_id`` (les deux champs de
``AuditLog`` qui distinguent une action Ghost Mode) sont deduits d'ici par
``apps.core.services.log_action`` quand l'appelant ne les fournit pas
explicitement -- exactement comme ``ip_address``/``user_agent`` sont deduits
de ``apps.core.request_context`` quand ils sont omis. Un appelant qui
fournit explicitement ces deux parametres n'est jamais ecrase par ce
contexte (meme regle que pour le club actif/l'IP/le user-agent).
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator, NamedTuple, Optional


class GhostContext(NamedTuple):
    support_session_id: str = ""


_ghost_context_var: "contextvars.ContextVar[Optional[GhostContext]]" = contextvars.ContextVar(
    "vesta_ghost_context", default=None
)


def get_ghost_context() -> Optional[GhostContext]:
    """Renvoie le contexte Ghost Mode courant, ou ``None`` hors session de support."""

    return _ghost_context_var.get()


def set_ghost_context(support_session_id: str) -> contextvars.Token:
    """Positionne le contexte Ghost Mode courant.

    Renvoie un jeton a passer a :func:`reset_ghost_context` pour restaurer
    l'etat precedent.
    """

    return _ghost_context_var.set(GhostContext(support_session_id=str(support_session_id)))


def reset_ghost_context(token: contextvars.Token) -> None:
    """Restaure l'etat du contexte Ghost Mode precedant :func:`set_ghost_context`."""

    _ghost_context_var.reset(token)


def clear_ghost_context() -> None:
    """Force explicitement « aucune session de support en cours ».

    Utilise par ``apps.core.middleware.RequestContextMiddleware`` en sortie
    de requete (meme principe que ``apps.core.tenant.set_active_club(None)``
    dans ce meme middleware) : une requete HTTP doit toujours repartir d'un
    etat neutre, sans dependre d'un jeton conserve par l'appelant -- le
    Ghost Mode ne doit jamais survivre au-dela de la requete qui l'a
    positionne, y compris en cas d'exception.
    """

    _ghost_context_var.set(None)


@contextmanager
def ghost_mode(support_session_id: str) -> Iterator[None]:
    """Gestionnaire de contexte pratique : ``with ghost_mode(str(session.pk)): ...``.

    Garantit que le contexte est restaure (y compris en cas d'exception),
    utilise notamment par les tests et par tout appelant hors requete HTTP
    (ex. commande de gestion qui interviendrait un jour au nom d'une
    session de support).
    """

    token = set_ghost_context(support_session_id)
    try:
        yield
    finally:
        reset_ghost_context(token)
