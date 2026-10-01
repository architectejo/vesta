"""Complements de couverture Ghost Mode / etancheite entre clubs (CDC 4.18,
5.4 ; tache 1.8t -- revue independante de test-engineer).

Ce fichier ne duplique pas `test_services_ghost_mode.py` /
`test_authentication_ghost_mode.py` / `test_ghost_mode_end_to_end.py` :
il cible specifiquement les scenarios cites par la revue comme les plus
critiques et pas encore couverts explicitement :

1. Deux sessions de support valides SIMULTANEMENT ouvertes par le MEME
   Superuser sur deux clubs DIFFERENTS -- aucune ne doit jamais laisser
   fuiter l'acces a l'autre club, y compris via l'API REST reelle.
2. Isolation reelle entre THREADS (simulation de deux requetes HTTP
   concurrentes sur un serveur WSGI synchrone) : les `contextvars`
   (club actif, contexte Ghost Mode) ne doivent jamais se mélanger entre
   deux threads qui authentifient des sessions differentes en parallele.
3. Frontiere exacte de `is_support_session_valid` a l'instant PRECIS de
   `expires_at` (egalite stricte).
4. Composition avec le garde-fou d'ecriture `TenantMismatchError`
   (`apps.core.models.TenantModel.save()`) : meme arme en Ghost Mode, une
   tentative d'ecriture sur une donnee tenant-aware d'un AUTRE club que
   celui de la session est refusee.
"""

from __future__ import annotations

import datetime
import threading

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.models import Membership
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.core.authentication import TenantJWTAuthentication
from apps.core.ghost_context import clear_ghost_context, get_ghost_context
from apps.core.tenant import TenantMismatchError, active_club, get_active_club, set_active_club
from apps.licences.services import enter_ghost_mode, is_support_session_valid
from apps.licences.tests.factories import SupportSessionFactory


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
class TestDeuxSessionsSimultaneesSurDeuxClubs:
    """Priorite n1 de la revue : deux sessions valides EN MEME TEMPS sur
    deux clubs differents, ouvertes par le meme Superuser via l'API REST
    reelle -- jamais de fuite de l'une vers l'autre."""

    def test_chaque_en_tete_reste_strictement_scope_a_son_propre_club(self, api_client):
        superuser = SuperuserFactory()
        club_a = ClubFactory()
        club_b = ClubFactory()
        MembershipFactory(club=club_a, status="active")
        MembershipFactory(club=club_b, status="active")

        access = _authenticate(api_client, superuser)

        start_a = api_client.post(
            reverse("licences:support-session-start"),
            {"club_id": club_a.pk, "reason": "Intervention club A."},
            format="json",
        )
        start_b = api_client.post(
            reverse("licences:support-session-start"),
            {"club_id": club_b.pk, "reason": "Intervention club B."},
            format="json",
        )
        assert start_a.status_code == status.HTTP_201_CREATED
        assert start_b.status_code == status.HTTP_201_CREATED
        session_a_id = start_a.data["id"]
        session_b_id = start_b.data["id"]

        # Les DEUX sessions sont valides EN MEME TEMPS (ni expiree, ni
        # terminee) : ce n'est pas un cas "l'une apres l'autre".
        request_a = RequestFactory().get(
            "/", HTTP_AUTHORIZATION=f"Bearer {access}", HTTP_X_SUPPORT_SESSION=str(session_a_id)
        )
        TenantJWTAuthentication().authenticate(request_a)
        assert get_active_club() == club_a
        assert get_active_club() != club_b
        set_active_club(None)
        clear_ghost_context()

        request_b = RequestFactory().get(
            "/", HTTP_AUTHORIZATION=f"Bearer {access}", HTTP_X_SUPPORT_SESSION=str(session_b_id)
        )
        TenantJWTAuthentication().authenticate(request_b)
        assert get_active_club() == club_b
        assert get_active_club() != club_a

    def test_l_en_tete_de_la_session_b_n_ouvre_jamais_le_club_a_meme_avec_pk_voisin(self, api_client):
        """Manipulation directe de l'en-tete : un Superuser qui essaierait
        de deviner/forcer l'identifiant d'une AUTRE de ses sessions ne peut
        de toute facon obtenir que le club REELLEMENT attache a cette
        session en base -- jamais un club choisi via un autre parametre."""

        superuser = SuperuserFactory()
        club_a = ClubFactory()
        club_b = ClubFactory()
        session_a = SupportSessionFactory(superuser=superuser, club=club_a)
        session_b = SupportSessionFactory(superuser=superuser, club=club_b)

        access = str(RefreshToken.for_user(superuser).access_token)

        for session, expected_club, forbidden_club in (
            (session_a, club_a, club_b),
            (session_b, club_b, club_a),
        ):
            request = RequestFactory().get(
                "/", HTTP_AUTHORIZATION=f"Bearer {access}", HTTP_X_SUPPORT_SESSION=str(session.pk)
            )
            TenantJWTAuthentication().authenticate(request)
            assert get_active_club() == expected_club
            assert get_active_club() != forbidden_club
            set_active_club(None)
            clear_ghost_context()


