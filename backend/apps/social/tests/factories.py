"""Factories factory_boy de l'app social (tache 4.6)."""

from __future__ import annotations

import io

import factory
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.tests.factories import UserFactory
from apps.clubs.tests.factories import ClubFactory
from apps.core.tests.factories import TenantDjangoModelFactory
from apps.social.models import Announcement, ChatChannel, ChatMessage, Comment, Post, PostImage


def _make_tiny_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


TINY_PNG = _make_tiny_png()


def uploaded_image(name: str = "image.png"):
    """Fichier image pret pour un champ modele valide par
    ``apps.core.validators.validate_image_format`` (qui exige l'attribut
    ``image`` pose par ``forms.ImageField.to_python`` -- voir sa docstring).
    Un ``ContentFile``/``SimpleUploadedFile`` brut, jamais passe par ce
    nettoyage, echoue toujours cette validation : necessaire pour tout
    test qui appelle un service directement (sans passer par le
    serializer DRF, qui fait ce travail a la frontiere API)."""

    upload = SimpleUploadedFile(name, TINY_PNG, content_type="image/png")
    return forms.ImageField().clean(upload)


class PostFactory(TenantDjangoModelFactory):
    class Meta:
        model = Post

    club = factory.SubFactory(ClubFactory)
    author = factory.SubFactory(UserFactory)
    body = "Une publication de test."
    visibility = Post.Visibility.CLUB_ONLY


class PostImageFactory(TenantDjangoModelFactory):
    class Meta:
        model = PostImage

    club = factory.SelfAttribute("post.club")
    post = factory.SubFactory(PostFactory)
    order = 1
    file = factory.LazyFunction(lambda: uploaded_image())


class CommentFactory(TenantDjangoModelFactory):
    class Meta:
        model = Comment

    club = factory.SelfAttribute("post.club")
    post = factory.SubFactory(PostFactory)
    author = factory.SubFactory(UserFactory)
    body = "Un commentaire de test."


class AnnouncementFactory(TenantDjangoModelFactory):
    class Meta:
        model = Announcement

    club = factory.SubFactory(ClubFactory)
    title = "Un communique de test"
    body = "Corps du communique."
    published_by = factory.SubFactory(UserFactory)


class ChatChannelFactory(TenantDjangoModelFactory):
    class Meta:
        model = ChatChannel

    club = factory.SubFactory(ClubFactory)
    channel_type = ChatChannel.ChannelType.GENERAL


class ChatMessageFactory(TenantDjangoModelFactory):
    class Meta:
        model = ChatMessage

    club = factory.SelfAttribute("channel.club")
    channel = factory.SubFactory(ChatChannelFactory)
    sender = factory.SubFactory(UserFactory)
    body = "Un message de test."
