"""Gestionnaire d'exceptions DRF : messages d'authentification en français.

DRF et SimpleJWT produisent par défaut des messages en anglais
(« Token is invalid », « Authentication credentials were not provided. »).
Ce gestionnaire les remplace par des messages en français clair, en
conservant le code HTTP et le champ ``code`` pour le client.
"""

from __future__ import annotations

from django.http import Http404
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, NotFound
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

INVALID_SESSION_MESSAGE = "Votre session est invalide ou a expiré. Reconnectez-vous."
NOT_AUTHENTICATED_MESSAGE = "Vous n'êtes pas connecté. Connectez-vous pour continuer."
AUTHENTICATION_FAILED_MESSAGE = "Authentification impossible. Reconnectez-vous."
GENERIC_NOT_FOUND_MESSAGE = "Cet élément n'existe pas."


def _is_generic_not_found(exc) -> bool:
    """Vrai pour les 404 « génériques » produits par Django/DRF en anglais
    (``get_object_or_404`` : « No X matches the given query. » ; ``NotFound``
    sans détail : « Not found. »). Un message déjà rédigé en français par
    l'application (``Http404("...")``, ``NotFound("...")``) n'est jamais écrasé."""
    if isinstance(exc, Http404):
        message = str(exc.args[0]) if exc.args else ""
        return not message or "matches the given query" in message or message == "Not found."
    if isinstance(exc, NotFound):
        return str(exc.detail) == str(NotFound.default_detail)
    return False


def vesta_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return response

    if _is_generic_not_found(exc):
        response.data = {"detail": GENERIC_NOT_FOUND_MESSAGE, "code": "not_found"}
    elif isinstance(exc, (InvalidToken, TokenError)):
        response.data = {"detail": INVALID_SESSION_MESSAGE, "code": "token_not_valid"}
    elif isinstance(exc, NotAuthenticated):
        response.data = {"detail": NOT_AUTHENTICATED_MESSAGE, "code": "not_authenticated"}
    elif isinstance(exc, AuthenticationFailed):
        code = getattr(exc.detail, "code", "authentication_failed")
        response.data = {"detail": AUTHENTICATION_FAILED_MESSAGE, "code": str(code)}
    return response