class TestIsolationEntreThreadsConcurrents:
    """Priorite n1 de la revue : « une requete concurrente ». Un serveur
    WSGI synchrone (Passenger/LiteSpeed, cf CLAUDE.md) traite les requetes
    HTTP simultanees sur des threads distincts : ce test le simule
    directement avec `threading.Thread`, sans passer par le test client
    Django (qui serialise les appels), pour prouver que les
    `contextvars` (club actif, contexte Ghost Mode) ne se melangent
    jamais entre deux threads qui authentifient des sessions de support
    differentes en parallele."""

    @pytest.mark.django_db(transaction=True)
    def test_deux_threads_authentifiant_deux_sessions_differentes_ne_se_contaminent_jamais(self):
        """``transaction=True`` (plutot que le wrapping habituel en une
        seule transaction non commitee) : chaque thread ouvre sa PROPRE
        connexion SQLite -- il lui faut donc voir les donnees de la
        fixture reellement COMMITEES, pas seulement visibles dans la
        transaction (non partagee entre threads) du thread principal.
        `connections.close_all()` en fin de thread : une connexion SQLite
        oubliee ouverte sur un thread qui se termine ferait echouer le
        nettoyage de la base de test entre les tests suivants."""

        from django.db import connections

        superuser = SuperuserFactory()
        club_a = ClubFactory()
        club_b = ClubFactory()
        session_a = SupportSessionFactory(superuser=superuser, club=club_a)
        session_b = SupportSessionFactory(superuser=superuser, club=club_b)
        access = str(RefreshToken.for_user(superuser).access_token)

        barrier = threading.Barrier(2)
        results: dict[str, object] = {}
        errors: list[BaseException] = []

        def _run(label: str, session, expected_club):
            try:
                request = RequestFactory().get(
                    "/",
                    HTTP_AUTHORIZATION=f"Bearer {access}",
                    HTTP_X_SUPPORT_SESSION=str(session.pk),
                )
                # Synchronise les deux threads pour maximiser le
                # chevauchement reel des deux authentifications.
                barrier.wait(timeout=5)
                TenantJWTAuthentication().authenticate(request)
                # Pause volontaire : si les contextvars etaient
                # partages entre threads, l'autre thread aurait
                # largement le temps d'ecraser cette valeur ici.
                barrier.wait(timeout=5)
                results[label] = get_active_club()
                ghost = get_ghost_context()
                results[f"{label}_ghost"] = ghost.support_session_id if ghost else None
                set_active_club(None)
                clear_ghost_context()
            except BaseException as exc:  # pragma: no cover - remonte au thread principal
                errors.append(exc)
            finally:
                connections.close_all()

        thread_a = threading.Thread(target=_run, args=("a", session_a, club_a))
        thread_b = threading.Thread(target=_run, args=("b", session_b, club_b))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)

        assert not errors, errors
        assert results["a"] == club_a
        assert results["b"] == club_b
        assert results["a"] != club_b
        assert results["b"] != club_a
        assert results["a_ghost"] == str(session_a.pk)
        assert results["b_ghost"] == str(session_b.pk)


