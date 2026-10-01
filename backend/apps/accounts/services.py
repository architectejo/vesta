"""Regles metier de l'app accounts.

Sources : CDC 4.1 (compte, mot de passe initial/oublie), 7.1
(authentification), 7.5 (CGU) ; 10.2 n°21 (mot de passe temporaire), n°27
(CGU versionnees) ; docs/lot0/schema-donnees.md §3.1 (`User`), §3.6
(`TermsVersion`/`TermsAcceptance`), §13.2 (`PasswordResetRequest`) ;
docs/ecrans/comptes-connexion.md (comportements attendus par l'ecran).

Tache 1.6 : journalisation de l'acceptation des CGU (deja en place, voir
:func:`log_terms_accepted`). Tache 1.3 : authentification complete
(connexion, blocage, mot de passe oublie/temporaire, deconnexion,
desambiguisation du club actif a la connexion).
"""

from __future__ import annotations

import secrets
import string
from datetime import timedelta
from typing import Any, NamedTuple, Optional, Sequence

from django.apps import apps
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.accounts.models import PasswordResetRequest, TermsAcceptance, TermsVersion, User
from apps.core.services import log_action

__all__ = [
    "MAX_LOGIN_ATTEMPTS",
    "LOGIN_LOCKOUT_DURATION",
    "TEMP_PASSWORD_LENGTH",
    "TEMP_PASSWORD_VALIDITY",
    "AuthenticationError",
    "InvalidCredentialsError",
    "AccountLockedError",
    "AccountDisabledError",
    "TemporaryPasswordExpiredError",
    "NoClubMembershipError",
    "ClubDisambiguationRequiredError",
    "InvalidRefreshTokenError",
    "PasswordChangeNotForcedError",
    "LoginResult",
    "authenticate_login",
    "resolve_login_club",
    "change_forced_password",
    "request_password_reset",
    "reset_password_by_superuser",
    "search_accounts",
    "deactivate_account",
    "list_pending_password_reset_requests",
    "logout",
    "logout_all_devices",
    "get_pending_terms_version",
    "accept_terms",
    "TermsPublicationError",
    "publish_terms_version",
    "log_terms_accepted",
    "get_or_create_platform_user",
    "PlatformUserResult",
    "PersonalInfoError",
    "update_personal_info",
    "CredentialsUpdateError",
    "CurrentPasswordIncorrectError",
    "EmailAlreadyUsedByAnotherAccountError",
    "NewPasswordMismatchError",
    "update_credentials",
    "update_profile_photo",
    "remove_profile_photo",
    "MIN_PIN_DIGITS",
    "MAX_PIN_DIGITS",
    "MAX_PIN_ATTEMPTS",
    "PIN_LOCKOUT_DURATION",
    "PinError",
    "PinNotSetError",
    "InvalidPinFormatError",
    "PinAlreadySetError",
    "PinMismatchError",
    "PinResetPasswordIncorrectError",
    "InvalidPinError",
    "PinLockedError",
    "define_pin",
    "redefine_pin",
    "verify_pin",
    "require_valid_pin",
]


# ---------------------------------------------------------------------------
# Connexion, blocage (CDC 7.1)
# ---------------------------------------------------------------------------

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_DURATION = timedelta(minutes=15)

# Mot de passe temporaire (10.2 n°21 ; schema §13.2).
TEMP_PASSWORD_LENGTH = 8
TEMP_PASSWORD_VALIDITY = timedelta(hours=48)
_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits


class AuthenticationError(Exception):
    """Base des erreurs d'authentification (CDC 7.1). Vues : traduction en reponse HTTP."""


class InvalidCredentialsError(AuthenticationError):
    """Email inconnu ou mot de passe incorrect.

    Meme message quel que soit le cas (CDC 7.6, point ouvert
    comptes-connexion.md §7 : ne jamais reveler quelles adresses sont
    inscrites). ``attempts_remaining`` reste ``None`` quand l'email est
    inconnu (aucun compteur n'existe pour un compte qui n'existe pas).
    """

    def __init__(self, attempts_remaining: Optional[int] = None):
        self.attempts_remaining = attempts_remaining
        super().__init__("Email ou mot de passe incorrect.")


class AccountLockedError(AuthenticationError):
    """Blocage de 15 minutes apres 5 echecs (CDC 7.1)."""

    def __init__(self, locked_until):
        self.locked_until = locked_until
        super().__init__("Compte bloque temporairement apres 5 echecs de connexion.")


class AccountDisabledError(AuthenticationError):
    """Compte desactive par le support Vesta (CDC 4.18). Affiche seulement si le mot de passe est juste."""


class TemporaryPasswordExpiredError(AuthenticationError):
    """Mot de passe temporaire expire (48h, 10.2 n°21)."""


class NoClubMembershipError(AuthenticationError):
    """Aucune adhesion active : « Votre compte n'est rattache a aucun club pour l'instant. »

    Point ouvert applique par defaut (proposition de comptes-connexion.md
    §7) : aucune session n'est ouverte dans ce cas.
    """


class ClubDisambiguationRequiredError(AuthenticationError):
    """Plusieurs adhesions actives simultanees : le club actif est ambigu sans slug.

    ``candidates`` : liste des ``Membership`` actifs concernes (pour que
    la vue puisse lister les clubs possibles a la personne).
    """

    def __init__(self, candidates: Sequence):
        self.candidates = list(candidates)
        super().__init__(
            "Plusieurs clubs sont associes a ce compte : precisez lequel (adresse /c/<slug>)."
        )


class InvalidRefreshTokenError(AuthenticationError):
    """Jeton de renouvellement invalide, deja utilise ou deja mis en liste noire."""


class PasswordChangeNotForcedError(AuthenticationError):
    """``change_forced_password`` appele hors du cas de changement force.

    Audit de securite du Lot 1 (ecart bloquant B3) :
    ``change_forced_password`` ne verifiait jamais
    ``user.must_change_password`` -- n'importe quel utilisateur
    authentifie (mot de passe deja pose, CGU deja acceptees) pouvait
    changer son mot de passe sans jamais fournir l'ancien, simplement en
    appelant cet endpoint. Ce point d'acces reste reserve au parcours
    « mot de passe initial ou temporaire » (CDC 4.1, qui ne demande
    jamais l'ancien mot de passe dans ce cas precis) : un futur
    changement volontaire depuis le profil (avec verification explicite
    de l'ancien mot de passe) est un point d'acces separe, hors
    perimetre de cette correction.
    """


class LoginResult(NamedTuple):
    user: User
    membership: Optional[object]  # apps.clubs.models.Membership ; None pour un Superuser.


def _resolve_active_memberships(user) -> list:
    """Adhesions actives de ``user``, tous clubs confondus (usage plateforme).

    ``all_objects`` : la connexion determine precisement le club actif --
    aucun n'existe encore dans le contexte courant a cet instant (meme
    logique que ``apps.core.services.resolve_active_membership``).
    """

    Membership = apps.get_model("clubs", "Membership")
    return list(
        Membership.all_objects.select_related("club").filter(
            user=user, status=Membership.Status.ACTIVE
        )
    )


