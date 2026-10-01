"""Tests HTTP des endpoints « Comptes » de l'espace Superuser (CDC 2.5, 4.18 ; tache 1.8)."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import PasswordResetRequest
from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs.tests.factories import MembershipFactory
from django.utils import timezone


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


def _authenticate(api_client, user):
    access = str(RefreshToken.for_user(user).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")


@pytest.mark.django_db
class TestSuperuserAccountSearchView:
    def test_reserve_au_superuser(self, api_client):
        membership = MembershipFactory(status="active")
        _authenticate(api_client, membership.user)

        response = api_client.get(reverse("accounts:superuser-accounts-search"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_recherche_par_email(self, api_client):
        superuser = SuperuserFactory()
        cible = UserFactory(email="recherche-cible@example.com")
        _authenticate(api_client, superuser)

        response = api_client.get(
            reverse("accounts:superuser-accounts-search"), {"query": "recherche-cible"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert [r["id"] for r in response.data] == [cible.id]


@pytest.mark.django_db
class TestSuperuserAccountDeactivateView:
    def test_reserve_au_superuser(self, api_client):
        membership = MembershipFactory(status="active")
        cible = UserFactory()
        _authenticate(api_client, membership.user)

        response = api_client.post(
            reverse("accounts:superuser-accounts-deactivate"), {"user_id": cible.id}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_desactive_le_compte(self, api_client):
        superuser = SuperuserFactory()
        cible = UserFactory(is_active=True)
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("accounts:superuser-accounts-deactivate"),
            {"user_id": cible.id, "reason": "Depart du club."},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        cible.refresh_from_db()
        assert cible.is_active is False

    def test_compte_inexistant(self, api_client):
        superuser = SuperuserFactory()
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("accounts:superuser-accounts-deactivate"), {"user_id": 999999}, format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestSuperuserPendingPasswordResetsView:
    def test_reserve_au_superuser(self, api_client):
        membership = MembershipFactory(status="active")
        _authenticate(api_client, membership.user)

        response = api_client.get(reverse("accounts:superuser-password-resets-pending"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_liste_les_demandes_en_attente(self, api_client):
        superuser = SuperuserFactory()
        user = UserFactory()
        pending = PasswordResetRequest.objects.create(user=user, requested_at=timezone.now())
        _authenticate(api_client, superuser)

        response = api_client.get(reverse("accounts:superuser-password-resets-pending"))

        assert response.status_code == status.HTTP_200_OK
        assert [r["id"] for r in response.data] == [pending.pk]
