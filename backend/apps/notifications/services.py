"""Regles metier de l'app notifications (CDC 4.17, 6.5 ; tache 1.7).

Point d'entree unique utilise par tous les autres modules (deja
consomme par ``apps.clubs.services`` pour les quatre evenements produits
par le Lot 1 -- nomination/revocation, fiche a signer, rappel/refus du
parrain) :

- :func:`create_notification` cree TOUJOURS la notification en base ;
  elle decide, a partir du type d'evenement (canal attendu, table CDC
  4.17) et de la preference de l'utilisateur, si un envoi email doit
  etre mis EN FILE -- jamais envoye ici (CDC 6.5 : « les actions qui
  envoient des emails ne font qu'enregistrer l'envoi ; la tache cron
  l'execute »).
- :func:`send_pending_notification_emails` est la fonction appelee par
  la commande de gestion ``send_notification_emails`` (elle-meme
  appelee par le cron, hors perimetre de cette tache -- voir
  ``devops-cpanel``) : c'est la SEULE fonction de ce module qui envoie
  reellement un email.
"""

from __future__ import annotations

from typing import Any, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.notifications.models import Notification, NotificationPreference

__all__ = [
    "create_notification",
    "get_or_create_preference",
    "set_email_preference",
    "mark_notification_read",
    "mark_all_notifications_read",
    "unread_count",
    "send_pending_notification_emails",
]

# Evenements a double canal (in-app + email, CDC 4.17). Tous les autres
# evenements de `Notification.EventType` restent in-app seulement. Cette
# liste couvre TOUT le tableau CDC 4.17 (pas seulement les evenements
# deja cables par cette tache) : elle sert de reference stable pour les
# futurs modules qui emettront ces evenements (sport/medical/mercato/
# assemblies/licences, hors perimetre de la tache 1.7 elle-meme).
EMAIL_CHANNEL_EVENT_TYPES = frozenset(
    {
        Notification.EventType.PAYMENT_VALIDATED,
        Notification.EventType.TRANSFER_OFFER,
        Notification.EventType.ASSEMBLY_CONVENED,
        Notification.EventType.LICENCE_EXPIRING,
    }
)

# Sentinelle distincte de `None` : `club=None` est une valeur legitime
# (notification de portee plateforme, sans club de rattachement -- voir
# docstring de `Notification`), alors que "parametre omis" doit deduire
# le club depuis `target` quand c'est possible. Meme principe que
# `apps.core.services.log_action`.
_CLUB_NOT_PROVIDED = object()


def get_or_create_preference(user) -> NotificationPreference:
    """Renvoie la preference email de ``user``, creee avec sa valeur par
    defaut (``email_enabled=True``) si elle n'existe pas encore (CDC
    4.17 ; schema §11.2)."""

    preference, _created = NotificationPreference.objects.get_or_create(user=user)
    return preference


def set_email_preference(*, user, email_enabled: bool) -> NotificationPreference:
    """Modifie la preference email globale de ``user`` (onglet « Informations »
    de la modale Mon profil, tache 1.9 -- consomme cet endpoint via
    ``apps.notifications.views``)."""

    preference = get_or_create_preference(user)
    preference.email_enabled = bool(email_enabled)
    preference.save()
    return preference