def resolve_login_club(user, club_slug: Optional[str] = None):
    """Determine l'adhesion active a utiliser pour cette connexion (CLAUDE.md regle n9).

    CDC 7.3 / comptes-connexion.md §2 : l'adresse ``/c/<slug>`` n'est
    qu'une presentation, jamais une contrainte d'acces -- si une seule
    adhesion active existe, elle est renvoyee telle quelle, **meme si le
    slug transmis ne correspond pas** (« aucune erreur n'est affichee
    dans ce cas »). Le slug ne sert qu'a desambiguiser le cas rare de
    plusieurs adhesions actives simultanees.

    Leve :class:`NoClubMembershipError` si aucune adhesion active, ou
    :class:`ClubDisambiguationRequiredError` si plusieurs existent sans
    qu'un slug valide ne permette de choisir.
    """

    memberships = _resolve_active_memberships(user)

    if not memberships:
        raise NoClubMembershipError()

    if len(memberships) == 1:
        return memberships[0]

    if club_slug:
        match = next((m for m in memberships if m.club.slug == club_slug), None)
        if match is not None:
            return match

    raise ClubDisambiguationRequiredError(memberships)


def authenticate_login(*, email: str, password: str, club_slug: Optional[str] = None) -> LoginResult:
    """Verifie les identifiants et determine le club actif de la connexion (CDC 4.1, 7.1).

    Leve une sous-classe d':class:`AuthenticationError` pour chaque cas
    d'echec documente par ``docs/ecrans/comptes-connexion.md`` §5.2.
    Aucune exception n'est levee en cas de succes : la fonction renvoie
    alors un :class:`LoginResult` ; c'est a l'appelant (vue) d'emettre les
    jetons JWT -- cette fonction ne fait que la verification metier.
    """

    normalized_email = (email or "").strip().lower()
    user = User.objects.filter(email=normalized_email).first()

    if user is None:
        # Meme cout de calcul qu'un compte reel (CDC 7.6) : sans cet appel,
        # l'absence de hachage bcrypt/PBKDF2 rendrait cette branche
        # mesurablement plus rapide qu'un mauvais mot de passe sur un
        # email connu, ce qui permettrait d'enumerer les comptes par le
        # temps de reponse meme avec un message et un corps de reponse
        # identiques. Meme mecanisme que
        # ``django.contrib.auth.backends.ModelBackend`` (``UserModel().set_password(password)``) ;
        # le hachage est jete, jamais sauvegarde.
        User().set_password(password)
        # Aucun acteur reel : impossible (et non souhaitable, CDC 5.1) de
        # journaliser une tentative contre un compte qui n'existe pas.
        raise InvalidCredentialsError(attempts_remaining=None)

    now = timezone.now()

    if user.login_locked_until and user.login_locked_until > now:
        raise AccountLockedError(locked_until=user.login_locked_until)

    if not user.check_password(password):
        # Incrementation atomique au niveau de la ligne (``UPDATE ... SET
        # failed_login_attempts = failed_login_attempts + 1``), plutot
        # qu'une lecture-modification-ecriture en Python
        # (``user.failed_login_attempts += 1``) : sous MySQL/MariaDB en
        # production, deux connexions concurrentes sur le meme compte ne
        # peuvent plus se marcher dessus et perdre une ecriture (CDC 7.1).
        # ``refresh_from_db`` relit ensuite la valeur reelle en base --
        # necessaire pour connaitre le compteur exact (seuil de blocage,
        # ``attempts_remaining``) puisque l'expression F() ci-dessus n'est
        # pas un entier Python.
        user.failed_login_attempts = F("failed_login_attempts") + 1
        user.save(update_fields=["failed_login_attempts"])
        user.refresh_from_db(fields=["failed_login_attempts"])

        if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            before = {"failed_login_attempts": user.failed_login_attempts - 1, "login_locked_until": None}
            user.login_locked_until = now + LOGIN_LOCKOUT_DURATION
            user.save(update_fields=["login_locked_until"])
            log_action(
                actor=user,
                club=None,
                action_type="auth.account_locked",
                obj=user,
                before=before,
                after={
                    "failed_login_attempts": user.failed_login_attempts,
                    "login_locked_until": user.login_locked_until,
                },
            )
            raise AccountLockedError(locked_until=user.login_locked_until)

        log_action(
            actor=user,
            club=None,
            action_type="auth.login_failed",
            obj=user,
            after={"failed_login_attempts": user.failed_login_attempts},
        )
        raise InvalidCredentialsError(attempts_remaining=MAX_LOGIN_ATTEMPTS - user.failed_login_attempts)

    # Mot de passe correct au-dela de ce point (CDC 7.1 : les cas suivants
    # ne sont affiches que si le mot de passe est juste).
    if not user.is_active:
        raise AccountDisabledError()

    if user.temp_password_expires_at and now > user.temp_password_expires_at:
        raise TemporaryPasswordExpiredError()

    if user.failed_login_attempts or user.login_locked_until:
        user.failed_login_attempts = 0
        user.login_locked_until = None
        user.save(update_fields=["failed_login_attempts", "login_locked_until"])

    membership = None
    if not user.is_superuser:
        try:
            membership = resolve_login_club(user, club_slug=club_slug)
        except NoClubMembershipError:
            log_action(
                actor=user,
                club=None,
                action_type="auth.login_denied_no_club",
                obj=user,
            )
            raise
        except ClubDisambiguationRequiredError as exc:
            log_action(
                actor=user,
                club=None,
                action_type="auth.login_denied_ambiguous_club",
                obj=user,
                after={"candidate_club_ids": [m.club_id for m in exc.candidates]},
            )
            raise

    user.last_login = now
    user.save(update_fields=["last_login"])

    log_action(
        actor=user,
        club=membership.club if membership else None,
        action_type="auth.login_succeeded",
        obj=user,
        after={"club_id": membership.club_id if membership else None},
    )

    return LoginResult(user=user, membership=membership)


# ---------------------------------------------------------------------------
# Changement de mot de passe force (CDC 4.1, 7.1)
# ---------------------------------------------------------------------------


def change_forced_password(*, user: User, new_password: str, confirm_password: str) -> None:
    """Change le mot de passe et leve le blocage ``must_change_password`` (CDC 4.1).

    Leve ``django.core.exceptions.ValidationError`` (liste de messages en
    francais) si l'une des regles echoue. Aucune de ces regles ne
    necessite le mot de passe actuel : coherent avec la modale « Changez
    votre mot de passe » (comptes-connexion.md §4.2), qui ne le demande
    pas (le joueur vient de s'authentifier avec) -- **mais** reserve pour
    cette meme raison au seul cas force (``user.must_change_password``) :
    voir :class:`PasswordChangeNotForcedError` (audit de securite du Lot
    1, ecart bloquant B3).

    Revoque egalement, en cas de succes, tous les jetons de
    renouvellement existants de ``user`` (meme logique que
    :func:`logout_all_devices`) : un jeton d'acces vole (15 min) ne doit
    pas survivre au changement de mot de passe qu'il vient de declencher
    -- l'attaquant est expulse au meme titre qu'un appareil legitime
    reconnecte ailleurs (audit de securite du Lot 1, ecart bloquant B3).
    """

    if not user.must_change_password:
        log_action(
            actor=user,
            club=None,
            action_type="auth.forced_password_change_denied",
            obj=user,
            after={"must_change_password": user.must_change_password},
        )
        raise PasswordChangeNotForcedError(
            "Ce point d'acces est reserve au changement de mot de passe "
            "force (mot de passe initial ou temporaire, CDC 4.1)."
        )

    errors: list[str] = []

    if new_password != confirm_password:
        errors.append("Les deux mots de passe ne correspondent pas.")

    if new_password and user.email and new_password == user.email:
        errors.append("Le mot de passe doit etre different de votre email.")

    if new_password and user.password and user.check_password(new_password):
        # Couvre a la fois « different de l'email » (mot de passe
        # initial) et « different du mot de passe temporaire » (10.2
        # n°21, regle prudente appliquee a titre provisoire par
        # comptes-connexion.md §7).
        errors.append("Choisissez un mot de passe different de votre mot de passe actuel.")

    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        errors.extend(exc.messages)

    if errors:
        raise ValidationError(errors)

    before = {
        "must_change_password": user.must_change_password,
        "had_temp_password": user.temp_password_expires_at is not None,
    }

    user.set_password(new_password)
    user.must_change_password = False
    user.temp_password_expires_at = None
    user.save(update_fields=["password", "must_change_password", "temp_password_expires_at"])

    tokens_revoked = _blacklist_all_outstanding_tokens(user)

    log_action(
        actor=user,
        club=None,
        action_type="auth.password_changed",
        obj=user,
        before=before,
        after={"must_change_password": False, "tokens_revoked": tokens_revoked},
    )


