"""Tests des sessions de support / Ghost Mode (CDC 4.18, 5.4 ; tache 1.8).

Sources : docs/cahier-des-charges.md 4.18, 5.4 ;
docs/lot0/schema-donnees.md §13.1.
"""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.core.ghost_context import get_ghost_context
from apps.core.services import log_action
from apps.core.tenant import NoActiveClubError, get_active_club
from apps.licences.models import SupportSession
from apps.licences.services import (
    SupportSessionError,
    SupportSessionPermissionError,
    end_support_session,
    enter_ghost_mode,
    is_support_session_valid,
    start_support_session,
)
from apps.licences.tests.factories import SupportSessionFactory


@pytest.mark.django_db
class TestStartEndSupportSession:
    def test_ouvre_une_session_avec_motif_obligatoire(self):
        superuser = SuperuserFactory()
        club = ClubFactory()

        session = start_support_session(superuser=superuser, club=club, reason="Correction d'un score de match.")

        assert session.pk is not None
        assert session.club_id == club.id
        assert session.superuser_id == superuser.id
        assert session.expires_at == session.started_at + datetime.timedelta(minutes=60)

    def test_journalise_l_ouverture_avec_l_identite_reelle_hors_ghost_mode(self):
        superuser = SuperuserFactory()
        club = ClubFactory()

        session = start_support_session(superuser=superuser, club=club, reason="Motif de test.")

        entry = AuditLog.objects.get(action_type="licence.support_session.started", object_id=str(session.pk))
        assert entry.actor_id == superuser.id
        assert entry.acted_as_ghost is False

    def test_refuse_un_motif_vide(self):
        superuser = SuperuserFactory()
        club = ClubFactory()

        with pytest.raises(SupportSessionError):
            start_support_session(superuser=superuser, club=club, reason="   ")

    def test_refuse_un_non_superuser(self):
        joueur_normal = UserFactory(is_superuser=False)
        club = ClubFactory()

        with pytest.raises(PermissionError):
            start_support_session(superuser=joueur_normal, club=club, reason="Motif.")

    def test_fin_anticipee_par_le_meme_superuser(self):
        superuser = SuperuserFactory()
        session = SupportSessionFactory(superuser=superuser)

        end_support_session(session=session, superuser=superuser)

        session.refresh_from_db()
        assert session.ended_at is not None
        assert not is_support_session_valid(session)

    def test_fin_anticipee_refusee_a_un_autre_superuser(self):
        superuser = SuperuserFactory()
        autre_superuser = SuperuserFactory()
        session = SupportSessionFactory(superuser=superuser)

        with pytest.raises(SupportSessionPermissionError):
            end_support_session(session=session, superuser=autre_superuser)

        session.refresh_from_db()
        assert session.ended_at is None

    def test_fin_anticipee_deux_fois_refusee(self):
        superuser = SuperuserFactory()
        session = SupportSessionFactory(superuser=superuser)
        end_support_session(session=session, superuser=superuser)

        with pytest.raises(SupportSessionError):
            end_support_session(session=session, superuser=superuser)


@pytest.mark.django_db
class TestIsSupportSessionValid:
    def test_valide_pendant_la_fenetre(self):
        now = timezone.now()
        session = SupportSessionFactory(started_at=now)
        assert is_support_session_valid(session, now=now + datetime.timedelta(minutes=30)) is True

    def test_invalide_apres_expiration(self):
        now = timezone.now()
        session = SupportSessionFactory(started_at=now)
        assert is_support_session_valid(session, now=now + datetime.timedelta(minutes=61)) is False

    def test_invalide_apres_fin_anticipee(self):
        now = timezone.now()
        session = SupportSessionFactory(started_at=now)
        session.ended_at = now + datetime.timedelta(minutes=10)
        session.save()

        assert is_support_session_valid(session, now=now + datetime.timedelta(minutes=20)) is False
        # Encore dans la fenetre de 60 minutes, mais deja terminee par
        # anticipation : `ended_at` prime toujours.
        assert is_support_session_valid(session, now=now + datetime.timedelta(minutes=5)) is True


