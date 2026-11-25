"""Tests HTTP des nouveaux points d'acces de la tache 1.9 : assistant de
creation de club (public), « Mon profil » (lecture), « Identite du club »
et « Fiche du joueur » (`apps.clubs.views`).

Sources : docs/ecrans/clubs-creation.md ; comptes-mon-profil.md ;
club-comite-bureau.md §4.7 ; CDC 2.4, 3.5, 4.1, 4.2, 7.6 ; CLAUDE.md
regles 8 (etancheite multi-tenant) et 9 (club actif jamais fige).
"""

from __future__ import annotations

import io

import pytest
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import TermsVersion
from apps.accounts.tests.factories import TermsVersionFactory, UserFactory
from apps.clubs.models import Club, ClubSettings, Membership, MembershipRole
from apps.clubs.tests.factories import ClubFactory, ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.clubs.throttling import ClubCreationRateThrottle, ClubCreationSettingsRateThrottle
from apps.clubs.views import ClubCreationView, PublicClubCreationSettingsView

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


def _authenticated_client(user) -> APIClient:
    """Jeton d'acces reel (pas `force_authenticate`) : passe par
    `TenantJWTAuthentication` comme en production, club actif resolu
    depuis l'adhesion reelle (CLAUDE.md regle n9)."""

    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


def _active_club_with_settings(**kwargs) -> Club:
    club = ClubFactory(**kwargs)
    ClubSettingsFactory(club=club)
    return club


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# PublicClubCreationSettingsView
# ---------------------------------------------------------------------------