# ---------------------------------------------------------------------------
# Mot de passe oublie / reinitialisation (CDC 4.1 ; 10.2 n°21 ; schema §13.2)
# ---------------------------------------------------------------------------


def request_password_reset(*, email: str) -> None:
    """Enregistre une demande de reinitialisation (CDC 4.1).

    Ne revele jamais si l'email correspond a un compte (CDC 7.6) :
    l'appelant (vue) renvoie systematiquement le meme message de succes,
    que cette fonction ait ou non cree une ``PasswordResetRequest``.
    Aucun email n'est envoye ici (CLAUDE.md : pas de tache longue dans
    une requete) -- l'envoi reel est une commande cron (tache 1.7).
    """

    normalized_email = (email or "").strip().lower()
    user = User.objects.filter(email=normalized_email).first()
    if user is None:
        return

    reset_request = PasswordResetRequest.objects.create(user=user, requested_at=timezone.now())
    log_action(
        actor=user,
        club=None,
        action_type="accounts.password_reset.requested",
        obj=reset_request,
        after={"requested_at": reset_request.requested_at},
    )


def _generate_temp_password(length: int = TEMP_PASSWORD_LENGTH) -> str:
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))


def reset_password_by_superuser(*, superuser: User, target_email: str) -> str:
    """Genere un mot de passe temporaire pour ``target_email`` (10.2 n°21 ; schema §13.2).

    Renvoie le mot de passe **en clair** : c'est la seule fois ou il est
    disponible ailleurs que dans la memoire de cette fonction -- il n'est
    jamais stocke en clair (seul son hachage l'est, comme n'importe quel
    mot de passe) ni jamais journalise. L'appelant (vue) doit le
    retourner **une seule fois** dans la reponse de l'API, jamais dans
    une reponse ulterieure.
    """

    if not getattr(superuser, "is_superuser", False):
        raise PermissionError(
            "Seul un Superuser peut reinitialiser le mot de passe d'un compte (CDC 4.1, 4.18)."
        )

    normalized_email = (target_email or "").strip().lower()
    target_user = User.objects.filter(email=normalized_email).first()
    if target_user is None:
        raise User.DoesNotExist("Aucun compte ne correspond a cette adresse email.")

    temp_password = _generate_temp_password()
    now = timezone.now()

    target_user.set_password(temp_password)
    target_user.must_change_password = True
    target_user.temp_password_expires_at = now + TEMP_PASSWORD_VALIDITY
    target_user.failed_login_attempts = 0
    target_user.login_locked_until = None
    target_user.save(
        update_fields=[
            "password",
            "must_change_password",
            "temp_password_expires_at",
            "failed_login_attempts",
            "login_locked_until",
        ]
    )

    # Revoque tous les jetons de renouvellement existants (audit de
    # securite du Lot 1, ecart bloquant B3) : sans cela, un attaquant deja
    # connecte avec un jeton vole n'est jamais expulse par une
    # reinitialisation forcee par le Superuser -- seul le mot de passe
    # changeait, pas les sessions actives.
    tokens_revoked = _blacklist_all_outstanding_tokens(target_user)

    pending_request = (
        PasswordResetRequest.objects.filter(
            user=target_user, status=PasswordResetRequest.Status.PENDING
        )
        .order_by("-requested_at")
        .first()
    )
    if pending_request is not None:
        before_request = {"status": pending_request.status, "handled_by_id": pending_request.handled_by_id}
        pending_request.status = PasswordResetRequest.Status.DONE
        pending_request.handled_by = superuser
        pending_request.handled_at = now
        pending_request.save(update_fields=["status", "handled_by", "handled_at"])
        log_action(
            actor=superuser,
            club=None,
            action_type="accounts.password_reset.handled",
            obj=pending_request,
            before=before_request,
            after={"status": pending_request.status, "handled_by_id": pending_request.handled_by_id},
        )

    log_action(
        actor=superuser,
        club=None,
        action_type="accounts.password_reset.completed",
        obj=target_user,
        after={
            "must_change_password": True,
            "temp_password_expires_at": target_user.temp_password_expires_at,
            "tokens_revoked": tokens_revoked,
        },
    )

    return temp_password


# ---------------------------------------------------------------------------
# Comptes -- espace Superuser (CDC 2.5, 4.18 ; schema §13.3 ; tache 1.8)
# ---------------------------------------------------------------------------


def search_accounts(*, query: str = "", club_id: Optional[int] = None, role: Optional[str] = None) -> list[dict]:
    """Recherche de comptes pour l'espace Superuser (CDC 2.5, 4.18 : «
    recherche sur tous les comptes, identifiant, club, roles »).

    ``query`` filtre sur l'email (CDC 4.1 : « l'email est l'identifiant »),
    et par confort de recherche egalement sur le prenom/nom (decision par
    defaut, non explicitement demandee par le CDC pour ce champ precis --
    a confirmer par le client). ``club_id``/``role`` filtrent sur les
    adhesions actuelles, **tous statuts confondus** (y compris `departed`) :
    decision par defaut appliquee ici -- le Superuser doit pouvoir
    retrouver un compte meme si son adhesion n'est plus active (ex. pour
    une reinitialisation de mot de passe suite a un depart).

    Renvoie une liste de dictionnaires plutot qu'un queryset : agrege des
    informations de plusieurs apps (`User`, `Membership`, `MembershipRole`)
    sans creer de dependance de modele croisee sur `apps.accounts.models`.
    Utilise volontairement `apps.get_model` (import tardif via le registre
    des apps, meme technique que `resolve_active_membership` ci-dessus) :
    `apps.clubs` est charge apres `apps.accounts` (voir `LOCAL_APPS`,
    `config.settings.base`).
    """

    Membership = apps.get_model("clubs", "Membership")
    MembershipRole = apps.get_model("clubs", "MembershipRole")

    users_qs = User.objects.all().order_by("email")

    normalized_query = (query or "").strip()
    if normalized_query:
        users_qs = users_qs.filter(
            Q(email__icontains=normalized_query)
            | Q(first_name__icontains=normalized_query)
            | Q(last_name__icontains=normalized_query)
        )

    if club_id is not None or role:
        membership_filter = Q()
        if club_id is not None:
            membership_filter &= Q(memberships__club_id=club_id)
        if role:
            membership_filter &= Q(
                memberships__roles__role=role, memberships__roles__revoked_at__isnull=True
            )
        users_qs = users_qs.filter(membership_filter).distinct()

    results: list[dict] = []
    for user in users_qs:
        memberships = Membership.all_objects.select_related("club").filter(user=user)
        clubs_payload = []
        for membership in memberships:
            roles = list(
                MembershipRole.all_objects.filter(
                    membership=membership, revoked_at__isnull=True
                ).values_list("role", flat=True)
            )
            clubs_payload.append(
                {
                    "club_id": membership.club_id,
                    "club_name": membership.club.name,
                    "membership_status": membership.status,
                    "roles": roles,
                }
            )
        results.append(
            {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "clubs": clubs_payload,
            }
        )

    return results


