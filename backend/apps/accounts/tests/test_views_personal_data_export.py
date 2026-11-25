"""« Telecharger mes donnees » (CDC 7.5) : perimetre restrictif, etancheite,
journalisation sans contenu sensible."""

from __future__ import annotations

import json

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import SuperuserFactory, TermsAcceptanceFactory, UserFactory
from apps.accounts.tests.test_views_profile import _authenticated_client
from apps.audit.models import AuditLog
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import ClubSettingsFactory, MembershipFactory, MembershipRoleFactory
from apps.medical.models import HealthRecord

pytestmark = pytest.mark.django_db

URL = "accounts:profile-export"


def _member(club, **user_kwargs):
    user = UserFactory(**user_kwargs)
    return MembershipFactory(club=club, user=user, status=Membership.Status.ACTIVE)


def test_requires_authentication():
    assert APIClient().get(reverse(URL)).status_code == status.HTTP_401_UNAUTHORIZED


def test_export_contains_only_own_data_across_clubs():
    club_a = ClubSettingsFactory().club
    club_b = ClubSettingsFactory().club
    me = _member(club_a, first_name="Moi", last_name="Meme", phone="+243111")
    MembershipFactory(
        club=club_b,
        user=me.user,
        status=Membership.Status.DEPARTED,
        left_on="2025-01-01",
        left_reason="resignation",
    )
    MembershipRoleFactory(membership=me, club=club_a, role=MembershipRole.Role.COACH, appointed_at=timezone.now())
    terms = TermsAcceptanceFactory(user=me.user).terms_version
    stranger = _member(club_a, first_name="Intrus", last_name="Secret", phone="+243999")
    MembershipRoleFactory(
        membership=stranger,
        club=club_a,
        role=MembershipRole.Role.DOCTOR,
        appointed_at=timezone.now(),
        is_qualified_professional=False,
    )
    TermsAcceptanceFactory(user=stranger.user, terms_version=terms)

    response = _authenticated_client(me.user).get(reverse(URL))

    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    data = response.json()
    assert data["identity"]["email"] == me.user.email
    assert data["identity"]["phone"] == "+243111"
    assert {m["club"]["slug"] for m in data["memberships"]} == {club_a.slug, club_b.slug}
    assert len(data["terms_acceptances"]) == 1
    raw = json.dumps(data)
    assert "Intrus" not in raw and "+243999" not in raw and stranger.user.email not in raw


def test_export_never_contains_medical_content_nor_secrets():
    club = ClubSettingsFactory().club
    me = _member(club)
    HealthRecord.all_objects.create(
        club=club, membership=me, self_declaration="DIAGNOSTIC-CONFIDENTIEL", allergies="PENICILLINE"
    )

    response = _authenticated_client(me.user).get(reverse(URL))

    raw = response.content.decode()
    assert "DIAGNOSTIC-CONFIDENTIEL" not in raw and "PENICILLINE" not in raw
    assert "pbkdf2" not in raw
    assert "password" not in raw.lower() and "pin_" not in raw
    assert "health" not in raw.lower() and "fitness" not in raw.lower()


def test_export_is_logged_without_content():
    club = ClubSettingsFactory().club
    me = _member(club, phone="+243555")

    _authenticated_client(me.user).get(reverse(URL))

    entry = AuditLog.objects.get(action_type="accounts.personal_data.exported")
    assert entry.actor_id == me.user.id
    assert entry.object_id == str(me.user.id)
    logged = json.dumps(entry.after)
    assert "+243555" not in logged and me.user.email not in logged


def test_superuser_gets_identity_only():
    response = _authenticated_client(SuperuserFactory()).get(reverse(URL))
    assert response.status_code == 200
    assert response.json()["memberships"] == []


def test_ignores_any_user_id_parameter():
    club = ClubSettingsFactory().club
    me = _member(club)
    other = _member(club)
    response = _authenticated_client(me.user).get(reverse(URL), {"user": other.user.id, "user_id": other.user.id})
    assert response.json()["identity"]["email"] == me.user.email