def create_notification(
    *,
    recipient,
    event_type: str,
    message: str,
    title: Optional[str] = None,
    club: Any = _CLUB_NOT_PROVIDED,
    target=None,
    now=None,
) -> Notification:
    """Cree une ``Notification`` en base (jamais d'envoi email direct, CDC 6.5).

    Parametres :

    - ``recipient`` : l'utilisateur destinataire (``accounts.User``).
    - ``event_type`` : une valeur de ``Notification.EventType`` (une
      ligne du tableau CDC 4.17).
    - ``message`` : le texte pret a afficher, en francais clair
      (CLAUDE.md regle n20) -- stocke dans ``Notification.body``.
    - ``title`` : titre court affiche dans la liste (CDC 3.4, 4.17). Si
      omis, deduit automatiquement du libelle de ``event_type`` (evite
      toute duplication du meme titre a chaque appelant).
    - ``club`` : club de rattachement. Si **omis**, deduit de
      ``target.club`` quand ``target`` porte un tel champ (le cas de
      tous les appelants actuels -- une adhesion, un dossier
      d'adhesion...) ; reste ``None`` sinon (notification de portee
      plateforme). Passer explicitement ``club=None`` pour forcer une
      notification sans club, meme si ``target`` en porte un.
    - ``target`` : l'objet concerne, dont un clic sur la notification
      doit mener (CDC 4.17 : « mene a l'element concerne ») --
      ``link_object_type``/``link_object_id`` en sont deduits
      (``target.__class__.__name__``, ``target.pk``), meme principe que
      ``apps.core.services.log_action``. Facultatif : certains
      evenements de portee plateforme n'ont pas de cible unique.

    Decide elle-meme, a partir du canal attendu pour ``event_type``
    (:data:`EMAIL_CHANNEL_EVENT_TYPES`) ET de la preference email du
    destinataire (:func:`get_or_create_preference`), si un envoi email
    doit etre mis en file (``email_requested=True``,
    ``email_status=PENDING``) -- jamais envoye ici.
    """

    now = now or timezone.now()

    resolved_club = club
    if resolved_club is _CLUB_NOT_PROVIDED:
        resolved_club = getattr(target, "club", None)

    resolved_title = title
    if resolved_title is None:
        resolved_title = Notification.EventType(event_type).label

    link_object_type = ""
    link_object_id = None
    if target is not None:
        link_object_type = target.__class__.__name__
        link_object_id = target.pk

    email_channel = event_type in EMAIL_CHANNEL_EVENT_TYPES
    email_requested = False
    if email_channel:
        preference = get_or_create_preference(recipient)
        email_requested = preference.email_enabled

    email_status = Notification.EmailStatus.PENDING if email_requested else Notification.EmailStatus.NOT_APPLICABLE

    return Notification.objects.create(
        club=resolved_club,
        recipient=recipient,
        event_type=event_type,
        title=resolved_title,
        body=message,
        link_object_type=link_object_type,
        link_object_id=link_object_id,
        email_requested=email_requested,
        email_status=email_status,
        created_at=now,
    )


def mark_notification_read(*, notification: Notification, user, now=None) -> Notification:
    """Marque ``notification`` comme lue. Reserve a son destinataire
    (defense en profondeur : la vue filtre deja sur ``recipient=request.user``,
    meme principe que les autres controles « revalides cote service » du
    projet, ex. ``apps.accounts.services.reset_password_by_superuser``)."""

    if notification.recipient_id != getattr(user, "id", None):
        raise PermissionError("Seul le destinataire peut marquer sa propre notification comme lue.")

    if notification.is_read:
        return notification

    now = now or timezone.now()
    notification.is_read = True
    notification.read_at = now
    notification.save(update_fields=["is_read", "read_at"])
    return notification


def mark_all_notifications_read(*, user, now=None) -> int:
    """« Tout marquer comme lu » (CDC 4.17). Renvoie le nombre de notifications
    modifiees."""

    now = now or timezone.now()
    return Notification.objects.filter(recipient=user, is_read=False).update(is_read=True, read_at=now)


def unread_count(*, user) -> int:
    """Compteur affiche sur l'icone cloche (CDC 4.17)."""

    return Notification.objects.filter(recipient=user, is_read=False).count()


def send_pending_notification_emails(*, now=None) -> dict[str, int]:
    """Envoie les emails en file (CDC 6.5 : traitement cron, jamais dans une
    requete). Appelee par la commande de gestion
    ``send_notification_emails`` (elle-meme appelee par le cron -- le
    branchement reel du crontab reste hors perimetre de cette tache,
    ``devops-cpanel`` a la mise en production, meme limite que
    ``process_sponsor_reminders``).

    Pas de nouvelle tentative automatique pour un envoi ``FAILED`` dans
    cette tache (point ouvert signale au compte rendu) : seules les
    entrees ``PENDING`` sont traitees a chaque execution.
    """

    now = now or timezone.now()
    sent = 0
    failed = 0

    pending = Notification.objects.filter(email_status=Notification.EmailStatus.PENDING).select_related("recipient")
    for notification in pending:
        recipient_email = getattr(notification.recipient, "email", "") or ""
        try:
            if not recipient_email:
                raise ValueError("Le destinataire n'a pas d'adresse email.")
            send_mail(
                subject=notification.title,
                message=notification.body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or None,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
        except Exception:  # noqa: BLE001 - toute erreur d'envoi marque l'echec, ne bloque pas les suivantes
            notification.email_status = Notification.EmailStatus.FAILED
            notification.save(update_fields=["email_status"])
            failed += 1
            continue

        notification.email_status = Notification.EmailStatus.SENT
        notification.email_sent_at = now
        notification.save(update_fields=["email_status", "email_sent_at"])
        sent += 1

    return {"sent": sent, "failed": failed}
