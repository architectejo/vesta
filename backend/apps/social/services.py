"""Regles metier de l'app social : fil, communiques, chat (CDC 4.16 ;
tache 4.6).

Sources : docs/lot0/schema-donnees.md §10 ; docs/ecrans/fil-public-communication.md ;
10.2 n° 12, 16, 23 ; CLAUDE.md regles n° 6, n° 8, n° 9, n° 10.

Point de securite critique (images publiques/privees) : voir la docstring
de ``apps.social.models`` -- ce module ne fait qu'orchestrer la creation
des ``PostImage``/``ChatMessage.image``, le choix de stockage lui-meme
est fait par ``PostImage.save()``/le champ ``storage=private_storage`` de
``ChatMessage``.

Perimetre non construit ici (signale au compte rendu, comme les autres
points d'integration en attente du projet, ex. ``apps.sport.services``
pour le medical) : les publications automatiques (``post_kind`` =
``auto_result``/``auto_transfer``/``auto_new_player``) ne sont pas
declenchees par ce module -- elles supposent une integration depuis
``apps.sport``/``apps.mercato``, hors perimetre de la tache 4.6
(fil-public-communication.md ne les detaille pas non plus, elles sont
citees comme decrites ailleurs : sport-feuille-de-match.md §4.6 pour les
resultats).
"""

from __future__ import annotations

from typing import Optional

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.clubs.models import Membership, MembershipRole
from apps.core.private_files import rename_upload_to_real_type
from apps.core.roles import has_any_role
from apps.core.services import log_action
from apps.social.models import (
    Announcement,
    AnnouncementImage,
    AnnouncementRead,
    ChatChannel,
    ChatChannelRead,
    ChatMessage,
    Comment,
    Like,
    Post,
    PostImage,
    PostReport,
)
from apps.social.permissions import BOARD_CHANNEL_ROLES

__all__ = [
    "SocialError",
    "SocialValidationError",
    "SocialPermissionError",
    "MAX_POST_IMAGES",
    "create_post",
    "delete_post",
    "can_read_post",
    "can_interact_with_post",
    "get_visible_posts",
    "add_comment",
    "delete_comment",
    "toggle_like",
    "report_post",
    "create_announcement",
    "mark_announcement_read",
    "set_announcement_pinned",
    "get_announcement_read_summary",
    "ensure_channels",
    "can_access_channel",
    "send_chat_message",
    "mark_channel_read",
    "get_unread_count",
]

MAX_POST_IMAGES = 4
MAX_ANNOUNCEMENT_IMAGES = 4


class SocialError(Exception):
    """Racine des erreurs metier de l'app social."""


class SocialValidationError(SocialError):
    """Donnee ou etat invalide (traduite en 400 par les vues)."""


class SocialPermissionError(SocialError, PermissionError):
    """Action refusee malgre un role a priori suffisant."""


# ---------------------------------------------------------------------------
# Fil d'actualite (fil-public-communication.md, PARTIE A)
# ---------------------------------------------------------------------------


def create_auto_result_post(*, club, actor, body: str) -> Post:
    """Publication automatique du résultat d'un match (CDC 4.8).

    Visibilité « Club » : jamais publique sans consentement (10.2 n° 160).
    L'appelant (``apps.sport.services``) est responsable de la règle
    « une seule publication par match » et de la journalisation métier.
    """

    return Post.all_objects.create(
        club=club,
        author=actor,
        body=(body or "").strip(),
        visibility=Post.Visibility.CLUB_ONLY,
        post_kind=Post.PostKind.AUTO_RESULT,
    )


def create_post(*, club, actor, body: str, visibility: str, images: Optional[list] = None, now=None) -> Post:
    now = now or timezone.now()
    body = (body or "").strip()
    images = images or []

    if not body and not images:
        raise SocialValidationError("Écrivez un texte ou ajoutez au moins une image.")
    if len(images) > MAX_POST_IMAGES:
        raise SocialValidationError("4 images au maximum.")
    if visibility not in Post.Visibility.values:
        raise SocialValidationError("Visibilité invalide.")

    with transaction.atomic():
        post = Post.all_objects.create(
            club=club,
            author=actor,
            body=body,
            visibility=visibility,
            post_kind=Post.PostKind.MANUAL,
        )
        for index, uploaded in enumerate(images, start=1):
            rename_upload_to_real_type(uploaded)
            PostImage.all_objects.create(club=club, post=post, file=uploaded, order=index)

    log_action(
        actor=actor,
        club=club,
        action_type="social.post.created",
        obj=post,
        after={"visibility": post.visibility, "image_count": len(images)},
    )
    return post