def deactivate_account(*, superuser: User, target_user: User, reason: str = "") -> User:
    """Desactive un compte (CDC 4.18 : « desactivation d'un compte »).

    `User.is_active=False` (deja existant, tache 1.2) bloque immediatement
    toute nouvelle connexion (`authenticate_login` leve
    `AccountDisabledError` une fois le mot de passe verifie correct, CDC
    7.1) ; revoque en plus tous les jetons de renouvellement existants
    (meme principe que `reset_password_by_superuser`/
    `change_forced_password` : un compte desactive ne doit pas continuer a
    repondre avec un jeton d'acces deja emis).

    Idempotent : desactiver un compte deja desactive ne cree pas de
    deuxieme entree de journal (rien n'a reellement change).

    ``reason`` est recommande mais pas obligatoire (le CDC ne l'exige pas
    explicitement pour cette action precise, a la difference de la
    resiliation d'une licence -- 10.2 n26 -- ou de la suspension d'une
    licence : decision par defaut, a confirmer par le client).
    """

    if not getattr(superuser, "is_superuser", False):
        raise PermissionError("Seul un Superuser peut desactiver un compte (CDC 4.18).")

    if not target_user.is_active:
        return target_user

    before = {"is_active": True}
    target_user.is_active = False
    target_user.save(update_fields=["is_active"])

    tokens_revoked = _blacklist_all_outstanding_tokens(target_user)

    log_action(
        actor=superuser,
        club=None,
        action_type="accounts.account.deactivated",
        obj=target_user,
        before=before,
        after={"is_active": False, "reason": reason or "", "tokens_revoked": tokens_revoked},
    )
    return target_user


def list_pending_password_reset_requests():
    """Demandes de reinitialisation en attente de traitement (CDC 4.18 :
    « reinitialisation du mot de passe sur demande »).

    Simple requete de lecture (pas de regle metier a proprement parler) :
    fournie ici plutot que directement dans la vue pour que
    `apps.accounts.views` n'importe jamais `PasswordResetRequest`
    directement pour cet usage, coherent avec le reste du module.
    """

    return (
        PasswordResetRequest.objects.filter(status=PasswordResetRequest.Status.PENDING)
        .select_related("user")
        .order_by("-requested_at")
    )


# ---------------------------------------------------------------------------
# Deconnexion (CDC 7.1 : blacklist du jeton de renouvellement / tous les appareils)
# ---------------------------------------------------------------------------


def logout(*, user: User, refresh_token: str) -> None:
    """Blackliste le jeton de renouvellement fourni (CDC 7.1)."""

    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import RefreshToken

    try:
        token = RefreshToken(refresh_token)
    except TokenError as exc:
        raise InvalidRefreshTokenError(str(exc)) from exc

    token.blacklist()
    log_action(actor=user, club=None, action_type="auth.logout", obj=user)


def _blacklist_all_outstanding_tokens(user: User) -> int:
    """Blackliste tous les jetons de renouvellement actifs de ``user``.

    Fonction interne partagee, sans journalisation propre : chaque
    appelant journalise a sa maniere (voir :func:`logout_all_devices` --
    une entree dediee -- et :func:`change_forced_password` /
    :func:`reset_password_by_superuser` -- le compte revoque est ajoute
    a l'entree ``after`` deja ecrite pour l'action principale, audit de
    securite du Lot 1, ecart bloquant B3 : pas de nouvelle entree
    separee pour une simple consequence du changement/de la
    reinitialisation).
    """

    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    outstanding_tokens = OutstandingToken.objects.filter(user=user)
    blacklisted_count = 0
    for token in outstanding_tokens:
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        if created:
            blacklisted_count += 1
    return blacklisted_count


def logout_all_devices(*, user: User) -> int:
    """Blackliste tous les jetons de renouvellement actifs de ``user`` (CDC 7.1).

    « Deconnecter tous mes appareils », disponible depuis le profil.
    """

    blacklisted_count = _blacklist_all_outstanding_tokens(user)

    log_action(
        actor=user,
        club=None,
        action_type="auth.logout_all_devices",
        obj=user,
        after={"tokens_blacklisted": blacklisted_count},
    )
    return blacklisted_count


# ---------------------------------------------------------------------------
# Code PIN (CDC 7.2) : mecanisme generique de securite de compte
# ---------------------------------------------------------------------------
#
# Reutilisable tel quel par n'importe quelle app pour n'importe quelle
# action sensible (CDC 7.2 : validation d'un paiement ou d'une depense --
# `finance-engine` --, derogation, signature du parrain -- tache 1.4b,
# juste apres celle-ci --, signature d'un PV, annulation d'un paiement, y
# compris l'annulation d'une adhesion avec remboursement apres un refus de
# parrain, 10.2 n°36). Construit une seule fois ici, exactement comme
# `apps.core.roles` a ete construit en tache 1.5 pour les roles -- mais a
# dessein dans `apps.accounts.services` (et non `apps.core`) : le PIN est
# un champ du modele `User` (`pin_hash`/`pin_failed_attempts`/
# `pin_locked_until`, tache 1.2), propre a cette app, au meme titre que le
# mot de passe (`change_forced_password`, `reset_password_by_superuser`
# ci-dessus) -- pas un mecanisme transverse de multi-tenant/permissions
# comme les roles. N'importe quelle autre app l'importe simplement :
#
#     from apps.accounts.services import require_valid_pin, PinError
#
#     try:
#         require_valid_pin(user=request.user, pin=pin)
#     except PinError as exc:
#         ...  # traduire chaque sous-classe en reponse HTTP/message clair
#
# Deux compteurs INDEPENDANTS a ne jamais confondre (audit de securite du
# Lot 1, tache 1.3t) : `pin_failed_attempts`/`pin_locked_until` (ici) ne
# sont jamais lus ni ecrits par `authenticate_login`/`failed_login_attempts`/
# `login_locked_until` (connexion, CDC 7.1) -- deux mecanismes de blocage
# distincts sur deux actions distinctes.

MIN_PIN_DIGITS = 4
MAX_PIN_DIGITS = 6
MAX_PIN_ATTEMPTS = 3
PIN_LOCKOUT_DURATION = timedelta(minutes=30)


