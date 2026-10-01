"""Tests de `apps.social.services` (CDC 4.16 ; tache 4.6)."""

from __future__ import annotations

import pytest
from django.core.files.storage import default_storage

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubFactory, MembershipFactory, MembershipRoleFactory
from apps.core.storage import private_storage
from apps.core.tenant import active_club
from apps.notifications.models import Notification
from apps.social import services
from apps.social.models import Announcement, ChatChannel, Post, PostImage
from apps.social.tests.factories import AnnouncementFactory, ChatChannelFactory, PostFactory, uploaded_image

pytestmark = pytest.mark.django_db


def _image(name="image.png"):
    return uploaded_image(name)


class TestCreatePost:
    def test_refuses_a_post_without_text_or_image(self):
        club = ClubFactory()
        author = MembershipFactory(club=club).user

        with active_club(club):
            with pytest.raises(services.SocialValidationError, match="texte"):
                services.create_post(club=club, actor=author, body="", visibility=Post.Visibility.CLUB_ONLY)

    def test_refuses_more_than_four_images(self):
        club = ClubFactory()
        author = MembershipFactory(club=club).user
        images = [_image(f"{i}.png") for i in range(5)]

        with active_club(club):
            with pytest.raises(services.SocialValidationError, match="4 images"):
                services.create_post(
                    club=club, actor=author, body="Texte", visibility=Post.Visibility.CLUB_ONLY, images=images
                )

    def test_creates_a_post_and_journalises_it(self):
        club = ClubFactory()
        author = MembershipFactory(club=club).user

        with active_club(club):
            post = services.create_post(club=club, actor=author, body="Bonjour le club", visibility=Post.Visibility.PUBLIC)

        assert post.body == "Bonjour le club"
        assert AuditLog.objects.filter(action_type="social.post.created").exists()


class TestPostImageStorageSecurity:
    """Point de securite critique (fil-public-communication.md, point ouvert
    F.13) : une image de publication PUBLIQUE reste sur le stockage public
    existant ; une image de publication CLUB bascule vers le stockage
    prive -- jamais l'inverse."""

    def test_public_post_image_uses_the_public_storage(self):
        club = ClubFactory()
        author = MembershipFactory(club=club).user

        with active_club(club):
            post = services.create_post(
                club=club, actor=author, body="Texte", visibility=Post.Visibility.PUBLIC, images=[_image()]
            )

        image = post.images.first()
        assert image.file.storage is default_storage
        assert image.file.url  # ne leve jamais (stockage public)

    def test_club_only_post_image_uses_the_private_storage(self):
        club = ClubFactory()
        author = MembershipFactory(club=club).user

        with active_club(club):
            post = services.create_post(
                club=club, actor=author, body="Texte", visibility=Post.Visibility.CLUB_ONLY, images=[_image()]
            )

        image = post.images.first()
        assert image.file.storage is private_storage
        with pytest.raises(ValueError):
            _ = image.file.url  # jamais d'URL publique pour un fichier prive


