"""Regles metier de l'app licences (CDC 1.4, 2.5, 4.18, 5.4 ; 10.2 n19/n20/n26 ;
tache 1.8).

Trois familles de fonctions :

1. **Cycle de vie de la licence** (:func:`activate_licence`,
   :func:`extend_licence`, :func:`suspend_licence`, :func:`resume_licence`,
   :func:`terminate_licence`) : chaque transition explicite du Superuser
   cree a la fois une :class:`~apps.licences.models.LicenceEvent`
   (historique METIER de la licence, affiche dans l'ecran « Licences »,
   CDC 4.18) et une entree ``AuditLog`` via
   ``apps.core.services.log_action`` (journal generique de la plateforme,
   CDC chapitre 5). Ce n'est **pas** une duplication au sens CLAUDE.md
   regle n6 : les deux jouent un role different -- ``LicenceEvent`` est
   une denormalisation deliberee du schema (schema-donnees.md §4.6),
   pensee pour l'ecran « historique », alors que ``AuditLog`` reste le
   seul journal d'audit inalterable de toute la plateforme.

2. **Transitions automatiques** (:func:`process_licence_expirations`,
   :func:`process_licence_reminders`) : fonctions idempotentes appelees
   par une commande de gestion (elle-meme appelee par le cron -- CLAUDE.md
   « pas de processus permanent »). N'ecrivent JAMAIS d'``AuditLog`` :
   aucun acteur reel n'existe pour une transition purement temporelle
   (CDC 5.1 exige un acteur reel, y compris en Ghost Mode) -- meme choix,
   pour la meme raison, que
   ``apps.clubs.services.process_sponsor_reminders_and_alerts``.

3. **Sessions de support / Ghost Mode** (:func:`start_support_session`,
   :func:`end_support_session`, :func:`is_support_session_valid`,
   :func:`enter_ghost_mode`) : CDC 4.18, 5.4. Le mecanisme qui rend le
   Ghost Mode automatique pour tout le reste de la plateforme (club actif
   restreint au SEUL club de la session, `acted_as_ghost`/
   `support_session_id` automatiques sur chaque `AuditLog`) vit dans
   ``apps.core.ghost_context`` (contexte dedie) et
   ``apps.core.tenant`` (club actif, mecanisme deja existant depuis la
   tache 1.2) -- ce module ne fait qu'armer/verifier ces deux contextes,
   jamais les reinventer.
"""

from __future__ import annotations

import datetime
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.clubs.models import Club, MembershipRole
from apps.core.ghost_context import ghost_mode as _ghost_mode_context
from apps.core.services import log_action
from apps.core.tenant import active_club as _active_club_context
from apps.licences.models import Licence, LicenceEvent, SupportSession

__all__ = [
    "LicenceError",
    "InvalidLicenceTransitionError",
    "LicenceTerminationConfirmationError",
    "SupportSessionError",
    "SupportSessionPermissionError",
    "TRIAL_DURATION_DAYS",
    "REMINDER_THRESHOLDS_DAYS",
    "activate_licence",
    "extend_licence",
    "suspend_licence",
    "resume_licence",
    "terminate_licence",
    "process_licence_expirations",
    "process_licence_reminders",
    "start_support_session",
    "end_support_session",
    "is_support_session_valid",
    "enter_ghost_mode",
]


# ---------------------------------------------------------------------------
# Erreurs
# ---------------------------------------------------------------------------


class LicenceError(Exception):
    """Base commune des erreurs metier du cycle de vie d'une licence (CDC 1.4, 2.5)."""


class InvalidLicenceTransitionError(LicenceError):
    """Transition refusee : l'etat actuel de la licence est incompatible
    avec l'action demandee (CDC 1.4 : essai -> active -> expiree ->
    suspendue -> resiliee)."""


class LicenceTerminationConfirmationError(LicenceError):
    """Nom du club saisi en confirmation de resiliation incorrect (10.2 n26).

    Rien n'est modifie dans ce cas : ni le statut de la licence, ni aucune
    entree de journal -- verifie AVANT toute mutation par
    :func:`terminate_licence`.
    """


class SupportSessionError(Exception):
    """Base commune des erreurs de session de support / Ghost Mode (CDC 4.18)."""


class SupportSessionPermissionError(SupportSessionError):
    """Action reservee au Superuser proprietaire de la session de support."""