def can_delete_post(*, user, post: Post) -> bool:
    if post.author_id == getattr(user, "id", None):
        return True
    return has_any_role(user, {MembershipRole.Role.PRESIDENT}, club=post.club)


def delete_post(*, post: Post, actor, now=None) -> Post:
    now = now or timezone.now()
    if not can_delete_post(user=actor, post=post):
        raise SocialPermissionError("Vous n'êtes pas autorisé à supprimer cette publication.")
    if post.deleted_at is not None:
        return post

    post.deleted_by = actor
    post.deleted_at = now
    post.save()

    log_action(
        actor=actor,
        club=post.club,
        action_type="social.post.deleted",
        obj=post,
        before={"deleted_at": None},
        after={"deleted_at": str(now)},
    )
    return post


def can_read_post(*, user, post: Post, active_club) -> bool:
    if post.visibility == Post.Visibility.PUBLIC:
        return True
    return post.club_id == getattr(active_club, "id", None)


def can_interact_with_post(*, user, post: Post, active_club) -> bool:
    """Commenter, aimer, signaler (CDC 4.16, §A2 : « tous ceux qui peuvent
    lire la publication », donc en principe y compris un lecteur d'un
    AUTRE club sur une publication Publique).

    Restriction PROVISOIRE, plus stricte que la lecture (CLAUDE.md
    section 1 : en cas de contradiction entre une regle metier et une
    regle de securite non negociable, position la plus prudente tant que
    le client n'a pas tranche) : ``Comment``/``Like``/``PostReport``
    portent un champ ``club`` obligatoire (schema-donnees.md §10.1/§10.4,
    « copie depuis le club de l'entite parente » pour ``PostReport``), et
    ``apps.core.models.TenantModel.save()`` refuse TOUJOURS d'ecrire une
    ligne dont ``club`` differe du club actif du contexte courant (ecart
    bloquant B4 du Lot 1, CLAUDE.md regle n8 -- garde-fou de securite non
    negociable, jamais affaibli ici). Ecrire ``club=post.club`` pour un
    commentaire/like/signalement sur une publication PUBLIQUE d'un AUTRE
    club leverait donc systematiquement ``TenantMismatchError``.

    Position appliquee ici : interagir (commenter/aimer/signaler) reste
    reserve aux publications du club actif de l'acteur -- que la
    publication soit Publique ou Club -- jusqu'a ce que le client tranche
    entre (a) autoriser reellement l'interaction inter-clubs (ce qui
    demanderait de revoir le garde-fou ``TenantModel.save()`` lui-meme,
    hors perimetre d'une tache Lot 4) et (b) confirmer cette restriction.
    La LECTURE cross-club (:func:`can_read_post`), elle, n'est pas
    concernee : aucune ecriture n'y est associee."""

    return post.club_id == getattr(active_club, "id", None)


def get_visible_posts(*, active_club, scope: str):
    """Publications visibles selon le filtre (§A3) :

    - ``mon_club`` (defaut) : publications de mon club, publiques et
      reservees ;
    - ``tous`` : publications publiques de tous les clubs (y compris les
      miennes) ET les publications reservees de MON club -- jamais les
      publications reservees d'un autre club (§A2).

    Utilise ``Post.all_objects`` (echappement documente du manager
    tenant-aware, CLAUDE.md regle n° 8 : meme principe que
    ``TransferOffer``/``MercatoThread``, exception §1.2 du schema pour
    les entites explicitement multi-clubs) -- le filtre explicite ci-
    dessous reste la SEULE porte d'entree, jamais un `.all()` nu."""

    base = Post.all_objects.filter(deleted_at__isnull=True)
    if scope == "tous":
        from django.db.models import Q

        return base.filter(Q(visibility=Post.Visibility.PUBLIC) | Q(club=active_club)).order_by("-created_at")
    return base.filter(club=active_club).order_by("-created_at")


def add_comment(*, post: Post, actor, body: str, active_club, now=None) -> Comment:
    now = now or timezone.now()
    if not can_interact_with_post(user=actor, post=post, active_club=active_club):
        raise SocialPermissionError("Vous n'avez pas accès à cette publication.")
    body = (body or "").strip()
    if not body:
        raise SocialValidationError("Écrivez un commentaire.")

    comment = Comment.all_objects.create(club=post.club, post=post, author=actor, body=body)
    log_action(actor=actor, club=post.club, action_type="social.comment.created", obj=comment)
    return comment


def can_delete_comment(*, user, comment: Comment) -> bool:
    if comment.author_id == getattr(user, "id", None):
        return True
    return has_any_role(user, {MembershipRole.Role.PRESIDENT}, club=comment.post.club)