@pytest.mark.django_db
class TestFrontiereExacteExpiresAt:
    """Priorite n1 de la revue : inegalite stricte/large au moment PRECIS
    de l'expiration. `is_support_session_valid` compare avec `<`
    (strict) : a l'instant EXACT de `expires_at`, la session doit deja
    etre consideree comme invalide (jamais acceptee « pile a la limite
    »)."""

    def test_invalide_a_l_instant_exact_de_expires_at(self):
        now = timezone.now()
        session = SupportSessionFactory(started_at=now)

        assert is_support_session_valid(session, now=session.expires_at) is False
        # Un instant avant, encore valide (bascule bien exactement a
        # `expires_at`, pas avant).
        assert is_support_session_valid(
            session, now=session.expires_at - datetime.timedelta(microseconds=1)
        ) is True

    def test_valide_a_l_instant_exact_de_started_at(self):
        """Borne inferieure inclusive (`<=`) : symmetrie volontaire avec
        la borne superieure exclusive, verifiee explicitement."""

        now = timezone.now()
        session = SupportSessionFactory(started_at=now)

        assert is_support_session_valid(session, now=now) is True


@pytest.mark.django_db
class TestGhostModeEtTenantMismatchError:
    """Composition de deux garde-fous independants : le Ghost Mode arme
    le club actif au SEUL club de la session (`apps.core.tenant`), et
    `apps.core.models.TenantModel.save()` refuse toute ecriture dont le
    `club` differe du club actif courant. Preuve bout-en-bout que ces
    deux mecanismes se combinent correctement : meme un Superuser en
    Ghost Mode sur le club A ne peut pas ecrire une donnee tenant-aware
    portant le club B, meme par une manipulation directe du champ
    `club` sur l'objet avant `.save()`."""

    def test_ecriture_directe_vers_un_autre_club_refusee_pendant_une_session_ghost_mode(self):
        """Instance minimale (seul `club` renseigne) : le controle de
        `TenantModel.save()` intervient AVANT `full_clean()` (meme
        technique que `apps.core.tests.test_tenant_scope_coverage`), pas
        besoin de remplir les autres champs obligatoires de `Membership`
        pour declencher `TenantMismatchError`."""

        superuser = SuperuserFactory()
        club_a = ClubFactory()
        club_b = ClubFactory()
        session = SupportSessionFactory(superuser=superuser, club=club_a)

        with enter_ghost_mode(session=session, superuser=superuser):
            instance = Membership(club=club_b)
            with pytest.raises(TenantMismatchError):
                instance.save()

    def test_mise_a_jour_d_un_enregistrement_d_un_autre_club_refusee_pendant_une_session_ghost_mode(self):
        superuser = SuperuserFactory()
        club_a = ClubFactory()
        club_b = ClubFactory()
        membership_de_b = MembershipFactory(club=club_b)
        session = SupportSessionFactory(superuser=superuser, club=club_a)

        with enter_ghost_mode(session=session, superuser=superuser):
            membership_de_b.position = Membership.Position.FORWARD
            with pytest.raises(TenantMismatchError):
                membership_de_b.save(update_fields=["position"])

        membership_de_b.refresh_from_db()
        assert membership_de_b.position != Membership.Position.FORWARD

    def test_ecriture_vers_le_club_de_la_session_reussit(self):
        superuser = SuperuserFactory()
        club_a = ClubFactory()
        membership_de_a = MembershipFactory(club=club_a)
        session = SupportSessionFactory(superuser=superuser, club=club_a)

        with enter_ghost_mode(session=session, superuser=superuser):
            membership_de_a.position = Membership.Position.FORWARD
            membership_de_a.save(update_fields=["position"])

        membership_de_a.refresh_from_db()
        assert membership_de_a.position == Membership.Position.FORWARD