class PinError(Exception):
    """Base commune de toutes les erreurs liees au code PIN (CDC 7.2).

    Permet a un appelant qui ne distingue pas les cas de capturer large
    (``except PinError``) ; les sous-classes ci-dessous permettent en
    revanche a un appelant plus precis (une vue DRF, par exemple) de
    traduire chaque cas en un message francais clair distinct
    (CLAUDE.md chapitre 3, point 4 de la tache).
    """


class PinNotSetError(PinError):
    """Le joueur n'a jamais defini de code PIN (CDC 7.2 : « defini par le
    joueur a sa premiere action sensible »). Distinct d'un PIN incorrect :
    il n'y a ici rien a comparer -- l'appelant doit d'abord proposer la
    modale de definition du PIN (:func:`define_pin`) avant de rejouer
    l'action sensible interrompue.
    """

    def __init__(self):
        super().__init__("Vous devez definir votre code PIN avant de continuer.")


class InvalidPinFormatError(PinError):
    """Le PIN propose n'est pas une suite de 4 a 6 chiffres (CDC 7.2)."""

    def __init__(self):
        super().__init__(
            f"Le code PIN doit comporter {MIN_PIN_DIGITS} a {MAX_PIN_DIGITS} chiffres."
        )


class PinAlreadySetError(PinError):
    """:func:`define_pin` appele alors qu'un PIN existe deja pour ce compte.

    La premiere definition (:func:`define_pin`) et la redefinition « code
    oublie » (:func:`redefine_pin`, qui exige le mot de passe) sont deux
    chemins distincts du CDC 7.2 -- ne jamais les fusionner : le premier
    ne demande rien d'autre que le nouveau PIN (le joueur vient de
    s'authentifier normalement), le second doit revalider l'identite.
    """

    def __init__(self):
        super().__init__(
            "Un code PIN est deja defini pour ce compte : utilisez la "
            "redefinition (code oublie) pour le changer."
        )


class PinMismatchError(PinError):
    """Les deux saisies du PIN (nouveau + confirmation) ne correspondent pas."""

    def __init__(self):
        super().__init__("Les deux codes PIN ne correspondent pas.")


class PinResetPasswordIncorrectError(PinError):
    """Mot de passe incorrect lors d'une redefinition de PIN oublie (CDC 7.2)."""

    def __init__(self):
        super().__init__("Mot de passe incorrect : le code PIN n'a pas ete redefini.")


class InvalidPinError(PinError):
    """Code PIN incorrect (CDC 7.2). ``attempts_remaining`` avant blocage
    (identique dans l'esprit a ``InvalidCredentialsError.attempts_remaining``
    ci-dessus pour la connexion)."""

    def __init__(self, attempts_remaining: int):
        self.attempts_remaining = attempts_remaining
        super().__init__("Code PIN incorrect.")


class PinLockedError(PinError):
    """Blocage de 30 minutes apres 3 codes errones (CDC 7.2)."""

    def __init__(self, locked_until):
        self.locked_until = locked_until
        super().__init__("Code PIN bloque temporairement apres 3 echecs.")


def _validate_pin_format(pin: str) -> None:
    if not isinstance(pin, str) or not pin.isascii() or not pin.isdigit():
        raise InvalidPinFormatError()
    if not (MIN_PIN_DIGITS <= len(pin) <= MAX_PIN_DIGITS):
        raise InvalidPinFormatError()


def define_pin(*, user: User, pin: str, confirm_pin: str) -> None:
    """Definit le code PIN d'un joueur a sa toute premiere action sensible
    (CDC 7.2). Reserve au cas ou aucun PIN n'existe encore -- leve
    :class:`PinAlreadySetError` sinon ; toute redefinition ulterieure passe
    par :func:`redefine_pin` (« code oublie »).

    Hache le PIN avec le hasher de mot de passe par defaut de Django
    (``django.contrib.auth.hashers.make_password``/``check_password`` --
    fonctions generiques, independantes du champ ``User.password``, donc
    utilisables ici sur ``User.pin_hash`` sans toucher au mot de passe de
    connexion) plutot qu'un hachage rapide dedie : l'espace des valeurs
    possibles d'un PIN a 4-6 chiffres est minuscule (10 000 a 1 000 000
    combinaisons) -- un hachage deliberement LENT (PBKDF2/Argon2 selon
    ``settings.PASSWORD_HASHERS``) est ici une protection essentielle
    contre une attaque hors ligne si ``pin_hash`` venait a fuiter, alors
    qu'un hachage rapide rendrait cet espace trivialement exhaustif.
    """

    if user.pin_hash:
        raise PinAlreadySetError()

    _validate_pin_format(pin)
    if pin != confirm_pin:
        raise PinMismatchError()

    user.pin_hash = make_password(pin)
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    user.save(update_fields=["pin_hash", "pin_failed_attempts", "pin_locked_until"])

    log_action(
        actor=user,
        club=None,
        action_type="accounts.pin.defined",
        obj=user,
        before={"pin_defined": False},
        after={"pin_defined": True},
    )


def redefine_pin(*, user: User, password: str, new_pin: str, confirm_new_pin: str) -> None:
    """Redefinit le code PIN apres un « code PIN oublie » (CDC 7.2 :
    « redefinition apres saisie du mot de passe »).

    Ne verifie jamais l'ancien PIN (par definition inconnu/oublie de
    l'appelant) : verifie a la place le mot de passe de connexion, comme
    le CDC le demande explicitement. Utilisable aussi bien si un PIN
    existait deja que si aucun n'a jamais ete defini -- ce chemin n'est
    pas reserve au seul cas « j'ai oublie mon PIN », un joueur peut tout
    aussi bien s'en servir pour definir son PIN pour la premiere fois s'il
    prefere reverifier son mot de passe au passage.

    Reinitialise systematiquement ``pin_failed_attempts``/
    ``pin_locked_until`` (une redefinition reussie leve tout blocage en
    cours : le joueur vient de reprouver son identite par le mot de
    passe, CDC 7.2).
    """

    if not user.check_password(password):
        raise PinResetPasswordIncorrectError()

    _validate_pin_format(new_pin)
    if new_pin != confirm_new_pin:
        raise PinMismatchError()

    before = {"pin_defined": bool(user.pin_hash)}

    user.pin_hash = make_password(new_pin)
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    user.save(update_fields=["pin_hash", "pin_failed_attempts", "pin_locked_until"])

    log_action(
        actor=user,
        club=None,
        action_type="accounts.pin.reset",
        obj=user,
        before=before,
        after={"pin_defined": True},
    )


