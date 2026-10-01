"""Tests du branchement Ghost Mode sur `TenantJWTAuthentication` (CDC 5.4 ; tache 1.8).

Complete `apps.core.tests.test_authentication` (club actif, tache 1.3)
sans le modifier : ce fichier est dedie au mecanisme ajoute par la tache
1.8 (en-tete `X-Support-Session`).
"""

from __future__ import annotations

import datetime

import pytest
from django.test import RequestFactory
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.tests.factories import ClubFactory
from apps.core.authentication import TenantJWTAuthentication
from apps.core.ghost_context import clear_ghost_context, get_ghost_context
from apps.core.tenant import get_active_club, set_active_club
from apps.licences.tests.factories import SupportSessionFactory


@pytest.fixture(autouse=True)
def _reset_contexts_after_each_test():
    yield
    set_active_club(None)
    clear_ghost_context()


def _authenticated_request(user, headers: dict | None = None):
    access = RefreshToken.for_user(user).access_token
    extra = {f"HTTP_{key}": value for key, value in (headers or {}).items()}
    return RequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {access}", **extra)


@pytest.mark.django_db
class TestGhostModeHeaderWiring:
    def test_en_tete_absent_ne_change_rien_pour_un_superuser(self):
        superuser = SuperuserFactory()
        request = _authenticated_request(superuser)

        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() is None
        assert get_ghost_context() is None

    def test_session_valide_arme_le_club_actif_et_le_contexte_ghost(self):
        superuser = SuperuserFactory()
        club = ClubFactory()
        session = SupportSessionFactory(superuser=superuser, club=club)

        request = _authenticated_request(superuser, {"X_SUPPORT_SESSION": str(session.pk)})
        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() == club
        ghost = get_ghost_context()
        assert ghost is not None
        assert ghost.support_session_id == str(session.pk)

    def test_session_d_un_autre_superuser_est_ignoree(self):
        superuser = SuperuserFactory()
        autre_superuser = SuperuserFactory()
        session = SupportSessionFactory(superuser=autre_superuser)

        request = _authenticated_request(superuser, {"X_SUPPORT_SESSION": str(session.pk)})
        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() is None
        assert get_ghost_context() is None

    def test_session_expiree_est_ignoree(self):
        superuser = SuperuserFactory()
        now = timezone.now()
        session = SupportSessionFactory(superuser=superuser, started_at=now - datetime.timedelta(minutes=90))

        request = _authenticated_request(superuser, {"X_SUPPORT_SESSION": str(session.pk)})
        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() is None
        assert get_ghost_context() is None

    def test_session_terminee_par_anticipation_est_ignoree(self):
        superuser = SuperuserFactory()
        now = timezone.now()
        session = SupportSessionFactory(superuser=superuser, started_at=now)
        session.ended_at = now
        session.save()

        request = _authenticated_request(superuser, {"X_SUPPORT_SESSION": str(session.pk)})
        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() is None

    def test_identifiant_malforme_est_ignore_sans_lever(self):
        superuser = SuperuserFactory()
        request = _authenticated_request(superuser, {"X_SUPPORT_SESSION": "n-importe-quoi"})

        # Ne doit jamais lever : un en-tete malforme est traite comme absent.
        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() is None

    def test_en_tete_ignore_pour_un_joueur_normal(self):
        """Seuls les Superusers passent par ce mecanisme -- un joueur normal
        garde son club actif deduit de son adhesion, jamais d'un en-tete."""

        from apps.clubs.tests.factories import MembershipFactory

        membership = MembershipFactory(status="active")
        session = SupportSessionFactory()

        request = _authenticated_request(membership.user, {"X_SUPPORT_SESSION": str(session.pk)})
        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() == membership.club
        assert get_ghost_context() is None

    def test_ne_donne_jamais_acces_a_un_autre_club_que_celui_de_la_session(self):
        """Etancheite : le club actif vient TOUJOURS de `session.club` resolu
        en base, jamais d'un parametre transmis directement par le client."""

        superuser = SuperuserFactory()
        club_de_la_session = ClubFactory()
        autre_club = ClubFactory()
        session = SupportSessionFactory(superuser=superuser, club=club_de_la_session)

        request = _authenticated_request(superuser, {"X_SUPPORT_SESSION": str(session.pk)})
        TenantJWTAuthentication().authenticate(request)

        assert get_active_club() == club_de_la_session
        assert get_active_club() != autre_club
