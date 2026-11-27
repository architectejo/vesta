"""Vues DRF de l'app social (CDC 4.16 ; tache 4.6).

Orchestrent uniquement : permission -> service -> serializer (CLAUDE.md
section 5). Toute regle metier vit dans ``apps.social.services``.

Point de securite critique (rappel) : ``PostImageDownloadView`` et
``ChatMessageImageDownloadView`` sont les vues authentifiees qui servent
les images qui NE sont PAS sur le stockage public (voir docstring de
``apps.social.models``) -- jamais atteignables via ``MEDIA_URL``.
"""

from __future__ import annotations

from typing import Optional

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.models import Membership
from apps.clubs.permissions import IsActiveClubMember
from apps.core.private_files import private_file_response
from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence
from apps.core.roles import is_ghost_read_access
from apps.core.services import resolve_active_membership
from apps.core.tenant import get_active_club
from apps.social import serializers as ser
from apps.social import services
from apps.social.models import Announcement, AnnouncementImage, ChatChannel, ChatMessage, Comment, Post, PostImage
from apps.social.permissions import CanManageAnnouncements

_GATE = [IsAuthenticated, HasCompletedPasswordSetup, HasAcceptedLatestTerms, HasUsableLicence]

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50

_POST_NOT_FOUND = "Cette publication n'existe plus."
_COMMENT_NOT_FOUND = "Ce commentaire n'existe pas."
_ANNOUNCEMENT_NOT_FOUND = "Ce communiqué n'existe pas dans ce club."
_CHANNEL_NOT_FOUND = "Ce canal n'existe pas dans ce club."
_CHAT_MESSAGE_NOT_FOUND = "Ce message n'existe pas dans ce club."
_INTERACTION_RESTRICTED = (
    "Commenter, aimer et signaler restent pour l'instant réservés aux publications de votre "
    "propre club, y compris quand la publication est Publique (restriction technique provisoire, "
    "voir apps.social.services.can_interact_with_post)."
)


def _not_found(message: str) -> Response:
    return Response({"detail": message}, status=status.HTTP_404_NOT_FOUND)


def _social_error_response(exc: services.SocialError) -> Response:
    if isinstance(exc, services.SocialPermissionError):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _paginate(request, queryset):
    try:
        limit = int(request.query_params.get("limit", DEFAULT_PAGE_SIZE))
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError):
        limit, offset = DEFAULT_PAGE_SIZE, 0
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    count = queryset.count()
    items = list(queryset[offset : offset + limit])
    next_offset = offset + limit if offset + limit < count else None
    return items, count, next_offset


def _own_membership(request) -> Optional[Membership]:
    """Adhésion du lecteur dans le club actif ; ``None`` pour un Superuser en
    lecture pendant une session de support (Ghost Mode : pas de fiche joueur,
    donc ni accusé de lecture ni compteur de non-lus)."""

    if is_ghost_read_access(request):
        return None
    return resolve_active_membership(request.user, club=get_active_club())


# ---------------------------------------------------------------------------
# Fil d'actualite (PARTIE A)
# ---------------------------------------------------------------------------


class PostListCreateView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        scope = request.query_params.get("portee", "mon_club")
        queryset = services.get_visible_posts(active_club=get_active_club(), scope=scope)
        items, count, next_offset = _paginate(request, queryset)
        data = ser.PostSerializer(items, many=True, context={"request": request}).data
        return Response({"results": data, "count": count, "next_offset": next_offset})

    def post(self, request):
        serializer = ser.PostCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            post = services.create_post(
                club=get_active_club(),
                actor=request.user,
                body=data.get("body", ""),
                visibility=data["visibility"],
                images=data.get("images", []),
            )
        except services.SocialError as exc:
            return _social_error_response(exc)

        return Response(ser.PostSerializer(post, context={"request": request}).data, status=status.HTTP_201_CREATED)


def _get_post_or_404(pk):
    try:
        return Post.all_objects.select_related("club", "author").get(pk=pk, deleted_at__isnull=True)
    except Post.DoesNotExist:
        return None


class PostDetailView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        post = _get_post_or_404(pk)
        if post is None or not services.can_read_post(user=request.user, post=post, active_club=get_active_club()):
            # Etancheite entre clubs (meme convention que le reste du
            # projet, ex. apps.clubs.tests.test_views_private_files) :
            # une publication « Club » d'un autre club repond 404, jamais
            # 403 -- son existence meme n'est pas confirmee a un tiers.
            return _not_found(_POST_NOT_FOUND)
        return Response(ser.PostSerializer(post, context={"request": request}).data)