def verify_pin(*, user: User, pin: str) -> bool:
    """Verifie le code PIN de ``user`` (CDC 7.2). Fonction generique de bas
    niveau, reutilisable par n'importe quelle app -- voir
    :func:`require_valid_pin` pour le point d'entree recommande a la
    plupart des appelants (leve des exceptions plutot qu'un simple
    booleen).

    Effets de bord, MEME PATTERN que ``authenticate_login``/CDC 7.1 -- y
    compris la correction de la race condition sur l'incrementation
    atomique apportee en tache 1.3t (``F()`` plutot qu'une lecture-
    modification-ecriture Python) -- volontairement reproduit a
    l'identique ici plutot que reinvente, mais sur un compteur totalement
    INDEPENDANT (``pin_failed_attempts``/``pin_locked_until`` != ``failed
    _login_attempts``/``login_locked_until``) :

    - leve :class:`PinNotSetError` si ``user.pin_hash`` est vide -- ce
      n'est pas "un PIN incorrect", rien n'existe encore a comparer ;
    - leve :class:`PinLockedError` si un blocage de 30 minutes est deja en
      cours -- verifie AVANT toute comparaison, exactement comme
      ``AccountLockedError`` est leve par ``authenticate_login`` avant
      toute comparaison du mot de passe ;
    - incremente ``pin_failed_attempts`` de facon atomique sur un code
      errone ; au 3e echec consecutif, pose ``pin_locked_until`` (30
      minutes) et leve :class:`PinLockedError` pour CETTE tentative aussi
      (encore une fois, meme pattern que ``authenticate_login``, qui leve
      ``AccountLockedError`` -- pas ``InvalidCredentialsError`` -- sur le
      5e echec) ;
    - reinitialise le compteur a 0 sur succes.

    Ne renvoie ``True``/``False`` que pour departager un code
    effectivement compare : ``True`` s'il est correct, ``False`` s'il est
    incorrect mais n'atteint pas encore le seuil de blocage.

    Ne journalise jamais le PIN lui-meme, ni en clair ni sous forme de
    hachage (CLAUDE.md regle n6 ; CDC 5.1) : uniquement le compteur et
    l'horodatage de blocage, comme ``authenticate_login`` le fait deja
    pour le mot de passe.
    """

    if not user.pin_hash:
        raise PinNotSetError()

    now = timezone.now()
    if user.pin_locked_until and user.pin_locked_until > now:
        raise PinLockedError(locked_until=user.pin_locked_until)

    if check_password(pin, user.pin_hash):
        if user.pin_failed_attempts or user.pin_locked_until:
            user.pin_failed_attempts = 0
            user.pin_locked_until = None
            user.save(update_fields=["pin_failed_attempts", "pin_locked_until"])
        return True

    # Incrementation atomique au niveau de la ligne (voir
    # ``authenticate_login`` ci-dessus pour la justification complete,
    # tache 1.3t) : deux verifications concurrentes du meme PIN ne peuvent
    # pas se marcher dessus et perdre un echec sous MySQL/MariaDB.
    user.pin_failed_attempts = F("pin_failed_attempts") + 1
    user.save(update_fields=["pin_failed_attempts"])
    user.refresh_from_db(fields=["pin_failed_attempts"])

    if user.pin_failed_attempts >= MAX_PIN_ATTEMPTS:
        before = {"pin_failed_attempts": user.pin_failed_attempts - 1, "pin_locked_until": None}
        user.pin_locked_until = now + PIN_LOCKOUT_DURATION
        user.save(update_fields=["pin_locked_until"])
        log_action(
            actor=user,
            club=None,
            action_type="accounts.pin.locked",
            obj=user,
            before=before,
            after={
                "pin_failed_attempts": user.pin_failed_attempts,
                "pin_locked_until": user.pin_locked_until,
            },
        )
        raise PinLockedError(locked_until=user.pin_locked_until)

    log_action(
        actor=user,
        club=None,
        action_type="accounts.pin.verification_failed",
        obj=user,
        after={"pin_failed_attempts": user.pin_failed_attempts},
    )
    return False


def require_valid_pin(*, user: User, pin: str) -> None:
    """Point d'entree RECOMMANDE pour exiger un PIN valide avant de
    poursuivre une action sensible (CDC 7.2 ; CLAUDE.md regle n7). A
    importer ainsi par tout module hors ``accounts`` (signature du
    parrain -- tache 1.4b --, validation d'un paiement/depense par
    `finance-engine`, derogation, signature de PV, annulation...) :

        from apps.accounts.services import (
            require_valid_pin,
            PinError,           # base -- capture large, si besoin
            PinNotSetError,
            InvalidPinError,
            PinLockedError,
        )

        require_valid_pin(user=request.user, pin=pin)
        # Aucune exception levee => PIN valide, l'action peut se
        # poursuivre. Chaque sous-classe de PinError ci-dessus porte un
        # message francais clair (CLAUDE.md chapitre 3) ; a l'appelant
        # (vue) de la traduire en reponse HTTP adaptee.

    Ne renvoie rien en cas de succes (meme contrat que
    ``authenticate_login`` pour le mot de passe : "aucune exception =
    valide"). Leve sinon :

    - :class:`PinNotSetError` si le joueur n'a jamais defini de PIN ;
    - :class:`InvalidPinError` (``attempts_remaining``) si le PIN est
      incorrect mais que le seuil de blocage n'est pas encore atteint ;
    - :class:`PinLockedError` (``locked_until``) si le blocage de 30
      minutes est en cours (deja actif, ou qui vient de se declencher a
      cette tentative).
    """

    if verify_pin(user=user, pin=pin):
        return

    raise InvalidPinError(attempts_remaining=MAX_PIN_ATTEMPTS - user.pin_failed_attempts)


# ---------------------------------------------------------------------------
# CGU versionnees (CDC 7.5 ; 10.2 n°27)
# ---------------------------------------------------------------------------


def get_pending_terms_version(user: User) -> Optional[TermsVersion]:
    """Derniere version des CGU non encore acceptee par ``user`` (ou ``None``)."""

    latest = TermsVersion.objects.order_by("-published_at", "-id").first()
    if latest is None:
        return None
    if TermsAcceptance.objects.filter(user=user, terms_version=latest).exists():
        return None
    return latest


def accept_terms(*, user: User, terms_version: TermsVersion) -> TermsAcceptance:
    """Enregistre l'acceptation d'une version des CGU (CDC 7.5, 10.2 n°27).

    Idempotent (``get_or_create`` sur la contrainte unique
    ``(user, terms_version)``) : la journalisation reelle est deleguee au
    signal ``post_save`` existant (:func:`log_terms_accepted`, tache 1.6),
    qui ne se declenche qu'a la creation -- pas de doublon si l'appelant
    accepte deux fois la meme version.
    """

    acceptance, _created = TermsAcceptance.objects.get_or_create(
        user=user, terms_version=terms_version, defaults={"accepted_at": timezone.now()}
    )
    return acceptance


class TermsPublicationError(Exception):
    """Publication d'une version des CGU refusee (message en francais, affichable tel quel)."""


def publish_terms_version(
    *, published_by: User, content: str, published_at=None
) -> TermsVersion:
    """Publie une nouvelle version des CGU (CDC 2.5, 7.5 ; 10.2 n°27).

    Portee plateforme, reservee a un Superuser. Le texte des CGU est un
    contenu juridique fourni par le client : ce service ne fournit jamais
    de texte par defaut. Le numero de version (ex. « 2026-1 ») est genere
    par ``TermsVersion.save()``. L'operation est journalisee
    (``accounts.terms.published``, ``club=None``) ; le texte integral n'est
    pas copie dans le journal (seuls numero, date et longueur le sont).
    """

    if published_by is None or not published_by.is_superuser:
        raise TermsPublicationError(
            "Seul un Superuser peut publier une version des CGU."
        )
    text = (content or "").strip()
    if not text:
        raise TermsPublicationError("Le texte des CGU est vide.")

    version = TermsVersion(
        published_at=published_at or timezone.now(),
        content=text,
        created_by=published_by,
    )
    try:
        version.full_clean()
    except ValidationError as exc:
        raise TermsPublicationError(" ".join(exc.messages)) from exc

    with transaction.atomic():
        version.save()
        log_action(
            actor=published_by,
            club=None,
            action_type="accounts.terms.published",
            obj=version,
            before=None,
            after={
                "version_number": version.version_number,
                "published_at": version.published_at,
                "content_length": len(text),
            },
        )
    return version


