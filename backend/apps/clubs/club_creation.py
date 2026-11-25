"""Assistant de creation d'un club en libre-service (tache 1.9).

Sources : `docs/ecrans/clubs-creation.md` (specification d'ecran complete,
Lot 0) ; CDC 1.4 (licence d'essai), 2.1, 2.3 (le createur devient
President), 4.1 (« Creation d'un club », tableau des champs d'« Ajout
d'un joueur »), 5.2, 7.1, 7.5, 7.6 ; 10.2 n1, 18, 20, 24, 27.

Module SEPARE de ``apps.clubs.services`` (deja tres volumineux, tache
1.4-1.6) plutot qu'une nouvelle section dans ce fichier : cette
fonctionnalite est un point d'entree PUBLIC (non authentifie), avec des
regles propres (idempotence, generation de slug, cle d'essai) qui ne
concernent aucune autre fonction existante de ``apps.clubs.services`` --
nom explicite choisi pour qu'un futur lecteur du module trouve
immediatement ce qui est propre a l'assistant de creation, CLAUDE.md
section 5.

Une seule fonction publique orchestre tout : :func:`create_club_with_founder`,
qui cree dans une SEULE transaction (docs/ecrans/clubs-creation.md §5) :

- le ``Club`` (identite) et son ``ClubSettings`` (parametres, valeurs par
  defaut du modele -- 10.2 n18/n24, rien a ajouter ici) ;
- la ``Licence`` d'essai (10.2 n1/n20 : 30 jours, grace 15 jours -- voir
  ``apps.licences.services.TRIAL_DURATION_DAYS`` et
  ``Licence.grace_period_days`` pour les deux constantes nommees) ;
  ``created_by=None`` : aucun Superuser n'intervient dans ce parcours
  (voir la docstring de ``Licence.created_by``, migration additive de
  cette tache) ;
- le compte ``User`` du fondateur (mot de passe initial = email,
  ``must_change_password=True``, CDC 7.1 ; reutilise
  ``apps.accounts.services.get_or_create_platform_user``) ;
- le ``Membership`` (statut Inscrit directement -- point ouvert de la
  spec applique par defaut, voir §8 de la spec et le compte rendu de
  cette tache) et le ``MembershipRole`` President ;
- l'acceptation des CGU (``TermsAcceptance``, reutilise
  ``apps.accounts.services.accept_terms``) ;
- les entrees du journal (5.2 : creation du club, licence ; le compte et
  la nomination sont deja couverts automatiquement par les signaux
  existants de ``apps.clubs.signals``/``apps.accounts.signals`` --
  ``membership.created``, ``role.appointed``, ``accounts.terms.accepted``
  -- voir le compte rendu de la tache pour le detail de cette
  correspondance).

Si une seule ecriture echoue, rien n'est cree (``transaction.atomic``).
"""

from __future__ import annotations

import datetime
import unicodedata
from decimal import Decimal
from typing import NamedTuple, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts import services as accounts_services
from apps.accounts.models import TermsVersion, User
from apps.clubs.models import Club, ClubCreationRequest, ClubSettings, Membership, MembershipRole
from apps.clubs.services import notify_role_change
from apps.core.reserved_accounts import validate_email_not_reserved
from apps.core.services import log_action
from apps.licences.models import Licence
from apps.licences.services import TRIAL_DURATION_DAYS

__all__ = [
    "ClubCreationError",
    "EmailAlreadyUsedError",
    "TermsVersionOutdatedError",
    "ClubCreationResult",
    "generate_unique_slug",
    "get_public_creation_settings",
    "create_club_with_founder",
]


class ClubCreationError(Exception):
    """Erreur metier de l'assistant de creation de club, message en
    francais clair destine a une reponse HTTP (CLAUDE.md chapitre 3)."""


class EmailAlreadyUsedError(ClubCreationError):
    """L'email du fondateur est deja utilise sur la plateforme (CDC 4.1 :
    l'email est unique sur toute la plateforme).

    Comportement provisoire retenu par la spec (§8, point ouvert, non
    tranche par le client) : aucune fusion de compte, aucune reprise
    d'un compte existant -- un joueur qui a deja un compte (autre club,
    ou parti) ne peut pas creer de club avec son email par cet assistant.
    """

    def __init__(self):
        super().__init__("Cette adresse email est déjà utilisée.")


class TermsVersionOutdatedError(ClubCreationError):
    """La version des CGU acceptee par le client ne correspond plus a la
    derniere version publiee (docs/ecrans/clubs-creation.md §6 : « Version
    des CGU remplacee pendant la saisie »).

    ``latest_terms_version`` : la version courante, a renvoyer au client
    pour qu'il l'affiche et la fasse accepter a nouveau.
    """

    def __init__(self, latest_terms_version: Optional[TermsVersion]):
        self.latest_terms_version = latest_terms_version
        super().__init__(
            "Les conditions générales ont été mises à jour. Lisez la "
            "nouvelle version et acceptez-la pour continuer."
        )


