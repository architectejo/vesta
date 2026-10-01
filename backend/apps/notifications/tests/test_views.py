"""Tests HTTP de l'app notifications (CDC 3.4, 4.17 ; tache 1.7).

Verifie le cablage vue -> service -> reponse HTTP et, surtout,
l'isolation stricte par destinataire (consigne explicite de la tache
1.7 : « la lecture d'une notification par son destinataire ne fuite
jamais vers un autre utilisateur »).
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.licences.models import Licence
from apps.licences.tests.factories import LicenceFactory
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db


def _authenticated_client(user) -> APIClient:
    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


class TestNotificationListView:
    def test_liste_uniquement_les_notifications_du_destinataire(self):
        user = UserFactory()
        other_user = UserFactory()
        NotificationFactory.create_batch(3, recipient=user)
        NotificationFactory.create_batch(2, recipient=other_user)
        client = _authenticated_client(user)

        response = client.get(reverse("notifications:list"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 3

    def test_pagine_par_10_avec_voir_plus(self):
        user = UserFactory()
        NotificationFactory.create_batch(15, recipient=user)
        client = _authenticated_client(user)

        first_page = client.get(reverse("notifications:list"))

        assert first_page.status_code == status.HTTP_200_OK
        assert len(first_page.data["results"]) == 10
        assert first_page.data["next"] is not None

        second_page = client.get(first_page.data["next"])
        assert len(second_page.data["results"]) == 5

    def test_la_premiere_page_est_triee_de_la_plus_recente_a_la_plus_ancienne(self):
        """CDC 3.4/4.17 : « 10 dernieres notifications ». Verifie l'ordre
        reel, pas seulement le nombre d'elements retournes (tache 1.7t,
        point 7)."""

        # `Notification.created_at` est `auto_now_add=True` : Django ignore
        # toute valeur explicite passee a la creation (verifie ici a la
        # main). Seul un `timezone.now()` patche (meme convention que
        # ``apps.accounts.tests.test_services_auth``) pose un horodatage
        # deterministe pour chaque notification.
        user = UserFactory()
        base = timezone.now() - datetime.timedelta(days=1)
        titles_oldest_to_newest = [f"Notification {i}" for i in range(12)]
        for index, title in enumerate(titles_oldest_to_newest):
            with patch("django.utils.timezone.now", return_value=base + datetime.timedelta(minutes=index)):
                NotificationFactory(recipient=user, title=title)
        client = _authenticated_client(user)

        first_page = client.get(reverse("notifications:list"))

        returned_titles = [item["title"] for item in first_page.data["results"]]
        assert returned_titles == list(reversed(titles_oldest_to_newest))[:10]

    def test_le_compteur_de_non_lues_reste_correct_independamment_de_la_pagination(self):
        """Tache 1.7t, point 7 : ``unread_count`` porte sur TOUTES les
        notifications non lues du destinataire, pas seulement sur la page
        courante -- ici 12 non lues alors qu'une seule page en affiche 10."""

        user = UserFactory()
        NotificationFactory.create_batch(12, recipient=user, is_read=False)
        NotificationFactory.create_batch(3, recipient=user, is_read=True)
        client = _authenticated_client(user)

        list_response = client.get(reverse("notifications:list"))
        unread_response = client.get(reverse("notifications:unread-count"))

        assert len(list_response.data["results"]) == 10
        assert list_response.data["count"] == 15
        assert unread_response.data["unread_count"] == 12

    def test_la_liste_d_un_membre_n_inclut_jamais_une_notification_d_un_autre_membre_du_meme_club(self):
        """Tache 1.7t, point 2 : ``Notification`` n'est pas un
        ``TenantModel`` -- meme club, mais destinataires differents, ne
        doit jamais fuiter."""

        club = ClubFactory()
        member = MembershipFactory(club=club).user
        colleague = MembershipFactory(club=club).user
        NotificationFactory.create_batch(2, recipient=member, club=club)
        colleague_notification = NotificationFactory(recipient=colleague, club=club)
        client = _authenticated_client(member)

        response = client.get(reverse("notifications:list"))

        assert response.data["count"] == 2
        returned_ids = {item["id"] for item in response.data["results"]}
        assert colleague_notification.id not in returned_ids