class TestVisiblePosts:
    def test_mon_club_scope_excludes_other_clubs(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        author_a = MembershipFactory(club=club_a).user
        author_b = MembershipFactory(club=club_b).user

        with active_club(club_a):
            services.create_post(club=club_a, actor=author_a, body="A", visibility=Post.Visibility.PUBLIC)
        with active_club(club_b):
            services.create_post(club=club_b, actor=author_b, body="B", visibility=Post.Visibility.PUBLIC)

        results = services.get_visible_posts(active_club=club_a, scope="mon_club")
        assert list(results.values_list("body", flat=True)) == ["A"]

    def test_tous_scope_includes_public_posts_of_other_clubs_but_not_their_private_ones(self):
        club_a = ClubFactory()
        club_b = ClubFactory()
        author_a = MembershipFactory(club=club_a).user
        author_b = MembershipFactory(club=club_b).user

        with active_club(club_a):
            services.create_post(club=club_a, actor=author_a, body="Mon club prive", visibility=Post.Visibility.CLUB_ONLY)
        with active_club(club_b):
            services.create_post(club=club_b, actor=author_b, body="Autre club public", visibility=Post.Visibility.PUBLIC)
            services.create_post(club=club_b, actor=author_b, body="Autre club prive", visibility=Post.Visibility.CLUB_ONLY)

        bodies = set(services.get_visible_posts(active_club=club_a, scope="tous").values_list("body", flat=True))
        assert bodies == {"Mon club prive", "Autre club public"}


class TestInteractions:
    def test_cannot_comment_on_another_clubs_public_post(self):
        """Restriction technique provisoire (voir docstring de
        can_interact_with_post) : commenter reste reserve a son propre club."""

        club_a = ClubFactory()
        club_b = ClubFactory()
        commenter = MembershipFactory(club=club_a).user
        author_b = MembershipFactory(club=club_b).user

        with active_club(club_b):
            post = services.create_post(club=club_b, actor=author_b, body="Public", visibility=Post.Visibility.PUBLIC)

        with active_club(club_a):
            with pytest.raises(services.SocialPermissionError):
                services.add_comment(post=post, actor=commenter, body="Salut", active_club=club_a)

    def test_can_comment_and_like_within_the_same_club(self):
        club = ClubFactory()
        author = MembershipFactory(club=club).user
        other = MembershipFactory(club=club).user

        with active_club(club):
            post = services.create_post(club=club, actor=author, body="Texte", visibility=Post.Visibility.CLUB_ONLY)
            comment = services.add_comment(post=post, actor=other, body="Bien joue !", active_club=club)
            liked = services.toggle_like(post=post, actor=other, active_club=club)
            liked_again = services.toggle_like(post=post, actor=other, active_club=club)

        assert comment.body == "Bien joue !"
        assert liked is True
        assert liked_again is False  # bascule : retire le like

    def test_president_of_origin_club_can_delete_someone_elses_post(self):
        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        author = MembershipFactory(club=club).user

        with active_club(club):
            post = services.create_post(club=club, actor=author, body="Texte", visibility=Post.Visibility.CLUB_ONLY)
            services.delete_post(post=post, actor=president_membership.user)

        post.refresh_from_db()
        assert post.deleted_at is not None

    def test_a_plain_member_cannot_delete_someone_elses_post(self):
        club = ClubFactory()
        author = MembershipFactory(club=club).user
        other = MembershipFactory(club=club).user

        with active_club(club):
            post = services.create_post(club=club, actor=author, body="Texte", visibility=Post.Visibility.CLUB_ONLY)
            with pytest.raises(services.SocialPermissionError):
                services.delete_post(post=post, actor=other)


class TestReportPost:
    def test_reports_notify_superusers_and_are_journalised(self):
        club = ClubFactory()
        author = MembershipFactory(club=club).user
        reporter = MembershipFactory(club=club).user
        superuser = SuperuserFactory()

        with active_club(club):
            post = services.create_post(club=club, actor=author, body="Texte", visibility=Post.Visibility.CLUB_ONLY)
            services.report_post(post=post, actor=reporter, reason="Propos deplaces", active_club=club)

        assert AuditLog.objects.filter(action_type="social.post.reported").exists()
        assert Notification.objects.filter(
            recipient=superuser, event_type=Notification.EventType.POST_REPORTED
        ).exists()

    def test_cannot_report_the_same_post_twice(self):
        club = ClubFactory()
        author = MembershipFactory(club=club).user
        reporter = MembershipFactory(club=club).user

        with active_club(club):
            post = services.create_post(club=club, actor=author, body="Texte", visibility=Post.Visibility.CLUB_ONLY)
            services.report_post(post=post, actor=reporter, reason="", active_club=club)
            with pytest.raises(services.SocialValidationError, match="deja signale"):
                services.report_post(post=post, actor=reporter, reason="", active_club=club)


class TestAnnouncements:
    def test_create_announcement_notifies_active_members(self):
        club = ClubFactory()
        president_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=president_membership, role=MembershipRole.Role.PRESIDENT)
        player = MembershipFactory(club=club)

        with active_club(club):
            announcement = services.create_announcement(
                club=club, actor=president_membership.user, title="Titre", body="Corps"
            )

        assert Notification.objects.filter(
            recipient=player.user, event_type=Notification.EventType.ANNOUNCEMENT_PUBLISHED
        ).exists()
        assert announcement.pinned is True

    def test_mark_read_is_idempotent_and_journalised_once(self):
        club = ClubFactory()
        announcement = AnnouncementFactory(club=club)
        member = MembershipFactory(club=club)

        with active_club(club):
            services.mark_announcement_read(announcement=announcement, membership=member)
            services.mark_announcement_read(announcement=announcement, membership=member)

        assert announcement.reads.count() == 1
        assert AuditLog.objects.filter(action_type="social.announcement.read").count() == 1

    def test_read_summary_counts_active_members(self):
        club = ClubFactory()
        announcement = AnnouncementFactory(club=club)
        member_a = MembershipFactory(club=club)
        MembershipFactory(club=club)

        with active_club(club):
            services.mark_announcement_read(announcement=announcement, membership=member_a)
            summary = services.get_announcement_read_summary(announcement)

        assert summary == {"read_count": 1, "total": 2}


