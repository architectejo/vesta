"""Tests HTTP de l'API comptes (tache 1.3, 1.3t).

Utilise l'API reelle (``rest_framework.test.APIClient``) pour verifier :
- le parcours de connexion complet (CDC 4.1, 7.1) ;
- que ``must_change_password`` bloque bien l'acces aux autres routes
  tant qu'il n'est pas resolu (critere d'acceptation CDC 4.1) ;
- la deconnexion et le blacklist de tous les appareils (CDC 7.1) ;
- que l'IP/le user-agent reels de la requete sont bien journalises (CDC
  5.1 ; point ouvert de la tache 1.6, resolu par la tache 1.3) ;
- l'acceptation des CGU depuis une requete HTTP reelle (10.2 n27).
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

import io

import pytest
from django.core.files.base import ContentFile
from PIL import Image

from django.core.cache import cache

from apps.accounts.models import PasswordResetRequest
from apps.accounts.tests.factories import SuperuserFactory, TermsVersionFactory, UserFactory
from apps.audit.models import AuditLog
from apps.clubs.tests.factories import MembershipFactory

RAW_PASSWORD = "MotDePasse123"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestLoginEndpoint:
    def test_connexion_reussie_renvoie_des_jetons_et_l_identite_du_club(self, api_client):
        membership = MembershipFactory(status="active")
        user = membership.user

        response = api_client.post(
            reverse("accounts:login"), {"email": user.email, "password": RAW_PASSWORD}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["club"]["slug"] == membership.club.slug
        assert response.data["must_change_password"] is False

    def test_logo_du_club_est_renvoye_en_url_absolue(self, api_client):
        """Bug remarques.md : un chemin relatif (``MEDIA_URL``) pointe vers
        le mauvais serveur des que l'interface et l'API sont sur des
        origines differentes (sous-domaines distincts en production, proxy
        Vite qui ne couvre que ``/api`` en developpement) -- l'image ne
        charge alors jamais."""

        membership = MembershipFactory(status="active")
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), color="blue").save(buffer, format="PNG")
        membership.club.logo.save("logo.png", ContentFile(buffer.getvalue()), save=True)
        user = membership.user

        response = api_client.post(
            reverse("accounts:login"), {"email": user.email, "password": RAW_PASSWORD}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["club"]["logo"].startswith("http://testserver/media/")

    def test_mot_de_passe_incorrect_renvoie_401_avec_essais_restants(self, api_client):
        membership = MembershipFactory(status="active")
        user = membership.user

        response = api_client.post(
            reverse("accounts:login"), {"email": user.email, "password": "faux"}, format="json"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["attempts_remaining"] == 4

    def test_ne_revele_pas_l_existence_d_un_compte_par_le_corps_de_la_reponse(self, api_client):
        """CDC 7.6 ; comptes-connexion.md §7 (point ouvert securite) : « pour ne pas
        reveler quelles adresses ont un compte, l'API doit repondre de la meme
        facon (meme message, meme compteur d'essais...) qu'un email existe ou
        non. »

        Verifie que le corps de la reponse ne contient pas une cle
        supplementaire (``attempts_remaining``) uniquement quand l'email
        correspond a un compte reel avec un mauvais mot de passe -- ce qui
        permettrait de deduire, par la seule forme de la reponse (sans lire
        le message), qu'un email est inscrit.
        """
        membership = MembershipFactory(status="active")
        user = membership.user

        response_compte_existant = api_client.post(
            reverse("accounts:login"), {"email": user.email, "password": "faux"}, format="json"
        )
        response_email_inconnu = api_client.post(
            reverse("accounts:login"),
            {"email": "totalement-inconnu@example.com", "password": "faux"},
            format="json",
        )

        assert response_compte_existant.status_code == response_email_inconnu.status_code
        assert set(response_compte_existant.data.keys()) == set(response_email_inconnu.data.keys()), (
            "Le corps de la reponse ne doit pas contenir de cle "
            "supplementaire (`attempts_remaining`) selon que l'email "
            "correspond ou non a un compte reel : c'est un moyen de deviner "
            "quelles adresses sont inscrites sur la plateforme, meme sans "
            "lire le message d'erreur."
        )
        assert response_compte_existant.data["detail"] == response_email_inconnu.data["detail"]

    def test_ip_et_user_agent_reels_sont_journalises(self, api_client):
        """Point ouvert de la tache 1.6 (CDC 5.1), resolu par le contexte de requete."""

        membership = MembershipFactory(status="active")
        user = membership.user

        api_client.post(
            reverse("accounts:login"),
            {"email": user.email, "password": RAW_PASSWORD},
            format="json",
            REMOTE_ADDR="203.0.113.42",
            HTTP_USER_AGENT="VestaTestClient/1.0",
        )

        entry = AuditLog.objects.get(actor=user, action_type="auth.login_succeeded")
        assert entry.ip_address == "203.0.113.42"
        assert entry.user_agent == "VestaTestClient/1.0"


@pytest.mark.django_db
class TestLimitationDeRequetesMalgreUnJetonBearerValide:
    """Preuve de fermeture de l'ecart bloquant B1 (audit de securite du Lot 1).

    Avant correction, ``LoginView``/``PasswordResetRequestView`` gardaient
    ``DEFAULT_AUTHENTICATION_CLASSES`` (``TenantJWTAuthentication``) malgre
    ``permission_classes = [AllowAny]`` : un attaquant qui presentait son
    propre jeton ``Bearer`` valide (obtenu legitimement par ailleurs)
    devenait alors un utilisateur "authentifie" aux yeux de DRF sur CES
    endpoints -- ce qui desactive silencieusement ``AnonRateThrottle``
    (qui ne s'applique qu'aux requetes anonymes), rendant la limitation de
    requetes inoperante. ``authentication_classes = []`` explicite sur ces
    deux vues (voir ``apps.accounts.views``) ferme ce contournement :
    ``request.user`` reste anonyme quel que soit l'en-tete ``Authorization``
    presente, la limitation par IP se declenche donc normalement.

    Chaque requete de la boucle utilise un email different pour isoler la
    limitation par IP (``LoginRateThrottle``/``PasswordResetRateThrottle``)
    de celle par email (``LoginEmailRateThrottle``/
    ``PasswordResetEmailRateThrottle``, tres proche mais keyee differemment) --
    sans quoi les deux se declencheraient au meme moment et le test ne
    prouverait pas laquelle des deux protege effectivement contre le jeton
    ``Bearer``."""

    def _attacker_bearer_header(self) -> str:
        attaquant = UserFactory()
        access = str(RefreshToken.for_user(attaquant).access_token)
        return f"Bearer {access}"

    def test_login_reste_limite_par_ip_malgre_un_jeton_bearer_valide(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION=self._attacker_bearer_header())

        statuses = []
        for i in range(25):
            response = api_client.post(
                reverse("accounts:login"),
                {"email": f"cible-{i}@example.com", "password": "peu-importe"},
                format="json",
            )
            statuses.append(response.status_code)

        assert status.HTTP_429_TOO_MANY_REQUESTS in statuses, (
            "La limitation par IP (`LoginRateThrottle`) ne s'est jamais "
            "declenchee malgre 25 requetes rapides : le jeton Bearer de "
            "l'attaquant a rendu la requete 'authentifiee', desactivant "
            "silencieusement `AnonRateThrottle` (ecart B1)."
        )

    def test_password_reset_request_reste_limite_par_ip_malgre_un_jeton_bearer_valide(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION=self._attacker_bearer_header())

        statuses = []
        for i in range(10):
            response = api_client.post(
                reverse("accounts:password-reset-request"),
                {"email": f"cible-{i}@example.com"},
                format="json",
            )
            statuses.append(response.status_code)

        assert status.HTTP_429_TOO_MANY_REQUESTS in statuses


@pytest.mark.django_db
class TestForcedPasswordChangeViewReserveAuChangementForce:
    """Preuve de fermeture de l'ecart bloquant B3 (audit de securite du Lot
    1), au niveau HTTP : `test_services_password.py` ne verifie le mappage
    de `PasswordChangeNotForcedError` qu'au niveau du service -- ce test
    verifie que la vue le traduit bien en 403 avec un message francais
    clair (CLAUDE.md regle n20), pas en 500 ni en un autre code."""

    def test_refuse_403_avec_message_francais_si_le_changement_n_est_pas_force(self, api_client):
        membership = MembershipFactory(status="active")
        user = membership.user  # must_change_password=False (defaut de UserFactory).
        access = str(RefreshToken.for_user(user).access_token)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = api_client.post(
            reverse("accounts:password-change"),
            {"new_password": "UnAutreMotDePasse9", "confirm_password": "UnAutreMotDePasse9"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "changement de mot de passe" in response.data["detail"].lower()

        user.refresh_from_db()
        assert user.check_password(RAW_PASSWORD), "Le mot de passe ne doit pas avoir change."


@pytest.mark.django_db
class TestLimitationParEmailViaEndpointReelMalgreDesIpDifferentes:
    """Complete `TestLimitationDeRequetesMalgreUnJetonBearerValide` (qui
    isole la defense par IP en faisant varier l'email a chaque requete) :
    ici, on isole au contraire la defense par EMAIL en faisant varier
    `REMOTE_ADDR` a chaque requete pour une MEME adresse email vises --
    seule `LoginEmailRateThrottle` peut declencher un 429 dans ce
    scenario, ce qui prouve que les deux defenses (IP et email) sont
    bien actives simultanement sur l'API reelle (pas seulement au niveau
    unitaire de `test_throttling.py`), sans que l'une masque l'autre."""

    def test_meme_email_vise_avec_des_ip_differentes_declenche_la_limite(self, api_client):
        cible = "cible-fixe@example.com"
        statuses = []
        for i in range(25):
            response = api_client.post(
                reverse("accounts:login"),
                {"email": cible, "password": "peu-importe"},
                format="json",
                REMOTE_ADDR=f"203.0.113.{i + 1}",
            )
            statuses.append(response.status_code)

        assert status.HTTP_429_TOO_MANY_REQUESTS in statuses, (
            "La limitation par email vise (`LoginEmailRateThrottle`) ne s'est "
            "jamais declenchee sur l'API reelle malgre 25 requetes rapides "
            "utilisant une adresse IP differente a chaque fois -- elle ne doit "
            "jamais dependre de l'adresse IP (ecart B1)."
        )


@pytest.mark.django_db
class TestJetonAccesResteValideApresChangementDeMotDePasse:
    """Documente un residu connu, deja signale par le docstring de
    `apps.accounts.services.change_forced_password` (audit de securite du
    Lot 1, ecart bloquant B3) : SimpleJWT ne met en liste noire que les
    jetons de RENOUVELLEMENT (refresh) par defaut -- un jeton d'ACCES (15
    min) deja emis avant le changement de mot de passe reste utilisable
    jusqu'a son expiration naturelle, meme apres un changement de mot de
    passe reussi qui revoque tous les jetons de renouvellement. Ce test
    fixe ce comportement ACTUEL (ce n'est pas un bug a corriger dans cette
    tache : c'est un residu deja documente et accepte) -- il sert de
    garde-fou pour qu'un changement silencieux de ce comportement (ex. une
    future evolution de l'authentification) soit visible ici plutot que
    decouvert en production."""

    def test_l_ancien_jeton_d_acces_reste_utilisable_juste_apres_le_changement(self, api_client):
        membership = MembershipFactory(status="active")
        user = membership.user
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])

        login_response = api_client.post(
            reverse("accounts:login"), {"email": user.email, "password": RAW_PASSWORD}, format="json"
        )
        access_avant_changement = login_response.data["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_avant_changement}")

        change_response = api_client.post(
            reverse("accounts:password-change"),
            {"new_password": "UnAutreMotDePasse9", "confirm_password": "UnAutreMotDePasse9"},
            format="json",
        )
        assert change_response.status_code == status.HTTP_200_OK

        # Meme jeton d'acces qu'avant le changement (jamais renouvele),
        # utilise sur un autre endpoint protege : reste accepte (residu
        # documente ci-dessus), bien que tous les jetons de renouvellement
        # de l'utilisateur aient ete mis en liste noire par le changement.
        response = api_client.post(reverse("accounts:logout-all"))
        assert response.status_code == status.HTTP_200_OK


class _GenericProtectedView(APIView):
    """Vue jetable, sans ``permission_classes`` explicite.

    Soumise donc a ``DEFAULT_PERMISSION_CLASSES``
    (``HasCompletedPasswordSetup``, ``HasAcceptedLatestTerms``) :
    represente n'importe quel futur endpoint d'un autre module qui
    n'exclut pas ces garde-fous (le cas normal -- seuls les endpoints du
    parcours de deblocage les excluent, voir ``apps.accounts.views``).
    Aucune app hors ``accounts`` n'existe encore au Lot 1 pour l'exercer
    via une vraie route ``urls.py`` : ce point verifie directement le
    comportement des permissions par defaut sur une requete authentifiee
    reelle.
    """

    def get(self, request):
        return Response({"detail": "ok"})


@pytest.mark.django_db
class TestGardeFousParDefautBloquentLesAutresRoutes:
    """CDC 4.1 (critere d'acceptation) ; CDC 7.5, 10.2 n27."""

    def _call_generic_view(self, user):
        factory = APIRequestFactory()
        request = factory.get("/quelconque/")
        force_authenticate(request, user=user)
        return _GenericProtectedView.as_view()(request)

    def test_refuse_tant_que_le_mot_de_passe_n_est_pas_change(self):
        membership = MembershipFactory(status="active")
        user = membership.user
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])

        response = self._call_generic_view(user)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_refuse_tant_que_les_cgu_ne_sont_pas_acceptees(self):
        membership = MembershipFactory(status="active")
        user = membership.user
        TermsVersionFactory()  # une version existe, jamais acceptee par ce compte

        response = self._call_generic_view(user)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_superuser_n_est_jamais_bloque_par_les_cgu(self):
        superuser = SuperuserFactory()
        TermsVersionFactory()

        response = self._call_generic_view(superuser)

        assert response.status_code == status.HTTP_200_OK

    def test_autorise_une_fois_le_mot_de_passe_change_et_les_cgu_acceptees(self):
        membership = MembershipFactory(status="active")
        user = membership.user

        response = self._call_generic_view(user)

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestMustChangePasswordBloqueLesAutresRoutes:
    def _login(self, api_client, user):
        response = api_client.post(
            reverse("accounts:login"), {"email": user.email, "password": RAW_PASSWORD}, format="json"
        )
        return response.data["access"], response.data["refresh"]

    def test_deconnexion_reste_possible_pendant_le_blocage(self, api_client):
        """« Seule issue secondaire : Se deconnecter » (comptes-connexion.md §4.2)."""

        membership = MembershipFactory(status="active")
        user = membership.user
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])

        access, _refresh = self._login(api_client, user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = api_client.post(reverse("accounts:logout-all"))
        assert response.status_code == status.HTTP_200_OK

    def test_changement_de_mot_de_passe_leve_le_blocage(self, api_client):
        membership = MembershipFactory(status="active")
        user = membership.user
        user.must_change_password = True
        user.save(update_fields=["must_change_password"])

        access, _refresh = self._login(api_client, user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        change_response = api_client.post(
            reverse("accounts:password-change"),
            {"new_password": "UnAutreMotDePasse9", "confirm_password": "UnAutreMotDePasse9"},
            format="json",
        )
        assert change_response.status_code == status.HTTP_200_OK

        user.refresh_from_db()
        assert user.must_change_password is False


@pytest.mark.django_db
class TestLogout:
    def test_deconnexion_blackliste_le_jeton_de_renouvellement(self, api_client):
        membership = MembershipFactory(status="active")
        user = membership.user

        login_response = api_client.post(
            reverse("accounts:login"), {"email": user.email, "password": RAW_PASSWORD}, format="json"
        )
        access, refresh = login_response.data["access"], login_response.data["refresh"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        logout_response = api_client.post(reverse("accounts:logout"), {"refresh": refresh}, format="json")
        assert logout_response.status_code == status.HTTP_204_NO_CONTENT

        refresh_response = api_client.post(reverse("accounts:token-refresh"), {"refresh": refresh}, format="json")
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_deconnexion_de_tous_les_appareils_blackliste_tous_les_jetons(self, api_client):
        membership = MembershipFactory(status="active")
        user = membership.user

        refresh_1 = RefreshToken.for_user(user)
        refresh_2 = RefreshToken.for_user(user)

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh_1.access_token}")
        response = api_client.post(reverse("accounts:logout-all"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["tokens_blacklisted"] == 2

        refresh_response = api_client.post(
            reverse("accounts:token-refresh"), {"refresh": str(refresh_2)}, format="json"
        )
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPasswordResetRequestEndpoint:
    def test_reponse_identique_que_le_compte_existe_ou_non(self, api_client):
        user = UserFactory()

        response_existant = api_client.post(
            reverse("accounts:password-reset-request"), {"email": user.email}, format="json"
        )
        response_inconnu = api_client.post(
            reverse("accounts:password-reset-request"), {"email": "inconnu@example.com"}, format="json"
        )

        assert response_existant.status_code == response_inconnu.status_code == status.HTTP_200_OK
        assert response_existant.data == response_inconnu.data
        assert PasswordResetRequest.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestSuperuserPasswordResetEndpoint:
    def test_reserve_au_superuser(self, api_client):
        membership = MembershipFactory(status="active")
        cible = UserFactory()
        access = str(RefreshToken.for_user(membership.user).access_token)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = api_client.post(
            reverse("accounts:password-reset-superuser"), {"email": cible.email}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_superuser_recoit_le_mot_de_passe_temporaire_une_seule_fois(self, api_client):
        superuser = SuperuserFactory()
        cible = UserFactory()
        access = str(RefreshToken.for_user(superuser).access_token)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = api_client.post(
            reverse("accounts:password-reset-superuser"), {"email": cible.email}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["temporary_password"]) == 8

        cible.refresh_from_db()
        assert cible.must_change_password is True


@pytest.mark.django_db
class TestCguDepuisUneRequeteHttpReelle:
    def test_acceptation_journalisee_avec_ip_et_user_agent_reels(self, api_client):
        membership = MembershipFactory(status="active")
        user = membership.user
        version = TermsVersionFactory()
        access = str(RefreshToken.for_user(user).access_token)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = api_client.post(
            reverse("accounts:terms-accept"),
            {"terms_version_id": version.pk},
            format="json",
            REMOTE_ADDR="198.51.100.7",
            HTTP_USER_AGENT="VestaTestClient/CGU",
        )

        assert response.status_code == status.HTTP_200_OK
        entry = AuditLog.objects.get(actor=user, action_type="accounts.terms.accepted")
        assert entry.ip_address == "198.51.100.7"
        assert entry.user_agent == "VestaTestClient/CGU"

    def test_terms_pending_et_terms_accept_restent_accessibles_pendant_le_blocage(self, api_client):
        """Ces deux endpoints doivent rester atteignables pour permettre de sortir du blocage."""

        membership = MembershipFactory(status="active")
        user = membership.user
        version = TermsVersionFactory()  # jamais acceptee par ce compte : le blocage est actif
        access = str(RefreshToken.for_user(user).access_token)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        pending_response = api_client.get(reverse("accounts:terms-pending"))
        assert pending_response.status_code == status.HTTP_200_OK
        assert pending_response.data["id"] == version.pk

        accept_response = api_client.post(
            reverse("accounts:terms-accept"), {"terms_version_id": version.pk}, format="json"
        )
        assert accept_response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestThirdSeriesFixes:
    """Corrections de la troisième série de tests (15/11/2026)."""

    def test_terms_pending_sans_version_en_attente_renvoie_le_litteral_json_null(self, api_client):
        membership = MembershipFactory(status="active")
        version = TermsVersionFactory()
        api_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(membership.user).access_token}"
        )
        accept = api_client.post(reverse("accounts:terms-accept"), {"terms_version_id": version.pk}, format="json")
        assert accept.status_code == status.HTTP_200_OK

        response = api_client.get(reverse("accounts:terms-pending"))

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"].startswith("application/json")
        assert response.content == b"null"
        assert response.json() is None


@pytest.mark.django_db
class TestSecondSeriesFixes:
    """Corrections de la deuxieme serie de tests (15/11/2026)."""

    def test_refresh_invalide_renvoie_un_message_francais(self, api_client):
        response = api_client.post(reverse("accounts:token-refresh"), {"refresh": "n-importe-quoi"}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Token" not in str(response.data)
        assert "invalide" in response.data["detail"]
        assert "Reconnectez-vous" in response.data["detail"]

    def test_acces_sans_jeton_renvoie_un_message_francais(self, api_client):
        response = api_client.get(reverse("accounts:terms-pending"))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "credentials" not in str(response.data)
        assert "Connectez-vous" in response.data["detail"]

    def test_superuser_n_a_pas_de_cgu_en_attente_a_la_connexion(self, api_client):
        superuser = SuperuserFactory()
        TermsVersionFactory()

        response = api_client.post(
            reverse("accounts:login"), {"email": superuser.email, "password": RAW_PASSWORD}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["terms_acceptance_required"] is False

    def test_superuser_n_a_pas_de_cgu_en_attente_sur_la_route_dediee(self, api_client):
        superuser = SuperuserFactory()
        TermsVersionFactory()
        api_client.force_authenticate(user=superuser)

        response = api_client.get(reverse("accounts:terms-pending"))

        assert response.status_code == status.HTTP_200_OK
        assert response.json() is None

    def test_joueur_reste_soumis_aux_cgu(self, api_client):
        membership = MembershipFactory(status="active")
        TermsVersionFactory()

        response = api_client.post(
            reverse("accounts:login"),
            {"email": membership.user.email, "password": RAW_PASSWORD},
            format="json",
        )

        assert response.data["terms_acceptance_required"] is True
