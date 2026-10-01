"""Middlewares transverses de l'app core.

Deux responsabilites independantes, toutes deux CDC 7.6 / CLAUDE.md
section 2 :

- :class:`RequestContextMiddleware` : positionne le contexte de requete
  (IP, user-agent -- CDC 5.1) et garantit qu'aucun club actif ni aucun
  contexte Ghost Mode (tache 1.8 ; CDC 5.4) ne fuit d'une requete a
  l'autre sur un meme thread/processus (regle n8/n9 ; le club actif et le
  contexte Ghost Mode sont eux-memes positionnes plus loin, par
  ``apps.core.authentication.TenantJWTAuthentication``, au moment de
  l'authentification -- ce middleware se contente de nettoyer en sortie,
  quelle que soit l'issue de la requete, y compris une exception).
- :class:`RestrictedCorsMiddleware` : CORS restreint a l'origine du
  frontend (CDC 7.6 : « L'API n'accepte que les appels provenant de
  vesta.eschoolb.com »). Implementation maison, volontairement minimale :
  ``django-cors-headers`` n'a pas pu etre installe hors ligne pour cette
  tache (voir compte rendu de la tache 1.3) -- a remplacer par ce paquet
  standard des qu'un acces reseau au depot de paquets est disponible,
  sans changer le comportement attendu (origine exacte, jamais de
  joker ``*``).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse

from apps.core.ghost_context import clear_ghost_context
from apps.core.request_context import reset_request_meta, set_request_meta
from apps.core.tenant import set_active_club


class RequestContextMiddleware:
    """Positionne l'IP/le user-agent de la requete ; nettoie le club actif en sortie."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip_address = self._client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:1000]
        token = set_request_meta(ip_address=ip_address, user_agent=user_agent)
        try:
            return self.get_response(request)
        finally:
            reset_request_meta(token)
            # Pas de jeton a restaurer ici : le club actif (et, tache 1.8,
            # le contexte Ghost Mode) sont positionnes plus tard dans le
            # cycle (authentification DRF, a l'interieur de la vue),
            # jamais par ce middleware lui-meme. Chaque requete HTTP doit
            # repartir d'un etat neutre : on force donc explicitement
            # "aucun club actif" / "aucune session de support en cours" en
            # sortie, plutot que de restaurer un etat anterieur qui n'a pas
            # de sens ici (CLAUDE.md regle n8/n9 ; CDC 5.4).
            set_active_club(None)
            clear_ghost_context()

    @staticmethod
    def _client_ip(request) -> str:
        """IP reelle du client (CDC 5.1), jamais choisie librement par lui.

        Audit de securite du Lot 1 (ecart bloquant B1) : la version
        precedente faisait confiance sans condition au premier element de
        `X-Forwarded-For`, un en-tete entierement choisi par le client --
        l'IP journalisee etait donc falsifiable a volonte. Desormais,
        `X-Forwarded-For` n'est utilise que si `settings.TRUSTED_PROXY_COUNT`
        (variable d'environnement `TRUSTED_PROXY_COUNT`, defaut 0) indique
        explicitement un nombre de proxys de confiance -- meme reglage et
        meme logique que `REST_FRAMEWORK["NUM_PROXIES"]` (DRF,
        `config.settings.base`), pour que la limitation de requetes et le
        journal d'activite s'accordent sur la meme IP.

        Cette equivalence a ete affinee par une revue independante de
        test-engineer (ecart residuel de B1, voir
        `apps.core.tests.test_num_proxies_misconfiguration`) : pour une
        valeur NEGATIVE (erreur de configuration), cette methode traite
        deja tout nombre `<= 0` comme "aucun proxy de confiance" (voir
        ci-dessous), mais `SimpleRateThrottle.get_ident` de DRF (code
        tiers) ne s'en protegeait pas par lui-meme -- `config.settings.base`
        borne donc desormais `TRUSTED_PROXY_COUNT`/`NUM_PROXIES` a `>= 0`
        au chargement des settings, et
        `apps.accounts.throttling.HardenedIdentThrottle` applique le meme
        bornage directement dans `get_ident`, en defense en profondeur,
        pour que les deux mecanismes ne puissent plus diverger meme si
        `NUM_PROXIES` venait a etre negatif par une autre voie. Le nombre
        reel de proxys derriere LiteSpeed/Passenger en production reste a
        confirmer par `devops-cpanel` (tache 1.SEC-A, ecart M8).
        """

        remote_addr = request.META.get("REMOTE_ADDR", "") or ""
        trusted_proxy_count = getattr(settings, "TRUSTED_PROXY_COUNT", 0)

        if trusted_proxy_count <= 0:
            return remote_addr

        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if not forwarded:
            return remote_addr

        addrs = [addr.strip() for addr in forwarded.split(",")]
        index = -min(trusted_proxy_count, len(addrs))
        return addrs[index] or remote_addr


class RestrictedCorsMiddleware:
    """CORS restreint a la liste d'origines de ``settings.CORS_ALLOWED_ORIGINS``.

    Jamais de joker ``*`` : seule l'origine exacte configuree (variable
    d'environnement, jamais ecrite en dur -- CLAUDE.md regle n12) reçoit
    les en-tetes ``Access-Control-Allow-*``. Repond directement aux
    requetes de pre-vol (``OPTIONS``) sans atteindre la vue.
    """

    _ALLOWED_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    # `x-support-session` (tache 1.8, CDC 5.4) : identifiant de la
    # `apps.licences.models.SupportSession` en cours, transmis par le
    # frontend pendant une intervention Ghost Mode -- voir
    # `apps.core.authentication.TenantJWTAuthentication`.
    _ALLOWED_HEADERS = "authorization, content-type, x-club-slug, x-support-session"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.META.get("HTTP_ORIGIN", "")
        allowed = origin and origin in set(getattr(settings, "CORS_ALLOWED_ORIGINS", []))

        if request.method == "OPTIONS" and "HTTP_ACCESS_CONTROL_REQUEST_METHOD" in request.META:
            response = HttpResponse()
            if allowed:
                response["Access-Control-Allow-Methods"] = self._ALLOWED_METHODS
                response["Access-Control-Allow-Headers"] = self._ALLOWED_HEADERS
                response["Access-Control-Max-Age"] = "86400"
        else:
            response = self.get_response(request)

        if origin:
            # `Vary: Origin` doit etre pose des qu'une decision CORS a ete
            # prise en fonction de l'``Origin`` recue, qu'elle soit
            # positive ou negative -- sinon un cache intermediaire (CDN,
            # reverse proxy) qui ignorerait l'``Origin`` peut confondre les
            # reponses destinees a des origines differentes (cache
            # poisoning, CDC 7.6). Comportement standard de
            # ``django-cors-headers``, que ce middleware maison remplace
            # temporairement.
            existing_vary = response.get("Vary", "")
            response["Vary"] = f"{existing_vary}, Origin".strip(", ") if existing_vary else "Origin"

        if allowed:
            response["Access-Control-Allow-Origin"] = origin

        return response