class TestChat:
    def test_ensure_channels_creates_general_and_board_once(self):
        club = ClubFactory()

        with active_club(club):
            general1, board1 = services.ensure_channels(club)
            general2, board2 = services.ensure_channels(club)

        assert general1.pk == general2.pk
        assert board1.pk == board2.pk
        assert ChatChannel.all_objects.filter(club=club).count() == 2

    def test_board_channel_is_restricted_to_board_roles(self):
        club = ClubFactory()
        board = ChatChannelFactory(club=club, channel_type=ChatChannel.ChannelType.BOARD)
        treasurer_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=treasurer_membership, role=MembershipRole.Role.TREASURER)
        coach_membership = MembershipFactory(club=club)
        MembershipRoleFactory(membership=coach_membership, role=MembershipRole.Role.COACH)

        with active_club(club):
            assert services.can_access_channel(user=treasurer_membership.user, channel=board) is True
            assert services.can_access_channel(user=coach_membership.user, channel=board) is False

    def test_doctor_is_excluded_from_the_board_channel(self):
        """Position provisoire la plus restrictive (point ouvert F.10)."""

        club = ClubFactory()
        board = ChatChannelFactory(club=club, channel_type=ChatChannel.ChannelType.BOARD)
        doctor_membership = MembershipFactory(club=club)
        MembershipRoleFactory(
            membership=doctor_membership, role=MembershipRole.Role.DOCTOR, is_qualified_professional=True
        )

        with active_club(club):
            assert services.can_access_channel(user=doctor_membership.user, channel=board) is False

    def test_general_channel_is_open_to_any_active_member(self):
        club = ClubFactory()
        general = ChatChannelFactory(club=club, channel_type=ChatChannel.ChannelType.GENERAL)
        member = MembershipFactory(club=club)

        with active_club(club):
            assert services.can_access_channel(user=member.user, channel=general) is True

    def test_send_message_and_unread_count(self):
        club = ClubFactory()
        general = ChatChannelFactory(club=club, channel_type=ChatChannel.ChannelType.GENERAL)
        sender = MembershipFactory(club=club)
        reader = MembershipFactory(club=club)

        with active_club(club):
            message = services.send_chat_message(channel=general, actor=sender.user, body="Salut l'equipe")
            assert services.get_unread_count(channel=general, membership=reader) == 1

            services.mark_channel_read(channel=general, membership=reader, message=message)
            assert services.get_unread_count(channel=general, membership=reader) == 0

    def test_message_requires_body_or_image(self):
        club = ClubFactory()
        general = ChatChannelFactory(club=club, channel_type=ChatChannel.ChannelType.GENERAL)
        sender = MembershipFactory(club=club)

        with active_club(club):
            with pytest.raises(services.SocialValidationError):
                services.send_chat_message(channel=general, actor=sender.user, body="")
