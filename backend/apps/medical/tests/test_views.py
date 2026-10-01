"""Vues DRF de l'app medical : permissions (matrice 2.4) et etancheite
multi-club (CLAUDE.md regle n8 -- un objet d'un autre club renvoie 404,
jamais 403)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.medical import services
from apps.medical.tests.conftest import client_for

pytestmark = pytest.mark.django_db


def test_health_record_forbidden_for_captain(ctx):
    client = client_for(ctx.captain.user)
    url = reverse("medical:health-record-detail", args=[ctx.player.pk])
    response = client.get(url)
    assert response.status_code == 403


def test_health_record_accessible_by_doctor(ctx):
    client = client_for(ctx.doctor.user)
    url = reverse("medical:health-record-detail", args=[ctx.player.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert response.data["fitness_status"] == "fit"


def test_health_record_accessible_by_self(ctx):
    client = client_for(ctx.player.user)
    url = reverse("medical:health-record-detail", args=[ctx.player.pk])
    response = client.get(url)
    assert response.status_code == 200


def test_health_record_forbidden_for_president_without_consent(ctx):
    client = client_for(ctx.president.user)
    url = reverse("medical:health-record-detail", args=[ctx.player.pk])
    response = client.get(url)
    assert response.status_code == 403


def test_health_record_404_for_membership_of_another_club(ctx, other_ctx):
    """Isolation multi-tenant (CLAUDE.md regle n8) : jamais 403, toujours
    404 pour un objet d'un autre club (pas de fuite d'existence)."""

    client = client_for(ctx.doctor.user)
    url = reverse("medical:health-record-detail", args=[other_ctx.player.pk])
    response = client.get(url)
    assert response.status_code == 404


def test_fitness_update_forbidden_for_coach(ctx):
    client = client_for(ctx.coach.user)
    url = reverse("medical:fitness-update", args=[ctx.player.pk])
    response = client.patch(url, {"fitness_status": "fit"}, format="json")
    assert response.status_code == 403


def test_fitness_update_by_doctor_succeeds(ctx):
    client = client_for(ctx.doctor.user)
    url = reverse("medical:fitness-update", args=[ctx.player.pk])
    response = client.patch(url, {"fitness_status": "fit_with_restriction"}, format="json")
    assert response.status_code == 200
    assert response.data["fitness_status"] == "fit_with_restriction"


def test_report_injury_forbidden_for_player(ctx):
    client = client_for(ctx.player.user)
    url = reverse("medical:injury-list")
    response = client.post(
        url, {"membership_id": ctx.player.pk, "circumstances": "Chute au sol."}, format="json"
    )
    assert response.status_code == 403


def test_report_injury_by_coach_succeeds(ctx):
    client = client_for(ctx.coach.user)
    url = reverse("medical:injury-list")
    response = client.post(
        url, {"membership_id": ctx.player.pk, "circumstances": "Chute au sol."}, format="json"
    )
    assert response.status_code == 201


def test_injury_detail_404_for_other_club(ctx, other_ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
    client = client_for(other_ctx.doctor.user)
    url = reverse("medical:injury-detail", args=[injury.pk])
    response = client.get(url)
    assert response.status_code == 404


def test_injury_detail_forbidden_for_teammate(ctx):
    injury = services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")
    client = client_for(ctx.other_player.user)
    url = reverse("medical:injury-detail", args=[injury.pk])
    response = client.get(url)
    assert response.status_code == 403


def test_my_president_access_grant_and_revoke_round_trip(ctx):
    client = client_for(ctx.player.user)
    url = reverse("medical:my-president-access")

    response = client.get(url)
    assert response.status_code == 200
    assert response.data["granted"] is False

    response = client.post(url)
    assert response.status_code == 200
    assert response.data["granted"] is True

    response = client.delete(url)
    assert response.status_code == 200
    assert response.data["granted"] is False


def test_unfit_page_forbidden_for_vice_president(ctx):
    client = client_for(ctx.vice_president.user)
    url = reverse("medical:page-unfit")
    response = client.get(url)
    assert response.status_code == 403