# Duree de l'essai gratuit (10.2 n1/n20, tache 1.9) : consommee par
# ``apps.clubs.club_creation.create_club_with_founder`` (assistant de
# creation de club en libre-service) et exposee telle quelle par son
# point d'acces public de parametres (``docs/ecrans/clubs-creation.md``
# §4.3 : « aucune de ces valeurs n'est ecrite dans le code [cote
# interface] »). La duree de grace, elle, a deja sa propre valeur par
# defaut nommee sur le champ du modele (``Licence.grace_period_days``,
# defaut 15) : pas de deuxieme constante pour ne pas dupliquer la meme
# information a deux endroits.
TRIAL_DURATION_DAYS = 30


def _require_superuser(user, *, message: str) -> None:
    if not getattr(user, "is_superuser", False):
        raise PermissionError(message)


def _licence_snapshot(licence: Licence) -> dict:
    return {
        "status": licence.status,
        "start_date": licence.start_date,
        "end_date": licence.end_date,
        "grace_period_days": licence.grace_period_days,
    }


# ---------------------------------------------------------------------------
# Cycle de vie (actions explicites du Superuser, CDC 2.5, 4.18)
# ---------------------------------------------------------------------------


def activate_licence(
    *,
    superuser,
    licence: Licence,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    note: str = "",
    now=None,
) -> Licence:
    """Active une licence (CDC 2.5 : « activer [...] la licence d'un club »).

    Autorisee depuis TRIAL ou EXPIRED (reactivation, y compris au-dela de
    la periode de grace : redonne immediatement l'acces complet --
    `Club.status` repasse a `ACTIVE` s'il etait `READ_ONLY`, 10.2 n19).
    Refusee depuis SUSPENDED (utiliser :func:`resume_licence`, qui porte
    un type d'evenement distinct, schema §4.6) et depuis TERMINATED (etat
    final, 10.2 n26).
    """

    now = now or timezone.now()
    _require_superuser(superuser, message="Seul un Superuser peut activer une licence (CDC 2.5).")

    if licence.status == Licence.Status.TERMINATED:
        raise InvalidLicenceTransitionError("Une licence resiliee ne peut plus etre activee (10.2 n26).")
    if licence.status == Licence.Status.SUSPENDED:
        raise InvalidLicenceTransitionError(
            "Une licence suspendue doit d'abord etre reprise (resume_licence), pas activee."
        )

    with transaction.atomic():
        before = _licence_snapshot(licence)

        if start_date is not None:
            licence.start_date = start_date
        if end_date is not None:
            licence.end_date = end_date
        licence.status = Licence.Status.ACTIVE
        licence.save()

        if licence.club.status == Club.Status.READ_ONLY:
            licence.club.status = Club.Status.ACTIVE
            licence.club.save(update_fields=["status"])

        LicenceEvent.objects.create(
            licence=licence,
            event_type=LicenceEvent.EventType.ACTIVATED,
            event_date=now,
            actor=superuser,
            note=note,
        )
        log_action(
            actor=superuser,
            club=licence.club,
            action_type="licence.activated",
            obj=licence,
            before=before,
            after=_licence_snapshot(licence),
        )

    return licence


