"""Limitation du nombre de requetes sur les points sensibles de l'authentification.

CDC 7.6 : « Limitation du nombre de requetes sur la connexion et les
points sensibles. » Deux defenses independantes et complementaires,
actives simultanement sur ``LoginView``/``PasswordResetRequestView``
(audit de securite du Lot 1, ecart bloquant B1) :

- Cle par adresse IP (``AnonRateThrottle``) -- ces points sont
  accessibles sans jeton (``AllowAny``). A elle seule, cette defense est
  contournable par un attaquant qui change d'adresse IP a chaque requete
  (``X-Forwarded-For`` falsifie, ou un reseau de machines) : elle reste
  utile contre un attaquant qui reste sur une seule IP, mais ne suffit
  pas contre un attaquant distribue qui vise un compte precis.
- Cle par **email vise** (``BaseEmailKeyedThrottle``) -- lit
  ``request.data.get("email")``, normalise exactement comme
  ``apps.accounts.services`` (``strip().lower()``) : quelle que soit
  l'adresse IP utilisee par l'attaquant, le nombre de tentatives contre
  un email donne reste borne. C'est une defense complementaire au
  blocage par compte apres 5 echecs (``apps.accounts.services``), pas un
  remplacement (CDC 7.1) : le blocage de compte protege contre un
  attaquant qui connait deja l'email et essaie des mots de passe : cette
  limitation protege le service lui-meme contre un volume de requetes
  anormal, y compris avant meme que le compte n'existe.

Aucune des deux classes ne depend de l'authentification JWT : les vues
qui les utilisent posent explicitement ``authentication_classes = []``
(``apps.accounts.views``) pour qu'un jeton ``Bearer`` presente par
l'attaquant ne rende jamais la requete "authentifiee" aux yeux de DRF
(ce qui desactiverait silencieusement ``AnonRateThrottle`` -- ecart B1
de l'audit de securite du Lot 1).
"""

from __future__ import annotations

from rest_framework.settings import api_settings
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class HardenedIdentThrottle:
    """Reimplemente ``BaseThrottle.get_ident`` (DRF) en bornant ``NUM_PROXIES``
    a ``>= 0`` avant de l'utiliser -- defense en profondeur pour la
    limitation par IP (``LoginRateThrottle``/``PasswordResetRateThrottle``,
    CDC 7.6), a placer AVANT la classe de throttle DRF dans l'ordre des
    classes de base pour que cette version l'emporte (ordre de resolution
    des methodes).

    Revue independante de test-engineer, ecart residuel de l'audit de
    securite du Lot 1 (ecart B1) -- voir
    ``apps.core.tests.test_num_proxies_misconfiguration``.
    ``config.settings.base`` borne deja ``TRUSTED_PROXY_COUNT``
    (donc ``REST_FRAMEWORK["NUM_PROXIES"]``) a ``>= 0`` au chargement des
    settings, ce qui ferme la seule source reelle d'une valeur negative en
    exploitation (variable d'environnement mal renseignee). Mais
    ``BaseThrottle.get_ident`` (DRF, code tiers non modifie ici) ne se
    protege lui-meme jamais contre une valeur negative : avec
    ``NUM_PROXIES=-1``, son expression interne
    ``addrs[-min(num_proxies, len(addrs))]`` devient ``addrs[1]`` -- le
    DEUXIEME element de ``X-Forwarded-For``, choisi librement par le
    client, jamais une IP de proxy valide. Ce mixin protege donc aussi
    contre toute autre facon dont ``NUM_PROXIES`` pourrait un jour se
    retrouver negatif (settings recomposes ailleurs que via
    ``TRUSTED_PROXY_COUNT``) : la limitation de requetes par IP ne doit
    jamais dependre uniquement d'une hypothese verifiee ailleurs dans le
    code.
    """

    def get_ident(self, request):
        xff = request.headers.get("x-forwarded-for")
        remote_addr = request.META.get("REMOTE_ADDR")
        num_proxies = api_settings.NUM_PROXIES

        if num_proxies is not None:
            # Seule ligne qui differe de ``BaseThrottle.get_ident`` (DRF) :
            # une valeur negative est traitee comme "aucun proxy de
            # confiance" (0), jamais comme une invite a lire un element
            # plus loin dans `X-Forwarded-For` -- meme choix que
            # `apps.core.middleware.RequestContextMiddleware._client_ip`
            # pour la meme valeur de configuration.
            num_proxies = max(0, num_proxies)
            if num_proxies == 0 or xff is None:
                return remote_addr
            addrs = xff.split(",")
            client_addr = addrs[-min(num_proxies, len(addrs))]
            return client_addr.strip()

        return "".join(xff.split()) if xff else remote_addr


class LoginRateThrottle(HardenedIdentThrottle, AnonRateThrottle):
    scope = "login"


class PasswordResetRateThrottle(HardenedIdentThrottle, AnonRateThrottle):
    scope = "password_reset"


class BaseEmailKeyedThrottle(SimpleRateThrottle):
    """Limite par email soumis dans le corps de la requete, pas par IP.

    Ne s'appuie jamais sur ``request.user`` (ces vues sont volontairement
    non authentifiees, voir le docstring du module) : la cle du cache est
    directement derivee du champ ``email`` du corps de la requete, avant
    meme toute validation de serializer -- une requete sans email
    exploitable (absent, mal forme) n'est simplement pas limitee par
    cette classe (la validation du serializer la rejettera de toute
    facon ; la limitation par IP reste active dans tous les cas).
    """

    def get_cache_key(self, request, view) -> str | None:
        data = getattr(request, "data", None)
        try:
            raw_email = data.get("email") if isinstance(data, dict) else None
        except (AttributeError, TypeError):  # pragma: no cover - defense en profondeur
            raw_email = None

        email = (raw_email or "").strip().lower()
        if not email:
            return None

        return self.cache_format % {"scope": self.scope, "ident": email}


class LoginEmailRateThrottle(BaseEmailKeyedThrottle):
    scope = "login_email"


class PasswordResetEmailRateThrottle(BaseEmailKeyedThrottle):
    scope = "password_reset_email"