class TestNotificationUnreadCountView:
    def test_compte_uniquement_les_non_lues_du_destinataire(self):
        user = UserFactory()
        NotificationFactory.create_batch(2, recipient=user, is_read=False)
        NotificationFactory(recipient=user, is_read=True)
        client = _authenticated_client(user)

        response = client.get(reverse("notifications:unread-count"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["unread_count"] == 2


class TestNotificationUnreadCountViewLicenceGate:
    """Non-regression HTTP (audit securite tache 1.13, ecart bloquant B1) :
    ``HasUsableLicence`` doit figurer dans ``_GATE``
    (apps/notifications/views.py), sinon un membre d'un club dont la
    licence est suspendue continuerait a acceder aux vues protegees par ce
    garde (CDC 1.4 ; 10.2 n19). Ce test verifie le CABLAGE HTTP reel de
    cette vue precise, pas ``HasUsableLicence`` elle-meme (deja testee en
    isolation dans apps/core/tests/test_permissions.py)."""

    def test_licence_suspendue_refuse_meme_la_lecture_du_compteur_de_non_lues(self):
        club = ClubFactory()
        membership = MembershipFactory(club=club, status=Membership.Status.ACTIVE)
        LicenceFactory(club=club, status=Licence.Status.SUSPENDED)
        NotificationFactory(recipient=membership.user, is_read=False)
        client = _authenticated_client(membership.user)

        response = client.get(reverse("notifications:unread-count"))

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestNotificationMarkReadView:
    def test_le_destinataire_marque_sa_notification_comme_lue(self):
        user = UserFactory()
        notification = NotificationFactory(recipient=user, is_read=False)
        client = _authenticated_client(user)

        response = client.post(
            reverse("notifications:mark-read", kwargs={"notification_id": notification.id})
        )

        assert response.status_code == status.HTTP_200_OK
        notification.refresh_from_db()
        assert notification.is_read is True

    def test_un_autre_utilisateur_ne_peut_pas_marquer_lue_une_notification_qui_ne_lui_appartient_pas(self):
        owner = UserFactory()
        someone_else = UserFactory()
        notification = NotificationFactory(recipient=owner, is_read=False)
        client = _authenticated_client(someone_else)

        response = client.post(
            reverse("notifications:mark-read", kwargs={"notification_id": notification.id})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        notification.refresh_from_db()
        assert notification.is_read is False


class TestNotificationMarkAllReadView:
    def test_tout_marquer_comme_lu_ne_touche_pas_les_notifications_d_un_autre_utilisateur(self):
        user = UserFactory()
        other_user = UserFactory()
        NotificationFactory.create_batch(2, recipient=user, is_read=False)
        other_notification = NotificationFactory(recipient=other_user, is_read=False)
        client = _authenticated_client(user)

        response = client.post(reverse("notifications:mark-all-read"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["updated"] == 2
        other_notification.refresh_from_db()
        assert other_notification.is_read is False


class TestNotificationPreferenceView:
    def test_lecture_de_la_preference_avec_defaut_active(self):
        user = UserFactory()
        client = _authenticated_client(user)

        response = client.get(reverse("notifications:preference"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email_enabled"] is True

    def test_modification_de_la_preference(self):
        user = UserFactory()
        client = _authenticated_client(user)

        response = client.patch(reverse("notifications:preference"), {"email_enabled": False})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email_enabled"] is False
        assert NotificationPreference.objects.get(user=user).email_enabled is False

    def test_la_preference_d_un_utilisateur_n_affecte_pas_celle_d_un_autre(self):
        user = UserFactory()
        other_user = UserFactory()
        client = _authenticated_client(user)

        client.patch(reverse("notifications:preference"), {"email_enabled": False})

        other_client = _authenticated_client(other_user)
        response = other_client.get(reverse("notifications:preference"))
        assert response.data["email_enabled"] is True
