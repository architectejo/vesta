"""Tests HTTP de l'espace Superuser « Licences » et « Support » (CDC 2.5,
4.18, 5.4 ; 10.2 n19/n20/n26 ; tache 1.8).
"""

from __future__ import annotations

import datetime

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.licences.models import Licence, LicenceEvent, SupportSession
from apps.licences.tests.factories import LicenceFactory, SupportSessionFactory


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
class TestLicenceEndpointsReservedToSuperuser:
    """Priorite « permissions » de la revue independante : chaque
    endpoint de l'espace Superuser doit refuser un membre de club, pas
    seulement l'ecran « Licences » liste (`test_liste_reservee_au_superuser`)."""

    def test_liste_reservee_au_superuser(self, api_client):
        membership = MembershipFactory(status="active")
        _authenticate(api_client, membership.user)

        response = api_client.get(reverse("licences:licence-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_detail_reservee_au_superuser(self, api_client):
        membership = MembershipFactory(status="active")
        licence = LicenceFactory()
        _authenticate(api_client, membership.user)

        response = api_client.get(reverse("licences:licence-detail", args=[licence.pk]))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_historique_reservee_au_superuser(self, api_client):
        membership = MembershipFactory(status="active")
        licence = LicenceFactory()
        _authenticate(api_client, membership.user)

        response = api_client.get(reverse("licences:licence-events", args=[licence.pk]))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize(
        "url_name,payload",
        [
            ("licences:licence-activate", {}),
            ("licences:licence-extend", {"end_date": "2099-01-01"}),
            ("licences:licence-suspend", {"reason": "Motif."}),
            ("licences:licence-resume", {}),
            ("licences:licence-terminate", {"reason": "Motif.", "confirm_club_name": "X"}),
        ],
    )
    def test_chaque_action_du_cycle_de_vie_est_reservee_au_superuser(self, api_client, url_name, payload):
        membership = MembershipFactory(status="active")
        licence = LicenceFactory(status=Licence.Status.SUSPENDED if url_name.endswith("resume") else Licence.Status.ACTIVE)
        _authenticate(api_client, membership.user)

        response = api_client.post(reverse(url_name, args=[licence.pk]), payload, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestLicenceLifecycleEndpoints:
    def test_liste_le_tableau_des_licences_avec_dates_et_statut(self, api_client):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.TRIAL)
        _authenticate(api_client, superuser)

        response = api_client.get(reverse("licences:licence-list"))

        assert response.status_code == status.HTTP_200_OK
        payload = next(item for item in response.data if item["id"] == licence.pk)
        assert payload["status"] == Licence.Status.TRIAL
        assert payload["start_date"] == licence.start_date.isoformat()
        assert payload["end_date"] == licence.end_date.isoformat()
        assert "plan" not in payload

    def test_active_une_licence_avec_seulement_deux_dates(self, api_client):
        """Critere de fin de la tache 1.8 : « une licence sans formule
        s'attribue avec seulement deux dates »."""

        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.TRIAL)
        _authenticate(api_client, superuser)

        nouveau_debut = datetime.date.today().isoformat()
        nouvelle_fin = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()

        response = api_client.post(
            reverse("licences:licence-activate", args=[licence.pk]),
            {"start_date": nouveau_debut, "end_date": nouvelle_fin},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Licence.Status.ACTIVE
        assert response.data["start_date"] == nouveau_debut
        assert response.data["end_date"] == nouvelle_fin

    def test_prolonge_une_licence(self, api_client):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.ACTIVE)
        nouvelle_fin = (licence.end_date + datetime.timedelta(days=30)).isoformat()
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("licences:licence-extend", args=[licence.pk]), {"end_date": nouvelle_fin}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["end_date"] == nouvelle_fin

    def test_suspend_une_licence_avec_motif(self, api_client):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.ACTIVE)
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("licences:licence-suspend", args=[licence.pk]),
            {"reason": "Impaye signale."},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Licence.Status.SUSPENDED

    def test_suspend_refuse_sans_motif(self, api_client):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.ACTIVE)
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("licences:licence-suspend", args=[licence.pk]), {"reason": ""}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reprend_une_licence_suspendue(self, api_client):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.SUSPENDED)
        _authenticate(api_client, superuser)

        response = api_client.post(reverse("licences:licence-resume", args=[licence.pk]), {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Licence.Status.ACTIVE

    def test_resilie_avec_confirmation_du_nom_du_club(self, api_client):
        superuser = SuperuserFactory()
        club = ClubFactory(name="Loisirs Club Discovery Test")
        licence = LicenceFactory(club=club, status=Licence.Status.ACTIVE)
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("licences:licence-terminate", args=[licence.pk]),
            {"reason": "Demande ecrite.", "confirm_club_name": "Loisirs Club Discovery Test"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Licence.Status.TERMINATED

    def test_resiliation_refusee_si_le_nom_ne_correspond_pas(self, api_client):
        """10.2 n26."""

        superuser = SuperuserFactory()
        club = ClubFactory(name="Loisirs Club Discovery Test")
        licence = LicenceFactory(club=club, status=Licence.Status.ACTIVE)
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("licences:licence-terminate", args=[licence.pk]),
            {"reason": "Demande ecrite.", "confirm_club_name": "Mauvais nom"},
            format="json",
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        licence.refresh_from_db()
        assert licence.status == Licence.Status.ACTIVE

    def test_historique_d_une_licence(self, api_client):
        superuser = SuperuserFactory()
        licence = LicenceFactory(status=Licence.Status.TRIAL)
        _authenticate(api_client, superuser)

        api_client.post(reverse("licences:licence-activate", args=[licence.pk]), {}, format="json")

        response = api_client.get(reverse("licences:licence-events", args=[licence.pk]))

        assert response.status_code == status.HTTP_200_OK
        assert any(event["event_type"] == LicenceEvent.EventType.ACTIVATED for event in response.data)


@pytest.mark.django_db
class TestSupportSessionEndpoints:
    def test_ouvre_une_session_de_support(self, api_client):
        superuser = SuperuserFactory()
        club = ClubFactory()
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("licences:support-session-start"),
            {"club_id": club.pk, "reason": "Correction d'un paiement."},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["club_id"] == club.pk
        assert response.data["is_valid"] is True

    def test_refuse_un_motif_vide(self, api_client):
        superuser = SuperuserFactory()
        club = ClubFactory()
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("licences:support-session-start"), {"club_id": club.pk, "reason": ""}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_termine_une_session_par_anticipation(self, api_client):
        superuser = SuperuserFactory()
        session = SupportSessionFactory(superuser=superuser)
        _authenticate(api_client, superuser)

        response = api_client.post(
            reverse("licences:support-session-end", args=[session.pk]), {}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_valid"] is False

    def test_fin_anticipee_refusee_a_un_autre_superuser(self, api_client):
        proprietaire = SuperuserFactory()
        autre = SuperuserFactory()
        session = SupportSessionFactory(superuser=proprietaire)
        _authenticate(api_client, autre)

        response = api_client.post(
            reverse("licences:support-session-end", args=[session.pk]), {}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_liste_les_sessions_filtrables_par_club(self, api_client):
        superuser = SuperuserFactory()
        club_a = ClubFactory()
        club_b = ClubFactory()
        session_a = SupportSessionFactory(superuser=superuser, club=club_a)
        SupportSessionFactory(superuser=superuser, club=club_b)
        _authenticate(api_client, superuser)

        response = api_client.get(reverse("licences:support-session-list"), {"club_id": club_a.pk})

        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.data] == [session_a.pk]

    def test_reserve_au_superuser(self, api_client):
        membership = MembershipFactory(status="active")
        _authenticate(api_client, membership.user)

        response = api_client.post(
            reverse("licences:support-session-start"),
            {"club_id": membership.club_id, "reason": "Motif."},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_liste_des_sessions_reservee_au_superuser(self, api_client):
        membership = MembershipFactory(status="active")
        _authenticate(api_client, membership.user)

        response = api_client.get(reverse("licences:support-session-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_fin_anticipee_reservee_au_superuser(self, api_client):
        """Un membre de club (non-Superuser) ne peut pas cloturer une
        session de support, meme celle ouverte sur SON PROPRE club."""

        superuser = SuperuserFactory()
        session = SupportSessionFactory(superuser=superuser)
        membership = MembershipFactory(status="active")
        _authenticate(api_client, membership.user)

        response = api_client.post(
            reverse("licences:support-session-end", args=[session.pk]), {}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
