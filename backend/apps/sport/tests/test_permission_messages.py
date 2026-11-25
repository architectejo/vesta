"""Messages 403 : l'Assistant du Coach étant autorisé, ils doivent le citer
(troisième série de tests, 15/11/2026)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from apps.sport.tests.conftest import client_for
from apps.sport.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db

EXPECTED = "Réservé au Coach du club ou à son assistant."


def test_creation_de_seance_refusee_cite_l_assistant(ctx):
    response = client_for(ctx.player.user).post(reverse("sport:session-list"), {}, format="json")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["detail"] == EXPECTED


def test_publication_du_resultat_refusee_cite_l_assistant(ctx):
    match = MatchFactory(club=ctx.club, event__club=ctx.club, event__season=ctx.season)

    response = client_for(ctx.player.user).post(
        reverse("sport:match-publish-result", args=[match.pk]), {}, format="json"
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["detail"] == EXPECTED


def test_aucun_message_reserve_au_coach_n_oublie_l_assistant():
    from apps.clubs import permissions as clubs_permissions
    from apps.logistics import permissions as logistics_permissions
    from apps.medical import permissions as medical_permissions
    from apps.mercato import permissions as mercato_permissions
    from apps.sport import permissions as sport_permissions

    for module in (clubs_permissions, logistics_permissions, medical_permissions, mercato_permissions, sport_permissions):
        for name, cls in vars(module).items():
            message = getattr(cls, "message", None)
            roles = getattr(cls, "required_roles", None)
            if not isinstance(message, str) or "Coach" not in message or roles is None:
                continue
            if "Assistant du Coach" in {str(role.label) for role in roles} or "assistant_coach" in {str(r) for r in roles}:
                assert "assistant" in message, f"{module.__name__}.{name} : {message}"
