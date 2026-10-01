"""Tests du mecanisme generique de roles (CDC 2.2 ; tache 1.5).

Sources : CDC 2.2 (cumul de roles, « ses droits sont alors l'union des
droits de ses roles ») ; CLAUDE.md regle n9 (club actif jamais fige).
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubFactory, MembershipFactory, MembershipRoleFactory
from apps.core.roles import get_active_roles, has_any_role
from apps.core.tenant import active_club


@pytest.mark.django_db
class TestGetActiveRoles:
    def test_ensemble_vide_sans_adhesion_active(self):
        user = UserFactory()
        club = ClubFactory()
        with active_club(club):
            assert get_active_roles(user, club=club) == frozenset()

    def test_ensemble_vide_pour_un_superuser(self):
        """CLAUDE.md regle n1 : un Superuser n'a jamais de fiche joueur."""

        superuser = SuperuserFactory()
        club = ClubFactory()
        with active_club(club):
            assert get_active_roles(superuser, club=club) == frozenset()

    def test_renvoie_uniquement_les_roles_actifs_non_revoques(self):
        membership = MembershipFactory()
        MembershipRoleFactory(membership=membership, role=MembershipRole.Role.COACH)
        MembershipRoleFactory(membership=membership, role=MembershipRole.Role.TREASURER)
        revoked = MembershipRoleFactory(membership=membership, role=MembershipRole.Role.CAPTAIN)
        revoked.revoked_by = membership.added_by
        revoked.revoked_at = timezone.now()
        revoked.save()

        with active_club(membership.club):
            roles = get_active_roles(membership.user, club=membership.club)

        assert roles == {MembershipRole.Role.COACH, MembershipRole.Role.TREASURER}

    def test_club_explicite_prevaut_sur_le_club_actif_du_contexte(self):
        membership = MembershipFactory()
        MembershipRoleFactory(membership=membership, role=MembershipRole.Role.COACH)
        autre_club = ClubFactory()

        with active_club(autre_club):
            # Le club actif du contexte est `autre_club`, mais le club
            # explicite est celui de l'adhesion : c'est lui qui doit
            # etre resolu, jamais le contexte courant.
            roles = get_active_roles(membership.user, club=membership.club)

        assert roles == {MembershipRole.Role.COACH}


@pytest.mark.django_db
class TestHasAnyRole:
    def test_vrai_si_l_un_des_roles_cumules_correspond(self):
        """CDC 2.2 : « Un joueur peut cumuler plusieurs roles [...] Ses
        droits sont alors l'union des droits de ses roles. »"""

        membership = MembershipFactory()
        MembershipRoleFactory(membership=membership, role=MembershipRole.Role.CAPTAIN)
        MembershipRoleFactory(membership=membership, role=MembershipRole.Role.ASSISTANT_TREASURER)

        with active_club(membership.club):
            assert has_any_role(
                membership.user,
                {MembershipRole.Role.CAPTAIN, MembershipRole.Role.PRESIDENT},
                club=membership.club,
            )
            assert not has_any_role(membership.user, {MembershipRole.Role.PRESIDENT}, club=membership.club)

    def test_faux_pour_un_joueur_sans_role(self):
        membership = MembershipFactory()
        with active_club(membership.club):
            assert not has_any_role(membership.user, {MembershipRole.Role.COACH}, club=membership.club)
