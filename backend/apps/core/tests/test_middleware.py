"""Tests des middlewares transverses (tache 1.3).

Sources : CDC 5.1 (IP/user-agent), 7.6 (CORS restreint) ; CLAUDE.md
regles n8, n9, n12.
"""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.ghost_context import get_ghost_context, set_ghost_context
from apps.core.middleware import RequestContextMiddleware, RestrictedCorsMiddleware
from apps.core.request_context import get_request_meta
from apps.core.tenant import get_active_club, set_active_club


class TestRequestContextMiddleware:
    def test_positionne_l_ip_et_le_user_agent_pendant_la_vue(self):
        captured = {}

        def get_response(request):
            meta = get_request_meta()
            captured["ip_address"] = meta.ip_address
            captured["user_agent"] = meta.user_agent
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get("/", HTTP_USER_AGENT="TestAgent/1.0", REMOTE_ADDR="10.0.0.5")

        middleware(request)

        assert captured["ip_address"] == "10.0.0.5"
        assert captured["user_agent"] == "TestAgent/1.0"

    def test_ignore_x_forwarded_for_par_defaut_sans_proxy_de_confiance_configure(self, settings):
        """Audit de securite du Lot 1 (ecart bloquant B1) : par defaut
        (``TRUSTED_PROXY_COUNT`` non configure, donc 0), `X-Forwarded-For`
        est un en-tete choisi librement par le client -- lui faire confiance
        sans condition rendrait l'IP journalisee (CDC 5.1) falsifiable a
        volonte. Seule `REMOTE_ADDR` (vue directement par ce processus) est
        utilisee tant qu'aucun nombre de proxys de confiance n'est
        explicitement configure."""

        settings.TRUSTED_PROXY_COUNT = 0
        captured = {}

        def get_response(request):
            captured["ip_address"] = get_request_meta().ip_address
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get(
            "/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1"
        )

        middleware(request)

        assert captured["ip_address"] == "10.0.0.5"

    def test_utilise_x_forwarded_for_si_un_proxy_de_confiance_est_configure(self, settings):
        """Avec ``TRUSTED_PROXY_COUNT=1`` (un seul reverse proxy de confiance
        devant Django, ex. LiteSpeed/Passenger), l'IP retenue est celle que
        ce proxy a ajoutee (dernier element pertinent de la liste), pas
        `REMOTE_ADDR` (l'adresse du proxy lui-meme)."""

        settings.TRUSTED_PROXY_COUNT = 1
        captured = {}

        def get_response(request):
            captured["ip_address"] = get_request_meta().ip_address
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get(
            "/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1"
        )

        middleware(request)

        assert captured["ip_address"] == "10.0.0.1"

    def test_trusted_proxy_count_negatif_retombe_sur_remote_addr(self, settings):
        """Complete la couverture de l'ecart bloquant B1 : seuls 0 et 1 sont
        couverts par les tests existants de cette classe. Une valeur
        negative (erreur de configuration -- variable d'environnement mal
        saisie, calcul errone en amont) ne doit jamais etre traitee comme
        "un ou plusieurs proxys de confiance" : elle doit se comporter
        exactement comme 0 (ignorer `X-Forwarded-For`, en entier choisi par
        le client)."""

        settings.TRUSTED_PROXY_COUNT = -1
        captured = {}

        def get_response(request):
            captured["ip_address"] = get_request_meta().ip_address
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get(
            "/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="203.0.113.9, valeur-choisie-par-le-client"
        )

        middleware(request)

        assert captured["ip_address"] == "10.0.0.5"

    def test_trusted_proxy_count_tres_grand_se_rabat_sur_le_premier_element(self, settings):
        """Un `TRUSTED_PROXY_COUNT` superieur au nombre reel de sauts de la
        liste ne doit jamais lever ni indexer hors limites : il se rabat
        sur l'element le plus a gauche de `X-Forwarded-For` (limite
        connue -- si ce nombre est mal configure trop haut, on retombe sur
        une confiance totale dans l'en-tete, comme documente pour
        `REST_FRAMEWORK["NUM_PROXIES"]`), jamais sur une erreur."""

        settings.TRUSTED_PROXY_COUNT = 999_999
        captured = {}

        def get_response(request):
            captured["ip_address"] = get_request_meta().ip_address
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get(
            "/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2, 3.3.3.3"
        )

        middleware(request)

        assert captured["ip_address"] == "1.1.1.1"

    def test_x_forwarded_for_absent_retombe_sur_remote_addr_meme_avec_proxy_configure(self, settings):
        settings.TRUSTED_PROXY_COUNT = 1
        captured = {}

        def get_response(request):
            captured["ip_address"] = get_request_meta().ip_address
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.5")

        middleware(request)

        assert captured["ip_address"] == "10.0.0.5"

    def test_nettoie_le_contexte_apres_la_reponse(self):
        def get_response(request):
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get("/", HTTP_USER_AGENT="TestAgent/1.0")

        middleware(request)

        meta = get_request_meta()
        assert meta.ip_address == ""
        assert meta.user_agent == ""

    def test_force_aucun_club_actif_en_sortie_meme_si_positionne_pendant_la_vue(self):
        """Reproduit exactement ce que fait `TenantJWTAuthentication` : positionne
        le club actif sans jamais le restaurer elle-meme (aucun jeton conserve) --
        c'est ce middleware qui doit garantir qu'il ne fuit pas vers la requete
        suivante sur le meme thread (regles n8/n9)."""

        club_marqueur = object()

        def get_response(request):
            set_active_club(club_marqueur)
            assert get_active_club() is club_marqueur
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get("/")

        middleware(request)

        assert get_active_club() is None

    def test_nettoie_meme_si_la_vue_leve_une_exception(self):
        def get_response(request):
            raise RuntimeError("erreur simulee")

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get("/", HTTP_USER_AGENT="TestAgent/1.0")

        with pytest.raises(RuntimeError):
            middleware(request)

        assert get_request_meta().user_agent == ""

    def test_force_aucun_contexte_ghost_en_sortie_meme_si_positionne_pendant_la_vue(self):
        """Tache 1.8 (CDC 5.4) : meme garantie que pour le club actif
        (`test_force_aucun_club_actif_en_sortie_meme_si_positionne_pendant_la_vue`
        ci-dessus), pour le contexte Ghost Mode. Sans ce nettoyage, le
        thread suivant (reutilise par le serveur WSGI, CLAUDE.md section
        4) heriterait a tort d'une session de support d'une requete
        precedente."""

        def get_response(request):
            set_ghost_context("42")
            assert get_ghost_context() is not None
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get("/")

        middleware(request)

        assert get_ghost_context() is None

    def test_nettoie_le_contexte_ghost_meme_si_la_vue_leve_une_exception(self):
        """Meme garantie que ci-dessus, mais avec une vue qui leve : le
        Ghost Mode ne doit jamais survivre a une exception non geree par
        la vue elle-meme."""

        def get_response(request):
            set_ghost_context("42")
            raise RuntimeError("erreur simulee")

        middleware = RequestContextMiddleware(get_response)
        request = RequestFactory().get("/")

        with pytest.raises(RuntimeError):
            middleware(request)

        assert get_ghost_context() is None