class PostDeleteView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def delete(self, request, pk):
        post = _get_post_or_404(pk)
        if post is None:
            return _not_found(_POST_NOT_FOUND)
        try:
            services.delete_post(post=post, actor=request.user)
        except services.SocialError as exc:
            return _social_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PostLikeToggleView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def post(self, request, pk):
        post = _get_post_or_404(pk)
        if post is None or not services.can_read_post(user=request.user, post=post, active_club=get_active_club()):
            return _not_found(_POST_NOT_FOUND)
        if not services.can_interact_with_post(user=request.user, post=post, active_club=get_active_club()):
            return Response({"detail": _INTERACTION_RESTRICTED}, status=status.HTTP_403_FORBIDDEN)
        try:
            liked = services.toggle_like(post=post, actor=request.user, active_club=get_active_club())
        except services.SocialError as exc:
            return _social_error_response(exc)
        return Response({"liked": liked, "like_count": post.likes.count()})


class PostCommentListCreateView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        post = _get_post_or_404(pk)
        if post is None or not services.can_read_post(user=request.user, post=post, active_club=get_active_club()):
            return _not_found(_POST_NOT_FOUND)

        queryset = Comment.all_objects.filter(club=post.club, post=post, deleted_at__isnull=True).order_by("-created_at")
        items, count, next_offset = _paginate(request, queryset)
        items = list(reversed(items))
        data = ser.CommentSerializer(items, many=True, context={"request": request}).data
        return Response({"results": data, "count": count, "next_offset": next_offset})

    def post(self, request, pk):
        post = _get_post_or_404(pk)
        if post is None or not services.can_read_post(user=request.user, post=post, active_club=get_active_club()):
            return _not_found(_POST_NOT_FOUND)
        if not services.can_interact_with_post(user=request.user, post=post, active_club=get_active_club()):
            return Response({"detail": _INTERACTION_RESTRICTED}, status=status.HTTP_403_FORBIDDEN)
        serializer = ser.CommentCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            comment = services.add_comment(
                post=post, actor=request.user, body=serializer.validated_data["body"], active_club=get_active_club()
            )
        except services.SocialError as exc:
            return _social_error_response(exc)

        return Response(
            ser.CommentSerializer(comment, context={"request": request}).data, status=status.HTTP_201_CREATED
        )


class CommentDeleteView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def delete(self, request, pk):
        # `all_objects` (pas `objects`) : l'autorisation reelle est
        # entierement verifiee par le service (auteur ou President du club
        # d'origine de la publication) -- ce filtre ne fait que recuperer
        # la ligne, jamais un raccourci de securite.
        try:
            comment = Comment.all_objects.select_related("post", "post__club").get(pk=pk, deleted_at__isnull=True)
        except Comment.DoesNotExist:
            return _not_found(_COMMENT_NOT_FOUND)
        try:
            services.delete_comment(comment=comment, actor=request.user)
        except services.SocialError as exc:
            return _social_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PostReportView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def post(self, request, pk):
        post = _get_post_or_404(pk)
        if post is None or not services.can_read_post(user=request.user, post=post, active_club=get_active_club()):
            return _not_found(_POST_NOT_FOUND)
        if not services.can_interact_with_post(user=request.user, post=post, active_club=get_active_club()):
            return Response({"detail": _INTERACTION_RESTRICTED}, status=status.HTTP_403_FORBIDDEN)
        serializer = ser.ReportPostInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            services.report_post(
                post=post,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
                active_club=get_active_club(),
            )
        except services.SocialError as exc:
            return _social_error_response(exc)

        return Response({"detail": "Merci. La publication a été signalée à l'équipe Vesta."}, status=status.HTTP_201_CREATED)