@pytest.mark.django_db
class TestEnterGhostModeContextManager:
    """Mecanisme central de la tache 1.8 : contextvars, jamais de fuite,
    restriction stricte au SEUL club de la session."""

    def test_arme_le_club_actif_et_le_contexte_ghost_pendant_le_bloc(self):
        superuser = SuperuserFactory()
        club = ClubFactory()
        session = SupportSessionFactory(superuser=superuser, club=club)

        assert get_active_club() is None
        assert get_ghost_context() is None

        with enter_ghost_mode(session=session, superuser=superuser):
            assert get_active_club() == club
            ghost = get_ghost_context()
            assert ghost is not None
            assert ghost.support_session_id == str(session.pk)

        assert get_active_club() is None
        assert get_ghost_context() is None

    def test_remet_a_zero_meme_en_cas_d_exception(self):
        superuser = SuperuserFactory()
        session = SupportSessionFactory(superuser=superuser)

        with pytest.raises(RuntimeError):
            with enter_ghost_mode(session=session, superuser=superuser):
                assert get_active_club() == session.club
                raise RuntimeError("erreur simulee")

        assert get_active_club() is None
        assert get_ghost_context() is None

    def test_refuse_une_session_qui_n_appartient_pas_au_superuser(self):
        superuser = SuperuserFactory()
        autre_superuser = SuperuserFactory()
        session = SupportSessionFactory(superuser=superuser)

        with pytest.raises(SupportSessionPermissionError):
            with enter_ghost_mode(session=session, superuser=autre_superuser):
                pass  # pragma: no cover - ne doit jamais s'executer

        assert get_active_club() is None

    def test_refuse_une_session_expiree(self):
        superuser = SuperuserFactory()
        now = timezone.now()
        session = SupportSessionFactory(superuser=superuser, started_at=now - datetime.timedelta(minutes=90))

        with pytest.raises(SupportSessionError):
            with enter_ghost_mode(session=session, superuser=superuser):
                pass  # pragma: no cover

        assert get_active_club() is None

    def test_log_action_marque_automatiquement_ghost_pendant_la_session(self):
        """Point le plus sensible (CDC 5.4) : chaque `AuditLog` cree
        pendant une session valide porte automatiquement
        `acted_as_ghost=True`/`support_session_id`, sans que l'appelant
        n'ait a le preciser."""

        superuser = SuperuserFactory()
        club = ClubFactory()
        session = SupportSessionFactory(superuser=superuser, club=club)

        with enter_ghost_mode(session=session, superuser=superuser):
            entry = log_action(
                actor=superuser,
                action_type="treasury.payment.corrected",
                obj=session,
            )

        assert entry.acted_as_ghost is True
        assert entry.support_session_id == str(session.pk)
        assert entry.club_id == club.id

    def test_appel_explicite_prevaut_toujours_sur_le_contexte_ghost(self):
        """Meme regle que pour le club actif/l'IP/le user-agent : un appelant
        qui precise explicitement `acted_as_ghost=False` n'est jamais
        ecrase par le contexte Ghost Mode courant."""

        superuser = SuperuserFactory()
        session = SupportSessionFactory(superuser=superuser)

        with enter_ghost_mode(session=session, superuser=superuser):
            entry = log_action(
                actor=superuser,
                action_type="licence.support_session.started",
                obj=session,
                acted_as_ghost=False,
                support_session_id="",
            )

        assert entry.acted_as_ghost is False
        assert entry.support_session_id == ""

    def test_hors_ghost_mode_aucun_marquage_automatique(self):
        membership = MembershipFactory(status="active")

        entry = log_action(
            actor=membership.user,
            club=membership.club,
            action_type="role.appointed",
            obj=membership,
        )

        assert entry.acted_as_ghost is False
        assert entry.support_session_id == ""


@pytest.mark.django_db
class TestGhostModeEtancheiteEntreClubs:
    """CLAUDE.md/critere de recette : un Superuser en Ghost Mode sur le
    club A ne doit JAMAIS toucher au club B."""

    def test_impossible_de_lire_les_donnees_du_club_b_pendant_une_session_sur_le_club_a(self):
        superuser = SuperuserFactory()
        club_a = ClubFactory()
        club_b = ClubFactory()
        membership_a = MembershipFactory(club=club_a, status="active")
        MembershipFactory(club=club_b, status="active")

        session = SupportSessionFactory(superuser=superuser, club=club_a)

        with enter_ghost_mode(session=session, superuser=superuser):
            visibles = list(Membership.objects.all())
            assert all(m.club_id == club_a.id for m in visibles)
            assert membership_a in visibles

    def test_une_session_sur_le_club_a_n_arme_jamais_le_club_b(self):
        superuser = SuperuserFactory()
        club_a = ClubFactory()
        club_b = ClubFactory()
        session_a = SupportSessionFactory(superuser=superuser, club=club_a)

        with enter_ghost_mode(session=session_a, superuser=superuser):
            assert get_active_club() == club_a
            assert get_active_club() != club_b
