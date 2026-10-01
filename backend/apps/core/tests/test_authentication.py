"""Tests de `TenantJWTAuthentication` (tache 1.3).

CLAUDE.md regle n9 : le club actif se deduit de l'adhesion en cours,
jamais d'un `tenant_id` fige dans le jeton -- verifie ici en branchant
reellement l'authentification JWT sur une requete, comme le fera chaque
vue protegee des les taches suivantes.
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs.tests.factories import MembershipFactory
from apps.core.authentication import TenantJWTAuthentication
from apps.core.tenant import get_active_club, set_active_club


@pytest.fixture(autouse=True)
def _reset_active_club_after_each_test():
    yield
    set_active_club(None)


def _authenticated_request(user):
    access = RefreshToken.for_user(user).access_token
    request = RequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {access}")
    return request


@pytest.mark.django_db
class TestTenantJWTAuthentication:
    def test_positionne_le_club_actif_de_l_adhesion_en_cours(self):
        membership = MembershipFactory(status="active")
        request = _authenticated_request(membership.user)

        user, _token = TenantJWTAuthentication().authenticate(request)

        assert user.pk == membership.user_id
        assert get_active_club() == membership.club

    def test_ne_positionne_aucun_club_pour_un_superuser(self):
        superuser = SuperuserFactory()
        request = _authenticated_request(superuser)

        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() is None

    def test_aucun_club_actif_si_aucune_adhesion(self):
        user = UserFactory()
        request = _authenticated_request(user)

        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() is None

    def test_aucun_club_actif_si_adhesions_multiples_ambigues(self):
        """Point ouvert (tache 1.3) : voir docstring de `TenantJWTAuthentication`."""

        user = UserFactory()
        MembershipFactory(user=user, status="active")
        MembershipFactory(user=user, status="active")
        request = _authenticated_request(user)

        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() is None

    def test_aucun_jeton_ne_renvoie_aucun_resultat(self):
        request = RequestFactory().get("/")

        assert TenantJWTAuthentication().authenticate(request) is None