def extend_licence(
    *,
    superuser,
    licence: Licence,
    end_date: datetime.date,
    start_date: Optional[datetime.date] = None,
    note: str = "",
    now=None,
) -> Licence:
    """Prolonge une licence (CDC 2.5 : « prolonger »), en modifiant ses dates.

    Refusee depuis TERMINATED (etat final) et depuis SUSPENDED (prolonger
    les dates d'une licence suspendue ne redonne pas l'acces : 10.2 n19
    dit explicitement que le blocage d'une licence suspendue est
    independant des dates -- utiliser :func:`resume_licence` explicitement
    au prealable). La nouvelle ``end_date`` doit etre strictement
    posterieure a l'actuelle (sinon ce n'est pas une prolongation).

    Si la licence etait EXPIREE, la prolongation la reactive (statut
    ACTIVE) et redonne l'acces complet au club (`Club.status` repasse a
    `ACTIVE` s'il etait `READ_ONLY`) : prolonger les dates d'une licence
    expiree n'a de sens que pour lui redonner vie.
    """

    now = now or timezone.now()
    _require_superuser(superuser, message="Seul un Superuser peut prolonger une licence (CDC 2.5).")

    if licence.status == Licence.Status.TERMINATED:
        raise InvalidLicenceTransitionError("Une licence resiliee ne peut plus etre prolongee (10.2 n26).")
    if licence.status == Licence.Status.SUSPENDED:
        raise InvalidLicenceTransitionError(
            "Une licence suspendue doit d'abord etre reprise (resume_licence) avant d'etre prolongee."
        )
    if end_date <= licence.end_date:
        raise InvalidLicenceTransitionError(
            "La nouvelle date de fin doit etre strictement posterieure a la date de fin actuelle."
        )

    with transaction.atomic():
        before = _licence_snapshot(licence)

        if start_date is not None:
            licence.start_date = start_date
        licence.end_date = end_date
        if licence.status == Licence.Status.EXPIRED:
            licence.status = Licence.Status.ACTIVE
        licence.save()

        if licence.status == Licence.Status.ACTIVE and licence.club.status == Club.Status.READ_ONLY:
            licence.club.status = Club.Status.ACTIVE
            licence.club.save(update_fields=["status"])

        LicenceEvent.objects.create(
            licence=licence,
            event_type=LicenceEvent.EventType.EXTENDED,
            event_date=now,
            actor=superuser,
            note=note,
        )
        log_action(
            actor=superuser,
            club=licence.club,
            action_type="licence.extended",
            obj=licence,
            before=before,
            after=_licence_snapshot(licence),
        )

    return licence


def suspend_licence(*, superuser, licence: Licence, reason: str, now=None) -> Licence:
    """Suspend une licence (CDC 2.5).

    10.2 n19 : bloque l'acces du club, ne touche **jamais** `Club.status`
    -- c'est un controle d'acces applicatif, voir
    `apps.core.permissions.HasUsableLicence`, pas un changement d'etat du
    club.
    """

    now = now or timezone.now()
    _require_superuser(superuser, message="Seul un Superuser peut suspendre une licence (CDC 2.5).")

    if not (reason or "").strip():
        raise InvalidLicenceTransitionError("Le motif de suspension est obligatoire.")
    if licence.status == Licence.Status.TERMINATED:
        raise InvalidLicenceTransitionError("Une licence resiliee ne peut plus etre suspendue (10.2 n26).")
    if licence.status == Licence.Status.SUSPENDED:
        raise InvalidLicenceTransitionError("Cette licence est deja suspendue.")

    with transaction.atomic():
        before = _licence_snapshot(licence)
        licence.status = Licence.Status.SUSPENDED
        licence.save()

        LicenceEvent.objects.create(
            licence=licence,
            event_type=LicenceEvent.EventType.SUSPENDED,
            event_date=now,
            actor=superuser,
            note=reason,
        )
        log_action(
            actor=superuser,
            club=licence.club,
            action_type="licence.suspended",
            obj=licence,
            before=before,
            after=_licence_snapshot(licence),
        )

    return licence


def resume_licence(*, superuser, licence: Licence, note: str = "", now=None) -> Licence:
    """Reprend une licence suspendue (CDC 2.5). Seule transition valide
    depuis SUSPENDED -- redonne l'acces complet au club immediatement.

    Ne modifie jamais `Club.status` (deja inchange par
    :func:`suspend_licence`, 10.2 n19) : si les dates de la licence
    restent au-dela de la periode de grace, la prochaine execution de
    :func:`process_licence_expirations` la fera repasser EXPIREE (et
    `Club.status` en lecture seule) -- comportement idempotent attendu,
    pas un defaut.
    """

    now = now or timezone.now()
    _require_superuser(superuser, message="Seul un Superuser peut reprendre une licence (CDC 2.5).")

    if licence.status != Licence.Status.SUSPENDED:
        raise InvalidLicenceTransitionError("Seule une licence suspendue peut etre reprise.")

    with transaction.atomic():
        before = _licence_snapshot(licence)
        licence.status = Licence.Status.ACTIVE
        licence.save()

        LicenceEvent.objects.create(
            licence=licence,
            event_type=LicenceEvent.EventType.RESUMED,
            event_date=now,
            actor=superuser,
            note=note,
        )
        log_action(
            actor=superuser,
            club=licence.club,
            action_type="licence.resumed",
            obj=licence,
            before=before,
            after=_licence_snapshot(licence),
        )

    return licence


