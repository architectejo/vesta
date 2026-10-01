"""Serializers DRF de l'app social (CDC 4.16 ; fil-public-communication.md).

Rappel §0.3 (jamais affiche sur ces pages) : aucun poids, taille,
telephone, email, date de naissance, solde, montant, information medicale
ou d'aptitude, aucun ``StatusBadge`` de joueur -- seulement avatar, prenom,
nom, et pour le fil, nom/logo du club. Ces serializers n'exposent QUE ces
champs pour un auteur/commentateur/expediteur.
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import serializers

from apps.social.models import (
    Announcement,
    AnnouncementImage,
    ChatChannel,
    ChatMessage,
    Comment,
    Like,
    Post,
    PostImage,
    PostReport,
)


def _author_summary(user, request) -> dict:
    photo_url = None
    if getattr(user, "photo", None):
        try:
            photo_url = request.build_absolute_uri(user.photo.url) if request else user.photo.url
        except ValueError:
            photo_url = None
    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "avatar_url": photo_url,
    }


class PostImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = PostImage
        fields = ["id", "order", "url"]
        read_only_fields = fields

    def get_url(self, obj: PostImage) -> str | None:
        if not obj.file:
            return None
        if obj.post.visibility == Post.Visibility.PUBLIC:
            request = self.context.get("request")
            url = obj.file.url
            return request.build_absolute_uri(url) if request else url
        # Point de securite critique (voir docstring apps.social.models) :
        # une image de publication « Club » n'est JAMAIS exposee via
        # `MEDIA_URL`, uniquement via la vue de telechargement authentifiee.
        return reverse("social:post-image-download", kwargs={"pk": obj.pk})


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "post_id", "author", "body", "created_at"]
        read_only_fields = fields

    def get_author(self, obj: Comment) -> dict:
        return _author_summary(obj.author, self.context.get("request"))


class PostSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    club_name = serializers.CharField(source="club.name", read_only=True)
    images = PostImageSerializer(many=True, read_only=True)
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    is_liked_by_me = serializers.SerializerMethodField()
    recent_comments = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    is_reported_by_me = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "author",
            "club_id",
            "club_name",
            "body",
            "visibility",
            "post_kind",
            "created_at",
            "images",
            "like_count",
            "comment_count",
            "is_liked_by_me",
            "recent_comments",
            "can_delete",
            "is_reported_by_me",
        ]
        read_only_fields = fields

    def get_author(self, obj: Post) -> dict:
        return _author_summary(obj.author, self.context.get("request"))

    def get_like_count(self, obj: Post) -> int:
        return obj.likes.count()

    def get_comment_count(self, obj: Post) -> int:
        return obj.comments.filter(deleted_at__isnull=True).count()

    def _me(self):
        request = self.context.get("request")
        return getattr(request, "user", None) if request else None

    def get_is_liked_by_me(self, obj: Post) -> bool:
        user = self._me()
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return Like.objects.filter(post=obj, user=user).exists()

    def get_is_reported_by_me(self, obj: Post) -> bool:
        user = self._me()
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return PostReport.objects.filter(post=obj, reported_by=user).exists()

    def get_recent_comments(self, obj: Post) -> list:
        comments = obj.comments.filter(deleted_at__isnull=True).order_by("-created_at")[:2]
        return CommentSerializer(reversed(list(comments)), many=True, context=self.context).data

    def get_can_delete(self, obj: Post) -> bool:
        from apps.social.services import can_delete_post

        user = self._me()
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return can_delete_post(user=user, post=obj)


class PostCreateInputSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    visibility = serializers.ChoiceField(choices=Post.Visibility.choices)
    images = serializers.ListField(child=serializers.ImageField(), required=False, default=list)


class CommentCreateInputSerializer(serializers.Serializer):
    body = serializers.CharField(allow_blank=False, max_length=1000)


class ReportPostInputSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class AnnouncementImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = AnnouncementImage
        fields = ["id", "order", "url"]
        read_only_fields = fields

    def get_url(self, obj: AnnouncementImage) -> str | None:
        if not obj.file:
            return None
        # Toujours privee (un communique n'est jamais public, matrice 2.4) :
        # jamais une adresse `MEDIA_URL`, uniquement la vue authentifiee.
        return reverse("social:announcement-image-download", kwargs={"pk": obj.pk})


class AnnouncementSerializer(serializers.ModelSerializer):
    published_by = serializers.SerializerMethodField()
    images = AnnouncementImageSerializer(many=True, read_only=True)
    is_read_by_me = serializers.SerializerMethodField()
    read_summary = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = [
            "id",
            "title",
            "body",
            "published_by",
            "published_at",
            "pinned",
            "expires_at",
            "images",
            "is_read_by_me",
            "read_summary",
        ]
        read_only_fields = fields

    def get_published_by(self, obj: Announcement) -> dict:
        return _author_summary(obj.published_by, self.context.get("request"))

    def get_is_read_by_me(self, obj: Announcement) -> bool:
        membership = self.context.get("membership")
        if membership is None:
            return False
        return obj.reads.filter(membership=membership).exists()

    def get_read_summary(self, obj: Announcement) -> dict | None:
        if not self.context.get("can_manage"):
            return None
        from apps.social.services import get_announcement_read_summary

        return get_announcement_read_summary(obj)


class AnnouncementCreateInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    body = serializers.CharField()
    images = serializers.ListField(child=serializers.ImageField(), required=False, default=list)
    pinned = serializers.BooleanField(required=False, default=True)


class ChatMessageSerializer(serializers.ModelSerializer):
    sender = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ["id", "channel_id", "sender", "body", "image_url", "sent_at"]
        read_only_fields = fields

    def get_sender(self, obj: ChatMessage) -> dict:
        return _author_summary(obj.sender, self.context.get("request"))

    def get_image_url(self, obj: ChatMessage) -> str | None:
        if not obj.image:
            return None
        # Point de securite critique : toujours une vue authentifiee,
        # jamais `MEDIA_URL` (voir docstring apps.social.models).
        return reverse("social:chat-message-image-download", kwargs={"pk": obj.pk})


class ChatMessageCreateInputSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")
    image = serializers.ImageField(required=False, allow_null=True, default=None)


class ChatChannelSerializer(serializers.ModelSerializer):
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatChannel
        fields = ["id", "channel_type", "unread_count", "last_message"]
        read_only_fields = fields

    def get_unread_count(self, obj: ChatChannel) -> int:
        membership = self.context.get("membership")
        if membership is None:
            return 0
        from apps.social.services import get_unread_count

        return get_unread_count(channel=obj, membership=membership)

    def get_last_message(self, obj: ChatChannel) -> dict | None:
        message = obj.messages.order_by("-sent_at").first()
        if message is None:
            return None
        return ChatMessageSerializer(message, context=self.context).data
