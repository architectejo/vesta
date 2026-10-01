"""Test minimal de scaffolding (Lot 1, tache 1.0), mis a jour tache 1.2.

Ce test ne verifie aucune regle metier : il prouve seulement que Django
demarre avec la configuration de developpement et que la base de
donnees de test (SQLite) est accessible en lecture/ecriture via l'ORM,
ce qui valide que `pytest-django` est correctement configure.

Mise a jour tache 1.2 : le modele utilisateur par defaut de Django
(bases sur `username`) a ete remplace par le modele `accounts.User`
(email comme identifiant, CDC 4.1, `AUTH_USER_MODEL` positionne en
tache 1.2) -- ce test utilise donc desormais `email` au lieu de
`username`, sans quoi il echouerait pour une raison hors de son objet
(champ `username` inexistant), ce qui ne serait pas une "regression"
mais la consequence attendue et documentee du changement de modele
utilisateur (voir backend/README.md, section "Point ouvert pour la
tache 1.2").
"""

import django
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model


def test_django_est_correctement_configure():
    """Le projet Django demarre avec les apps attendues."""
    assert django.VERSION[:2] == (5, 2)
    assert "apps.core" in settings.INSTALLED_APPS
    assert "apps.accounts" in settings.INSTALLED_APPS
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert settings.AUTH_USER_MODEL == "accounts.User"


@pytest.mark.django_db
def test_base_de_donnees_de_test_accessible():
    """La base de donnees de test est accessible en lecture/ecriture.

    Utilise le modele utilisateur reel du projet (`accounts.User`,
    tache 1.2) pour prouver que les migrations s'appliquent et que
    l'ORM fonctionne.
    """
    User = get_user_model()
    assert User.objects.count() == 0

    User.objects.create_user(email="verification-scaffolding@example.com", password="x1234567")

    assert User.objects.count() == 1
