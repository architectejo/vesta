"""Lecture des dossiers d'adhesion (CDC 4.3) : dossier d'un joueur, fiches a
signer du parrain, dossiers suivis par le President. Lecture seule."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from apps.clubs.services import refuse_sponsor_application
from apps.clubs.tests.test_membership_application import add_player, build_context, pay
from apps.clubs.tests.test_views_membership_application import _authenticated_client
from apps.treasury.tests.conftest import make_member

pytestmark = pytest.mark.django_db


def test_dossier_visible_par_president_et_parrain_refuse_aux_autres():
    ctx = build_context()
    membership, _app = add_player(ctx)
    url = reverse("clubs:application-by-membership", kwargs={"membership_id": membership.id})

    ok = _authenticated_client(ctx.president.user).get(url)
    assert ok.status_code == status.HTTP_200_OK
    assert ok.data["player"]["first_name"] == "Recrue"
    assert ok.data["sponsor"]["membership_id"] == ctx.sponsor.id
    assert ok.data["membership_fee_paid"] is False
    assert _authenticated_client(ctx.sponsor.user).get(url).status_code == status.HTTP_200_OK

    assert _authenticated_client(ctx.treasurer.user).get(url).status_code == status.HTTP_200_OK

    other = make_member(ctx.club)
    assert _authenticated_client(other.user).get(url).status_code == status.HTTP_403_FORBIDDEN


def test_dossier_d_un_autre_club_est_introuvable():
    ctx = build_context()
    membership, _app = add_player(ctx)
    other_ctx = build_context()
    url = reverse("clubs:application-by-membership", kwargs={"membership_id": membership.id})
    assert _authenticated_client(other_ctx.president.user).get(url).status_code == status.HTTP_404_NOT_FOUND


def test_fiches_a_signer_du_parrain():
    ctx = build_context()
    _m, application = add_player(ctx)
    url = reverse("clubs:applications-pending-sponsor-signature")
    client = _authenticated_client(ctx.sponsor.user)
    assert client.get(url).data == []  # fiche pas encore generee (frais impayes)

    pay(ctx, application)
    data = client.get(url).data
    assert len(data) == 1 and data[0]["id"] == application.id
    assert data[0]["membership_fee_paid"] is True
    assert _authenticated_client(ctx.president.user).get(url).data == []


def test_dossiers_suivis_par_le_president():
    ctx = build_context()
    _m, application = add_player(ctx)
    pay(ctx, application)
    refuse_sponsor_application(application=application, sponsor_user=ctx.sponsor.user, reason="Inconnu")
    url = reverse("clubs:applications-pending-president-decision")

    response = _authenticated_client(ctx.president.user).get(url)
    assert response.status_code == status.HTTP_200_OK
    assert [a["id"] for a in response.data["refused"]] == [application.id]
    assert response.data["refused"][0]["sponsor_refused_reason"] == "Inconnu"
    assert response.data["awaiting_sponsor"] == []
    assert _authenticated_client(ctx.sponsor.user).get(url).status_code == status.HTTP_403_FORBIDDEN
