"""Tests du modele `User` et des CGU versionnees (tache 1.2).

Sources : CDC 4.1, 7.1, 7.5 ; 10.2 n27 ; docs/lot0/schema-donnees.md §3.1, §3.6.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import TermsAcceptance, TermsVersion, User
from apps.accounts.tests.factories import SuperuserFactory, TermsVersionFactory, UserFactory


@pytest.mark.django_db
class TestUser:
    def test_email_est_normalise_en_minuscules(self):
        user = User.objects.create_user(email="Joueur@EXAMPLE.com", password="motdepasse1")
        assert user.email == "joueur@example.com"

    def test_mot_de_passe_initial_exige_un_changement(self):
        """CDC 4.1 : mot de passe = email, changement obligatoire a la premiere connexion."""

        user = User.objects.create_user(email="nouveau@example.com", password="nouveau@example.com")
        assert user.must_change_password is True

    def test_email_unique_sur_toute_la_plateforme(self):
        User.objects.create_user(email="doublon@example.com", password="x1234567")
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create_user(email="doublon@example.com", password="x1234567")

    def test_superuser_na_pas_de_membership_par_defaut(self):
        """CLAUDE.md regle n1 : un Superuser n'a jamais de fiche joueur.

        `superuser.memberships` (relation inverse standard de Django) est
        elle-meme tenant-aware (regle n8 : meme un acces "par la bande"
        via une relation inverse reste filtre) ; verifier "aucun club" ne
        peut donc se faire qu'avec l'echappement documente `all_objects`,
        volontairement distinct de `objects` (voir apps.core.models).
        """

        from apps.clubs.models import Membership

        superuser = SuperuserFactory()
        assert superuser.is_superuser is True
        assert Membership.all_objects.filter(user=superuser).count() == 0


@pytest.mark.django_db
class TestTermsVersioning:
    def test_version_number_generee_automatiquement(self):
        version = TermsVersionFactory(published_at=timezone.now().replace(year=2026))
        assert version.version_number == "2026-1"

        deuxieme = TermsVersionFactory(
            published_at=timezone.now().replace(year=2026), created_by=version.created_by
        )
        assert deuxieme.version_number == "2026-2"

    def test_acceptation_unique_par_utilisateur_et_version(self):
        user = UserFactory()
        version = TermsVersionFactory()
        TermsAcceptance.objects.create(user=user, terms_version=version, accepted_at=timezone.now())

        with pytest.raises(IntegrityError), transaction.atomic():
            TermsAcceptance.objects.create(user=user, terms_version=version, accepted_at=timezone.now())
