"""Tests HTTP de l'API tenant-aware des types de cotisation."""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import MembershipFactory
from apps.treasury.models import ContributionType
from apps.treasury.tests.conftest import ClubContext
from apps.treasury.tests.factories import ContributionTypeFactory

pytestmark = pytest.mark.django_db


def client_for(user) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def list_url():
    return reverse("treasury:contribution-type-list")


def detail_url(ctype):
    return reverse("treasury:contribution-type-detail", args=[ctype.pk])


def payload(name="Mensuelle", **overrides):
    data = {
        "name": name,
        "nature": ContributionType.Nature.MANDATORY,
        "amount": "20.00",
        "periodicity": ContributionType.Periodicity.MONTHLY,
        "scope": ContributionType.Scope.ALL,
    }
    data.update(overrides)
    return data


def test_president_creates_updates_and_archives_type(ctx: ClubContext):
    client = client_for(ctx.president.user)
    created = client.post(list_url(), payload(), format="json")
    assert created.status_code == status.HTTP_201_CREATED
    ctype_id = created.data["id"]

    updated = client.patch(detail_url(ContributionType.all_objects.get(pk=ctype_id)), {"amount": "25.50"}, format="json")
    assert updated.status_code == status.HTTP_200_OK
    assert updated.data["amount"] == "25.50"

    archived = client.post(detail_url(ContributionType.all_objects.get(pk=ctype_id)), {"action": "archive"}, format="json")
    assert archived.status_code == status.HTTP_200_OK
    assert archived.data["status"] == ContributionType.Status.ARCHIVED
    assert AuditLog.objects.filter(action_type="treasury.contribution_type.updated").exists()
    assert AuditLog.objects.filter(action_type="treasury.contribution_type.archived").exists()


@pytest.mark.parametrize("role_name", ["vice_president", "assistant_treasurer"])
def test_read_roles_can_read_but_cannot_write(ctx: ClubContext, role_name: str):
    client = client_for(getattr(ctx, role_name).user)
    assert client.get(list_url()).status_code == status.HTTP_200_OK
    assert client.post(list_url(), payload(), format="json").status_code == status.HTTP_403_FORBIDDEN


def test_other_roles_are_refused(ctx: ClubContext):
    client = client_for(ctx.player.user)
    assert client.get(list_url()).status_code == status.HTTP_403_FORBIDDEN
    assert client.post(list_url(), payload(), format="json").status_code == status.HTTP_403_FORBIDDEN


def test_list_and_detail_are_scoped_to_active_club(ctx: ClubContext, other_ctx: ClubContext):
    own = ContributionTypeFactory(club=ctx.club)
    foreign = ContributionTypeFactory(club=other_ctx.club)
    response = client_for(ctx.president.user).get(list_url())
    assert response.status_code == status.HTTP_200_OK
    assert {row["id"] for row in response.data} == {own.pk}
    assert client_for(ctx.president.user).get(detail_url(foreign)).status_code == status.HTTP_404_NOT_FOUND


def test_archived_types_are_available_only_with_explicit_filter(ctx: ClubContext):
    archived = ContributionTypeFactory(
        club=ctx.club,
        status=ContributionType.Status.ARCHIVED,
        archived_at=timezone.now(),
        archived_by=ctx.president.user,
    )
    assert client_for(ctx.president.user).get(list_url()).data == []
    response = client_for(ctx.president.user).get(list_url(), {"status": "archived"})
    assert response.status_code == status.HTTP_200_OK
    assert [row["id"] for row in response.data] == [archived.pk]


def test_member_balance_summary_is_available_to_his_own_membership(ctx: ClubContext):
    response = client_for(ctx.player.user).get(reverse("treasury:my-balance"))

    assert response.status_code == status.HTTP_200_OK, response.data
    assert response.data["membership_id"] == ctx.player.pk
    assert response.data["balance"] == "0.00"
    assert response.data["amount_due"] == "0.00"
    assert response.data["is_in_good_standing"] is True


def test_member_balance_requires_authentication_and_an_active_membership(ctx: ClubContext):
    url = reverse("treasury:my-balance")

    assert APIClient().get(url).status_code == status.HTTP_401_UNAUTHORIZED
    assert client_for(ctx.pending_member.user).get(url).status_code == status.HTTP_403_FORBIDDEN


def test_member_balance_refuses_ambiguous_active_club(ctx: ClubContext, other_ctx: ClubContext):
    MembershipFactory(club=other_ctx.club, user=ctx.player.user, status="active")

    response = client_for(ctx.player.user).get(reverse("treasury:my-balance"))

    assert response.status_code == status.HTTP_403_FORBIDDEN

