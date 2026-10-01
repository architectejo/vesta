"""Preuve de fermeture de l'ecart bloquant B2 (audit de securite du Lot 1).

``/admin/login/`` passe par ``django.contrib.auth.backends.ModelBackend``,
jamais par ``apps.accounts.services.authenticate_login`` : aucun blocage
apres echecs, aucune limitation de requetes, aucune entree de journal
(CDC 7.1, 7.6, 5). Pire : ``accounts.User`` n'a pas d'attribut
``is_staff`` -- un mot de passe **correct** y provoquait une erreur 500
(``AttributeError``), alors qu'un mot de passe faux y repondait
simplement 200, ce qui suffisait deja a deviner un mot de passe correct
sans meme se connecter.

Correction (``config/urls.py``) : ``/admin/`` n'est enregistre dans
``urlpatterns`` que si ``settings.DEBUG`` est vrai. ``DEBUG`` est deja
force a ``False`` en production (``config.settings.prod``) : ``/admin/``
n'existe donc plus du tout en production (404, aucune route).

``config.urls`` construit ``urlpatterns`` une seule fois, a l'import du
module -- ces tests rechargent explicitement le module apres avoir
change ``settings.DEBUG`` (``override_settings`` seul ne suffit pas :
il ne re-execute pas le corps du module deja importe) et videntt le
cache de resolution d'URL de Django, pour observer exactement le meme
mecanisme qu'au demarrage reel du processus.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from django.test import Client, override_settings
from django.urls import clear_url_caches


def _reload_root_urlconf() -> None:
    module = sys.modules.get("config.urls")
    if module is None:
        importlib.import_module("config.urls")
    else:
        importlib.reload(module)
    clear_url_caches()


@pytest.fixture
def _restore_urlconf():
    """Recharge `config.urls` avec les settings d'origine apres chaque test.

    Necessaire car `config.urls` est un module partage : sans ce
    nettoyage, un test qui le recharge avec `DEBUG=False` laisserait les
    tests suivants (dans le meme processus) sans route `/admin/`, meme
    une fois `settings.DEBUG` restaure.
    """

    yield
    _reload_root_urlconf()


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_admin_indisponible_quand_debug_est_faux(_restore_urlconf):
    _reload_root_urlconf()

    response = Client().get("/admin/", follow=False)

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_admin_reste_disponible_en_developpement_quand_debug_est_vrai(_restore_urlconf):
    _reload_root_urlconf()

    response = Client().get("/admin/", follow=False)

    # Redirection vers /admin/login/ (non authentifie) : la route existe
    # bel et bien, contrairement au cas `DEBUG=False` ci-dessus.
    assert response.status_code in (301, 302)
