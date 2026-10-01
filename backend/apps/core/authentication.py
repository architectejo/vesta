"""Authentification JWT qui branche le club actif sur la requete reelle.

Tache 1.3 : « Club actif à la connexion (branche le mecanisme de
apps/core/tenant.py pose en 1.2 sur la requete reelle) [...] jamais d'un
``tenant_id`` dans le jeton. »

``TenantJWTAuthentication`` etend l'authentification JWT standard de
SimpleJWT : une fois l'utilisateur identifie par son jeton d'acces (qui
ne porte jamais de club, CLAUDE.md regle n9), elle deduit son club actif
de son adhesion en cours reelle (``apps.core.services.resolve_active_membership``)
et le positionne pour la duree de la requete (``apps.core.tenant.set_active_club``).
Le nettoyage (retour a "aucun club actif") est assure par
``apps.core.middleware.RequestContextMiddleware``, quelle que soit l'issue
de la requete (CDC 6.3 ; regle n8 : "une requete sans club actif est refusee").

Cas particulier documente (point ouvert, voir compte rendu de la tache
1.3) : un utilisateur avec plusieurs adhesions actives simultanees ne
peut pas etre desambiguise sur une requete quelconque (le jeton ne porte
aucun identifiant de club, et rien dans la requete ne permet de choisir
entre les deux de facon fiable) -- la desambiguisation explicite par slug
n'existe qu'a la connexion (``apps.accounts.services.resolve_login_club``).
Dans ce cas rare, aucun club n'est positionne ici : les acces a des
donnees privees de club echouent alors normalement, "sans club actif"
(regle n8), jusqu'a ce qu'une tache ulterieure traite ce cas (ex. en-tete
dedie sur chaque requete).

Tache 1.8 (Ghost Mode, CDC 5.4) : un Superuser n'a structurellement jamais
de club actif (CLAUDE.md regle n1, voir ``resolve_active_membership``
ci-dessus qui leve pour lui). Pendant une intervention de support, le
frontend transmet l'en-tete ``X-Support-Session`` (identifiant d'une
``apps.licences.models.SupportSession`` deja demarree) sur chaque requete
concernee : si cette session existe, appartient bien a CE Superuser et est
encore valide (``apps.licences.services.is_support_session_valid``), le
club actif est positionne sur le SEUL club de cette session -- jamais un
autre, meme par erreur de manipulation cote client, puisque le club vient
de l'enregistrement `SupportSession` resolu en base, jamais d'un parametre
club transmis directement -- et le contexte Ghost Mode
(``apps.core.ghost_context``) est arme pour que
``apps.core.services.log_action`` marque automatiquement
``acted_as_ghost=True``/``support_session_id=<id>`` sur toute entree de
journal ecrite pendant cette requete, sans que chaque service producteur
ait a s'en preoccuper explicitement. Un en-tete absent, invalide ou
perime est ignore silencieusement (aucun club n'est positionne : le
Superuser se retrouve alors dans son etat normal, "sans club actif",
comme avant cette tache) -- jamais d'erreur bloquante sur ce seul motif,
pour ne pas casser les autres ecrans de l'espace Superuser (Licences,
Comptes...) qui n'ont besoin d'aucun club actif.
"""

from __future__ import annotations

from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.ghost_context import set_ghost_context
from apps.core.tenant import NoActiveClubError, set_active_club


class TenantJWTAuthentication(JWTAuthentication):
    """``JWTAuthentication`` de SimpleJWT, augmentee de la resolution du club actif."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result

        if not getattr(user, "is_superuser", False):
            # Import tardif : evite tout import circulaire au chargement
            # des apps (apps.core est charge avant apps.clubs).
            from apps.core.services import resolve_active_membership

            try:
                membership = resolve_active_membership(user)
            except NoActiveClubError:
                pass
            else:
                set_active_club(membership.club)
        else:
            self._maybe_enter_ghost_mode(request, user)

        return user, validated_token

    @staticmethod
    def _maybe_enter_ghost_mode(request, superuser) -> None:
        """Arme le Ghost Mode pour cette requete si un en-tete de session
        de support valide est presente (tache 1.8, voir docstring du
        module)."""

        raw_session_id = request.META.get("HTTP_X_SUPPORT_SESSION", "")
        if not raw_session_id:
            return

        # Import tardif : evite tout import circulaire au chargement des
        # apps (apps.core est charge avant apps.licences).
        from apps.licences.models import SupportSession
        from apps.licences.services import is_support_session_valid

        try:
            session = (
                SupportSession.objects.select_related("club")
                .filter(pk=raw_session_id, superuser=superuser)
                .first()
            )
        except (ValueError, TypeError):
            # Identifiant non numerique transmis dans l'en-tete : traite
            # comme "aucune session" plutot que de faire echouer toute
            # l'authentification pour un en-tete malforme.
            return

        if session is None or not is_support_session_valid(session):
            return

        set_active_club(session.club)
        set_ghost_context(str(session.pk))