class TestPublicClubCreationSettingsView:
    def test_returns_expected_defaults_without_authentication(self):
        client = APIClient()

        response = client.get(reverse("clubs:public-creation-settings"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["trial_duration_days"] == 30
        assert response.data["grace_period_days"] == 15
        assert "Africa/Kinshasa" in response.data["timezones"]
        assert response.data["terms_version"] is None

    def test_returns_the_latest_published_terms_version(self):
        terms_version = TermsVersionFactory()
        client = APIClient()

        response = client.get(reverse("clubs:public-creation-settings"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["terms_version"]["id"] == terms_version.id

    def test_throttle_class_is_declared(self):
        assert PublicClubCreationSettingsView.throttle_classes == [ClubCreationSettingsRateThrottle]

    def test_repeated_calls_beyond_the_rate_limit_are_throttled(self):
        client = APIClient()
        url = reverse("clubs:public-creation-settings")

        for _ in range(60):
            response = client.get(url)
            assert response.status_code == status.HTTP_200_OK

        response = client.get(url)

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


# ---------------------------------------------------------------------------
# ClubCreationView
# ---------------------------------------------------------------------------


class TestClubCreationView:
    @staticmethod
    def _valid_payload(**overrides) -> dict:
        terms_version = overrides.pop("terms_version", None)
        if terms_version is None:
            terms_version = TermsVersion.objects.order_by("-published_at", "-id").first() or TermsVersionFactory()
        data = {
            "idempotency_key": "http-key-1",
            "name": "Club HTTP",
            "city": "Kinshasa",
            "country": "RD Congo",
            "currency": ClubSettings.Currency.USD,
            "timezone_name": "Africa/Kinshasa",
            "email": "http-fondateur@example.com",
            "first_name": "Jean",
            "last_name": "Fondateur",
            "position": Membership.Position.MIDFIELDER,
            "terms_version_id": terms_version.id,
            "accept_terms": True,
        }
        data.update(overrides)
        return data

    def test_creates_a_club_and_returns_tokens(self):
        client = APIClient()
        payload = self._valid_payload(idempotency_key="key-create-1", email="creation1@example.com")

        response = client.post(reverse("clubs:create"), payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["user"]["email"] == "creation1@example.com"
        assert response.data["must_change_password"] is True
        assert response.data["terms_acceptance_required"] is False
        assert Club.objects.filter(name="Club HTTP").exists()

    def test_same_idempotency_key_replays_without_creating_a_second_club(self):
        client = APIClient()
        payload = self._valid_payload(idempotency_key="key-create-2", email="creation2@example.com")

        first = client.post(reverse("clubs:create"), payload, format="json")
        second = client.post(reverse("clubs:create"), payload, format="json")

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_200_OK
        assert first.data["club"]["id"] == second.data["club"]["id"]
        assert Club.objects.filter(name="Club HTTP").count() == 1

    def test_stale_terms_version_returns_409_with_the_latest_version(self):
        old_version = TermsVersionFactory()
        new_version = TermsVersionFactory()
        client = APIClient()
        payload = self._valid_payload(
            idempotency_key="key-create-3", email="creation3@example.com", terms_version=old_version
        )

        response = client.post(reverse("clubs:create"), payload, format="json")

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["code"] == "terms_version_outdated"
        assert response.data["terms_version"]["id"] == new_version.id
        assert not Club.objects.filter(name="Club HTTP").exists()

    def test_email_already_used_returns_400_with_stable_error_code(self):
        UserFactory(email="deja-utilise-http@example.com")
        client = APIClient()
        payload = self._valid_payload(idempotency_key="key-create-4", email="deja-utilise-http@example.com")

        response = client.post(reverse("clubs:create"), payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "email_already_used"

    def test_throttle_class_is_declared(self):
        assert ClubCreationView.throttle_classes == [ClubCreationRateThrottle]

    def test_repeated_calls_beyond_the_rate_limit_are_throttled(self):
        client = APIClient()
        url = reverse("clubs:create")

        for i in range(10):
            payload = self._valid_payload(idempotency_key=f"key-throttle-{i}", email=f"throttle{i}@example.com")
            response = client.post(url, payload, format="json")
            assert response.status_code == status.HTTP_201_CREATED

        payload = self._valid_payload(idempotency_key="key-throttle-11", email="throttle11@example.com")
        response = client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


# ---------------------------------------------------------------------------
# MyProfileView
# ---------------------------------------------------------------------------


class TestMyProfileView:
    def test_returns_only_the_authenticated_users_own_data(self):
        club = _active_club_with_settings()
        alice = MembershipFactory(club=club)
        bob = MembershipFactory(club=club)

        alice_response = _authenticated_client(alice.user).get(reverse("clubs:profile-me"))
        bob_response = _authenticated_client(bob.user).get(reverse("clubs:profile-me"))

        assert alice_response.status_code == status.HTTP_200_OK
        assert bob_response.status_code == status.HTTP_200_OK
        assert alice_response.data["membership_id"] == alice.id
        assert alice_response.data["identity"]["email"] == alice.user.email
        assert bob_response.data["membership_id"] == bob.id
        assert bob_response.data["identity"]["email"] == bob.user.email
        # Aucun des deux ne recoit jamais les donnees de l'autre (2.4 « P »).
        assert alice_response.data["membership_id"] != bob_response.data["membership_id"]
        assert alice_response.data["identity"]["email"] != bob_response.data["identity"]["email"]

    def test_anonymous_user_is_rejected(self):
        response = APIClient().get(reverse("clubs:profile-me"))

        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_photo_and_club_logo_are_returned_as_absolute_urls(self):
        """Bug remarques.md : un chemin relatif (``MEDIA_URL``) pointe vers
        le mauvais serveur des que l'interface et l'API sont sur des
        origines differentes (sous-domaines distincts en production, proxy
        Vite qui ne couvre que ``/api`` en developpement)."""

        club = _active_club_with_settings(primary_color="#112233", secondary_color="#445566")
        club.logo.save("logo.png", ContentFile(_png_bytes()), save=True)
        member = MembershipFactory(club=club)
        member.user.photo.save("photo.png", ContentFile(_png_bytes()), save=True)

        response = _authenticated_client(member.user).get(reverse("clubs:profile-me"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["identity"]["photo"].startswith("http://testserver/media/")
        assert response.data["club"]["logo"].startswith("http://testserver/media/")
        # Bug remarques.md (theme Classic fige apres modification de
        # l'identite du club) : ces deux champs doivent toujours refleter
        # les couleurs actuelles du club, pas un snapshot pose au login.
        assert response.data["club"]["primary_color"] == "#112233"
        assert response.data["club"]["secondary_color"] == "#445566"


# ---------------------------------------------------------------------------
# ClubIdentityView
# ---------------------------------------------------------------------------


class TestClubIdentityView:
    def test_any_active_member_reads_without_the_payment_link_in_clear(self):
        club = _active_club_with_settings()
        club.settings.payment_link_url = "https://pay.example.com/club"
        club.settings.save()
        member = MembershipFactory(club=club)

        response = _authenticated_client(member.user).get(reverse("clubs:identity"))

        assert response.status_code == status.HTTP_200_OK
        assert "payment_link_url" not in response.data
        assert response.data["payment_link_configured"] is True

    def test_president_sees_the_payment_link_in_clear(self):
        club = _active_club_with_settings()
        club.settings.payment_link_url = "https://pay.example.com/club"
        club.settings.save()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, club=club, role=MembershipRole.Role.PRESIDENT)

        response = _authenticated_client(president.user).get(reverse("clubs:identity"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["payment_link_url"] == "https://pay.example.com/club"

    def test_logo_is_returned_as_an_absolute_url(self):
        """Bug remarques.md : voir
        ``TestMyProfileView.test_photo_and_club_logo_are_returned_as_absolute_urls``."""

        club = _active_club_with_settings()
        club.logo.save("logo.png", ContentFile(_png_bytes()), save=True)
        member = MembershipFactory(club=club)

        response = _authenticated_client(member.user).get(reverse("clubs:identity"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["logo"].startswith("http://testserver/media/")

    def test_non_president_cannot_patch(self):
        club = _active_club_with_settings()
        member = MembershipFactory(club=club)

        response = _authenticated_client(member.user).patch(
            reverse("clubs:identity"), {"city": "Lubumbashi"}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        club.refresh_from_db()
        assert club.city != "Lubumbashi"

    def test_president_can_patch(self):
        club = _active_club_with_settings()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, club=club, role=MembershipRole.Role.PRESIDENT)

        response = _authenticated_client(president.user).patch(
            reverse("clubs:identity"), {"city": "Lubumbashi"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        club.refresh_from_db()
        assert club.city == "Lubumbashi"

    def test_president_of_club_a_cannot_affect_club_bs_identity(self):
        """Etancheite multi-tenant : le club actif est toujours celui du
        President qui appelle (CLAUDE.md regle n9) -- jamais un autre club
        que le sien, quel que soit le corps de la requete."""

        club_a = _active_club_with_settings()
        club_b = _active_club_with_settings(name="Club B Identite", slug="club-b-identite")
        president_a = MembershipFactory(club=club_a)
        MembershipRoleFactory(membership=president_a, club=club_a, role=MembershipRole.Role.PRESIDENT)

        response = _authenticated_client(president_a.user).patch(
            reverse("clubs:identity"), {"city": "Ville Modifiee"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        club_b.refresh_from_db()
        assert club_b.city != "Ville Modifiee"


# ---------------------------------------------------------------------------
# PlayerCardView -- point le plus critique (etancheite multi-tenant)
# ---------------------------------------------------------------------------


class TestPlayerCardView:
    def test_member_can_view_a_teammates_card(self):
        club = _active_club_with_settings()
        viewer = MembershipFactory(club=club)
        teammate = MembershipFactory(club=club, jersey_number=10)

        response = _authenticated_client(viewer.user).get(reverse("clubs:player-card", args=[teammate.id]))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["membership_id"] == teammate.id
        assert response.data["jersey_number"] == 10

    def test_photo_is_returned_as_an_absolute_url(self):
        """Bug remarques.md : voir
        ``TestMyProfileView.test_photo_and_club_logo_are_returned_as_absolute_urls``."""

        club = _active_club_with_settings()
        viewer = MembershipFactory(club=club)
        teammate = MembershipFactory(club=club)
        teammate.user.photo.save("photo.png", ContentFile(_png_bytes()), save=True)

        response = _authenticated_client(viewer.user).get(reverse("clubs:player-card", args=[teammate.id]))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["photo"].startswith("http://testserver/media/")

    def test_cross_club_access_returns_404_never_403_and_leaks_no_data(self):
        """Etancheite multi-tenant (CLAUDE.md regle n8 ; club-comite-bureau.md
        §4.7) : un membre du club A qui demande la fiche d'un membre du club
        B recoit 404 (aucune fuite d'existence), jamais 403, et aucune
        donnee du membre vise ne doit apparaitre dans la reponse."""

        club_a = _active_club_with_settings()
        club_b = _active_club_with_settings(name="Club B Fiche", slug="club-b-fiche")
        member_a = MembershipFactory(club=club_a)
        member_b = MembershipFactory(club=club_b)

        response = _authenticated_client(member_a.user).get(reverse("clubs:player-card", args=[member_b.id]))

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data == {"detail": "Ce joueur n'existe pas dans ce club."}
        body_text = str(response.data)
        assert member_b.user.first_name not in body_text
        assert member_b.user.last_name not in body_text

    def test_nonexistent_membership_returns_the_same_404_as_a_cross_club_one(self):
        """Meme reponse pour "n'existe pas" et "existe dans un autre club" :
        sinon un attaquant pourrait distinguer les deux cas et enumerer les
        identifiants d'un club voisin (fuite d'existence, CDC 6.3)."""

        club = _active_club_with_settings()
        member = MembershipFactory(club=club)
        other_club = _active_club_with_settings(name="Club B Absent", slug="club-b-absent")
        other_member = MembershipFactory(club=other_club)

        response_missing = _authenticated_client(member.user).get(reverse("clubs:player-card", args=[999999]))
        response_other_club = _authenticated_client(member.user).get(
            reverse("clubs:player-card", args=[other_member.id])
        )

        assert response_missing.status_code == status.HTTP_404_NOT_FOUND
        assert response_other_club.status_code == status.HTTP_404_NOT_FOUND
        assert response_missing.data == response_other_club.data

    def test_response_never_contains_financial_or_medical_fields(self):
        """club-comite-bureau.md §4.7 : « Aucune donnee financiere ni
        medicale. » Verrou explicite contre toute regression future."""

        club = _active_club_with_settings()
        viewer = MembershipFactory(club=club)
        teammate = MembershipFactory(club=club)

        response = _authenticated_client(viewer.user).get(reverse("clubs:player-card", args=[teammate.id]))

        assert response.status_code == status.HTTP_200_OK
        expected_keys = {
            "membership_id",
            "first_name",
            "last_name",
            "photo",
            "position",
            "position_label",
            "position_detail",
            "jersey_number",
            "membership_status",
            "membership_status_label",
            "joined_on",
            "roles",
            # Booléen « bloqué » du pointage groupé, sans motif (10.2 n° 16).
            "is_unavailable",
        }
        assert set(response.data.keys()) == expected_keys

    def test_anonymous_user_is_rejected(self):
        club = _active_club_with_settings()
        teammate = MembershipFactory(club=club)

        response = APIClient().get(reverse("clubs:player-card", args=[teammate.id]))

        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