def terminate_licence(
    *, superuser, licence: Licence, reason: str, confirm_club_name: str, now=None
) -> Licence:
    """Resilie une licence (CDC 2.5 ; 10.2 n26 : confirmation par saisie du
    nom EXACT du club, en plus du motif habituel).

    Le nom saisi n'est **jamais** stocke : seule la comparaison a
    `Club.name` compte (schema §13.3). En cas de non-correspondance, RIEN
    n'est modifie -- ni le statut de la licence, ni aucune entree de
    journal, verifie **avant** toute mutation.

    Traitement volontairement le plus restrictif possible sur l'effet
    d'une resiliation vis-a-vis de l'acces du club (decision par defaut
    appliquee ici, faute de precision explicite du CDC/10.2 sur ce point
    precis, qui ne traite explicitement que le cas `suspended` -- voir
    `apps.core.permissions.HasUsableLicence` : une licence `TERMINATED`
    bloque l'acces exactement comme une licence `SUSPENDED`, jamais moins
    restrictif. A confirmer par le client, voir compte rendu).
    """

    now = now or timezone.now()
    _require_superuser(superuser, message="Seul un Superuser peut resilier une licence (CDC 2.5).")

    if not (reason or "").strip():
        raise InvalidLicenceTransitionError("Le motif de resiliation est obligatoire (10.2 n26).")
    if licence.status == Licence.Status.TERMINATED:
        raise InvalidLicenceTransitionError("Cette licence est deja resiliee.")

    if (confirm_club_name or "").strip() != licence.club.name:
        raise LicenceTerminationConfirmationError(
            "Le nom du club saisi ne correspond pas : la resiliation est annulee (10.2 n26)."
        )

    with transaction.atomic():
        before = _licence_snapshot(licence)
        licence.status = Licence.Status.TERMINATED
        licence.save()

        LicenceEvent.objects.create(
            licence=licence,
            event_type=LicenceEvent.EventType.TERMINATED,
            event_date=now,
            actor=superuser,
            note=reason,
        )
        log_action(
            actor=superuser,
            club=licence.club,
            action_type="licence.terminated",
            obj=licence,
            before=before,
            after=_licence_snapshot(licence),
        )

    return licence


# ---------------------------------------------------------------------------
# Transitions automatiques (cron, CDC 1.4)
# ---------------------------------------------------------------------------


def process_licence_expirations(*, now=None) -> dict[str, int]:
    """Transition automatique : toute licence ACTIVE/TRIAL dont
    ``end_date + grace_period_days`` est depassee passe EXPIREE, et
    `Club.status` passe READ_ONLY, dans la MEME transaction (CDC 1.4 ;
    10.2 n19).

    Idempotente : ne retraite jamais une licence deja EXPIREE (filtree en
    amont sur ACTIVE/TRIAL uniquement, revalidee sous verrou avant
    ecriture) ni un club deja READ_ONLY (mise a jour conditionnelle).
    Appelee par la commande de gestion `process_licence_lifecycle` (cron
    -- CLAUDE.md : pas de processus permanent), meme limite de perimetre
    que `apps.clubs.services.process_sponsor_reminders_and_alerts` pour le
    branchement reel du crontab (`devops-cpanel`).

    Ne cree AUCUNE `LicenceEvent` pour cette transition : le schema §4.6
    n'a pas de valeur "expiree" dans son enumeration `event_type` --
    lecture volontaire du schema, pas un oubli : l'expiration se lit
    directement sur `Licence.status`, sans necessiter une ligne
    d'historique separee, a la difference des actions explicites du
    Superuser et des relances (`reminder_sent`). N'ecrit non plus AUCUNE
    `AuditLog` : aucun acteur reel n'existe pour cette transition
    purement temporelle (meme choix, pour la meme raison, que
    `apps.clubs.services.process_sponsor_reminders_and_alerts` -- CDC 5.1
    exige un acteur reel, y compris en Ghost Mode) -- point ouvert signale
    au compte rendu de cette tache.

    Inclut aussi bien les licences `ACTIVE` que `TRIAL` : une periode
    d'essai qui arrive a echeance sans intervention du Superuser suit la
    meme mecanique de dates que toute autre licence (CDC 1.4 : « La
    periode d'essai suit la meme mecanique »). Decision par defaut
    appliquee ici, faute de precision explicite du CDC sur ce cas precis
    -- a confirmer par le client (voir compte rendu).

    Comparaison en date UTC (``now.date()``), pas dans le fuseau du club :
    les dates de licence (`start_date`/`end_date`) n'ont elles-memes aucun
    fuseau attache (`DateField` simple) -- point ouvert signale au compte
    rendu.
    """

    now = now or timezone.now()
    today = now.date()

    expired_count = 0
    read_only_count = 0

    candidates = Licence.objects.select_related("club").filter(
        status__in=[Licence.Status.ACTIVE, Licence.Status.TRIAL]
    )
    for licence in candidates:
        cutoff = licence.end_date + datetime.timedelta(days=licence.grace_period_days)
        if today <= cutoff:
            continue

        with transaction.atomic():
            # Reverifie sous verrou (MySQL/MariaDB en production ;
            # `select_for_update` est un no-op silencieux sous SQLite --
            # voir backend/README.md) : deux executions concurrentes du
            # meme cron ne doivent jamais faire passer deux fois la meme
            # licence a EXPIREE.
            locked = Licence.objects.select_for_update().get(pk=licence.pk)
            if locked.status not in (Licence.Status.ACTIVE, Licence.Status.TRIAL):
                continue

            locked.status = Licence.Status.EXPIRED
            locked.save()
            expired_count += 1

            club = locked.club
            if club.status != Club.Status.READ_ONLY:
                club.status = Club.Status.READ_ONLY
                club.save(update_fields=["status"])
                read_only_count += 1

    return {"expired": expired_count, "clubs_set_read_only": read_only_count}