def delete_comment(*, comment: Comment, actor, now=None) -> Comment:
    now = now or timezone.now()
    if not can_delete_comment(user=actor, comment=comment):
        raise SocialPermissionError("Vous n'êtes pas autorisé à supprimer ce commentaire.")
    if comment.deleted_at is not None:
        return comment

    comment.deleted_by = actor
    comment.deleted_at = now
    comment.save()

    log_action(
        actor=actor,
        club=comment.club,
        action_type="social.comment.deleted",
        obj=comment,
        before={"deleted_at": None},
        after={"deleted_at": str(now)},
    )
    return comment


def toggle_like(*, post: Post, actor, active_club, now=None) -> bool:
    """Bascule le « J'aime » (CDC 4.16). Renvoie ``True`` si le like existe
    desormais (ajoute), ``False`` s'il vient d'etre retire."""

    now = now or timezone.now()
    if not can_interact_with_post(user=actor, post=post, active_club=active_club):
        raise SocialPermissionError("Vous n'avez pas accès à cette publication.")

    like = Like.all_objects.filter(post=post, user=actor).first()
    if like is not None:
        like.delete()
        log_action(actor=actor, club=post.club, action_type="social.like.removed", obj=post)
        return False

    Like.all_objects.create(club=post.club, post=post, user=actor)
    log_action(actor=actor, club=post.club, action_type="social.like.added", obj=post)
    return True


def report_post(*, post: Post, actor, reason: str, active_club, now=None) -> PostReport:
    """Signalement (CDC 4.16 ; 10.2 n° 23, decide) : notifie le Superuser et
    journalise ``social.post.reported`` (schema §10.4). Une seule fois par
    personne (proposition, point ouvert F.3)."""

    now = now or timezone.now()
    if not can_interact_with_post(user=actor, post=post, active_club=active_club):
        raise SocialPermissionError("Vous n'avez pas accès à cette publication.")

    try:
        with transaction.atomic():
            report = PostReport.all_objects.create(
                club=post.club, post=post, reported_by=actor, reason=(reason or "").strip()
            )
    except (IntegrityError, DjangoValidationError):
        # `IntegrityError` (contrainte DB) ou `ValidationError` (verifiee
        # plus tot par `full_clean()`, appele par `TenantModel.save()`
        # avant meme d'atteindre le moteur de base de donnees) : les deux
        # traduisent la meme violation de la contrainte unique
        # ``(post, reported_by)`` (10.2 n° 23, proposition point ouvert F.3).
        raise SocialValidationError("Vous avez déjà signalé cette publication.") from None

    log_action(
        actor=actor,
        club=post.club,
        action_type="social.post.reported",
        obj=post,
        after={"reason": report.reason},
    )
    _notify_superusers_of_report(post=post, report=report, now=now)
    return report


def _notify_superusers_of_report(*, post: Post, report: PostReport, now) -> None:
    from apps.accounts.models import User
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    message = f"Publication signalée dans le club {post.club.name}"
    for superuser in User.objects.filter(is_superuser=True):
        create_notification(
            recipient=superuser,
            event_type=Notification.EventType.POST_REPORTED,
            message=message,
            club=None,
            target=post,
            now=now,
        )


# ---------------------------------------------------------------------------
# Communiques (fil-public-communication.md, PARTIE B)
# ---------------------------------------------------------------------------


def create_announcement(
    *, club, actor, title: str, body: str, images: Optional[list] = None, pinned: bool = True, now=None
) -> Announcement:
    now = now or timezone.now()
    title = (title or "").strip()
    body = (body or "").strip()
    images = images or []

    if not title:
        raise SocialValidationError("Ce champ est obligatoire.")
    if not body:
        raise SocialValidationError("Ce champ est obligatoire.")
    if len(images) > MAX_ANNOUNCEMENT_IMAGES:
        raise SocialValidationError("4 images au maximum.")

    with transaction.atomic():
        announcement = Announcement.all_objects.create(
            club=club, title=title, body=body, published_by=actor, pinned=bool(pinned)
        )
        for index, uploaded in enumerate(images, start=1):
            rename_upload_to_real_type(uploaded)
            AnnouncementImage.all_objects.create(club=club, announcement=announcement, file=uploaded, order=index)

    log_action(
        actor=actor,
        club=club,
        action_type="social.announcement.published",
        obj=announcement,
        after={"title": announcement.title, "pinned": announcement.pinned},
    )
    _notify_all_active_members_of_announcement(club, announcement, now=now)
    return announcement