class TestRestrictedCorsMiddleware:
    def _middleware(self, settings, allowed_origins):
        settings.CORS_ALLOWED_ORIGINS = allowed_origins
        return RestrictedCorsMiddleware(lambda request: HttpResponse())

    def test_origine_autorisee_recoit_l_en_tete(self, settings):
        middleware = self._middleware(settings, ["https://vesta.eschoolb.com"])
        request = RequestFactory().get("/", HTTP_ORIGIN="https://vesta.eschoolb.com")

        response = middleware(request)

        assert response["Access-Control-Allow-Origin"] == "https://vesta.eschoolb.com"
        assert "Origin" in response["Vary"]

    def test_origine_non_autorisee_ne_recoit_aucun_en_tete(self, settings):
        middleware = self._middleware(settings, ["https://vesta.eschoolb.com"])
        request = RequestFactory().get("/", HTTP_ORIGIN="https://attaquant.example.com")

        response = middleware(request)

        assert "Access-Control-Allow-Origin" not in response

    def test_jamais_de_joker_meme_sans_configuration(self, settings):
        middleware = self._middleware(settings, [])
        request = RequestFactory().get("/", HTTP_ORIGIN="https://n-importe-quoi.example.com")

        response = middleware(request)

        assert "Access-Control-Allow-Origin" not in response

    def test_repond_directement_au_pre_vol_pour_une_origine_autorisee(self, settings):
        middleware = self._middleware(settings, ["https://vesta.eschoolb.com"])
        request = RequestFactory().options(
            "/",
            HTTP_ORIGIN="https://vesta.eschoolb.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        response = middleware(request)

        assert response.status_code == 200
        assert "POST" in response["Access-Control-Allow-Methods"]

    def test_vary_origin_present_meme_quand_l_origine_est_refusee(self, settings):
        """CDC 7.6 (securite applicative) : un en-tete de reponse qui varie
        selon l'``Origin`` de la requete (ici : la presence ou non des
        en-tetes ``Access-Control-Allow-*``) doit **toujours** porter
        ``Vary: Origin``, y compris quand l'origine est refusee -- sinon un
        cache intermediaire (CDN, reverse proxy) qui ignorerait ce cas peut
        servir a une origine la reponse mise en cache pour une autre
        (« cache poisoning » : ex. une reponse sans en-tete CORS, mise en
        cache pour l'origine legitime, empechant son propre acces ; ou
        l'inverse, une reponse portant des en-tetes CORS accordes a une
        origine attaquante si le cache la reutilise pour elle).

        BUG REEL : l'implementation actuelle ne pose ``Vary: Origin`` que
        dans la branche ``if allowed:`` -- a signaler a backend-dev.
        """
        middleware = self._middleware(settings, ["https://vesta.eschoolb.com"])
        request = RequestFactory().get("/", HTTP_ORIGIN="https://attaquant.example.com")

        response = middleware(request)

        assert "Access-Control-Allow-Origin" not in response
        assert "Origin" in response.get("Vary", ""), (
            "La reponse a une origine refusee doit porter `Vary: Origin` au "
            "meme titre qu'une reponse a une origine autorisee : sans cet "
            "en-tete, un cache intermediaire peut confondre les reponses "
            "destinees a des origines differentes (risque de cache "
            "poisoning, CDC 7.6)."
        )

    def test_vary_origin_present_sur_le_pre_vol_refuse(self, settings):
        middleware = self._middleware(settings, ["https://vesta.eschoolb.com"])
        request = RequestFactory().options(
            "/",
            HTTP_ORIGIN="https://attaquant.example.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        response = middleware(request)

        assert "Access-Control-Allow-Methods" not in response
        assert "Origin" in response.get("Vary", "")

    def test_aucun_en_tete_origin_sur_une_requete_normale_est_traite_sans_erreur(self, settings):
        """Appel sans navigateur (pas d'en-tete `Origin`, ex. serveur a serveur) :
        ne doit jamais lever ni bloquer -- la restriction CORS ne s'applique
        qu'aux appels de navigateur, la protection reelle contre les appels
        non-navigateur venant d'ailleurs que du frontend restant
        l'authentification et la limitation de requetes (CDC 7.6)."""
        middleware = self._middleware(settings, ["https://vesta.eschoolb.com"])
        request = RequestFactory().get("/")

        response = middleware(request)

        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" not in response

    def test_ne_reflete_jamais_une_origine_arbitraire(self, settings):
        """Pas de reflexion de l'origine sans validation stricte : une origine
        qui ressemble a l'origine autorisee (sous-domaine, port different,
        schema different) doit etre refusee, seule l'egalite exacte compte."""
        middleware = self._middleware(settings, ["https://vesta.eschoolb.com"])

        for origine_proche in [
            "https://vesta.eschoolb.com.attaquant.example.com",
            "https://attaquant.example.com/https://vesta.eschoolb.com",
            "http://vesta.eschoolb.com",
            "https://vesta.eschoolb.com:8443",
            "https://sous-domaine.vesta.eschoolb.com",
        ]:
            request = RequestFactory().get("/", HTTP_ORIGIN=origine_proche)
            response = middleware(request)
            assert "Access-Control-Allow-Origin" not in response, origine_proche