REMINDER_THRESHOLDS_DAYS = (30, 7, 1)


def _active_president_membership(club):
    """Adhesion du President actif de ``club`` (ou ``None``).

    Meme logique que l'equivalent prive de `apps.clubs.services`
    (`_active_president_membership`) -- duplique ici a l'identique plutot
    que de creer une dependance vers un nom prive d'une autre app."""

    role = (
        MembershipRole.all_objects.select_related("membership__user")
        .filter(club=club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True)
        .first()
    )
    return role.membership if role is not None else None


def _build_licence_reminder_text(
    *, club_name: str, days_remaining: int, end_date: datetime.date, grace_period_days: int, is_trial: bool
) -> tuple[str, str]:
    """Titre et corps de la notification/email « Licence proche de
    l'expiration » (CDC 4.17 ; Annexe E §5/§8, tache 1.12). Le texte varie
    selon le palier (30/7/1 jour, ``REMINDER_THRESHOLDS_DAYS``) ET selon le
    statut de la licence (essai/active) -- chaîne exacte reprise telle
    quelle depuis l'annexe, y compris la phrase finale commune sur le
    passage en lecture seule après ``grace_period_days`` (``{grâce}`` ==
    0 remplacé par « dès le lendemain de cette date »)."""

    formatted_date = end_date.strftime("%d/%m/%Y")

    if is_trial:
        if days_remaining == 1:
            title = f"{club_name} : l'essai se termine demain"
            body = (
                f"La période d'essai de Vesta pour {club_name} se termine "
                f"demain, le {formatted_date}. Contactez le support Vesta "
                "dès aujourd'hui pour souscrire une licence."
            )
        else:
            title = f"{club_name} : fin de l'essai dans {days_remaining} jours"
            body = (
                f"La période d'essai de Vesta pour {club_name} se termine "
                f"le {formatted_date}, dans {days_remaining} jours. "
                "Contactez le support Vesta pour souscrire une licence."
            )
    else:
        if days_remaining == 1:
            title = f"{club_name} : la licence expire demain"
            body = (
                f"La licence Vesta de {club_name} expire demain, le "
                f"{formatted_date}. Contactez le support Vesta dès "
                "aujourd'hui pour la renouveler."
            )
        else:
            title = f"{club_name} : licence à renouveler dans {days_remaining} jours"
            body = (
                f"La licence Vesta de {club_name} expire le "
                f"{formatted_date}, dans {days_remaining} jours. "
                "Contactez le support Vesta pour la renouveler."
            )

    if grace_period_days == 0:
        grace_phrase = "dès le lendemain de cette date"
    elif grace_period_days == 1:
        grace_phrase = "1 jour après cette date"
    else:
        grace_phrase = f"{grace_period_days} jours après cette date"
    body = (
        f"{body} Sans renouvellement, le club passera en lecture seule "
        f"{grace_phrase} : les données resteront consultables et "
        "exportables."
    )

    return title, body


