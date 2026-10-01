"""Tests de la limitation de requetes sur les points sensibles (CDC 7.6).

Utilise directement les classes de throttle (plutot que l'API HTTP
complete) pour rester rapide. `SimpleRateThrottle.THROTTLE_RATES` est
fige au chargement du module DRF (copie de `DEFAULT_THROTTLE_RATES` a
l'import, non reactive a une surcharge ulterieure de
``settings.REST_FRAMEWORK``) : ces tests ajustent donc directement
``num_requests``/``duration`` sur l'instance plutot que de passer par la
fixture ``settings``.

``pytestmark`` : tous les tests de ce module touchent la base de donnees
(``cache.clear()``/``allow_request()`` passent par
``settings.CACHES["default"]`` -- ``DatabaseCache``, audit de securite du
Lot 1, ecart bloquant B1 : necessaire pour que la limitation soit
partagee entre tous les processus Passenger, pas seulement en memoire
d'un seul processus).
"""

from __future__ import annotations

import json

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from rest_framework.parsers import JSONParser
from rest_framework.request import Request

from apps.accounts.throttling import (
    LoginEmailRateThrottle,
    LoginRateThrottle,
    PasswordResetEmailRateThrottle,
    PasswordResetRateThrottle,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


def _drf_request(ip: str = "203.0.113.1", data: dict | None = None):
    if data is None:
        django_request = RequestFactory().post("/", REMOTE_ADDR=ip)
        return Request(django_request)

    # JSON explicite (comme le fera reellement le frontend, `format="json"`
    # partout ailleurs dans les tests d'API) : un parseur doit etre fourni
    # explicitement, la classe `Request` brute de DRF n'en configure aucun
    # par defaut (contrairement a une vue, qui recoit
    # `DEFAULT_PARSER_CLASSES`).
    django_request = RequestFactory().post(
        "/", data=json.dumps(data), content_type="application/json", REMOTE_ADDR=ip
    )
    return Request(django_request, parsers=[JSONParser()])


def _throttle_with_limit(throttle_class, max_requests: int):
    throttle = throttle_class()
    throttle.num_requests = max_requests
    throttle.duration = 60
    return throttle


class TestLoginRateThrottle:
    def test_autorise_jusqu_a_la_limite_puis_refuse(self):
        throttle = _throttle_with_limit(LoginRateThrottle, max_requests=2)
        request = _drf_request()

        assert throttle.allow_request(request, view=None) is True
        assert throttle.allow_request(request, view=None) is True
        assert throttle.allow_request(request, view=None) is False

    def test_deux_adresses_ip_ne_se_genent_pas(self):
        assert (
            _throttle_with_limit(LoginRateThrottle, max_requests=1).allow_request(
                _drf_request("203.0.113.1"), view=None
            )
            is True
        )
        assert (
            _throttle_with_limit(LoginRateThrottle, max_requests=1).allow_request(
                _drf_request("203.0.113.2"), view=None
            )
            is True
        )


class TestPasswordResetRateThrottle:
    def test_limite_independante_du_throttle_de_connexion(self):
        request = _drf_request()

        assert _throttle_with_limit(LoginRateThrottle, max_requests=1).allow_request(request, view=None) is True
        # Meme IP, mais un scope (donc une cle de cache) different : le
        # compteur de connexion ne consomme pas celui de reinitialisation.
        assert (
            _throttle_with_limit(PasswordResetRateThrottle, max_requests=1).allow_request(request, view=None)
            is True
        )
        assert (
            _throttle_with_limit(PasswordResetRateThrottle, max_requests=1).allow_request(request, view=None)
            is False
        )


class TestLoginEmailRateThrottle:
    """Preuve de fermeture de l'ecart bloquant B1 (audit de securite du Lot 1) :
    la limitation par IP seule est contournable par un attaquant qui change
    d'adresse IP (``X-Forwarded-For`` falsifie ou reseau distribue) a chaque
    requete. La limitation par email vise reste efficace dans ce cas."""

    def test_ip_qui_change_a_chaque_requete_ne_contourne_pas_la_limite_par_email(self):
        throttle = _throttle_with_limit(LoginEmailRateThrottle, max_requests=2)
        cible = "victime@example.com"

        # Chaque requete utilise une adresse IP differente (comme un
        # attaquant qui falsifie `X-Forwarded-For` a chaque tentative) :
        # une limitation par IP seule ne se declencherait jamais ici.
        assert throttle.allow_request(_drf_request("203.0.113.1", {"email": cible}), view=None) is True
        assert throttle.allow_request(_drf_request("203.0.113.2", {"email": cible}), view=None) is True
        assert throttle.allow_request(_drf_request("203.0.113.3", {"email": cible}), view=None) is False

    def test_deux_emails_vises_ne_se_genent_pas(self):
        assert (
            _throttle_with_limit(LoginEmailRateThrottle, max_requests=1).allow_request(
                _drf_request("203.0.113.1", {"email": "premier@example.com"}), view=None
            )
            is True
        )
        assert (
            _throttle_with_limit(LoginEmailRateThrottle, max_requests=1).allow_request(
                _drf_request("203.0.113.1", {"email": "second@example.com"}), view=None
            )
            is True
        )

    def test_email_normalise_comme_dans_les_services(self):
        """Meme normalisation que `apps.accounts.services` (`strip().lower()`) :
        `Victime@Example.com` et `victime@example.com  ` consomment le meme
        compteur -- sinon la casse/les espaces suffiraient a contourner la
        limite."""

        throttle = _throttle_with_limit(LoginEmailRateThrottle, max_requests=1)

        assert throttle.allow_request(_drf_request("203.0.113.1", {"email": "Victime@Example.com"}), view=None) is True
        assert (
            throttle.allow_request(_drf_request("203.0.113.2", {"email": "  victime@example.com  "}), view=None)
            is False
        )

    def test_requete_sans_email_exploitable_n_est_pas_limitee_par_cette_classe(self):
        """Une requete malformee (pas d'email) n'est pas de la responsabilite
        de cette classe : la limitation par IP (`LoginRateThrottle`) et la
        validation du serializer restent la defense pertinente dans ce cas."""

        throttle = _throttle_with_limit(LoginEmailRateThrottle, max_requests=1)

        for _ in range(5):
            assert throttle.allow_request(_drf_request("203.0.113.1", {}), view=None) is True


class TestPasswordResetEmailRateThrottle:
    def test_limite_independante_du_throttle_de_connexion_par_email(self):
        cible = "victime@example.com"

        assert (
            _throttle_with_limit(LoginEmailRateThrottle, max_requests=1).allow_request(
                _drf_request(data={"email": cible}), view=None
            )
            is True
        )
        assert (
            _throttle_with_limit(PasswordResetEmailRateThrottle, max_requests=1).allow_request(
                _drf_request(data={"email": cible}), view=None
            )
            is True
        )
        assert (
            _throttle_with_limit(PasswordResetEmailRateThrottle, max_requests=1).allow_request(
                _drf_request(data={"email": cible}), view=None
            )
            is False
        )
