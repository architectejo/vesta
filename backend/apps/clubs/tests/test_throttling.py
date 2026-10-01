"""Tests de la limitation de requetes de l'assistant de creation de club
(CDC 7.6 ; tache 1.9).

Meme convention et memes raisons que
`apps.accounts.tests.test_throttling` : `SimpleRateThrottle.THROTTLE_RATES`
est fige au chargement du module DRF, ces tests ajustent donc
`num_requests`/`duration` directement sur l'instance plutot que de passer
par la fixture `settings`. Complement de `test_views_club_creation.py`
(qui verifie la limite reelle configuree -- 60/min et 10/heure -- au
niveau HTTP) : ce module-ci prouve le mecanisme lui-meme, independamment
du reglage courant.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from rest_framework.request import Request

from apps.clubs.throttling import ClubCreationRateThrottle, ClubCreationSettingsRateThrottle

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


def _drf_request(ip: str = "203.0.113.10") -> Request:
    django_request = RequestFactory().get("/", REMOTE_ADDR=ip)
    return Request(django_request)


def _throttle_with_limit(throttle_class, max_requests: int):
    throttle = throttle_class()
    throttle.num_requests = max_requests
    throttle.duration = 60
    return throttle


class TestClubCreationSettingsRateThrottle:
    def test_autorise_jusqu_a_la_limite_puis_refuse(self):
        throttle = _throttle_with_limit(ClubCreationSettingsRateThrottle, max_requests=2)
        request = _drf_request()

        assert throttle.allow_request(request, view=None) is True
        assert throttle.allow_request(request, view=None) is True
        assert throttle.allow_request(request, view=None) is False

    def test_deux_adresses_ip_ne_se_genent_pas(self):
        assert (
            _throttle_with_limit(ClubCreationSettingsRateThrottle, max_requests=1).allow_request(
                _drf_request("203.0.113.10"), view=None
            )
            is True
        )
        assert (
            _throttle_with_limit(ClubCreationSettingsRateThrottle, max_requests=1).allow_request(
                _drf_request("203.0.113.11"), view=None
            )
            is True
        )


class TestClubCreationRateThrottle:
    def test_autorise_jusqu_a_la_limite_puis_refuse(self):
        throttle = _throttle_with_limit(ClubCreationRateThrottle, max_requests=2)
        request = _drf_request()

        assert throttle.allow_request(request, view=None) is True
        assert throttle.allow_request(request, view=None) is True
        assert throttle.allow_request(request, view=None) is False

    def test_limite_independante_du_throttle_de_lecture_des_parametres(self):
        """Deux scopes distincts (`club_creation_settings` vs
        `club_creation`) : la cle de cache differe, le compteur de l'un ne
        consomme jamais celui de l'autre."""

        request = _drf_request()

        assert (
            _throttle_with_limit(ClubCreationSettingsRateThrottle, max_requests=1).allow_request(request, view=None)
            is True
        )
        assert (
            _throttle_with_limit(ClubCreationRateThrottle, max_requests=1).allow_request(request, view=None) is True
        )
        assert (
            _throttle_with_limit(ClubCreationRateThrottle, max_requests=1).allow_request(request, view=None) is False
        )
