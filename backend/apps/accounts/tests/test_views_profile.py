"""Tests HTTP des mutations d'identite de « Mon profil » (tache 1.9,
slice Lot 1) : `MyPersonalInfoUpdateView`, `MyCredentialsUpdateView`,
`MyPinUpdateView`, `MyProfilePhotoView`.

Sources : docs/ecrans/comptes-mon-profil.md §4.1 ; CDC 4.1, 4.2, 7.1, 7.2 ;
CLAUDE.md regle n8 (etancheite -- ici : jamais un autre COMPTE que le
sien, meme injecte dans le corps de la requete).

La lecture agregee du profil (`apps.clubs.views.MyProfileView`) est
couverte par `apps.clubs.tests.test_views_club_creation`.
"""

from __future__ import annotations

import base64
import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import TermsVersionFactory, UserFactory

pytestmark = pytest.mark.django_db

# PNG 1x1 valide (Pillow doit pouvoir l'ouvrir : `ImageField` de DRF le verifie).
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _authenticated_client(user) -> APIClient:
    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


def _tiny_png(name: str = "photo.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, _TINY_PNG, content_type="image/png")


class TestMyPersonalInfoUpdateView:
    def test_updates_only_the_authenticated_user(self):
        user = UserFactory(first_name="Ancien", last_name="Nom", phone="")
        other = UserFactory(first_name="Autre", last_name="Personne")
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-personal-info"),
            {"first_name": "Nouveau", "last_name": "Nom", "phone": "+243900000000"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        other.refresh_from_db()
        assert user.first_name == "Nouveau"
        assert user.phone == "+243900000000"
        assert other.first_name == "Autre"  # jamais touche

    def test_requires_authentication(self):
        response = APIClient().patch(
            reverse("accounts:profile-personal-info"),
            {"first_name": "X", "last_name": "Y"},
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_a_smuggled_user_id_in_the_payload_never_targets_another_account(self):
        """Le serializer ne declare aucun champ d'identifiant : meme si un
        client malveillant glisse un `user_id`/`id` dans le corps, seul
        `request.user` peut jamais etre modifie (CLAUDE.md regle n8)."""

        user = UserFactory(first_name="Moi")
        other = UserFactory(first_name="Victime")
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-personal-info"),
            {"user_id": other.id, "id": other.id, "first_name": "ToujoursMoi", "last_name": "X"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        other.refresh_from_db()
        assert user.first_name == "ToujoursMoi"
        assert other.first_name == "Victime"

    def test_rejects_a_future_birth_date(self):
        user = UserFactory()
        client = _authenticated_client(user)
        future_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

        response = client.patch(
            reverse("accounts:profile-personal-info"),
            {"first_name": "A", "last_name": "B", "birth_date": future_date},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_blocked_while_forced_password_change_is_pending(self):
        """CDC 4.1 : « Tant qu'il ne l'a pas change, il n'accede a aucune
        donnee. » Meme garde-fou que partout ailleurs dans le projet
        (`apps.clubs.views._CLUB_MEMBER_GATE`, qui compose explicitement
        `HasCompletedPasswordSetup`) : absent des `permission_classes` de
        cette vue (`[IsAuthenticated]` seulement) -- voir le compte rendu
        de la tache pour le signalement de cet ecart."""

        user = UserFactory(must_change_password=True)
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-personal-info"),
            {"first_name": "A", "last_name": "B"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestMyCredentialsUpdateView:
    def test_updates_email_and_password_of_the_authenticated_user_only(self):
        user = UserFactory(email="ancien@example.com", password="MotDePasse123")
        other = UserFactory(email="intact@example.com")
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-credentials"),
            {
                "email": "nouveau@example.com",
                "current_password": "MotDePasse123",
                "new_password": "UnAutreMotDePasse456",
                "confirm_new_password": "UnAutreMotDePasse456",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        other.refresh_from_db()
        assert user.email == "nouveau@example.com"
        assert user.check_password("UnAutreMotDePasse456")
        assert other.email == "intact@example.com"

    def test_wrong_current_password_returns_400(self):
        user = UserFactory(email="a@example.com", password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-credentials"),
            {"email": "a@example.com", "current_password": "FauxMotDePasse"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.email == "a@example.com"

    def test_email_already_used_by_another_account_returns_400(self):
        UserFactory(email="deja-pris@example.com")
        user = UserFactory(email="moi@example.com", password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-credentials"),
            {"email": "deja-pris@example.com", "current_password": "MotDePasse123"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.email == "moi@example.com"

    def test_mismatched_new_passwords_return_400(self):
        user = UserFactory(email="a@example.com", password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-credentials"),
            {
                "email": "a@example.com",
                "current_password": "MotDePasse123",
                "new_password": "PremierMotDePasse1",
                "confirm_new_password": "SecondMotDePasse2",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_smuggled_user_id_never_targets_another_accounts_credentials(self):
        user = UserFactory(email="moi@example.com", password="MotDePasse123")
        other = UserFactory(email="victime@example.com")
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-credentials"),
            {"user_id": other.id, "email": "moi-modifie@example.com", "current_password": "MotDePasse123"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        other.refresh_from_db()
        assert user.email == "moi-modifie@example.com"
        assert other.email == "victime@example.com"

    def test_blocked_while_forced_password_change_is_pending(self):
        """Meme ecart que `MyPersonalInfoUpdateView` -- voir sa docstring.
        Consequence aggravante ici : `update_credentials` ne remet jamais
        `must_change_password` a False, donc un joueur qui passerait par ce
        point d'acces pendant l'etat force resterait bloque au prochain
        login malgre un mot de passe reel deja pose (etat sans issue)."""

        user = UserFactory(email="a@example.com", password="a@example.com", must_change_password=True)
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-credentials"),
            {
                "email": "a@example.com",
                "current_password": "a@example.com",
                "new_password": "NouveauMotDePasse1",
                "confirm_new_password": "NouveauMotDePasse1",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_blocked_while_latest_terms_are_not_yet_accepted(self):
        """Meme principe pour `HasAcceptedLatestTerms` (CDC 7.5) : absent des
        `permission_classes` de cette vue."""

        TermsVersionFactory()
        user = UserFactory(email="b@example.com", password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-credentials"),
            {"email": "b@example.com", "current_password": "MotDePasse123"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestMyPinUpdateView:
    def test_defines_the_pin_of_the_authenticated_user_only(self):
        user = UserFactory(password="MotDePasse123")
        other = UserFactory(password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.post(
            reverse("accounts:profile-pin"),
            {"current_password": "MotDePasse123", "new_pin": "1234", "confirm_new_pin": "1234"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        other.refresh_from_db()
        assert user.pin_hash != ""
        assert other.pin_hash == ""

    def test_wrong_password_returns_400(self):
        user = UserFactory(password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.post(
            reverse("accounts:profile-pin"),
            {"current_password": "FauxMotDePasse", "new_pin": "1234", "confirm_new_pin": "1234"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.pin_hash == ""

    def test_mismatched_confirmation_returns_400(self):
        user = UserFactory(password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.post(
            reverse("accounts:profile-pin"),
            {"current_password": "MotDePasse123", "new_pin": "1234", "confirm_new_pin": "5678"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_pin_format_returns_400(self):
        user = UserFactory(password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.post(
            reverse("accounts:profile-pin"),
            {"current_password": "MotDePasse123", "new_pin": "12", "confirm_new_pin": "12"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_smuggled_user_id_never_targets_another_users_pin(self):
        user = UserFactory(password="MotDePasse123")
        other = UserFactory(password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.post(
            reverse("accounts:profile-pin"),
            {"user_id": other.id, "current_password": "MotDePasse123", "new_pin": "4321", "confirm_new_pin": "4321"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        other.refresh_from_db()
        assert other.pin_hash == ""

    def test_blocked_while_forced_password_change_is_pending(self):
        """Meme garde-fou global que les trois autres mutations du profil
        (`_CLUB_MEMBER_GATE` compose `HasCompletedPasswordSetup`) : absent
        des `permission_classes` de cette vue -- comble le trou de
        couverture signale au compte rendu du correctif de securite
        (`MyPinUpdateView` n'avait pas son equivalent de
        `TestMyCredentialsUpdateView.test_blocked_while_forced_password_change_is_pending`)."""

        user = UserFactory(password="MotDePasse123", must_change_password=True)
        client = _authenticated_client(user)

        response = client.post(
            reverse("accounts:profile-pin"),
            {"current_password": "MotDePasse123", "new_pin": "1234", "confirm_new_pin": "1234"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        user.refresh_from_db()
        assert user.pin_hash == ""

    def test_blocked_while_latest_terms_are_not_yet_accepted(self):
        """Meme principe pour `HasAcceptedLatestTerms` (CDC 7.5) : absent des
        `permission_classes` de cette vue."""

        TermsVersionFactory()
        user = UserFactory(password="MotDePasse123")
        client = _authenticated_client(user)

        response = client.post(
            reverse("accounts:profile-pin"),
            {"current_password": "MotDePasse123", "new_pin": "1234", "confirm_new_pin": "1234"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        user.refresh_from_db()
        assert user.pin_hash == ""


class TestMyProfilePhotoView:
    def test_updates_the_photo_of_the_authenticated_user_only(self):
        user = UserFactory()
        other = UserFactory()
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-photo"), {"photo": _tiny_png()}, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        other.refresh_from_db()
        assert bool(user.photo)
        assert not other.photo

    def test_delete_removes_the_photo_of_the_authenticated_user_only(self):
        user = UserFactory()
        client = _authenticated_client(user)
        client.patch(reverse("accounts:profile-photo"), {"photo": _tiny_png()}, format="multipart")
        user.refresh_from_db()
        assert bool(user.photo)

        response = client.delete(reverse("accounts:profile-photo"))

        assert response.status_code == status.HTTP_204_NO_CONTENT
        user.refresh_from_db()
        assert not user.photo

    def test_requires_authentication(self):
        response = APIClient().patch(
            reverse("accounts:profile-photo"), {"photo": _tiny_png()}, format="multipart"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_blocked_while_forced_password_change_is_pending(self):
        """Meme garde-fou global que les trois autres mutations du profil --
        comble le trou de couverture signale au compte rendu du correctif de
        securite (`MyProfilePhotoView` n'avait pas son equivalent de
        `TestMyCredentialsUpdateView.test_blocked_while_forced_password_change_is_pending`)."""

        user = UserFactory(must_change_password=True)
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-photo"), {"photo": _tiny_png()}, format="multipart"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        user.refresh_from_db()
        assert not user.photo

    def test_blocked_while_latest_terms_are_not_yet_accepted(self):
        """Meme principe pour `HasAcceptedLatestTerms` (CDC 7.5) : absent des
        `permission_classes` de cette vue."""

        TermsVersionFactory()
        user = UserFactory()
        client = _authenticated_client(user)

        response = client.patch(
            reverse("accounts:profile-photo"), {"photo": _tiny_png()}, format="multipart"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        user.refresh_from_db()
        assert not user.photo
