"""Atomicite de `add_player_with_sponsor` (CDC 4.3 etape 1 ; CLAUDE.md regle n6).

Regression : quand l'email correspondait a un joueur DEJA membre du club
(`create_or_update_player` renvoie `outcome == "updated"`), le service levait
`MembershipApplicationError` apres avoir deja ecrit le `User` (telephone) et le
`Membership` (poste) ainsi que leurs entrees de journal. Ces ecritures
persistaient malgre l'erreur. Ces tests verrouillent le tout-ou-rien.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.clubs import services as clubs_services
from apps.clubs.models import Membership, MembershipApplication
from apps.clubs.tests.test_membership_application import add_player, build_context, pay
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

EXISTING_EMAIL = "deja.membre@example.com"
ORIGINAL_PHONE = "+243811111111"
NEW_PHONE = "+243899999999"
ORIGINAL_POSITION = Membership.Position.GOALKEEPER
NEW_POSITION = Membership.Position.FORWARD


def _authenticated_client(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _existing_active_player_other_than_sponsor(ctx):
    from apps.treasury.tests.conftest import make_member

    membership = make_member(ctx.club)
    membership.user.email = EXISTING_EMAIL
    membership.user.phone = ORIGINAL_PHONE
    membership.user.save()
    membership.position = ORIGINAL_POSITION
    membership.save()
    return membership


def _counts():
    return {
        "applications": MembershipApplication.all_objects.count(),
        "memberships": Membership.all_objects.count(),
        "users": User.objects.count(),
        "audit": AuditLog.objects.count(),
        "notifications": Notification.objects.count(),
    }


class TestAddPlayerWithSponsorAtomicityService:
    def test_existing_active_member_re_added_raises_and_leaves_user_and_membership_untouched(self):
        ctx = build_context()
        existing = _existing_active_player_other_than_sponsor(ctx)
        assert existing.status == Membership.Status.ACTIVE
        before = _counts()

        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, email=EXISTING_EMAIL, position=NEW_POSITION, phone=NEW_PHONE)

        existing.refresh_from_db()
        existing.user.refresh_from_db()
        assert existing.user.phone == ORIGINAL_PHONE
        assert existing.position == ORIGINAL_POSITION
        assert existing.status == Membership.Status.ACTIVE
        assert _counts() == before

    def test_existing_active_member_re_added_creates_no_application(self):
        ctx = build_context()
        existing = _existing_active_player_other_than_sponsor(ctx)
        applications_before = MembershipApplication.all_objects.count()

        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, email=EXISTING_EMAIL, position=NEW_POSITION, phone=NEW_PHONE)

        assert MembershipApplication.all_objects.count() == applications_before
        assert not MembershipApplication.all_objects.filter(membership=existing).exists()

    def test_existing_active_member_re_added_writes_no_audit_entry_nor_notification(self):
        ctx = build_context()
        _existing_active_player_other_than_sponsor(ctx)
        audit_before = AuditLog.objects.count()
        notifications_before = Notification.objects.count()

        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, email=EXISTING_EMAIL, position=NEW_POSITION, phone=NEW_PHONE)

        assert AuditLog.objects.count() == audit_before
        assert Notification.objects.count() == notifications_before

    def test_existing_email_is_matched_case_insensitively_and_still_rolls_back(self):
        ctx = build_context()
        existing = _existing_active_player_other_than_sponsor(ctx)
        before = _counts()

        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, email=EXISTING_EMAIL.upper(), position=NEW_POSITION, phone=NEW_PHONE)

        existing.refresh_from_db()
        existing.user.refresh_from_db()
        assert existing.user.phone == ORIGINAL_PHONE
        assert existing.position == ORIGINAL_POSITION
        assert _counts() == before

    def test_existing_pending_member_re_added_also_rolls_back(self):
        ctx = build_context()
        membership, _application = add_player(ctx, email="attente@example.com", phone=ORIGINAL_PHONE)
        before = _counts()

        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, email="attente@example.com", position=NEW_POSITION, phone=NEW_PHONE)

        membership.refresh_from_db()
        membership.user.refresh_from_db()
        assert membership.user.phone == ORIGINAL_PHONE
        assert membership.position == Membership.Position.MIDFIELDER
        assert _counts() == before

    def test_refused_re_add_does_not_block_a_later_valid_add(self):
        ctx = build_context()
        _existing_active_player_other_than_sponsor(ctx)
        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, email=EXISTING_EMAIL, position=NEW_POSITION, phone=NEW_PHONE)

        membership, application = add_player(ctx, email="apres@example.com")

        assert membership.status == Membership.Status.PENDING
        assert application.membership_id == membership.id


class TestAddPlayerWithSponsorAtomicityView:
    def test_post_existing_active_member_returns_400_in_french_and_leaves_database_untouched(self):
        ctx = build_context()
        existing = _existing_active_player_other_than_sponsor(ctx)
        client = _authenticated_client(ctx.president.user)
        before = _counts()

        response = client.post(
            reverse("clubs:players-add"),
            {
                "email": EXISTING_EMAIL,
                "first_name": "Deja",
                "last_name": "Membre",
                "phone": NEW_PHONE,
                "position": NEW_POSITION,
                "sponsor_membership_id": ctx.sponsor.id,
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "déjà membre de ce club" in response.data["detail"]
        existing.refresh_from_db()
        existing.user.refresh_from_db()
        assert existing.user.phone == ORIGINAL_PHONE
        assert existing.position == ORIGINAL_POSITION
        assert _counts() == before


class TestAddPlayerWithSponsorNonRegression:
    def test_valid_add_of_new_player_creates_application_and_audit_entry(self):
        ctx = build_context()
        before = _counts()

        membership, application = add_player(ctx, email="nouveau.valide@example.com", phone=NEW_PHONE)

        assert membership.status == Membership.Status.PENDING
        assert membership.sponsor_id == ctx.sponsor.id
        assert membership.user.phone == NEW_PHONE
        assert application.membership_id == membership.id
        after = _counts()
        assert after["applications"] == before["applications"] + 1
        assert after["memberships"] == before["memberships"] + 1
        assert after["users"] == before["users"] + 1
        assert after["audit"] > before["audit"]
        assert AuditLog.objects.filter(action_type="membership.created", object_id=str(membership.pk)).exists()

    def test_valid_add_then_payment_still_notifies_the_sponsor(self):
        """L'ajout lui-meme n'emet aucune notification (elle part au paiement de
        la fiche, CDC 4.3 etape 4) : le correctif d'atomicite ne doit pas
        l'avoir cassee."""

        ctx = build_context()
        notifications_before_add = Notification.objects.count()

        _membership, application = add_player(ctx, email="chaine@example.com")
        assert Notification.objects.count() == notifications_before_add

        pay(ctx, application)

        assert Notification.objects.filter(
            recipient=ctx.sponsor.user,
            event_type=Notification.EventType.MEMBERSHIP_SIGNATURE_PENDING,
        ).exists()

    def test_valid_add_via_api_returns_201_and_persists(self):
        ctx = build_context()
        client = _authenticated_client(ctx.president.user)

        response = client.post(
            reverse("clubs:players-add"),
            {
                "email": "api.valide@example.com",
                "first_name": "Api",
                "last_name": "Valide",
                "position": NEW_POSITION,
                "sponsor_membership_id": ctx.sponsor.id,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        membership = Membership.all_objects.get(club=ctx.club, user__email="api.valide@example.com")
        assert MembershipApplication.all_objects.filter(membership=membership).exists()
        assert AuditLog.objects.filter(action_type="membership.created", object_id=str(membership.pk)).exists()

    @pytest.mark.parametrize("failure", ["other_club_sponsor", "pending_sponsor", "no_sponsor", "missing_position"])
    def test_service_refused_before_writing_leaves_nothing_behind(self, failure):
        from apps.treasury.tests.conftest import make_member

        ctx = build_context()
        kwargs = {"email": "refuse@example.com", "phone": NEW_PHONE}
        if failure == "other_club_sponsor":
            kwargs["sponsor"] = build_context().sponsor
        elif failure == "pending_sponsor":
            kwargs["sponsor"] = make_member(ctx.club, status=Membership.Status.PENDING)
        elif failure == "no_sponsor":
            kwargs["sponsor"] = None
        else:
            kwargs["position"] = ""
        before = _counts()

        with pytest.raises(clubs_services.MembershipApplicationError):
            add_player(ctx, **kwargs)

        assert _counts() == before
        assert not User.objects.filter(email="refuse@example.com").exists()

    def test_api_refused_for_missing_position_leaves_nothing_behind(self):
        ctx = build_context()
        client = _authenticated_client(ctx.president.user)
        before = _counts()

        response = client.post(
            reverse("clubs:players-add"),
            {
                "email": "sanspost@example.com",
                "first_name": "Sans",
                "last_name": "Poste",
                "sponsor_membership_id": ctx.sponsor.id,
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert _counts() == before

    def test_api_refused_for_sponsor_of_another_club_leaves_nothing_behind(self):
        ctx = build_context()
        other = build_context()
        client = _authenticated_client(ctx.president.user)
        before = _counts()

        response = client.post(
            reverse("clubs:players-add"),
            {
                "email": "autreclub@example.com",
                "first_name": "Autre",
                "last_name": "Club",
                "position": NEW_POSITION,
                "sponsor_membership_id": other.sponsor.id,
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert _counts() == before