def process_licence_reminders(*, now=None) -> dict[str, int]:
    """Relance le President a 30, 7 et 1 jour avant l'expiration (CDC 1.4 ;
    tache 1.8).

    Idempotente : une seule relance par palier et par licence, grace au
    marqueur ``LicenceEvent(event_type=reminder_sent,
    note="reminder:<jours>")`` -- choix documente ici (alternative
    possible : un champ dedie sur `Licence`, ecarte pour ne pas alourdir
    ce modele d'un champ purement operationnel alors que `LicenceEvent`
    existe deja pour exactement cet usage, schema §4.6 : « Relances 30/7/1
    jour = `reminder_sent` »).

    Inclut les licences `TRIAL` et `ACTIVE` (memes considerations que
    :func:`process_licence_expirations`) ; exclut EXPIRED/SUSPENDED/
    TERMINATED (relancer une licence deja hors d'usage n'a pas de sens).

    Omet silencieusement la notification si le club n'a actuellement
    aucun President en poste (cas limite, meme choix que
    `apps.clubs.services._active_president_membership`) -- le marqueur
    `LicenceEvent` est neanmoins toujours pose pour rester idempotent.

    N'ecrit aucune `AuditLog` (voir :func:`process_licence_expirations`
    pour la justification complete : aucun acteur reel).
    """

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    now = now or timezone.now()
    today = now.date()

    reminders_sent = 0

    candidates = Licence.objects.select_related("club").filter(
        status__in=[Licence.Status.ACTIVE, Licence.Status.TRIAL]
    )
    for licence in candidates:
        days_remaining = (licence.end_date - today).days
        if days_remaining not in REMINDER_THRESHOLDS_DAYS:
            continue

        marker = f"reminder:{days_remaining}"
        already_sent = LicenceEvent.objects.filter(
            licence=licence, event_type=LicenceEvent.EventType.REMINDER_SENT, note=marker
        ).exists()
        if already_sent:
            continue

        president_membership = _active_president_membership(licence.club)

        LicenceEvent.objects.create(
            licence=licence,
            event_type=LicenceEvent.EventType.REMINDER_SENT,
            event_date=now,
            actor=None,
            note=marker,
        )

        if president_membership is not None:
            title, message = _build_licence_reminder_text(
                club_name=licence.club.name,
                days_remaining=days_remaining,
                end_date=licence.end_date,
                grace_period_days=licence.grace_period_days,
                is_trial=licence.status == Licence.Status.TRIAL,
            )
            create_notification(
                recipient=president_membership.user,
                event_type=Notification.EventType.LICENCE_EXPIRING,
                title=title,
                message=message,
                club=licence.club,
                target=licence,
                now=now,
            )

        reminders_sent += 1

    return {"reminders_sent": reminders_sent}


# ---------------------------------------------------------------------------
# Sessions de support / Ghost Mode (CDC 4.18, 5.4)
# ---------------------------------------------------------------------------


def start_support_session(*, superuser, club, reason: str, now=None) -> SupportSession:
    """Ouvre une session de support en Ghost Mode (CDC 4.18 : « bouton
    "Intervenir sur ce club" avec un motif obligatoire [...] dure 60
    minutes au plus »).

    Journalise avec l'identite REELLE du Superuser et `acted_as_ghost=False` :
    ouvrir la session elle-meme est un acte administratif du Superuser
    envers la plateforme, pas encore une action FAITE DANS le club au nom
    de « Systeme Vesta » (CDC 5.4) -- cette distinction n'a d'effet que
    sur l'affichage cote club ; l'identite reelle est de toute facon
    toujours conservee dans le journal (CDC 5.4).
    """

    now = now or timezone.now()
    _require_superuser(superuser, message="Seul un Superuser peut ouvrir une session de support (CDC 4.18).")
    if not (reason or "").strip():
        raise SupportSessionError("Le motif de la session de support est obligatoire (CDC 4.18).")

    session = SupportSession.objects.create(club=club, superuser=superuser, reason=reason, started_at=now)

    log_action(
        actor=superuser,
        club=club,
        action_type="licence.support_session.started",
        obj=session,
        after={"club_id": club.id, "expires_at": session.expires_at},
        acted_as_ghost=False,
        support_session_id="",
    )
    return session


