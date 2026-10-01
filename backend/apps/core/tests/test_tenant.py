"""Tests du contexte de club actif et du service d'audit `log_action` (taches 1.2, 1.6).

Sources : CLAUDE.md regles n6, n8, n9 ; CDC 6.3, 5 ; docs/lot0/schema-donnees.md §1.2, §1.3, §12.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.core.services import log_action, resolve_active_membership
from apps.core.tenant import NoActiveClubError, active_club, get_active_club, reset_active_club, set_active_club


def test_aucun_club_actif_par_defaut():
    """Hors de tout contexte, aucun club n'est actif."""

    assert get_active_club() is None


def test_set_get_reset_active_club():
    club = object()  # un simple marqueur suffit : ce test ne touche pas la base.
    token = set_active_club(club)
    try:
        assert get_active_club() is club
    finally:
        reset_active_club(token)
    assert get_active_club() is None


def test_active_club_context_manager_restaure_meme_en_cas_erreur():
    club = object()
    assert get_active_club() is None
    with pytest.raises(RuntimeError):
        with active_club(club):
            assert get_active_club() is club
            raise RuntimeError("erreur simulee")
    assert get_active_club() is None


@pytest.mark.django_db
class TestResolveActiveMembership:
    def test_leve_si_utilisateur_non_authentifie(self):
        class FauxAnonyme:
            is_authenticated = False
            is_superuser = False

        with pytest.raises(NoActiveClubError):
            resolve_active_membership(FauxAnonyme())

    def test_leve_pour_un_superuser(self):
        superuser = SuperuserFactory()
        with pytest.raises(NoActiveClubError):
            resolve_active_membership(superuser)

    def test_leve_sans_adhesion_active(self):
        user = UserFactory()
        with pytest.raises(NoActiveClubError):
            resolve_active_membership(user)

    def test_renvoie_l_adhesion_active_unique(self):
        membership = MembershipFactory(status="active")
        resolved = resolve_active_membership(membership.user)
        assert resolved.pk == membership.pk
        assert resolved.club_id == membership.club_id

    def test_leve_si_plusieurs_adhesions_actives_simultanees(self):
        """Cas rare mais non exclu par le modele (schema-donnees.md, note Q4)."""

        user = UserFactory()
        MembershipFactory(user=user, status="active")
        MembershipFactory(user=user, status="active")
        with pytest.raises(NoActiveClubError):
            resolve_active_membership(user)

    def test_club_explicite_verifie_contre_l_adhesion_reelle(self):
        membership = MembershipFactory(status="active")
        autre_club = ClubFactory()

        resolved = resolve_active_membership(membership.user, club=membership.club)
        assert resolved.pk == membership.pk

        with pytest.raises(NoActiveClubError):
            resolve_active_membership(membership.user, club=autre_club)


@pytest.mark.django_db
class TestLogAction:
    """Tache 1.6 : `log_action` ecrit reellement une entree `AuditLog`."""

    def test_ecrit_une_entree_reelle(self):
        from apps.audit.models import AuditLog

        membership = MembershipFactory(status="active")
        entry = log_action(
            actor=membership.user,
            club=membership.club,
            action_type="test.action",
            obj=membership,
            after={"statut": "actif"},
        )

        assert AuditLog.objects.filter(pk=entry.pk).exists()
        assert entry.object_type == "Membership"
        assert entry.object_id == str(membership.pk)

    def test_club_omis_est_deduit_du_contexte_actif(self):
        membership = MembershipFactory(status="active")

        with active_club(membership.club):
            entry = log_action(
                actor=membership.user,
                action_type="test.action",
                obj=membership,
            )

        assert entry.club_id == membership.club_id

    def test_club_explicitement_none_reste_une_action_de_plateforme(self):
        """Passer `club=None` explicitement ne doit jamais deduire un club actif."""

        membership = MembershipFactory(status="active")

        with active_club(membership.club):
            entry = log_action(
                actor=membership.user,
                club=None,
                action_type="test.action.plateforme",
                obj=membership,
            )

        assert entry.club_id is None

    def test_objet_concerne_obligatoire(self):
        with pytest.raises(ValueError):
            log_action(actor=None, club=None, action_type="test.stub", obj=None)

    def test_club_explicite_prevaut_toujours_sur_le_club_actif_du_contexte(self):
        """Un `club` explicite (meme different du club actif) n'est jamais ecrase.

        Complete `test_club_explicitement_none_reste_une_action_de_plateforme` :
        ce n'est pas seulement `club=None` qui doit rester intact face a un
        club actif pose par ailleurs -- un club explicite *different* du
        club actif ne doit pas non plus etre remplace par le club actif du
        contexte courant (risque de fuite d'un club dans le journal d'une
        action qui visait explicitement un autre club, CLAUDE.md regle n9).
        """

        membership_club_actif = MembershipFactory(status="active")
        autre_membership = MembershipFactory(status="active")

        with active_club(membership_club_actif.club):
            entry = log_action(
                actor=autre_membership.user,
                club=autre_membership.club,
                action_type="test.action.club_explicite",
                obj=autre_membership,
            )

        assert entry.club_id == autre_membership.club_id
        assert entry.club_id != membership_club_actif.club_id
