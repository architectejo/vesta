"""Test de bout en bout du Ghost Mode (CDC 4.18, 5.4 ; tache 1.8) :

1. Le Superuser ouvre une session de support par l'API REST reelle
   (``POST /api/v1/licences/support-sessions/start/``).
2. L'identifiant renvoye est utilise comme en-tete ``X-Support-Session``
   sur une requete authentifiee ulterieure : le club actif se restreint
   au SEUL club de la session (jamais un autre, meme si un second club
   existe), et le contexte Ghost Mode est arme.
3. Toute ``AuditLog`` ecrite pendant ce temps porte automatiquement
   ``acted_as_ghost=True``/``support_session_id`` correspondant.
4. Le masquage centralise (``apps.audit.services.get_actor_display_name``)
   affiche « Systeme Vesta » a un lecteur de club, jamais a un Superuser.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.services import GHOST_ACTOR_DISPLAY_NAME, get_actor_display_name
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.core.authentication import TenantJWTAuthentication
from apps.core.ghost_context import clear_ghost_context
from apps.core.services import log_action
from apps.core.tenant import get_active_club, set_active_club


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _reset_contexts_after_each_test():
    yield
    set_active_club(None)
    clear_ghost_context()


def _authenticate(api_client, user):
    access = str(RefreshToken.for_user(user).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return access


@pytest.mark.django_db
class TestGhostModeEndToEnd:
    def test_session_ouverte_par_l_api_puis_restreint_strictement_au_club_cible(self, api_client):
        superuser = SuperuserFactory()
        club_a = ClubFactory()
        club_b = ClubFactory()
        MembershipFactory(club=club_a, status="active")
        MembershipFactory(club=club_b, status="active")

        access = _authenticate(api_client, superuser)
        start_response = api_client.post(
            reverse("licences:support-session-start"),
            {"club_id": club_a.pk, "reason": "Verification d'une adhesion."},
            format="json",
        )
        assert start_response.status_code == status.HTTP_201_CREATED
        session_id = start_response.data["id"]

        request = RequestFactory().get(
            "/", HTTP_AUTHORIZATION=f"Bearer {access}", HTTP_X_SUPPORT_SESSION=str(session_id)
        )
        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() == club_a
        assert get_active_club() != club_b

    def test_action_faite_pendant_la_session_est_marquee_ghost_et_masquee_cote_club(self, api_client):
        superuser = SuperuserFactory()
        club = ClubFactory()

        access = _authenticate(api_client, superuser)
        start_response = api_client.post(
            reverse("licences:support-session-start"),
            {"club_id": club.pk, "reason": "Correction d'un paiement."},
            format="json",
        )
        session_id = start_response.data["id"]

        request = RequestFactory().get(
            "/", HTTP_AUTHORIZATION=f"Bearer {access}", HTTP_X_SUPPORT_SESSION=str(session_id)
        )
        TenantJWTAuthentication().authenticate(request)

        entry = log_action(actor=superuser, action_type="treasury.payment.corrected", obj=club)

        assert entry.acted_as_ghost is True
        assert entry.support_session_id == str(session_id)
        assert entry.actor_id == superuser.id  # identite reelle toujours conservee (CDC 5.4)

        club_member = UserFactory()
        assert get_actor_display_name(entry, reader=club_member) == GHOST_ACTOR_DISPLAY_NAME
        assert get_actor_display_name(entry, reader=superuser) != GHOST_ACTOR_DISPLAY_NAME
