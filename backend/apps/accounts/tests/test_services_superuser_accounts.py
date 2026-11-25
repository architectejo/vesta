"""Tests des fonctions « Comptes » de l'espace Superuser (CDC 2.5, 4.18 ; tache 1.8).

Sources : docs/cahier-des-charges.md 2.5, 4.18 ;
docs/lot0/schema-donnees.md §13.3.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services
from apps.accounts.models import PasswordResetRequest
from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import ClubFactory, MembershipFactory, MembershipRoleFactory


@pytest.mark.django_db
class TestSearchAccounts:
    def test_recherche_par_email(self):
        user = UserFactory(email="joueur-cherche@example.com")
        UserFactory(email="autre@example.com")

        results = services.search_accounts(query="joueur-cherche")

        assert [r["id"] for r in results] == [user.id]

    def test_recherche_par_prenom_ou_nom(self):
        user = UserFactory(first_name="Aristide", last_name="Kalonji")
        UserFactory(first_name="Autre", last_name="Personne")

        results = services.search_accounts(query="kalonji")

        assert [r["id"] for r in results] == [user.id]

    def test_sans_filtre_renvoie_tous_les_comptes(self):
        UserFactory()
        UserFactory()

        results = services.search_accounts()

        assert len(results) == 2

    def test_filtre_par_club(self):
        membership_a = MembershipFactory(status="active")
        membership_b = MembershipFactory(status="active")

        results = services.search_accounts(club_id=membership_a.club_id)

        ids = {r["id"] for r in results}
        assert membership_a.user_id in ids
        assert membership_b.user_id not in ids

    def test_filtre_par_role(self):
        president = MembershipFactory(status="active")
        MembershipRoleFactory(membership=president, club=president.club, role=MembershipRole.Role.PRESIDENT)
        simple_joueur = MembershipFactory(status="active")

        results = services.search_accounts(role=MembershipRole.Role.PRESIDENT)

        ids = {r["id"] for r in results}
        assert president.user_id in ids
        assert simple_joueur.user_id not in ids

    def test_expose_les_clubs_et_roles_actifs(self):
        membership = MembershipFactory(status="active")
        MembershipRoleFactory(membership=membership, club=membership.club, role=MembershipRole.Role.COACH)

        results = services.search_accounts(query=membership.user.email)

        assert len(results) == 1
        payload = results[0]
        assert payload["clubs"][0]["club_id"] == membership.club_id
        assert payload["clubs"][0]["club_name"] == membership.club.name
        assert MembershipRole.Role.COACH in payload["clubs"][0]["roles"]

    def test_role_revoque_n_apparait_plus(self):
        membership = MembershipFactory(status="active")
        role = MembershipRoleFactory(membership=membership, club=membership.club, role=MembershipRole.Role.COACH)
        role.revoked_at = timezone.now()
        role.revoked_by = SuperuserFactory()
        role.save()

        results = services.search_accounts(query=membership.user.email)

        assert results[0]["clubs"][0]["roles"] == []


@pytest.mark.django_db
class TestDeactivateAccount:
    def test_refuse_de_se_desactiver_soi_meme(self):
        superuser = SuperuserFactory()
        with pytest.raises(services.AccountDeactivationRefusedError, match="propre compte"):
            services.deactivate_account(superuser=superuser, target_user=superuser)
        superuser.refresh_from_db()
        assert superuser.is_active is True

    def test_refuse_de_desactiver_le_dernier_superuser_actif(self):
        actor = SuperuserFactory()
        actor_two = SuperuserFactory(is_active=False)
        with pytest.raises(services.AccountDeactivationRefusedError, match="dernier Superuser"):
            services.deactivate_account(superuser=actor_two, target_user=actor)

    def test_un_autre_superuser_reste_desactivable(self):
        first, second = SuperuserFactory(), SuperuserFactory()
        services.deactivate_account(superuser=first, target_user=second, reason="Test")
        second.refresh_from_db()
        assert second.is_active is False

    def test_desactive_le_compte(self):
        superuser = SuperuserFactory()
        target = UserFactory(is_active=True)

        services.deactivate_account(superuser=superuser, target_user=target, reason="Depart du club.")

        target.refresh_from_db()
        assert target.is_active is False

    def test_journalise_la_desactivation(self):
        superuser = SuperuserFactory()
        target = UserFactory(is_active=True)

        services.deactivate_account(superuser=superuser, target_user=target, reason="Depart du club.")

        entry = AuditLog.objects.get(action_type="accounts.account.deactivated", object_id=str(target.pk))
        assert entry.actor_id == superuser.id
        assert entry.after["reason"] == "Depart du club."

    def test_revoque_les_jetons_existants(self):
        superuser = SuperuserFactory()
        target = UserFactory(is_active=True)
        ancien_refresh = RefreshToken.for_user(target)
        assert OutstandingToken.objects.filter(user=target).exists()

        services.deactivate_account(superuser=superuser, target_user=target)

        assert BlacklistedToken.objects.filter(token__jti=ancien_refresh["jti"]).exists()

    def test_idempotent_sans_doublon_de_journal(self):
        superuser = SuperuserFactory()
        target = UserFactory(is_active=False)

        services.deactivate_account(superuser=superuser, target_user=target)

        assert not AuditLog.objects.filter(action_type="accounts.account.deactivated").exists()

    def test_refuse_un_non_superuser(self):
        acteur = UserFactory()
        target = UserFactory()

        with pytest.raises(PermissionError):
            services.deactivate_account(superuser=acteur, target_user=target)


@pytest.mark.django_db
class TestListPendingPasswordResetRequests:
    def test_renvoie_uniquement_les_demandes_en_attente(self):
        user = UserFactory()
        pending = PasswordResetRequest.objects.create(user=user, requested_at=timezone.now())
        done = PasswordResetRequest.objects.create(
            user=user,
            requested_at=timezone.now(),
            status=PasswordResetRequest.Status.DONE,
            handled_by=SuperuserFactory(),
            handled_at=timezone.now(),
        )

        results = list(services.list_pending_password_reset_requests())

        assert pending in results
        assert done not in results
