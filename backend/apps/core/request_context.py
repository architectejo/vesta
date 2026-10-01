"""Contexte de la requete HTTP courante (IP, user-agent) pour le journal (CDC 5.1).

Meme logique que ``apps.core.tenant`` pour le club actif (``contextvars``,
independant du mecanisme qui le renseigne) : positionne par
``apps.core.middleware.RequestContextMiddleware`` au debut de chaque
requete HTTP, lu par ``apps.core.services.log_action`` quand l'appelant
ne fournit pas explicitement ``ip_address``/``user_agent``.

Necessaire pour que les signaux qui journalisent une action (ex.
``apps.accounts.signals`` sur ``TermsAcceptance``, tache 1.6) portent
l'IP et le user-agent reels de la requete a l'origine de l'action, alors
qu'ils n'ont eux-memes aucun acces direct a l'objet ``request`` (CDC 5.1 ;
point ouvert laisse par la tache 1.6, resolu par la tache 1.3).
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator, NamedTuple


class RequestMeta(NamedTuple):
    ip_address: str = ""
    user_agent: str = ""


_request_meta_var: "contextvars.ContextVar[RequestMeta]" = contextvars.ContextVar(
    "vesta_request_meta", default=RequestMeta()
)


def get_request_meta() -> RequestMeta:
    """Renvoie le contexte de requete courant (vide hors requete HTTP)."""

    return _request_meta_var.get()


def set_request_meta(ip_address: str = "", user_agent: str = "") -> contextvars.Token:
    """Positionne le contexte de requete courant.

    Renvoie un jeton a passer a :func:`reset_request_meta`.
    """

    return _request_meta_var.set(RequestMeta(ip_address=ip_address or "", user_agent=user_agent or ""))


def reset_request_meta(token: contextvars.Token) -> None:
    """Restaure l'etat du contexte de requete precedant :func:`set_request_meta`."""

    _request_meta_var.reset(token)


@contextmanager
def request_meta(ip_address: str = "", user_agent: str = "") -> Iterator[None]:
    """Gestionnaire de contexte pratique, utilise notamment par les tests."""

    token = set_request_meta(ip_address, user_agent)
    try:
        yield
    finally:
        reset_request_meta(token)
