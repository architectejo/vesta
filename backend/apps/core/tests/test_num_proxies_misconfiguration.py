"""Divergence entre `_client_ip` et `REST_FRAMEWORK["NUM_PROXIES"]` (DRF)
quand `TRUSTED_PROXY_COUNT` est mal configure (CDC 7.6 ; audit de securite
du Lot 1, ecart bloquant B1).

Revue independante de test-engineer (pas ecrit par backend-dev) : les deux
mecanismes qui identifient "le vrai client" a partir de `X-Forwarded-For`
pretendent partager le meme reglage et la meme logique (voir le docstring
de `apps.core.middleware.RequestContextMiddleware._client_ip` : « meme
reglage et meme logique que `REST_FRAMEWORK["NUM_PROXIES"]` [...] pour que
la limitation de requetes et le journal d'activite s'accordent sur la meme
IP »). C'est vrai pour une valeur nulle ou positive de
`TRUSTED_PROXY_COUNT`, mais **faux pour une valeur negative** :

- `_client_ip` (`apps.core.middleware`) traite explicitement toute valeur
  ``<= 0`` comme "aucun proxy de confiance" -- voir
  ``apps.core.tests.test_middleware`` (y compris son cas negatif ajoute par
  cette revue). C'est un choix delibere du code applicatif.
- `SimpleRateThrottle.get_ident` (DRF, non modifie par le Lot 1 -- code
  tiers) ne verifie jamais que ``NUM_PROXIES >= 0``. Avec une valeur
  negative, ``addrs[-min(num_proxies, len(addrs))]`` devient
  ``addrs[-min(-1, len(addrs))]`` = ``addrs[1]`` (le DEUXIEME element de la
  liste, entierement choisi par le client dans son propre en-tete
  ``X-Forwarded-For`` -- aucun proxy ne l'a valide).

BUG REEL (a signaler a backend-dev, ne pas corriger ici) : si
``TRUSTED_PROXY_COUNT`` est un jour mis a une valeur negative en production
(erreur de saisie de la variable d'environnement, calcul errone en amont
cote `devops-cpanel`), l'identite utilisee par ``LoginRateThrottle``/
``PasswordResetRateThrottle`` (limitation par IP, CDC 7.6) redevient
entierement falsifiable par le client -- exactement la vulnerabilite que
l'ecart B1 visait a fermer. La limitation par email
(``LoginEmailRateThrottle``/``PasswordResetEmailRateThrottle``) reste, elle,
non affectee (elle ne depend jamais de l'IP), mais ce n'etait pas la seule
defense visee par B1.

Piste de correction pour backend-dev (a valider, pas decidee ici) : bornier
`TRUSTED_PROXY_COUNT`/`NUM_PROXIES` a `>= 0` au chargement des settings
(``max(0, env.int(...))``), ou lever explicitement `ImproperlyConfigured`
si une valeur negative est fournie -- pour que les deux mecanismes ne
puissent plus diverger sur ce point.
"""

from __future__ import annotations

from django.conf import settings
from django.test import RequestFactory, override_settings
from rest_framework.request import Request

from apps.accounts.throttling import LoginRateThrottle

_XFF_AVEC_VALEUR_CHOISIE_PAR_LE_CLIENT = "1.1.1.1, valeur-choisie-par-le-client, 9.9.9.9"


def _drf_request_with_xff(xff: str) -> Request:
    django_request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR=xff)
    return Request(django_request)


class TestDivergenceNumProxiesNegatif:
    def test_num_proxies_negatif_rend_l_identite_de_throttle_par_ip_falsifiable(self):
        """BUG REEL : ce test verifie le comportement SUR attendu (retomber sur
        `REMOTE_ADDR`, exactement comme `_client_ip` pour la meme valeur de
        configuration) -- il echoue avec le code actuel de DRF, ce qui est
        la preuve de la divergence documentee ci-dessus. Ne pas neutraliser
        ce test pour le faire passer : le signaler a backend-dev."""

        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": -1}):
            throttle = LoginRateThrottle()
            ident = throttle.get_ident(_drf_request_with_xff(_XFF_AVEC_VALEUR_CHOISIE_PAR_LE_CLIENT))

        assert ident == "10.0.0.5", (
            "BUG REEL (a signaler a backend-dev, cf. audit de securite du Lot 1, "
            f"ecart B1) : avec TRUSTED_PROXY_COUNT/NUM_PROXIES negatif, "
            f"`SimpleRateThrottle.get_ident` (DRF) renvoie {ident!r} -- un element "
            "choisi librement par le client dans son propre en-tete "
            "X-Forwarded-For -- au lieu de retomber sur REMOTE_ADDR comme le fait "
            "`RequestContextMiddleware._client_ip` pour la meme valeur de "
            "configuration. La limitation de requetes par IP "
            "(LoginRateThrottle/PasswordResetRateThrottle) redevient alors "
            "contournable a volonte par un attaquant qui fait varier cet en-tete, "
            "si TRUSTED_PROXY_COUNT est un jour mal configure a une valeur negative."
        )

    def test_num_proxies_tres_grand_ne_diverge_pas_de_client_ip_meme_limite_connue(self):
        """Contre-preuve : contrairement au cas negatif ci-dessus, une valeur
        excessive (positive) ne cree PAS de divergence entre les deux
        mecanismes -- les deux se rabattent sur le meme element ("le plus a
        gauche"), une limite connue et partagee, pas un bug."""

        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": 999_999}):
            throttle = LoginRateThrottle()
            ident = throttle.get_ident(_drf_request_with_xff(_XFF_AVEC_VALEUR_CHOISIE_PAR_LE_CLIENT))

        assert ident == "1.1.1.1"
