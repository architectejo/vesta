"""Tests unitaires des permissions DRF communes (tache 1.3).

Sources : CDC 4.1 (critere d'acceptation « aucune donnee accessible tant
que le mot de passe initial n'est pas change ») ; CDC 7.5, 10.2 n27.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import SuperuserFactory, TermsVersionFactory, UserFactory
from apps.clubs.models import Club
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.core.permissions import HasAcceptedLatestTerms, HasCompletedPasswordSetup, HasUsableLicence, IsSuperuser
from apps.core.tenant import active_club
from apps.licences.models import Licence
from apps.licences.tests.factories import LicenceFactory


class _FakeRequest:
    def __init__(self, user):
        self.user = user


class _FakeAnonymousUser:
    is_authenticated = False
    is_superuser = False


@pytest.mark.django_db
class TestHasCompletedPasswordSetup:
    permission = HasCompletedPasswordSetup()

    def test_refuse_un_utilisateur_non_authentifie(self):
        assert self.permission.has_permission(_FakeRequest(_FakeAnonymousUser()), None) is False

    def test_refuse_tant_que_must_change_password_est_vrai(self):
        user = UserFactory(must_change_password=True)
        assert self.permission.has_permission(_FakeRequest(user), None) is False

    def test_autorise_une_fois_le_mot_de_passe_change(self):
        user = UserFactory(must_change_password=False)
        assert self.permission.has_permission(_FakeRequest(user), None) is True


@pytest.mark.django_db
class TestHasAcceptedLatestTerms:
    permission = HasAcceptedLatestTerms()

    def test_refuse_un_utilisateur_non_authentifie(self):
        assert self.permission.has_permission(_FakeRequest(_FakeAnonymousUser()), None) is False

    def test_refuse_tant_qu_une_version_n_est_pas_acceptee(self):
        membership = MembershipFactory(status="active")
        TermsVersionFactory()

        assert self.permission.has_permission(_FakeRequest(membership.user), None) is False

    def test_autorise_sans_aucune_version_publiee(self):
        membership = MembershipFactory(status="active")

        assert self.permission.has_permission(_FakeRequest(membership.user), None) is True

    def test_autorise_toujours_un_superuser(self):
        """Documente un choix APPLIQUE A TITRE PROVISOIRE par backend-dev
        (voir `apps.core.permissions.HasAcceptedLatestTerms`), sans decision
        actee au 10.2 : le CDC 7.5 ne parle explicitement que de « chaque
        joueur » pour l'acceptation des CGU, pas des Superusers. Ce test ne
        tranche pas la question -- il verifie seulement que le comportement
        actuel du code est bien celui-la, pour qu'un changement de
        comportement soit visible ici. A remonter au client (CLAUDE.md §1) :
        un Superuser doit-il, lui aussi, accepter une nouvelle version des
        CGU avant de continuer a utiliser l'espace Superuser ?
        """
        superuser = SuperuserFactory()
        TermsVersionFactory()

        assert self.permission.has_permission(_FakeRequest(superuser), None) is True


@pytest.mark.django_db
class TestIsSuperuser:
    permission = IsSuperuser()

    def test_refuse_un_joueur(self):
        membership = MembershipFactory(status="active")
        assert self.permission.has_permission(_FakeRequest(membership.user), None) is False

    def test_autorise_un_superuser(self):
        superuser = SuperuserFactory()
        assert self.permission.has_permission(_FakeRequest(superuser), None) is True


class _FakeRequestWithMethod(_FakeRequest):
    def __init__(self, user, method="GET"):
        super().__init__(user)
        self.method = method


@pytest.mark.django_db
class TestHasUsableLicence:
    """CDC 1.4 ; 10.2 n19 ; tache 1.8 : deux regimes distincts, jamais melanges."""

    permission = HasUsableLicence()

    def test_refuse_un_utilisateur_non_authentifie(self):
        assert self.permission.has_permission(_FakeRequestWithMethod(_FakeAnonymousUser()), None) is False

    def test_autorise_toujours_un_superuser(self):
        superuser = SuperuserFactory()
        assert self.permission.has_permission(_FakeRequestWithMethod(superuser, "POST"), None) is True

    def test_autorise_sans_club_actif(self):
        """Hors du perimetre de ce garde-fou : une autre couche (regle n8)
        refuse deja l'acces aux donnees privees sans club actif."""

        user = UserFactory()
        assert self.permission.has_permission(_FakeRequestWithMethod(user, "GET"), None) is True

    def test_autorise_sans_licence_pour_le_club_actif(self):
        membership = MembershipFactory(status="active")
        with active_club(membership.club):
            assert self.permission.has_permission(_FakeRequestWithMethod(membership.user, "POST"), None) is True

    def test_autorise_avec_une_licence_active(self):
        membership = MembershipFactory(status="active")
        LicenceFactory(club=membership.club, status=Licence.Status.ACTIVE)
        with active_club(membership.club):
            assert self.permission.has_permission(_FakeRequestWithMethod(membership.user, "POST"), None) is True

    def test_licence_suspendue_bloque_meme_la_lecture(self):
        """10.2 n19 : « elle bloque l'acces du club », PAS une lecture seule."""

        membership = MembershipFactory(status="active")
        LicenceFactory(club=membership.club, status=Licence.Status.SUSPENDED)
        with active_club(membership.club):
            assert self.permission.has_permission(_FakeRequestWithMethod(membership.user, "GET"), None) is False
            assert self.permission.has_permission(_FakeRequestWithMethod(membership.user, "POST"), None) is False

    def test_licence_resiliee_bloque_aussi_tout_acces(self):
        """Decision par defaut appliquee (non explicitement tranchee par
        10.2 n19, qui ne detaille QUE `suspended`) : `terminated` traite
        aussi restrictivement que `suspended`."""

        membership = MembershipFactory(status="active")
        LicenceFactory(club=membership.club, status=Licence.Status.TERMINATED)
        with active_club(membership.club):
            assert self.permission.has_permission(_FakeRequestWithMethod(membership.user, "GET"), None) is False

    def test_club_en_lecture_seule_autorise_la_lecture(self):
        membership = MembershipFactory(status="active")
        membership.club.status = Club.Status.READ_ONLY
        membership.club.save(update_fields=["status"])
        LicenceFactory(club=membership.club, status=Licence.Status.EXPIRED)

        with active_club(membership.club):
            assert self.permission.has_permission(_FakeRequestWithMethod(membership.user, "GET"), None) is True
            assert self.permission.has_permission(_FakeRequestWithMethod(membership.user, "HEAD"), None) is True
            assert self.permission.has_permission(_FakeRequestWithMethod(membership.user, "OPTIONS"), None) is True

    def test_club_en_lecture_seule_refuse_toute_mutation(self):
        membership = MembershipFactory(status="active")
        membership.club.status = Club.Status.READ_ONLY
        membership.club.save(update_fields=["status"])
        LicenceFactory(club=membership.club, status=Licence.Status.EXPIRED)

        with active_club(membership.club):
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                assert self.permission.has_permission(_FakeRequestWithMethod(membership.user, method), None) is False