# ---------------------------------------------------------------------------
# Compte joueur (creation/mise a jour, tache 1.4 ; CDC 4.1)
# ---------------------------------------------------------------------------


class PlatformUserResult(NamedTuple):
    user: User
    created: bool
    # ``before``/``after`` du sous-ensemble des champs personnels usuels
    # (telephone, date de naissance, poids, taille) reellement modifies sur
    # un compte `User` deja existant -- ``None``/``None`` si le compte vient
    # d'etre cree (deja journalise ailleurs par l'appelant, ex.
    # ``membership.created``) ou si aucun champ n'a change (mise a jour
    # « no-op », rien a journaliser). Permet a l'appelant (qui detient le
    # contexte club/acteur, ce que cette fonction n'a jamais -- voir
    # docstring) d'ecrire lui-meme l'entree de journal correspondante
    # (audit tache 1.14, ecart bloquant B4).
    updated_fields_before: Optional[dict[str, Any]]
    updated_fields_after: Optional[dict[str, Any]]


def _platform_user_editable_fields_snapshot(user: User, fields: list[str]) -> dict[str, Any]:
    """Cliche des seuls champs listes dans ``fields``, parmi les champs
    personnels que :func:`get_or_create_platform_user` peut modifier sur un
    compte `User` deja existant (CDC 4.1 : « champs personnels usuels »).
    Le journal ne recoit ainsi jamais une donnee personnelle (poids, taille,
    date de naissance) qui n'a pas change. Distinct de
    ``apps.accounts.services._personal_info_snapshot`` (onglet « Mon profil »,
    qui couvre aussi prenom/nom, jamais touches ici pour un compte existant)."""

    return {field: getattr(user, field) for field in fields}


def get_or_create_platform_user(
    *,
    email: str,
    first_name: str,
    last_name: str,
    phone: str = "",
    birth_date=None,
    weight_kg=None,
    height_cm=None,
) -> PlatformUserResult:
    """Trouve ou cree le compte `User` correspondant a cet email (CDC 4.1 :
    « l'email [...] unique sur la plateforme »). Point d'entree unique pour
    la partie "compte global" de l'ajout/import d'un joueur -- utilise par
    ``apps.clubs.services.create_or_update_player`` (tache 1.4), reutilisable
    tel quel par un futur ajout manuel d'un seul joueur (hors perimetre de
    cette tache).

    Trois cas, selon que l'email est deja connu de la plateforme (CDC 4.1 :
    l'email est unique sur toute la plateforme, pas seulement dans un club) :

    - **Email inconnu** : nouveau compte. Mot de passe initial = l'email,
      ``must_change_password=True`` (CDC 4.1 : « le mot de passe initial est
      l'email [...] le joueur doit le changer a sa premiere connexion. Tant
      qu'il ne l'a pas change, il n'accede a aucune donnee. »). Implemente
      exactement tel qu'ecrit par le CDC, sans l'affaiblir ni le renforcer
      (rappel de contexte du premier audit de securite du Lot 1, decision
      client D1 non tranchee -- a reposer separement, pas a l'appelant).
    - **Email deja connu, dans le meme club que l'appelant** : ce cas est
      traite par l'appelant (``create_or_update_player``, qui detient le
      contexte du club) -- ici, du point de vue du seul compte `User`, il ne
      se distingue pas du cas suivant.
    - **Email deja connu, dans un AUTRE club (ou sans aucun club)** : ce
      compte existant n'est jamais recree ni duplique -- **jamais** de mot
      de passe touche ici. Seuls les « champs personnels usuels » (CDC 4.1 :
      telephone, date de naissance, poids, taille) sont mis a jour, et
      seulement s'ils sont fournis (une valeur absente du CSV/formulaire ne
      vient jamais effacer une donnee existante). Choix deliberement
      conservateur : le prenom/nom (identite globale de la personne,
      CDC 0.3) ne sont **jamais** modifies pour un compte existant, quel que
      soit le club appelant -- seulement fixes a la creation. Ce n'est pas
      une regle explicitement ecrite au CDC 4.1 pour ce cas precis (email
      deja present sur la plateforme, hors du club important) : interpretation
      par defaut la plus prudente, a confirmer par le client (CLAUDE.md
      circuit 9.4) -- voir le compte rendu de la tache 1.4.

    Renvoie un :class:`PlatformUserResult` -- ``updated_fields_before``/
    ``updated_fields_after`` valent ``None``/``None`` sauf si un compte
    existant a reellement ete modifie (creation, ou mise a jour « no-op »
    sans aucun champ fourni different de l'existant) : a l'appelant, qui
    detient le contexte club/acteur, d'ecrire l'entree de journal
    correspondante avec ces deux cliches (CLAUDE.md regle n6, audit tache
    1.14 ecart bloquant B4 -- cette fonction, volontairement
    club-agnostique, n'appelle jamais elle-meme ``apps.core.services.log_action``).
    """

    normalized_email = (email or "").strip().lower()
    user = User.objects.filter(email=normalized_email).first()

    if user is None:
        user = User(email=normalized_email, first_name=first_name, last_name=last_name)
        if phone:
            user.phone = phone
        if birth_date is not None:
            user.birth_date = birth_date
        if weight_kg is not None:
            user.weight_kg = weight_kg
        if height_cm is not None:
            user.height_cm = height_cm
        user.set_password(normalized_email)
        user.must_change_password = True
        user.save()
        return PlatformUserResult(user, True, None, None)

    before_values = {
        "phone": user.phone,
        "birth_date": user.birth_date,
        "weight_kg": user.weight_kg,
        "height_cm": user.height_cm,
    }

    update_fields: list[str] = []
    if phone and user.phone != phone:
        user.phone = phone
        update_fields.append("phone")
    if birth_date is not None and user.birth_date != birth_date:
        user.birth_date = birth_date
        update_fields.append("birth_date")
    if weight_kg is not None and user.weight_kg != weight_kg:
        user.weight_kg = weight_kg
        update_fields.append("weight_kg")
    if height_cm is not None and user.height_cm != height_cm:
        user.height_cm = height_cm
        update_fields.append("height_cm")
    if not update_fields:
        return PlatformUserResult(user, False, None, None)

    user.save(update_fields=update_fields)
    before = {field: before_values[field] for field in update_fields}
    after = _platform_user_editable_fields_snapshot(user, update_fields)
    return PlatformUserResult(user, False, before, after)


def log_terms_accepted(acceptance: TermsAcceptance) -> None:
    """Journalise l'acceptation d'une version des CGU par un utilisateur.

    Portee plateforme (``club=None``) : l'acceptation des CGU n'est pas
    propre a un club (un utilisateur peut adherer a plusieurs clubs dans
    le temps, CDC 6.3), conformement a docs/lot0/schema-donnees.md §1.2.

    ``ip_address``/``user_agent`` ne sont pas passes explicitement ici :
    ``apps.core.services.log_action`` les deduit desormais du contexte de
    la requete HTTP courante (``apps.core.request_context``) quand ce
    signal se declenche depuis une requete reelle (tache 1.3, resout le
    point ouvert laisse par la tache 1.6). Ils restent vides si ce signal
    se declenche hors requete HTTP (factory de test, commande de gestion).
    """

    log_action(
        actor=acceptance.user,
        club=None,
        action_type="accounts.terms.accepted",
        obj=acceptance,
        before=None,
        after={
            "terms_version_id": acceptance.terms_version_id,
            "accepted_at": acceptance.accepted_at,
        },
    )