def end_support_session(*, session: SupportSession, superuser, now=None) -> SupportSession:
    """Fin anticipee d'une session de support (schema §13.1 : `ended_at`).

    Reservee au MEME Superuser que celui qui l'a ouverte -- decision par
    defaut appliquee ici (le CDC ne tranche pas explicitement ce cas
    precis) : un autre Superuser qui voudrait clore la session d'un
    collegue doit passer par un autre moyen (support technique interne),
    jamais par ce point d'entree, pour que la responsabilite de chaque
    session reste claire et non ambigue dans le journal. A confirmer par
    le client (voir compte rendu).
    """

    now = now or timezone.now()
    _require_superuser(superuser, message="Seul un Superuser peut clore une session de support (CDC 4.18).")
    if session.superuser_id != superuser.id:
        raise SupportSessionPermissionError(
            "Seul le Superuser ayant ouvert cette session de support peut la clore par anticipation."
        )
    if session.ended_at is not None:
        raise SupportSessionError("Cette session de support est deja terminee.")

    session.ended_at = now
    session.save(update_fields=["ended_at"])

    log_action(
        actor=superuser,
        club=session.club,
        action_type="licence.support_session.ended",
        obj=session,
        after={"ended_at": session.ended_at},
        acted_as_ghost=False,
        support_session_id="",
    )
    return session


def is_support_session_valid(session: SupportSession, *, now=None) -> bool:
    """Vrai si ``session`` est actuellement utilisable pour agir en Ghost
    Mode (schema §13.1 : ``[started_at, expires_at ou ended_at]``).

    Utilise par `apps.core.authentication.TenantJWTAuthentication` (arme
    le Ghost Mode sur chaque requete) et par :func:`enter_ghost_mode`
    ci-dessous.
    """

    now = now or timezone.now()
    upper_bound = session.ended_at if session.ended_at is not None else session.expires_at
    return session.started_at <= now < upper_bound


def enter_ghost_mode(*, session: SupportSession, superuser, now=None):
    """Gestionnaire de contexte qui arme le Ghost Mode pour ``session``
    (CDC 5.4), reutilisable hors requete HTTP (tests, futurs appels
    programmatiques) -- exactement le meme mecanisme que celui applique
    automatiquement par `apps.core.authentication.TenantJWTAuthentication`
    sur chaque requete Superuser porteuse d'un en-tete `X-Support-Session`
    valide : club actif restreint au SEUL club de ``session``
    (`apps.core.tenant.active_club`) et contexte Ghost Mode arme
    (`apps.core.ghost_context.ghost_mode`), tous deux remis a zero en
    sortie, y compris en cas d'exception (composition directe des deux
    gestionnaires de contexte existants -- rien n'est reinvente).

    Leve :class:`SupportSessionPermissionError` si ``session`` n'appartient
    pas a ``superuser``, ou :class:`SupportSessionError` si elle n'est
    plus valide (expiree ou terminee) -- **avant** d'armer quoi que ce
    soit, pour qu'un appelant ne puisse jamais, meme par erreur, agir au
    nom d'une session qui ne lui appartient pas ou qui n'est plus active.

    Usage ::

        with enter_ghost_mode(session=session, superuser=superuser):
            ...  # tout code execute ici est restreint a `session.club`
    """

    if session.superuser_id != getattr(superuser, "id", None):
        raise SupportSessionPermissionError("Cette session de support n'appartient pas a ce Superuser.")
    if not is_support_session_valid(session, now=now):
        raise SupportSessionError("Cette session de support n'est plus valide (expiree ou terminee).")

    return _enter_ghost_mode_contexts(session)


def _enter_ghost_mode_contexts(session: SupportSession):
    """Compose les deux gestionnaires de contexte existants (club actif +
    Ghost Mode) en un seul, sans en creer un troisieme mecanisme."""

    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(_active_club_context(session.club))
    stack.enter_context(_ghost_mode_context(str(session.pk)))
    return stack
