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


# ---------------------------------------------------------------------------
# Sans club actif : 403 « Aucun club actif. », jamais 500 (regle n8)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,args,method",
    [
        ("medical:health-record-detail", [1], "get"),
        ("medical:fitness-update", [1], "patch"),
        ("medical:my-self-declaration", [], "patch"),
        ("medical:my-processing-consent", [], "post"),
        ("medical:my-president-access", [], "get"),
        ("medical:injury-list", [], "post"),
        ("medical:injury-detail", [1], "get"),
        ("medical:injury-complete", [1], "patch"),
        ("medical:injury-followups", [1], "post"),
        ("medical:injury-return", [1], "post"),
        ("medical:injury-document-upload", [1], "post"),
        ("medical:page-to-complete", [], "get"),
        ("medical:page-recent-injuries", [], "get"),
        ("medical:page-unfit", [], "get"),
        ("medical:document-download", [1], "get"),
    ],
)
def test_no_active_club_gives_403_not_500(name, args, method):
    from apps.accounts.tests.factories import SuperuserFactory, UserFactory

    for user in (UserFactory(), SuperuserFactory()):  # sans adhesion / Superuser hors Ghost Mode
        client = client_for(user)
        client.raise_request_exception = False
        response = getattr(client, method)(reverse(name, args=args), {}, format="json")
        assert response.status_code == 403, (name, response.status_code)
        assert response.json()["detail"] == "Aucun club actif."


def test_no_active_club_unauthenticated_stays_401():
    from rest_framework.test import APIClient

    assert APIClient().get(reverse("medical:page-unfit")).status_code == 401


def _make_injury(ctx):
    from apps.core.tenant import active_club

    with active_club(ctx.club):
        return services.report_injury(membership=ctx.player, actor=ctx.coach.user, circumstances="Chute.")


def test_injury_detail_view_is_logged_for_doctor_and_player(ctx):
    from apps.audit.models import AuditLog

    injury = _make_injury(ctx)
    url = reverse("medical:injury-detail", args=[injury.pk])
    for who in (ctx.doctor, ctx.player):
        assert client_for(who.user).get(url).status_code == 200
    entries = AuditLog.objects.filter(action_type="medical.injury.viewed", object_id=str(injury.pk))
    assert {e.actor_id for e in entries} == {ctx.doctor.user_id, ctx.player.user_id}
    assert all(e.club_id == ctx.club.id and not e.before and not e.after for e in entries)


def test_injury_detail_denied_is_not_logged(ctx):
    from apps.audit.models import AuditLog

    injury = _make_injury(ctx)
    response = client_for(ctx.coach.user).get(reverse("medical:injury-detail", args=[injury.pk]))
    assert response.status_code == 403
    assert not AuditLog.objects.filter(action_type="medical.injury.viewed").exists()
    assert not AuditLog.objects.filter(action_type="medical.record.viewed_by_president").exists()


def test_injury_detail_other_club_is_404_and_not_logged(ctx, other_ctx):
    from apps.audit.models import AuditLog

    injury = _make_injury(other_ctx)
    response = client_for(ctx.doctor.user).get(reverse("medical:injury-detail", args=[injury.pk]))
    assert response.status_code == 404
    assert not AuditLog.objects.filter(action_type="medical.injury.viewed").exists()


def test_injury_detail_president_with_consent_logged_as_president(ctx):
    from apps.audit.models import AuditLog
    from apps.core.tenant import active_club

    injury = _make_injury(ctx)
    with active_club(ctx.club):
        services.grant_president_access(membership=ctx.player, actor=ctx.player.user)
    response = client_for(ctx.president.user).get(reverse("medical:injury-detail", args=[injury.pk]))
    assert response.status_code == 200
    assert AuditLog.objects.filter(
        action_type="medical.record.viewed_by_president", actor=ctx.president.user, object_id=str(injury.pk)
    ).exists()