# ---------------------------------------------------------------------------
# Mon profil -- onglets « Informations », « Identifiant et mot de passe »,
# « Photo » (CDC 4.1, 4.2, 7.1 ; comptes-mon-profil.md §4.1 ; tache 1.9,
# slice Lot 1)
# ---------------------------------------------------------------------------
#
# L'onglet « Code PIN » de cette meme modale ne cree AUCUNE nouvelle
# fonction : il reutilise directement :func:`redefine_pin` ci-dessus (ses
# champs -- mot de passe actuel, nouveau code, confirmation -- sont
# exactement ceux de comptes-mon-profil.md §4.1) ; seul le point d'entree
# HTTP est nouveau (``apps.accounts.views.MyPinUpdateView``).


class PersonalInfoError(Exception):
    """Erreur metier de l'onglet « Informations » de Mon profil (CDC 4.1),
    message en francais clair destine a une reponse HTTP."""


def _personal_info_snapshot(user: User) -> dict:
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "birth_date": user.birth_date,
        "weight_kg": user.weight_kg,
        "height_cm": user.height_cm,
    }


def update_personal_info(
    *,
    user: User,
    first_name: str,
    last_name: str,
    phone: str = "",
    birth_date=None,
    weight_kg=None,
    height_cm=None,
) -> User:
    """Onglet « Informations » de la modale « Modifier mon profil »
    (comptes-mon-profil.md §4.1). Poste et numero de maillot ne sont PAS
    modifiables ici (lecture seule, reserves au Coach, CDC 2.4) -- ce ne
    sont d'ailleurs pas des champs de ``User`` mais de
    ``apps.clubs.models.Membership`` : hors de portee de ce service, qui
    n'ecrit jamais que sur le compte global.

    La validation de forme (longueurs, date non future, bornes de
    poids/taille) vit dans le serializer d'entree
    (``apps.accounts.serializers.PersonalInfoUpdateSerializer``), comme
    partout ailleurs dans ce projet (CLAUDE.md section 5) : ce service ne
    revalide donc pas ces bornes, il applique la mise a jour et
    journalise.
    """

    before = _personal_info_snapshot(user)

    user.first_name = first_name
    user.last_name = last_name
    user.phone = phone
    user.birth_date = birth_date
    user.weight_kg = weight_kg
    user.height_cm = height_cm
    user.save(update_fields=["first_name", "last_name", "phone", "birth_date", "weight_kg", "height_cm"])

    log_action(
        actor=user,
        club=None,
        action_type="accounts.profile.personal_info_updated",
        obj=user,
        before=before,
        after=_personal_info_snapshot(user),
    )
    return user


class CredentialsUpdateError(Exception):
    """Base commune des erreurs de l'onglet « Identifiant et mot de passe »
    (CDC 4.1, 7.1 ; comptes-mon-profil.md §4.1)."""


class CurrentPasswordIncorrectError(CredentialsUpdateError):
    def __init__(self):
        super().__init__("Mot de passe actuel incorrect.")


class EmailAlreadyUsedByAnotherAccountError(CredentialsUpdateError):
    """Distinct de :class:`apps.clubs.club_creation.EmailAlreadyUsedError` :
    ce cas-ci concerne un CHANGEMENT d'email sur un compte deja
    authentifie, pas la creation d'un nouveau compte."""

    def __init__(self):
        super().__init__("Cette adresse email est deja utilisee.")


class NewPasswordMismatchError(CredentialsUpdateError):
    def __init__(self):
        super().__init__("Les deux mots de passe ne correspondent pas.")


def update_credentials(
    *,
    user: User,
    current_password: str,
    new_email: str,
    new_password: str = "",
    confirm_new_password: str = "",
) -> User:
    """Onglet « Identifiant et mot de passe » (comptes-mon-profil.md §4.1) :
    changement volontaire d'email et/ou de mot de passe, avec verification
    du mot de passe actuel -- **distinct** de :func:`change_forced_password`
    ci-dessus (reserve au changement FORCE du mot de passe initial/
    temporaire, qui ne demande jamais l'ancien mot de passe -- voir
    :class:`PasswordChangeNotForcedError`). Le nouveau mot de passe est
    facultatif : un joueur peut ne changer que son email.

    Revoque tous les jetons de renouvellement existants si le mot de
    passe change reellement (meme principe de securite que
    :func:`change_forced_password`/:func:`reset_password_by_superuser` :
    un jeton deja emis ailleurs ne doit pas survivre au changement de mot
    de passe qui vient de l'invalider).
    """

    if not user.check_password(current_password):
        raise CurrentPasswordIncorrectError()

    normalized_email = (new_email or "").strip().lower()
    email_changed = normalized_email != user.email
    if email_changed and User.objects.filter(email=normalized_email).exclude(pk=user.pk).exists():
        raise EmailAlreadyUsedByAnotherAccountError()

    password_changed = bool(new_password)
    if password_changed:
        if new_password != confirm_new_password:
            raise NewPasswordMismatchError()

        errors: list[str] = []
        if normalized_email and new_password == normalized_email:
            errors.append("Le mot de passe doit etre different de votre email.")
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            errors.extend(exc.messages)
        if errors:
            raise ValidationError(errors)

    before = {"email": user.email}

    user.email = normalized_email
    update_fields = ["email"]
    if password_changed:
        user.set_password(new_password)
        update_fields.append("password")
    user.save(update_fields=update_fields)

    tokens_revoked = 0
    if password_changed:
        tokens_revoked = _blacklist_all_outstanding_tokens(user)

    log_action(
        actor=user,
        club=None,
        action_type="accounts.profile.credentials_updated",
        obj=user,
        before=before,
        after={
            "email": user.email,
            "email_changed": email_changed,
            "password_changed": password_changed,
            "tokens_revoked": tokens_revoked,
        },
    )
    return user


def update_profile_photo(*, user: User, photo) -> User:
    """Onglet « Photo » de Mon profil (comptes-mon-profil.md §4.1). Stockage
    public (comme ``Club.logo``) : une photo de profil n'est jamais un
    document personnel sensible au sens du schema (§1.1, type ``Image``),
    aucune infrastructure de fichier prive n'est necessaire ici."""

    before = {"had_photo": bool(user.photo)}
    user.photo = photo
    user.save(update_fields=["photo"])

    log_action(
        actor=user,
        club=None,
        action_type="accounts.profile.photo_updated",
        obj=user,
        before=before,
        after={"had_photo": True},
    )
    return user


def remove_profile_photo(*, user: User) -> User:
    """« Retirer la photo » (comptes-mon-profil.md §4.1) : les initiales
    s'affichent a la place, cote interface."""

    before = {"had_photo": bool(user.photo)}
    if user.photo:
        user.photo.delete(save=False)
    user.photo = None
    user.save(update_fields=["photo"])

    log_action(
        actor=user,
        club=None,
        action_type="accounts.profile.photo_removed",
        obj=user,
        before=before,
        after={"had_photo": False},
    )
    return user