class ClubCreationResult(NamedTuple):
    club: Club
    club_settings: ClubSettings
    licence: Licence
    user: User
    membership: Membership
    role: MembershipRole
    idempotent_replay: bool


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def generate_unique_slug(name: str) -> str:
    """Genere l'adresse ``/c/<slug>`` du club a partir de son nom (spec §8,
    point ouvert applique par defaut : « minuscules, sans accents,
    tirets, suffixe numerique si deja pris »).

    ``django.utils.text.slugify`` retire deja les accents (decomposition
    NFKD puis encodage ASCII, ce que fait aussi :func:`_strip_accents`
    ci-dessus -- appele en plus par prudence, ``slugify`` seul suffit en
    pratique mais un appel explicite documente l'intention sans cout
    reel) et les caracteres non alphanumeriques (remplaces par des
    tirets), en minuscules.

    ``Club`` n'est pas un ``TenantModel`` (portee plateforme) :
    ``Club.objects`` est deja le manager par defaut, non filtre -- aucun
    ``all_objects`` necessaire ici.
    """

    base_slug = slugify(_strip_accents(name))[: Club._meta.get_field("slug").max_length]
    if not base_slug:
        base_slug = "club"

    slug = base_slug
    suffix = 2
    while Club.objects.filter(slug=slug).exists():
        candidate_suffix = f"-{suffix}"
        max_length = Club._meta.get_field("slug").max_length
        slug = base_slug[: max_length - len(candidate_suffix)] + candidate_suffix
        suffix += 1

    return slug


def get_public_creation_settings() -> dict:
    """Parametres publics necessaires a l'etape 3 de l'assistant, avant
    toute authentification (docs/ecrans/clubs-creation.md §4.3) : duree
    d'essai, duree de grace, version en vigueur des CGU (avec son texte)
    et liste des fuseaux horaires.

    Aucune de ces valeurs n'est ecrite en dur dans le code de l'interface
    (spec §3) : elles viennent toutes d'ici, soit d'une constante nommee
    du backend (``TRIAL_DURATION_DAYS``), soit du champ par defaut du
    modele (``Licence.grace_period_days``), soit de la base
    (``TermsVersion``, bibliotheque standard ``zoneinfo`` pour les
    fuseaux).
    """

    from zoneinfo import available_timezones

    latest_terms_version = TermsVersion.objects.order_by("-published_at", "-id").first()

    return {
        "trial_duration_days": TRIAL_DURATION_DAYS,
        "grace_period_days": Licence._meta.get_field("grace_period_days").default,
        "timezones": sorted(available_timezones()),
        "terms_version": latest_terms_version,
    }


def _build_result(club: Club, *, idempotent_replay: bool) -> ClubCreationResult:
    club_settings = club.settings
    licence = club.licences.order_by("-created_at").first()
    membership = club.founder_membership
    role = MembershipRole.all_objects.get(
        club=club, membership=membership, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
    )
    return ClubCreationResult(
        club=club,
        club_settings=club_settings,
        licence=licence,
        user=membership.user,
        membership=membership,
        role=role,
        idempotent_replay=idempotent_replay,
    )


def _club_snapshot(club: Club, club_settings: ClubSettings) -> dict:
    return {
        "name": club.name,
        "slug": club.slug,
        "city": club.city,
        "country": club.country,
        "primary_color": club.primary_color,
        "secondary_color": club.secondary_color,
        "currency": club_settings.currency,
        "timezone": club_settings.timezone,
    }


def _licence_snapshot(licence: Licence) -> dict:
    return {
        "status": licence.status,
        "start_date": licence.start_date,
        "end_date": licence.end_date,
        "grace_period_days": licence.grace_period_days,
    }