def _notify_all_active_members_of_announcement(club, announcement: Announcement, *, now) -> None:
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    message = f"Nouveau communiqué : {announcement.title}"
    memberships = Membership.all_objects.filter(club=club, status=Membership.Status.ACTIVE).select_related("user")
    for membership in memberships:
        create_notification(
            recipient=membership.user,
            event_type=Notification.EventType.ANNOUNCEMENT_PUBLISHED,
            message=message,
            club=club,
            target=announcement,
            now=now,
        )


def mark_announcement_read(*, announcement: Announcement, membership: Membership, now=None) -> AnnouncementRead:
    now = now or timezone.now()
    if membership.club_id != announcement.club_id:
        raise SocialPermissionError("Vous n'avez pas accès à ce communiqué.")

    read, created = AnnouncementRead.all_objects.get_or_create(
        club=announcement.club, announcement=announcement, membership=membership, defaults={"read_at": now}
    )
    if created:
        log_action(
            actor=membership.user,
            club=announcement.club,
            action_type="social.announcement.read",
            obj=read,
            after={"membership_id": membership.id},
        )
    return read


def set_announcement_pinned(*, announcement: Announcement, actor, pinned: bool, now=None) -> Announcement:
    now = now or timezone.now()
    before = {"pinned": announcement.pinned}
    announcement.pinned = bool(pinned)
    announcement.save()

    log_action(
        actor=actor,
        club=announcement.club,
        action_type="social.announcement.pin_toggled",
        obj=announcement,
        before=before,
        after={"pinned": announcement.pinned},
    )
    return announcement


def get_announcement_read_summary(announcement: Announcement) -> dict:
    total = Membership.all_objects.filter(club=announcement.club, status=Membership.Status.ACTIVE).count()
    read_count = AnnouncementRead.all_objects.filter(club=announcement.club, announcement=announcement).count()
    return {"read_count": read_count, "total": total}


# ---------------------------------------------------------------------------
# Chat d'equipe (fil-public-communication.md, PARTIE C)
# ---------------------------------------------------------------------------


def ensure_channels(club) -> tuple[ChatChannel, ChatChannel]:
    """Garantit l'existence des deux canaux fixes du club (schema §10.3 :
    « crees a la creation du club »). Creation paresseuse ici (decision
    technique, signalee au compte rendu) plutot qu'un hook sur
    ``apps.clubs.club_creation`` -- idempotent, sans effet si les canaux
    existent deja."""

    general, _ = ChatChannel.all_objects.get_or_create(club=club, channel_type=ChatChannel.ChannelType.GENERAL)
    board, _ = ChatChannel.all_objects.get_or_create(club=club, channel_type=ChatChannel.ChannelType.BOARD)
    return general, board


def can_access_channel(*, user, channel: ChatChannel) -> bool:
    if channel.channel_type == ChatChannel.ChannelType.BOARD:
        return has_any_role(user, BOARD_CHANNEL_ROLES, club=channel.club)
    return True


def send_chat_message(*, channel: ChatChannel, actor, body: str = "", image=None, now=None) -> ChatMessage:
    now = now or timezone.now()
    if not can_access_channel(user=actor, channel=channel):
        raise SocialPermissionError("Vous n'avez pas accès à ce canal.")

    body = (body or "").strip()
    if not body and not image:
        raise SocialValidationError("Écrivez un message ou ajoutez une image.")

    if image:
        rename_upload_to_real_type(image)
    message = ChatMessage.all_objects.create(club=channel.club, channel=channel, sender=actor, body=body, image=image)
    log_action(
        actor=actor,
        club=channel.club,
        action_type="social.chat_message.sent",
        obj=message,
        after={"channel_type": channel.channel_type, "has_image": bool(image)},
    )
    return message


def mark_channel_read(*, channel: ChatChannel, membership: Membership, message: Optional[ChatMessage], now=None) -> ChatChannelRead:
    now = now or timezone.now()
    read, _created = ChatChannelRead.all_objects.get_or_create(
        club=channel.club, channel=channel, membership=membership, defaults={"last_read_message": message}
    )
    if message is not None and (read.last_read_message_id is None or message.id > read.last_read_message_id):
        read.last_read_message = message
        read.save()
    return read


def get_unread_count(*, channel: ChatChannel, membership: Membership) -> int:
    read = ChatChannelRead.all_objects.filter(club=channel.club, channel=channel, membership=membership).first()
    queryset = ChatMessage.all_objects.filter(club=channel.club, channel=channel)
    if read is not None and read.last_read_message_id is not None:
        queryset = queryset.filter(id__gt=read.last_read_message_id)
    return queryset.count()
