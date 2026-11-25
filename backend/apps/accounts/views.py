"""Vues DRF de l'app accounts (CDC 4.1, 7.1, 7.5 ; tache 1.3).

Orchestrent uniquement : permission -> service -> serializer (CLAUDE.md
section 5). Toute regle metier (blocage, generation du mot de passe
temporaire, desambiguisation du club actif...) vit dans
``apps.accounts.services``.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView

from apps.accounts import serializers, services
from apps.accounts.models import TermsVersion, User
from apps.accounts.throttling import (
    LoginEmailRateThrottle,
    LoginRateThrottle,
    PasswordResetEmailRateThrottle,
    PasswordResetRateThrottle,
)
from apps.core.permissions import (
    HasAcceptedLatestTerms,
    HasCompletedPasswordSetup,
    HasUsableLicence,
    IsSuperuser,
)


def _serialize_club(club, request) -> dict | None:
    """Identite publique minimale du club (CDC 7.3) -- jamais `ClubSettings`.

    ``logo`` est renvoye en URL ABSOLUE (``request.build_absolute_uri``,
    bug remarques.md) : un chemin relatif (``MEDIA_URL``) pointe vers le
    mauvais serveur des que l'interface et l'API sont sur des origines
    differentes (sous-domaines distincts en production, proxy Vite qui ne
    couvre que ``/api`` en developpement) -- l'image ne charge alors
    jamais. Ce n'est pas un fichier prive (pas de justificatif/document
    medical) : pas de passage par une vue authentifiee, juste l'URL
    absolue vers le bon host.
    """

    if club is None:
        return None
    return {
        "id": club.id,
        "slug": club.slug,
        "name": club.name,
        "logo": request.build_absolute_uri(club.logo.url) if club.logo else None,
        "primary_color": club.primary_color,
        "secondary_color": club.secondary_color,
    }


class TokenRefreshView(SimpleJWTTokenRefreshView):
    """Renouvellement de jeton (CDC 7.1). Sous-classe locale, configurable.

    Audit de securite du Lot 1 (ecart bloquant B1) : ``TokenViewBase``
    (SimpleJWT) pose deja ``authentication_classes = ()`` /
    ``permission_classes = ()`` par defaut -- ce endpoint n'authentifie
    donc, en l'etat, jamais la requete via un jeton ``Bearer`` presente
    par l'appelant (contrairement a ``LoginView``/``PasswordResetRequestView``
    avant correction, qui heritaient silencieusement de
    ``DEFAULT_AUTHENTICATION_CLASSES``). Cette sous-classe rend ce choix
    **explicite** plutot que de continuer a dependre implicitement d'un
    detail interne de SimpleJWT qui pourrait changer a l'avenir -- et
    donne un point d'extension local (``apps.accounts.urls``) si une
    future tache doit y attacher une limitation de requetes dediee
    (aucune n'est ajoutee ici : contrairement a la connexion et a la
    reinitialisation, cet endpoint ne verifie aucun mot de passe, la
    surface d'abus est donc plus faible -- voir compte rendu de la tache).
    """

    authentication_classes = []
    permission_classes = []


class LoginView(APIView):
    """Connexion par email + mot de passe (CDC 4.1, 7.1). Accessible sans jeton.

    ``authentication_classes = []`` (audit de securite du Lot 1, ecart
    bloquant B1) : sans cette exclusion explicite,
    ``DEFAULT_AUTHENTICATION_CLASSES`` (``TenantJWTAuthentication``)
    s'appliquerait quand meme malgre ``permission_classes = [AllowAny]``
    -- un attaquant qui presente son propre jeton ``Bearer`` valide (le
    sien, obtenu legitimement par ailleurs) deviendrait alors un
    utilisateur authentifie aux yeux de DRF sur CET endpoint, ce qui
    desactive silencieusement ``AnonRateThrottle`` (``LoginRateThrottle``
    ne s'applique qu'aux requetes anonymes) : connexions illimitees. Cet
    endpoint n'a de toute facon jamais besoin d'authentification (CDC
    4.1 : accessible sans jeton).
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle, LoginEmailRateThrottle]

    def post(self, request):
        serializer = serializers.LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = services.authenticate_login(
                email=data["email"],
                password=data["password"],
                club_slug=data.get("club_slug") or None,
            )
        except services.AccountLockedError as exc:
            return Response(
                {
                    "code": "account_locked",
                    "detail": (
                        "Trop de tentatives. Pour protéger votre compte, la connexion "
                        "est bloquée pendant 15 minutes."
                    ),
                    "locked_until": exc.locked_until,
                },
                status=status.HTTP_423_LOCKED,
            )
        except services.InvalidCredentialsError as exc:
            # Meme forme de reponse (memes cles) que l'email corresponde ou
            # non a un compte reel (CDC 7.6) : `attempts_remaining` est
            # toujours present, avec une valeur de repli plausible
            # (equivalente a un premier echec) quand aucun compteur reel
            # n'existe -- sinon la seule presence de cette cle revelerait
            # qu'un email est inscrit, meme avec un message identique.
            attempts_remaining = (
                exc.attempts_remaining
                if exc.attempts_remaining is not None
                else services.MAX_LOGIN_ATTEMPTS - 1
            )
            payload = {
                "code": "invalid_credentials",
                "detail": "Email ou mot de passe incorrect.",
                "attempts_remaining": attempts_remaining,
            }
            return Response(payload, status=status.HTTP_401_UNAUTHORIZED)
        except services.TemporaryPasswordExpiredError:
            return Response(
                {
                    "code": "temporary_password_expired",
                    "detail": (
                        "Ce mot de passe temporaire a expiré. Faites une nouvelle "
                        "demande avec « Mot de passe oublié ? »."
                    ),
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except services.AccountDisabledError:
            return Response(
                {"code": "account_disabled", "detail": "Ce compte est désactivé. Contactez le support Vesta."},
                status=status.HTTP_403_FORBIDDEN,
            )
        except services.NoClubMembershipError:
            return Response(
                {
                    "code": "no_club_membership",
                    "detail": "Votre compte n'est rattaché à aucun club pour l'instant.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except services.ClubDisambiguationRequiredError as exc:
            return Response(
                {
                    "code": "club_disambiguation_required",
                    "detail": (
                        "Plusieurs clubs sont associés à ce compte : précisez lequel "
                        "(adresse /c/<slug>)."
                    ),
                    "clubs": [{"slug": m.club.slug, "name": m.club.name} for m in exc.candidates],
                },
                status=status.HTTP_409_CONFLICT,
            )

        from apps.clubs.profile_services import can_view_board_dashboard, default_landing_for_membership

        user = result.user
        refresh = RefreshToken.for_user(user)
        pending_terms = services.get_pending_terms_version(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": serializers.UserSummarySerializer(user).data,
                "club": _serialize_club(
                    result.membership.club if result.membership else None, request
                ),
                "must_change_password": user.must_change_password,
                "terms_acceptance_required": pending_terms is not None,
                # Destination d'arrivee calculee a partir des roles ACTIFS, a chaque
                # connexion (jamais figee dans le jeton, regle n9).
                "default_landing": default_landing_for_membership(result.membership),
                "capabilities": {"can_view_board_dashboard": can_view_board_dashboard(result.membership)},
            },
            status=status.HTTP_200_OK,
        )


class ForcedPasswordChangeView(APIView):
    """Changement de mot de passe force (CDC 4.1). Accessible avant meme CGU acceptees.

    Exclut volontairement ``HasCompletedPasswordSetup``/``HasAcceptedLatestTerms``
    (``DEFAULT_PERMISSION_CLASSES``) : c'est precisement l'endpoint qui
    permet de sortir de l'etat bloquant.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = serializers.ForcedPasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            services.change_forced_password(
                user=request.user,
                new_password=serializer.validated_data["new_password"],
                confirm_password=serializer.validated_data["confirm_password"],
            )
        except services.PasswordChangeNotForcedError as exc:
            # Audit de securite du Lot 1 (ecart bloquant B3) : ce point
            # d'acces est reserve au changement force (mot de passe
            # initial/temporaire) -- un changement volontaire depuis le
            # profil (avec l'ancien mot de passe) est un endpoint separe,
            # qui n'existe pas encore.
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Mot de passe modifié."}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Deconnexion : blacklist du jeton de renouvellement (CDC 7.1).

    Accessible meme si le mot de passe n'est pas encore change ou les CGU
    pas encore acceptees (« Seule issue secondaire : Se deconnecter »,
    comptes-connexion.md §4.2).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = serializers.LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            services.logout(user=request.user, refresh_token=serializer.validated_data["refresh"])
        except services.InvalidRefreshTokenError:
            return Response(
                {"detail": "Jeton de renouvellement invalide ou déjà invalidé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutAllDevicesView(APIView):
    """« Deconnecter tous mes appareils » (CDC 7.1), disponible depuis le profil."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        count = services.logout_all_devices(user=request.user)
        return Response({"tokens_blacklisted": count}, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    """Demande de reinitialisation depuis la page de connexion (CDC 4.1).

    ``authentication_classes = []` : meme raison que ``LoginView``
    ci-dessus (audit de securite du Lot 1, ecart bloquant B1).
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetRateThrottle, PasswordResetEmailRateThrottle]

    _GENERIC_SUCCESS_DETAIL = (
        "Si un compte existe avec cette adresse, le support Vesta vous transmettra un mot "
        "de passe temporaire. Il sera valable 48 heures."
    )

    def post(self, request):
        serializer = serializers.PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Meme reponse que l'email corresponde ou non a un compte (CDC 7.6).
        services.request_password_reset(email=serializer.validated_data["email"])

        return Response({"detail": self._GENERIC_SUCCESS_DETAIL}, status=status.HTTP_200_OK)


class SuperuserPasswordResetView(APIView):
    """Reinitialisation par le Superuser (CDC 4.1 ; 10.2 n°21).

    L'endpoint existe des cette tache ; son usage reel depuis l'espace
    Superuser (recherche d'un compte, etc.) est la tache 1.8.
    """

    permission_classes = [IsAuthenticated, IsSuperuser]

    def post(self, request):
        serializer = serializers.SuperuserPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            temp_password = services.reset_password_by_superuser(
                superuser=request.user, target_email=serializer.validated_data["email"]
            )
        except User.DoesNotExist:
            return Response(
                {"detail": "Aucun compte ne correspond à cette adresse e-mail."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Affiche une seule fois (CDC 4.1, 10.2 n°21) : jamais renvoye par
        # un autre endpoint ni journalise en clair.
        return Response({"temporary_password": temp_password}, status=status.HTTP_200_OK)


class SuperuserAccountSearchView(APIView):
    """Recherche de comptes (CDC 2.5, 4.18 : « recherche sur tous les
    comptes, identifiant, club, roles »)."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def get(self, request):
        serializer = serializers.AccountSearchQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        results = services.search_accounts(
            query=data["query"], club_id=data["club_id"], role=data["role"] or None
        )
        return Response(results, status=status.HTTP_200_OK)


class SuperuserAccountDeactivateView(APIView):
    """Desactivation d'un compte (CDC 4.18)."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def post(self, request):
        serializer = serializers.AccountDeactivateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            target_user = User.objects.get(pk=data["user_id"])
        except User.DoesNotExist:
            return Response({"detail": "Ce compte n'existe pas."}, status=status.HTTP_404_NOT_FOUND)

        try:
            services.deactivate_account(superuser=request.user, target_user=target_user, reason=data["reason"])
        except services.AccountDeactivationRefusedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Compte désactivé."}, status=status.HTTP_200_OK)


class SuperuserPendingPasswordResetsView(APIView):
    """Demandes de reinitialisation en attente (CDC 4.18)."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def get(self, request):
        pending = services.list_pending_password_reset_requests()
        return Response(
            serializers.PendingPasswordResetRequestSerializer(pending, many=True).data,
            status=status.HTTP_200_OK,
        )


class PendingTermsView(APIView):
    """Derniere version des CGU non encore acceptee par l'utilisateur courant (CDC 7.5)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        pending = services.get_pending_terms_version(request.user)
        if pending is None:
            # Littéral JSON `null` (et non un corps vide) : le client le lit comme « aucune version ».
            # (le rendu DRF d'un `None` produit un corps vide : on répond explicitement.)
            return HttpResponse(b"null", content_type="application/json", status=status.HTTP_200_OK)
        return Response(serializers.TermsVersionSerializer(pending).data, status=status.HTTP_200_OK)


class AcceptTermsView(APIView):
    """Acceptation d'une version des CGU (CDC 7.5, 10.2 n°27)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = serializers.AcceptTermsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            terms_version = TermsVersion.objects.get(
                pk=serializer.validated_data["terms_version_id"]
            )
        except TermsVersion.DoesNotExist:
            return Response(
                {"detail": "Cette version des CGU n'existe pas."}, status=status.HTTP_404_NOT_FOUND
            )

        acceptance = services.accept_terms(user=request.user, terms_version=terms_version)
        return Response(
            {"terms_version_id": acceptance.terms_version_id, "accepted_at": acceptance.accepted_at},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Mon profil -- mutations d'identite (CDC 4.1, 7.1, 7.2 ; comptes-mon-
# profil.md §4.1 ; tache 1.9, slice Lot 1). La lecture agregee du profil
# (identite + adhesion + roles + preference email) vit dans
# ``apps.clubs.views.MyProfileView`` (voir sa docstring) : ces vues-ci ne
# font que MODIFIER des champs de ``User``, propres a cette app.
# ---------------------------------------------------------------------------


class MyPersonalInfoUpdateView(APIView):
    """Onglet « Informations » (comptes-mon-profil.md §4.1).

    Pas d'override de ``permission_classes`` : les garde-fous globaux
    (``HasCompletedPasswordSetup``, ``HasAcceptedLatestTerms``, voir
    ``apps.core.permissions``) doivent s'appliquer ici (CDC 4.1, 7.5).
    """

    def patch(self, request):
        serializer = serializers.PersonalInfoUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        services.update_personal_info(
            user=request.user,
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone=data.get("phone", ""),
            birth_date=data.get("birth_date"),
            weight_kg=data.get("weight_kg"),
            height_cm=data.get("height_cm"),
        )
        return Response({"detail": "Profil mis à jour."}, status=status.HTTP_200_OK)


class MyPersonalDataExportView(APIView):
    """« Telecharger mes donnees » (CDC 7.5) : export JSON des seules
    donnees du joueur connecte. Garde-fous globaux conserves (voir
    ``MyPersonalInfoUpdateView``). Jamais de parametre designant un autre
    compte : l'utilisateur est toujours ``request.user``."""

    # Declaration explicite (CLAUDE.md §7) ; valeur identique aux garde-fous
    # globaux (comportement inchange, y compris HasUsableLicence : le droit
    # d'export pendant une suspension de licence n'est pas tranche ici).
    permission_classes = [
        IsAuthenticated,
        HasCompletedPasswordSetup,
        HasAcceptedLatestTerms,
        HasUsableLicence,
    ]

    def get(self, request):
        data = services.export_personal_data(user=request.user)
        response = Response(data, status=status.HTTP_200_OK)
        response["Content-Disposition"] = 'attachment; filename="mes-donnees-vesta.json"'
        response["Cache-Control"] = "no-store"
        return response


class MyCredentialsUpdateView(APIView):
    """Onglet « Identifiant et mot de passe » (comptes-mon-profil.md §4.1).

    Pas d'override de ``permission_classes`` : les garde-fous globaux
    (``HasCompletedPasswordSetup``, ``HasAcceptedLatestTerms``, voir
    ``apps.core.permissions``) doivent s'appliquer ici (CDC 4.1, 7.5). Le
    parcours de changement de mot de passe force passe exclusivement par
    ``ForcedPasswordChangeView``.
    """

    def patch(self, request):
        serializer = serializers.CredentialsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            services.update_credentials(
                user=request.user,
                current_password=data["current_password"],
                new_email=data["email"],
                new_password=data.get("new_password", ""),
                confirm_new_password=data.get("confirm_new_password", ""),
            )
        except services.CredentialsUpdateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Identifiants mis à jour."}, status=status.HTTP_200_OK)


class MyProfilePhotoView(APIView):
    """Onglet « Photo » (comptes-mon-profil.md §4.1).

    Pas d'override de ``permission_classes`` : les garde-fous globaux
    (``HasCompletedPasswordSetup``, ``HasAcceptedLatestTerms``, voir
    ``apps.core.permissions``) doivent s'appliquer ici (CDC 4.1, 7.5).
    """

    def patch(self, request):
        serializer = serializers.ProfilePhotoUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        services.update_profile_photo(user=request.user, photo=serializer.validated_data["photo"])
        return Response({"detail": "Photo mise à jour."}, status=status.HTTP_200_OK)

    def delete(self, request):
        services.remove_profile_photo(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
