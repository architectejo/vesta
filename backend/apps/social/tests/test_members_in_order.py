"""Messages du chat reserves aux membres en ordre (CDC 10.3 n° 182, decision
du client du 27/11/2026 ; docs/ecrans/fil-public-communication.md C7).

Le statut « En ordre » vient TOUJOURS de la tresorerie (regle 2 : solde
calcule, jamais stocke) : les dettes sont creees par un montant du echu,
les regularisations par un paiement valide et scelle (memes outils que les
tests de la tresorerie).
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.core.ghost_context import clear_ghost_context
from apps.core.tenant import active_club, set_active_club
from apps.notifications.models import Notification
from apps.social import services
from apps.social.models import ChatChannel, ChatMessage
from apps.social.tests.factories import ChatMessageFactory, uploaded_image
from apps.treasury.tests.expense_helpers import pay_mandatory, put_in_debt

pytestmark = pytest.mark.django_db

INCENTIVE = (
    "Un message réservé aux membres en ordre a été publié dans le chat. "
    "Régularisez votre cotisation pour voir toutes les informations et tous les messages du groupe."
)


def _client(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _with_role(club, role, **kwargs) -> Membership:
    membership = MembershipFactory(club=club, **kwargs)
    MembershipRoleFactory(membership=membership, club=club, role=role)
    return membership


@pytest.fixture
def ctx():
    club = ClubSettingsFactory().club
    president = _with_role(club, MembershipRole.Role.PRESIDENT)
    treasurer = _with_role(club, MembershipRole.Role.TREASURER)
    coach = _with_role(club, MembershipRole.Role.COACH)
    with active_club(club):
        general, board = services.ensure_channels(club)
    in_order = MembershipFactory(club=club)
    debtor = MembershipFactory(club=club)
    ns = SimpleNamespace(
        club=club,
        president=president,
        treasurer=treasurer,
        coach=coach,
        general=general,
        board=board,
        in_order=in_order,
        debtor=debtor,
    )
    with active_club(club):
        ns.ctype = put_in_debt(ns, debtor)
    return ns


def _send(ctx, sender, body="Info réservée", *, reserved=True, channel=None, image=None, now=None):
    with active_club(ctx.club):
        return services.send_chat_message(
            channel=channel or ctx.general,
            actor=sender.user,
            body=body,
            image=image,
            members_in_order_only=reserved,
            now=now,
        )


def _list_ids(ctx, membership, **params):
    response = _client(membership.user).get(
        reverse("social:chat-message-list", kwargs={"pk": ctx.general.pk}), params
    )
    assert response.status_code == status.HTTP_200_OK, response.data
    return [row["id"] for row in response.data["results"]], response


def _channels(membership):
    response = _client(membership.user).get(reverse("social:chat-channel-list"))
    assert response.status_code == status.HTTP_200_OK
    return {row["channel_type"]: row for row in response.data["results"]}


# ---------------------------------------------------------------------------
# Lecture filtree par l'API
# ---------------------------------------------------------------------------


class TestReadingFilter:
    def test_in_order_player_sees_the_reserved_message_with_its_flag(self, ctx):
        public = _send(ctx, ctx.president, "Pour tous", reserved=False)
        reserved = _send(ctx, ctx.president)

        ids, response = _list_ids(ctx, ctx.in_order)

        assert ids == [public.id, reserved.id]
        flags = {row["id"]: row["members_in_order_only"] for row in response.data["results"]}
        assert flags == {public.id: False, reserved.id: True}

    def test_player_in_debt_never_receives_the_reserved_message(self, ctx):
        public = _send(ctx, ctx.president, "Pour tous", reserved=False)
        _send(ctx, ctx.president)

        ids, response = _list_ids(ctx, ctx.debtor)

        assert ids == [public.id]
        assert response.data["count"] == 1

    def test_after_polling_is_filtered_too(self, ctx):
        first = _send(ctx, ctx.president, "Avant", reserved=False)
        _send(ctx, ctx.president)
        last = _send(ctx, ctx.president, "Après", reserved=False)

        debtor_ids, _ = _list_ids(ctx, ctx.debtor, after=first.id)
        in_order_ids, _ = _list_ids(ctx, ctx.in_order, after=first.id)

        assert debtor_ids == [last.id]
        assert len(in_order_ids) == 2

    def test_regularising_reveals_the_old_reserved_messages(self, ctx):
        reserved = _send(ctx, ctx.president)
        assert reserved.id not in _list_ids(ctx, ctx.debtor)[0]

        with active_club(ctx.club):
            pay_mandatory(ctx, ctx.debtor, ctx.ctype)

        assert reserved.id in _list_ids(ctx, ctx.debtor)[0]

    def test_board_author_in_debt_sees_own_and_others_reserved_messages(self, ctx):
        with active_club(ctx.club):
            put_in_debt(ctx, ctx.treasurer)
        own = _send(ctx, ctx.treasurer)
        other = _send(ctx, ctx.president)

        ids, _ = _list_ids(ctx, ctx.treasurer)

        assert {own.id, other.id} <= set(ids)

    def test_non_board_author_still_sees_own_reserved_message(self, ctx):
        # Cas limite : drapeau pose directement en base (l'API le refuse a un
        # non-membre du bureau), puis l'auteur passe en dette.
        message = ChatMessageFactory(
            channel=ctx.general, club=ctx.club, sender=ctx.debtor.user, members_in_order_only=True
        )

        assert message.id in _list_ids(ctx, ctx.debtor)[0]

    def test_pending_membership_is_treated_as_not_in_order(self, ctx):
        pending = MembershipFactory(club=ctx.club, status=Membership.Status.PENDING)

        with active_club(ctx.club):
            reader = services.get_chat_reader(user=pending.user, club=ctx.club, membership=pending)

        assert reader.can_read_reserved is False

    def test_coach_not_in_board_and_in_debt_does_not_see_it(self, ctx):
        with active_club(ctx.club):
            put_in_debt(ctx, ctx.coach)
        reserved = _send(ctx, ctx.president)

        assert reserved.id not in _list_ids(ctx, ctx.coach)[0]


class TestImageAndCounters:
    def test_reserved_image_is_404_for_a_player_not_in_order(self, ctx):
        message = _send(ctx, ctx.president, "", image=uploaded_image("photo.png"))
        url = reverse("social:chat-message-image-download", kwargs={"pk": message.pk})

        refused = _client(ctx.debtor.user).get(url)
        allowed = _client(ctx.in_order.user).get(url)

        assert refused.status_code == status.HTTP_404_NOT_FOUND
        assert refused.data["detail"] == "Ce message n'existe pas dans ce club."
        assert allowed.status_code == status.HTTP_200_OK

    def test_unread_count_and_last_message_ignore_hidden_messages(self, ctx):
        public = _send(ctx, ctx.president, "Pour tous", reserved=False)
        _send(ctx, ctx.president)

        debtor_general = _channels(ctx.debtor)["general"]
        in_order_general = _channels(ctx.in_order)["general"]

        assert debtor_general["unread_count"] == 1
        assert debtor_general["last_message"]["id"] == public.id
        assert in_order_general["unread_count"] == 2
        assert in_order_general["last_message"]["members_in_order_only"] is True

    def test_mark_read_never_points_to_a_hidden_message(self, ctx):
        public = _send(ctx, ctx.president, "Pour tous", reserved=False)
        reserved = _send(ctx, ctx.president)
        client = _client(ctx.debtor.user)

        client.post(
            reverse("social:chat-channel-read", kwargs={"pk": ctx.general.pk}),
            {"last_read_message_id": reserved.id},
            format="json",
        )
        client.post(reverse("social:chat-channel-read", kwargs={"pk": ctx.general.pk}), {}, format="json")

        from apps.social.models import ChatChannelRead

        read = ChatChannelRead.all_objects.get(channel=ctx.general, membership=ctx.debtor)
        assert read.last_read_message_id == public.id
        with active_club(ctx.club):
            pay_mandatory(ctx, ctx.debtor, ctx.ctype)
        # Apres regularisation, le message reserve (plus recent) devient non lu.
        assert _channels(ctx.debtor)["general"]["unread_count"] == 1

    def test_hidden_indicator_and_checkbox_flags(self, ctx):
        assert _channels(ctx.debtor)["general"]["has_hidden_reserved_messages"] is False
        _send(ctx, ctx.president)

        debtor = _channels(ctx.debtor)
        in_order = _channels(ctx.in_order)
        president = _channels(ctx.president)

        assert debtor["general"]["has_hidden_reserved_messages"] is True
        assert in_order["general"]["has_hidden_reserved_messages"] is False
        assert president["general"]["has_hidden_reserved_messages"] is False
        assert president["general"]["can_restrict_to_members_in_order"] is True
        assert president["board"]["can_restrict_to_members_in_order"] is False
        assert debtor["general"]["can_restrict_to_members_in_order"] is False
        assert _channels(ctx.coach)["general"]["can_restrict_to_members_in_order"] is False


# ---------------------------------------------------------------------------
# Pose du drapeau, journal
# ---------------------------------------------------------------------------


class TestSendingRestrictedMessage:
    def _post(self, ctx, membership, channel, **extra):
        return _client(membership.user).post(
            reverse("social:chat-message-list", kwargs={"pk": channel.pk}),
            {"body": "Info", "members_in_order_only": True, **extra},
            format="json",
        )

    def test_board_role_can_post_a_reserved_message(self, ctx):
        response = self._post(ctx, ctx.treasurer, ctx.general)

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["members_in_order_only"] is True

    def test_default_is_visible_to_all(self, ctx):
        response = _client(ctx.president.user).post(
            reverse("social:chat-message-list", kwargs={"pk": ctx.general.pk}), {"body": "Info"}, format="json"
        )

        assert response.data["members_in_order_only"] is False

    @pytest.mark.parametrize("who", ["coach", "in_order"])
    def test_non_board_role_is_refused_with_403(self, ctx, who):
        response = self._post(ctx, getattr(ctx, who), ctx.general)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["detail"] == (
            "Seuls les membres du bureau peuvent réserver un message aux membres en ordre."
        )
        assert not ChatMessage.all_objects.filter(club=ctx.club).exists()

    def test_board_channel_is_refused_with_400(self, ctx):
        response = self._post(ctx, ctx.president, ctx.board)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"] == (
            "Un message réservé aux membres en ordre ne peut être publié que dans le canal Général."
        )
        assert not ChatMessage.all_objects.filter(club=ctx.club).exists()

    def test_audit_log_records_the_flag_without_the_text(self, ctx):
        message = _send(ctx, ctx.president, "Texte confidentiel du bureau")

        entry = AuditLog.objects.get(action_type="social.chat_message.sent", object_id=str(message.pk))
        assert entry.after["members_in_order_only"] is True
        assert "Texte confidentiel" not in str(entry.after)
        assert "Texte confidentiel" not in str(entry.before)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class TestIncentiveNotification:
    def _incentives(self, ctx):
        return Notification.objects.filter(
            club=ctx.club, event_type=Notification.EventType.CHAT_MEMBERS_IN_ORDER_INCENTIVE
        )

    def test_only_players_not_in_order_receive_the_incentive(self, ctx):
        with active_club(ctx.club):
            put_in_debt(ctx, ctx.coach)
            put_in_debt(ctx, ctx.treasurer)  # bureau : lit le message, pas d'incitation
        _send(ctx, ctx.president, "Contenu secret")

        incentives = list(self._incentives(ctx))
        assert {n.recipient_id for n in incentives} == {ctx.debtor.user_id, ctx.coach.user_id}
        for notification in incentives:
            assert notification.body == INCENTIVE
            assert "Contenu secret" not in notification.title + notification.body
            assert notification.link_object_type == ""
            assert notification.email_requested is False

    def test_readers_get_no_bell_notification(self, ctx):
        _send(ctx, ctx.president)

        assert not Notification.objects.filter(recipient=ctx.in_order.user).exists()
        assert _channels(ctx.in_order)["general"]["unread_count"] == 1

    def test_a_normal_message_triggers_no_incentive(self, ctx):
        _send(ctx, ctx.president, reserved=False)

        assert not self._incentives(ctx).exists()

    def test_at_most_one_incentive_per_player_and_per_club_day(self, ctx):
        # 09:00 a Kinshasa (UTC+1) le 27/11, puis 23:30 le meme jour local.
        morning = datetime.datetime(2026, 11, 27, 8, 0, tzinfo=datetime.timezone.utc)
        late = datetime.datetime(2026, 11, 27, 22, 30, tzinfo=datetime.timezone.utc)
        next_day = datetime.datetime(2026, 11, 27, 23, 30, tzinfo=datetime.timezone.utc)  # 00:30 le 28

        _send(ctx, ctx.president, now=morning)
        _send(ctx, ctx.president, now=late)
        assert self._incentives(ctx).filter(recipient=ctx.debtor.user).count() == 1

        _send(ctx, ctx.president, now=next_day)
        assert self._incentives(ctx).filter(recipient=ctx.debtor.user).count() == 2


# ---------------------------------------------------------------------------
# Superuser en session de support (Ghost Mode)
# ---------------------------------------------------------------------------


@pytest.fixture
def _clean_ghost():
    cache.clear()
    yield
    set_active_club(None)
    clear_ghost_context()
    cache.clear()


def test_superuser_in_support_session_does_not_read_reserved_messages(ctx, _clean_ghost):
    public = _send(ctx, ctx.president, "Pour tous", reserved=False)
    reserved = _send(ctx, ctx.president)
    superuser = SuperuserFactory()
    client = _client(superuser)
    start = client.post(
        reverse("licences:support-session-start"), {"club_id": ctx.club.pk, "reason": "Vérification."}, format="json"
    )
    assert start.status_code == status.HTTP_201_CREATED
    session = str(start.data["id"])

    listing = client.get(
        reverse("social:chat-message-list", kwargs={"pk": ctx.general.pk}), HTTP_X_SUPPORT_SESSION=session
    )
    channels = client.get(reverse("social:chat-channel-list"), HTTP_X_SUPPORT_SESSION=session)

    assert [row["id"] for row in listing.data["results"]] == [public.id]
    assert reserved.id not in [row["id"] for row in listing.data["results"]]
    general = next(row for row in channels.data["results"] if row["channel_type"] == "general")
    assert general["has_hidden_reserved_messages"] is False
    assert general["can_restrict_to_members_in_order"] is False
    assert not Notification.objects.filter(recipient=superuser).exists()


# ---------------------------------------------------------------------------
# Etancheite et performances
# ---------------------------------------------------------------------------


def test_other_club_never_reaches_a_reserved_message(ctx):
    other_club = ClubSettingsFactory().club
    outsider = _with_role(other_club, MembershipRole.Role.PRESIDENT)
    message = _send(ctx, ctx.president, "", image=uploaded_image("photo.png"))

    image = _client(outsider.user).get(reverse("social:chat-message-image-download", kwargs={"pk": message.pk}))
    listing = _client(outsider.user).get(reverse("social:chat-message-list", kwargs={"pk": ctx.general.pk}))

    assert image.status_code == status.HTTP_404_NOT_FOUND
    assert listing.status_code == status.HTTP_404_NOT_FOUND
    assert not Notification.objects.filter(club=other_club).exists()
    assert not Notification.objects.filter(recipient=outsider.user).exists()


@pytest.mark.parametrize("who", ["debtor", "in_order", "president"])
def test_query_count_does_not_grow_with_the_number_of_messages(ctx, who):
    reader = getattr(ctx, who)

    def count_queries():
        client = _client(reader.user)
        with CaptureQueriesContext(connection) as listing:
            client.get(reverse("social:chat-message-list", kwargs={"pk": ctx.general.pk}))
        with CaptureQueriesContext(connection) as channels:
            client.get(reverse("social:chat-channel-list"))
        return len(listing), len(channels)

    for index in range(2):
        _send(ctx, ctx.president, f"m{index}", reserved=bool(index % 2))
    small = count_queries()
    for index in range(6):
        _send(ctx, ctx.president, f"n{index}", reserved=bool(index % 2))
    large = count_queries()

    assert small == large
