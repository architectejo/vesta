"""Tests HTTP de l'app social (CDC 4.16 ; tache 4.6).

Couvre en particulier le POINT DE SECURITE CRITIQUE remonte pour cette
tache (fil-public-communication.md, point ouvert F.13 ; contradiction avec
schema-donnees.md §1.1 qui classe `Image` comme un asset public par
conception) : une image de publication « Club » et une image du chat
(y compris le canal General) ne sont JAMAIS servies par une adresse
`MEDIA_URL` publique -- uniquement par une vue authentifiee qui verifie le
club (et, pour le canal Bureau, le role). Voir
``TestPostImagePublicVsPrivateSecurity`` et
``TestChatMessageImageSecurity`` ci-dessous.
"""

from __future__ import annotations

from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

import pytest

from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubFactory, MembershipFactory, MembershipRoleFactory
from apps.social.models import ChatChannel, Post
from apps.social.tests.factories import (
    TINY_PNG,
    AnnouncementFactory,
    ChatChannelFactory,
    ChatMessageFactory,
    PostFactory,
    PostImageFactory,
    uploaded_image,
)

pytestmark = pytest.mark.django_db


def _authenticated_client(user) -> APIClient:
    client = APIClient()
    access_token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    return client


def _png_upload(name="image.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, TINY_PNG, content_type="image/png")


def _body(response) -> bytes:
    return b"".join(response.streaming_content)


# ---------------------------------------------------------------------------
# Fil d'actualite
# ---------------------------------------------------------------------------


class TestPostCreateAndList:
    def test_create_a_public_post_with_an_image(self):
        club = ClubFactory()
        author = MembershipFactory(club=club)

        response = _authenticated_client(author.user).post(
            reverse("social:post-list"),
            {"body": "Bonjour !", "visibility": "public", "images": [_png_upload()]},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["visibility"] == "public"
        assert len(response.data["images"]) == 1

    def test_create_refuses_without_text_or_image(self):
        club = ClubFactory()
        author = MembershipFactory(club=club)

        response = _authenticated_client(author.user).post(
            reverse("social:post-list"), {"visibility": "club_only"}, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_mon_club_scope_is_the_default(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        member_a = MembershipFactory(club=club_a)
        MembershipFactory(club=club_b)
        PostFactory(club=club_a, visibility=Post.Visibility.PUBLIC, body="A")
        PostFactory(club=club_b, visibility=Post.Visibility.PUBLIC, body="B")

        response = _authenticated_client(member_a.user).get(reverse("social:post-list"))

        assert response.status_code == status.HTTP_200_OK
        bodies = {row["body"] for row in response.data["results"]}
        assert bodies == {"A"}

    def test_tous_scope_includes_public_posts_of_other_clubs(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        member_a = MembershipFactory(club=club_a)
        MembershipFactory(club=club_b)
        PostFactory(club=club_b, visibility=Post.Visibility.PUBLIC, body="Public B")
        PostFactory(club=club_b, visibility=Post.Visibility.CLUB_ONLY, body="Prive B")

        response = _authenticated_client(member_a.user).get(reverse("social:post-list"), {"portee": "tous"})

        bodies = {row["body"] for row in response.data["results"]}
        assert "Public B" in bodies
        assert "Prive B" not in bodies

    def test_a_club_only_post_of_another_club_is_not_found(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        member_a = MembershipFactory(club=club_a)
        post_b = PostFactory(club=club_b, visibility=Post.Visibility.CLUB_ONLY)

        response = _authenticated_client(member_a.user).get(reverse("social:post-detail", kwargs={"pk": post_b.pk}))

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPostDeleteLikeCommentReport:
    def test_author_can_delete_own_post(self):
        club = ClubFactory()
        author = MembershipFactory(club=club)
        post = PostFactory(club=club, author=author.user, visibility=Post.Visibility.CLUB_ONLY)

        response = _authenticated_client(author.user).delete(reverse("social:post-delete", kwargs={"pk": post.pk}))

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_like_toggle(self):
        club = ClubFactory()
        member = MembershipFactory(club=club)
        post = PostFactory(club=club, visibility=Post.Visibility.CLUB_ONLY)
        client = _authenticated_client(member.user)
        url = reverse("social:post-like", kwargs={"pk": post.pk})

        first = client.post(url)
        second = client.post(url)

        assert first.data["liked"] is True
        assert second.data["liked"] is False

    def test_comment_then_delete(self):
        club = ClubFactory()
        member = MembershipFactory(club=club)
        post = PostFactory(club=club, visibility=Post.Visibility.CLUB_ONLY)
        client = _authenticated_client(member.user)

        create = client.post(reverse("social:post-comments", kwargs={"pk": post.pk}), {"body": "Bravo"}, format="json")
        assert create.status_code == status.HTTP_201_CREATED

        delete = client.delete(reverse("social:comment-delete", kwargs={"pk": create.data["id"]}))
        assert delete.status_code == status.HTTP_204_NO_CONTENT

    def test_report_notifies_and_second_report_is_rejected(self):
        club = ClubFactory()
        member = MembershipFactory(club=club)
        post = PostFactory(club=club, visibility=Post.Visibility.CLUB_ONLY)
        client = _authenticated_client(member.user)
        url = reverse("social:post-report", kwargs={"pk": post.pk})

        first = client.post(url, {"reason": "Propos deplaces"}, format="json")
        second = client.post(url, {"reason": "Encore"}, format="json")

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# POINT DE SECURITE CRITIQUE : image publique vs image privee
# ---------------------------------------------------------------------------


class TestPostImagePublicVsPrivateSecurity:
    def test_public_post_image_is_exposed_on_the_public_media_path(self):
        club = ClubFactory()
        member = MembershipFactory(club=club)
        post = PostFactory(club=club, visibility=Post.Visibility.PUBLIC)
        image = PostImageFactory(post=post, club=club)

        response = _authenticated_client(member.user).get(reverse("social:post-detail", kwargs={"pk": post.pk}))

        url = response.data["images"][0]["url"]
        assert url is not None
        assert django_settings.MEDIA_URL in url

    def test_club_only_post_image_is_never_exposed_on_the_public_media_path(self):
        club = ClubFactory()
        member = MembershipFactory(club=club)
        post = PostFactory(club=club, visibility=Post.Visibility.CLUB_ONLY)
        image = PostImageFactory(post=post, club=club)

        response = _authenticated_client(member.user).get(reverse("social:post-detail", kwargs={"pk": post.pk}))

        url = response.data["images"][0]["url"]
        assert url is not None
        assert django_settings.MEDIA_URL not in url
        assert url == reverse("social:post-image-download", kwargs={"pk": image.pk})

    def test_club_only_post_image_download_requires_authentication(self):
        club = ClubFactory()
        post = PostFactory(club=club, visibility=Post.Visibility.CLUB_ONLY)
        image = PostImageFactory(post=post, club=club)

        response = APIClient().get(reverse("social:post-image-download", kwargs={"pk": image.pk}))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_club_only_post_image_download_is_not_found_for_another_club(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        member_a = MembershipFactory(club=club_a)
        post_b = PostFactory(club=club_b, visibility=Post.Visibility.CLUB_ONLY)
        image_b = PostImageFactory(post=post_b, club=club_b)

        response = _authenticated_client(member_a.user).get(
            reverse("social:post-image-download", kwargs={"pk": image_b.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_club_only_post_image_download_succeeds_for_a_club_member(self):
        club = ClubFactory()
        member = MembershipFactory(club=club)
        post = PostFactory(club=club, visibility=Post.Visibility.CLUB_ONLY)
        image = PostImageFactory(post=post, club=club)

        response = _authenticated_client(member.user).get(
            reverse("social:post-image-download", kwargs={"pk": image.pk})
        )

        assert response.status_code == status.HTTP_200_OK
        assert _body(response)


class TestChatMessageImageSecurity:
    """Le chat n'a aucune notion de visibilite Publique : TOUTE image de
    chat (canal General inclus) est privee (point de securite critique)."""

    @pytest.mark.parametrize("channel_type", [ChatChannel.ChannelType.GENERAL, ChatChannel.ChannelType.BOARD])
    def test_chat_image_is_never_exposed_on_the_public_media_path(self, channel_type):
        club = ClubFactory()
        member = MembershipFactory(club=club)
        if channel_type == ChatChannel.ChannelType.BOARD:
            MembershipRoleFactory(membership=member, role=MembershipRole.Role.PRESIDENT)
        channel = ChatChannelFactory(club=club, channel_type=channel_type)
        message = ChatMessageFactory(channel=channel, club=club, sender=member.user, body="", image=uploaded_image("photo.png"))

        response = _authenticated_client(member.user).get(
            reverse("social:chat-message-list", kwargs={"pk": channel.pk})
        )

        assert response.status_code == status.HTTP_200_OK
        image_url = response.data["results"][0]["image_url"]
        assert image_url is not None
        assert django_settings.MEDIA_URL not in image_url
        assert image_url == reverse("social:chat-message-image-download", kwargs={"pk": message.pk})

    def test_chat_image_download_requires_authentication(self):
        club = ClubFactory()
        channel = ChatChannelFactory(club=club, channel_type=ChatChannel.ChannelType.GENERAL)
        message = ChatMessageFactory(channel=channel, club=club, body="", image=uploaded_image("photo.png"))

        response = APIClient().get(reverse("social:chat-message-image-download", kwargs={"pk": message.pk}))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_board_channel_image_is_hidden_from_a_non_board_member(self):
        club = ClubFactory()
        board = ChatChannelFactory(club=club, channel_type=ChatChannel.ChannelType.BOARD)
        coach = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach, role=MembershipRole.Role.COACH)
        sender = MembershipFactory(club=club)
        MembershipRoleFactory(membership=sender, role=MembershipRole.Role.PRESIDENT)
        message = ChatMessageFactory(channel=board, club=club, sender=sender.user, body="", image=uploaded_image("photo.png"))

        response = _authenticated_client(coach.user).get(
            reverse("social:chat-message-image-download", kwargs={"pk": message.pk})
        )
        missing = _authenticated_client(coach.user).get(
            reverse("social:chat-message-image-download", kwargs={"pk": message.pk + 10_000})
        )

        # Même réponse qu'un identifiant inexistant : l'existence d'un message du
        # canal du bureau n'est jamais révélée (audit de sécurité du 27/11/2026).
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data == missing.data

    def test_board_channel_image_succeeds_for_a_board_member(self):
        club = ClubFactory()
        board = ChatChannelFactory(club=club, channel_type=ChatChannel.ChannelType.BOARD)
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        message = ChatMessageFactory(channel=board, club=club, sender=president.user, body="", image=uploaded_image("photo.png"))

        response = _authenticated_client(president.user).get(
            reverse("social:chat-message-image-download", kwargs={"pk": message.pk})
        )

        assert response.status_code == status.HTTP_200_OK
        assert _body(response)


# ---------------------------------------------------------------------------
# Chat : canaux, permissions, envoi
# ---------------------------------------------------------------------------


class TestChatChannels:
    def test_channel_list_never_shows_the_board_channel_to_a_plain_player(self):
        club = ClubFactory()
        player = MembershipFactory(club=club)

        response = _authenticated_client(player.user).get(reverse("social:chat-channel-list"))

        types = {row["channel_type"] for row in response.data["results"]}
        assert types == {"general"}

    def test_channel_list_shows_both_channels_to_the_president(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)

        response = _authenticated_client(president.user).get(reverse("social:chat-channel-list"))

        types = {row["channel_type"] for row in response.data["results"]}
        assert types == {"general", "board"}

    def test_a_coach_cannot_post_in_the_board_channel(self):
        club = ClubFactory()
        coach = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach, role=MembershipRole.Role.COACH)
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        # Le canal Bureau doit exister avant le test (creation paresseuse).
        _authenticated_client(president.user).get(reverse("social:chat-channel-list"))
        from apps.social.models import ChatChannel as _ChatChannel

        board = _ChatChannel.all_objects.get(club=club, channel_type=_ChatChannel.ChannelType.BOARD)

        response = _authenticated_client(coach.user).post(
            reverse("social:chat-message-list", kwargs={"pk": board.pk}), {"body": "Salut"}, format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_general_channel_send_and_read(self):
        club = ClubFactory()
        member = MembershipFactory(club=club)
        client = _authenticated_client(member.user)
        channels = client.get(reverse("social:chat-channel-list")).data["results"]
        general_id = next(c["id"] for c in channels if c["channel_type"] == "general")

        send = client.post(
            reverse("social:chat-message-list", kwargs={"pk": general_id}), {"body": "Salut l'equipe"}, format="json"
        )
        assert send.status_code == status.HTTP_201_CREATED

        read = client.post(reverse("social:chat-channel-read", kwargs={"pk": general_id}), {}, format="json")
        assert read.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Communiques
# ---------------------------------------------------------------------------


class TestAnnouncements:
    def test_president_publishes_and_player_reads(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        player = MembershipFactory(club=club)

        publish = _authenticated_client(president.user).post(
            reverse("social:announcement-list"), {"title": "Titre", "body": "Corps"}, format="multipart"
        )
        assert publish.status_code == status.HTTP_201_CREATED
        announcement_id = publish.data["id"]

        read = _authenticated_client(player.user).post(
            reverse("social:announcement-read", kwargs={"pk": announcement_id}), {}, format="json"
        )
        assert read.status_code == status.HTTP_200_OK

    def test_a_plain_player_cannot_publish_an_announcement(self):
        club = ClubFactory()
        player = MembershipFactory(club=club)

        response = _authenticated_client(player.user).post(
            reverse("social:announcement-list"), {"title": "Titre", "body": "Corps"}, format="multipart"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_read_receipts_reserved_to_president_and_vp(self):
        club = ClubFactory()
        announcement = AnnouncementFactory(club=club)
        player = MembershipFactory(club=club)

        response = _authenticated_client(player.user).get(
            reverse("social:announcement-read-receipts", kwargs={"pk": announcement.pk})
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_pin_toggle(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        announcement = AnnouncementFactory(club=club, pinned=True)

        response = _authenticated_client(president.user).patch(
            reverse("social:announcement-pin", kwargs={"pk": announcement.pk}), {"pinned": False}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["pinned"] is False

    def test_announcement_image_is_always_private_and_authenticated(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president, role=MembershipRole.Role.PRESIDENT)
        player = MembershipFactory(club=club)

        publish = _authenticated_client(president.user).post(
            reverse("social:announcement-list"),
            {"title": "Titre", "body": "Corps", "images": [_png_upload()]},
            format="multipart",
        )
        assert publish.status_code == status.HTTP_201_CREATED, publish.data
        image_url = publish.data["images"][0]["url"]
        assert django_settings.MEDIA_URL not in image_url
        assert image_url == reverse("social:announcement-image-download", kwargs={"pk": publish.data["images"][0]["id"]})

        unauthenticated = APIClient().get(image_url)
        assert unauthenticated.status_code == status.HTTP_401_UNAUTHORIZED

        authenticated = _authenticated_client(player.user).get(image_url)
        assert authenticated.status_code == status.HTTP_200_OK