def create_club_with_founder(
    *,
    idempotency_key: str,
    # Etape 1 -- « Votre club » (spec §4.1)
    name: str,
    city: str,
    country: str,
    currency: str,
    timezone_name: str,
    logo=None,
    primary_color: str = "",
    secondary_color: str = "",
    # Etape 2 -- « Votre fiche joueur » (spec §4.2)
    email: str,
    first_name: str,
    last_name: str,
    position: str,
    phone: str = "",
    position_detail: str = "",
    jersey_number: Optional[int] = None,
    birth_date=None,
    weight_kg: Optional[Decimal] = None,
    height_cm: Optional[Decimal] = None,
    # Etape 3 -- CGU (spec §4.3)
    terms_version_id: int,
    now=None,
) -> ClubCreationResult:
    """Cree un club, sa licence d'essai et son fondateur-President, en une
    seule transaction (spec §5). Voir la docstring du module pour le
    detail de ce qui est cree.

    Idempotent (spec §5) : un deuxieme appel avec la meme
    ``idempotency_key`` ne cree jamais un deuxieme club -- renvoie le
    resultat de la premiere creation (``idempotent_replay=True``).

    Leve :class:`EmailAlreadyUsedError` si l'email du fondateur est deja
    utilise sur la plateforme (spec §8, point ouvert), ou
    :class:`TermsVersionOutdatedError` si ``terms_version_id`` ne
    correspond plus a la derniere version publiee des CGU. Laisse se
    propager ``django.core.exceptions.ValidationError`` pour toute autre
    regle de coherence de modele (ex. couleur mal formee).
    """

    now = now or timezone.now()

    existing_request = (
        ClubCreationRequest.objects.filter(idempotency_key=idempotency_key).select_related("club").first()
    )
    if existing_request is not None:
        return _build_result(existing_request.club, idempotent_replay=True)

    latest_terms_version = TermsVersion.objects.order_by("-published_at", "-id").first()
    if latest_terms_version is None or latest_terms_version.id != terms_version_id:
        raise TermsVersionOutdatedError(latest_terms_version)

    normalized_email = (email or "").strip().lower()
    validate_email_not_reserved(normalized_email)
    if User.objects.filter(email=normalized_email).exists():
        raise EmailAlreadyUsedError()

    try:
        with transaction.atomic():
            slug = generate_unique_slug(name)

            club = Club(
                name=name,
                slug=slug,
                logo=logo,
                primary_color=primary_color,
                secondary_color=secondary_color,
                city=city,
                country=country,
                status=Club.Status.ACTIVE,
            )
            club.save()  # full_clean() (Club.save() l'appelle toujours)

            club_settings = ClubSettings(club=club, currency=currency, timezone=timezone_name)
            club_settings.full_clean()
            club_settings.save()

            licence = Licence(
                club=club,
                status=Licence.Status.TRIAL,
                start_date=now.date(),
                end_date=now.date() + datetime.timedelta(days=TRIAL_DURATION_DAYS),
                created_by=None,
            )
            licence.full_clean()
            licence.save()

            # Toujours une creation (jamais une mise a jour d'un compte
            # existant) : l'unicite de l'email est deja garantie ci-dessus
            # (`EmailAlreadyUsedError`) -- pas de `updated_fields_before`/
            # `updated_fields_after` a journaliser ici (voir
            # `apps.accounts.services.PlatformUserResult`, audit tache 1.14
            # ecart bloquant B4).
            platform_user_result = accounts_services.get_or_create_platform_user(
                email=normalized_email,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                birth_date=birth_date,
                weight_kg=weight_kg,
                height_cm=height_cm,
            )
            user = platform_user_result.user

            membership = Membership(
                club=club,
                user=user,
                status=Membership.Status.ACTIVE,
                sponsor=None,
                position=position,
                position_detail=position_detail,
                jersey_number=jersey_number,
                joined_on=now.date(),
                added_by=user,
            )
            membership.save()  # full_clean() + journal "membership.created" (signal, tache 1.6)

            club.founder_membership = membership
            club.save()  # full_clean() (Club.save() l'appelle toujours)

            role = MembershipRole(
                club=club,
                membership=membership,
                role=MembershipRole.Role.PRESIDENT,
                appointed_by=user,
                appointed_at=now,
            )
            role.save()  # full_clean() + journal "role.appointed" (signal, tache 1.6)
            notify_role_change(role_instance=role, event="appointed")

            accounts_services.accept_terms(user=user, terms_version=latest_terms_version)

            log_action(
                actor=user,
                club=club,
                action_type="clubs.created",
                obj=club,
                before=None,
                after=_club_snapshot(club, club_settings),
            )
            log_action(
                actor=user,
                club=club,
                action_type="licence.created",
                obj=licence,
                before=None,
                after=_licence_snapshot(licence),
            )

            ClubCreationRequest.objects.create(idempotency_key=idempotency_key, club=club)
    except IntegrityError:
        # Course concurrente la plus probable : une autre requete avec la
        # MEME cle d'idempotence a deja cree le club pendant que celle-ci
        # etait en cours (spec §5). La transaction ci-dessus est
        # integralement annulee (rien n'est cree par CETTE requete) ; on
        # renvoie le resultat du gagnant de la course.
        winner = ClubCreationRequest.objects.filter(idempotency_key=idempotency_key).select_related("club").first()
        if winner is not None:
            return _build_result(winner.club, idempotent_replay=True)

        # Deuxieme cause possible (cles d'idempotence DIFFERENTES, meme
        # email soumis en meme temps par deux onglets) : contrainte
        # d'unicite de `User.email`, revalidee ici pour renvoyer le
        # message metier attendu plutot qu'une erreur technique brute.
        if User.objects.filter(email=normalized_email).exists():
            raise EmailAlreadyUsedError() from None

        # Cas residuel non traite ici (documente au compte rendu de la
        # tache) : collision d'adresse `/c/<slug>` entre deux createurs
        # de club au nom quasi identique, exactement au meme instant --
        # fenetre de course extremement etroite entre la verification de
        # :func:`generate_unique_slug` et l'ecriture reelle.
        raise

    return _build_result(club, idempotent_replay=False)
