"""Vues du journal Superuser (CDC 4.18, 5.5 ; ecran superuser §3.4, §4.6)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.models import AuditLog
from apps.audit.services import create_audit_log
from apps.audit.tests.factories import AuditLogFactory
from apps.clubs.tests.factories import ClubSettingsFactory

pytestmark = pytest.mark.django_db


def client_for(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def superuser_client():
    return client_for(SuperuserFactory())


def test_list_requires_superuser():
    url = reverse("audit:log-list")
    assert APIClient().get(url).status_code == 401
    assert client_for(UserFactory()).get(url).status_code == 403
    assert client_for(UserFactory()).get(reverse("audit:log-export")).status_code == 403


def test_detail_forbidden_for_non_superuser():
    entry = AuditLogFactory()
    assert client_for(UserFactory()).get(reverse("audit:log-detail", args=[entry.pk])).status_code == 403


def test_list_is_paginated_most_recent_first_and_read_only(superuser_client):
    for _ in range(3):
        AuditLogFactory()
    response = superuser_client.get(reverse("audit:log-list"))
    assert response.status_code == 200
    assert response.data["count"] == 3
    ids = [r["id"] for r in response.data["results"]]
    assert ids == sorted(ids, reverse=True)
    assert "before" not in response.data["results"][0]
    assert superuser_client.post(reverse("audit:log-list"), {}).status_code == 405
    assert superuser_client.delete(reverse("audit:log-detail", args=[ids[0]])).status_code == 405


def test_filters_club_actor_type_alerts(superuser_client):
    club_a = ClubSettingsFactory().club
    club_b = ClubSettingsFactory().club
    actor = UserFactory()
    AuditLogFactory(club=club_a, actor=actor, action_type="auth.login_failed")
    AuditLogFactory(club=club_b, action_type="treasury.payment.validated")
    url = reverse("audit:log-list")
    assert superuser_client.get(url, {"club_id": club_a.id}).data["count"] == 1
    assert superuser_client.get(url, {"actor_id": actor.id}).data["count"] == 1
    assert superuser_client.get(url, {"action_type": "treasury.payment.validated"}).data["count"] == 1
    assert superuser_client.get(url, {"action_type": "treasury.*"}).data["count"] == 1
    assert superuser_client.get(url, {"alerts_only": "true"}).data["count"] == 1
    assert superuser_client.get(url, {"alerts_only": "true"}).data["results"][0]["is_alert"] is True


def test_date_filter_and_validation(superuser_client):
    AuditLogFactory()
    url = reverse("audit:log-list")
    assert superuser_client.get(url, {"date_from": "2999-01-01"}).data["count"] == 0
    assert superuser_client.get(url, {"date_to": "2999-01-01"}).data["count"] == 1
    assert superuser_client.get(url, {"date_from": "pas-une-date"}).status_code == 400
    assert superuser_client.get(url, {"date_from": "2026-02-01", "date_to": "2026-01-01"}).status_code == 400
    assert superuser_client.get(url, {"club_id": "abc"}).status_code == 400


def test_ghost_entry_shows_real_identity_to_superuser(superuser_client):
    ghost = SuperuserFactory()
    entry = create_audit_log(
        actor=ghost,
        club=ClubSettingsFactory().club,
        action_type="treasury.payment.corrected",
        object_type="Payment",
        object_id=1,
        acted_as_ghost=True,
        support_session_id="999",
    )
    data = superuser_client.get(reverse("audit:log-detail", args=[entry.pk])).data
    assert data["actor_id"] == ghost.id
    assert data["acted_as_ghost"] is True
    assert data["support_session"] == {"id": "999", "reason": None}


def test_detail_returns_before_after_and_context(superuser_client):
    entry = AuditLogFactory(before={"a": 1}, after={"a": 2})
    data = superuser_client.get(reverse("audit:log-detail", args=[entry.pk])).data
    assert data["before"] == {"a": 1} and data["after"] == {"a": 2}
    assert data["medical_content_withheld"] is False
    assert "ip_address" in data and "user_agent" in data
    assert superuser_client.get(reverse("audit:log-detail", args=[999999])).status_code == 404


def test_medical_entry_never_exposes_before_after_nor_csv_content(superuser_client):
    club = ClubSettingsFactory().club
    entry = create_audit_log(
        actor=UserFactory(),
        club=club,
        action_type="medical.record.updated",
        object_type="HealthRecord",
        object_id=5,
        after={"fields_changed": ["allergies"]},
    )
    data = superuser_client.get(reverse("audit:log-detail", args=[entry.pk])).data
    assert data["before"] is None and data["after"] is None
    assert data["medical_content_withheld"] is True

    csv_response = superuser_client.get(reverse("audit:log-export"))
    assert csv_response.status_code == 200
    body = csv_response.content.decode("utf-8-sig")
    assert "fields_changed" not in body and "allergies" not in body
    assert "medical.record.updated" in body


def test_export_csv_format_and_filters(superuser_client):
    club = ClubSettingsFactory().club
    AuditLogFactory(club=club, action_type="=cmd.injection")
    AuditLogFactory(action_type="other.action")
    response = superuser_client.get(reverse("audit:log-export"), {"club_id": club.id})
    assert response["Content-Type"].startswith("text/csv")
    assert "attachment" in response["Content-Disposition"]
    text = response.content.decode("utf-8-sig")
    lines = text.strip().split("\r\n")
    assert lines[0].startswith("Horodatage (UTC);Club;Acteur")
    assert len(lines) == 2
    assert "'=cmd.injection" in text


def test_export_csv_neutralizes_support_session_id(superuser_client):
    club = ClubSettingsFactory().club
    create_audit_log(
        actor=SuperuserFactory(),
        club=club,
        action_type="treasury.payment.corrected",
        object_type="Payment",
        object_id=1,
        acted_as_ghost=True,
        support_session_id="=HYPERLINK(1)",
    )
    text = superuser_client.get(reverse("audit:log-export"), {"club_id": club.id}).content.decode("utf-8-sig")
    assert "'=HYPERLINK(1)" in text
    assert ";=HYPERLINK(1)" not in text


def test_action_types_endpoint(superuser_client):
    AuditLogFactory(action_type="auth.login_failed")
    results = superuser_client.get(reverse("audit:action-types")).data["results"]
    assert {"action_type": "auth.login_failed", "is_alert": True} in results


def test_journal_stays_append_only():
    entry = AuditLogFactory()
    with pytest.raises(Exception):
        AuditLog.objects.filter(pk=entry.pk).delete()