class PostImageDownloadView(APIView):
    """Vue authentifiee pour une image de publication « Club » (point de
    securite critique, jamais une adresse `MEDIA_URL`)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            image = PostImage.objects.select_related("post", "post__club").get(pk=pk)
        except PostImage.DoesNotExist:
            return _not_found("Cette image n'existe pas dans ce club.")

        if image.post.visibility == Post.Visibility.PUBLIC:
            # Ne devrait jamais arriver (voir get_url du serializer) : une
            # image publique n'est jamais servie par cette vue -- filet de
            # securite, pas un chemin normal.
            return _not_found("Cette image n'existe pas dans ce club.")

        if not services.can_read_post(user=request.user, post=image.post, active_club=get_active_club()):
            return Response({"detail": "Vous n'avez pas accès à cette image."}, status=status.HTTP_403_FORBIDDEN)

        return private_file_response(image.file, download_stem=f"image-{image.pk}", as_attachment=False)


# ---------------------------------------------------------------------------
# Communiques (PARTIE B)
# ---------------------------------------------------------------------------


class AnnouncementListCreateView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        club = get_active_club()
        membership = _own_membership(request)
        can_manage = CanManageAnnouncements().has_permission(request, self)
        context = {"request": request, "membership": membership, "can_manage": can_manage}

        pinned_only = request.query_params.get("pinned") == "true"
        queryset = Announcement.objects.filter(club=club)
        if pinned_only:
            queryset = queryset.filter(pinned=True)
        items, count, next_offset = _paginate(request, queryset)
        data = ser.AnnouncementSerializer(items, many=True, context=context).data
        return Response({"results": data, "count": count, "next_offset": next_offset})

    def post(self, request):
        if not CanManageAnnouncements().has_permission(request, self):
            return Response({"detail": CanManageAnnouncements.message}, status=status.HTTP_403_FORBIDDEN)
        serializer = ser.AnnouncementCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            announcement = services.create_announcement(
                club=get_active_club(),
                actor=request.user,
                title=data["title"],
                body=data["body"],
                images=data.get("images", []),
                pinned=data.get("pinned", True),
            )
        except services.SocialError as exc:
            return _social_error_response(exc)

        context = {"request": request, "membership": _own_membership(request), "can_manage": True}
        return Response(ser.AnnouncementSerializer(announcement, context=context).data, status=status.HTTP_201_CREATED)


def _get_announcement_or_404(pk):
    try:
        return Announcement.objects.get(pk=pk)
    except Announcement.DoesNotExist:
        return None


class AnnouncementDetailView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        announcement = _get_announcement_or_404(pk)
        if announcement is None:
            return _not_found(_ANNOUNCEMENT_NOT_FOUND)
        can_manage = CanManageAnnouncements().has_permission(request, self)
        context = {"request": request, "membership": _own_membership(request), "can_manage": can_manage}
        return Response(ser.AnnouncementSerializer(announcement, context=context).data)


class AnnouncementReadView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def post(self, request, pk):
        announcement = _get_announcement_or_404(pk)
        if announcement is None:
            return _not_found(_ANNOUNCEMENT_NOT_FOUND)
        try:
            services.mark_announcement_read(announcement=announcement, membership=_own_membership(request))
        except services.SocialError as exc:
            return _social_error_response(exc)
        return Response({"detail": "Lecture confirmée."})


class AnnouncementPinView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def patch(self, request, pk):
        if not CanManageAnnouncements().has_permission(request, self):
            return Response({"detail": CanManageAnnouncements.message}, status=status.HTTP_403_FORBIDDEN)
        announcement = _get_announcement_or_404(pk)
        if announcement is None:
            return _not_found(_ANNOUNCEMENT_NOT_FOUND)
        pinned = bool(request.data.get("pinned", not announcement.pinned))
        announcement = services.set_announcement_pinned(announcement=announcement, actor=request.user, pinned=pinned)
        return Response({"pinned": announcement.pinned})


class AnnouncementReadReceiptsView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        if not CanManageAnnouncements().has_permission(request, self):
            return Response({"detail": CanManageAnnouncements.message}, status=status.HTTP_403_FORBIDDEN)
        announcement = _get_announcement_or_404(pk)
        if announcement is None:
            return _not_found(_ANNOUNCEMENT_NOT_FOUND)

        read_membership_ids = set(announcement.reads.values_list("membership_id", flat=True))
        memberships = Membership.objects.filter(club=announcement.club, status=Membership.Status.ACTIVE).select_related("user")
        view_filter = request.query_params.get("filter", "unread")
        results = []
        for membership in memberships:
            is_read = membership.id in read_membership_ids
            if view_filter == "read" and not is_read:
                continue
            if view_filter == "unread" and is_read:
                continue
            results.append(
                {
                    "membership_id": membership.id,
                    "first_name": membership.user.first_name,
                    "last_name": membership.user.last_name,
                    "read": is_read,
                }
            )
        return Response({"results": results, **services.get_announcement_read_summary(announcement)})


class AnnouncementImageDownloadView(APIView):
    """Vue authentifiee pour une image de communique : toujours privee
    (un communique n'est jamais public, matrice 2.4), jamais une adresse
    `MEDIA_URL` (point de securite critique, meme principe que
    ``PostImageDownloadView``)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            image = AnnouncementImage.objects.select_related("announcement").get(pk=pk)
        except AnnouncementImage.DoesNotExist:
            return _not_found("Cette image n'existe pas dans ce club.")
        return private_file_response(image.file, download_stem=f"image-{image.pk}", as_attachment=False)


# ---------------------------------------------------------------------------
# Chat d'equipe (PARTIE C)
# ---------------------------------------------------------------------------


def _chat_reader(request, membership: Optional[Membership]) -> services.ChatReader:
    """Droit de lecture des messages reserves (10.3 n° 182), calcule UNE fois
    par requete (le statut « En ordre » est calcule a la lecture)."""

    return services.get_chat_reader(user=request.user, club=get_active_club(), membership=membership)


class ChatChannelListView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        club = get_active_club()
        services.ensure_channels(club)
        membership = _own_membership(request)
        reader = _chat_reader(request, membership)
        channels = [c for c in ChatChannel.objects.filter(club=club) if services.can_access_channel(user=request.user, channel=c)]
        data = ser.ChatChannelSerializer(
            channels, many=True, context={"request": request, "membership": membership, "reader": reader}
        ).data
        return Response({"results": data})


def _get_channel_or_404(pk, *, user):
    try:
        channel = ChatChannel.objects.get(pk=pk)
    except ChatChannel.DoesNotExist:
        return None
    if not services.can_access_channel(user=user, channel=channel):
        return None
    return channel


class ChatMessageListCreateView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        channel = _get_channel_or_404(pk, user=request.user)
        if channel is None:
            return _not_found(_CHANNEL_NOT_FOUND)

        reader = _chat_reader(request, _own_membership(request))
        queryset = services.filter_readable_messages(
            ChatMessage.objects.filter(channel=channel).select_related("sender"), reader=reader
        )
        after = request.query_params.get("after")
        if after:
            try:
                queryset = queryset.filter(id__gt=int(after)).order_by("sent_at", "id")
            except ValueError:
                pass
            items = list(queryset)
            count = len(items)
            next_offset = None
        else:
            queryset = queryset.order_by("-sent_at", "-id")
            items, count, next_offset = _paginate(request, queryset)
            items = list(reversed(items))

        data = ser.ChatMessageSerializer(items, many=True, context={"request": request}).data
        return Response({"results": data, "count": count, "next_offset": next_offset})

    def post(self, request, pk):
        channel = _get_channel_or_404(pk, user=request.user)
        if channel is None:
            return _not_found(_CHANNEL_NOT_FOUND)

        serializer = ser.ChatMessageCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            message = services.send_chat_message(
                channel=channel,
                actor=request.user,
                body=data.get("body", ""),
                image=data.get("image"),
                members_in_order_only=data.get("members_in_order_only", False),
            )
        except services.SocialError as exc:
            return _social_error_response(exc)

        return Response(
            ser.ChatMessageSerializer(message, context={"request": request}).data, status=status.HTTP_201_CREATED
        )


class ChatChannelReadView(APIView):
    permission_classes = _GATE + [IsActiveClubMember]

    def post(self, request, pk):
        channel = _get_channel_or_404(pk, user=request.user)
        if channel is None:
            return _not_found(_CHANNEL_NOT_FOUND)

        membership = _own_membership(request)
        # Un message reserve que le lecteur ne peut pas lire n'est jamais pris
        # comme dernier lu (10.3 n° 182).
        readable = services.filter_readable_messages(
            ChatMessage.objects.filter(channel=channel), reader=_chat_reader(request, membership)
        )
        message = None
        last_read_message_id = request.data.get("last_read_message_id")
        if last_read_message_id:
            message = readable.filter(pk=last_read_message_id).first()
        else:
            message = readable.order_by("-sent_at", "-id").first()

        services.mark_channel_read(channel=channel, membership=membership, message=message)
        return Response({"detail": "ok"})


class ChatMessageImageDownloadView(APIView):
    """Vue authentifiee pour une image de chat (point de securite critique,
    TOUJOURS privee, meme canal General -- voir docstring de
    apps.social.models). Un message reserve aux membres en ordre que le
    lecteur ne peut pas lire repond 404, comme un message inexistant
    (10.3 n° 182 : le message est absent pour lui)."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            message = ChatMessage.objects.select_related("channel").get(pk=pk)
        except ChatMessage.DoesNotExist:
            return _not_found(_CHAT_MESSAGE_NOT_FOUND)

        if not message.image:
            return _not_found("Cette image n'existe pas.")

        if not services.can_access_channel(user=request.user, channel=message.channel):
            return Response({"detail": "Vous n'avez plus accès à ce canal."}, status=status.HTTP_403_FORBIDDEN)

        if not services.can_read_message(message=message, reader=_chat_reader(request, _own_membership(request))):
            return _not_found(_CHAT_MESSAGE_NOT_FOUND)

        return private_file_response(message.image, download_stem=f"image-{message.pk}", as_attachment=False)
