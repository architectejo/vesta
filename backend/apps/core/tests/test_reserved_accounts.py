"""Compte « Système » réservé (audit sécurité MA1 / m-B)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.accounts import services as accounts_services
from apps.accounts.models import User
from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs import services as clubs_services
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.core.reserved_accounts import SYSTEM_ACTOR_EMAIL, is_reserved_email
from apps.treasury import services as treasury_services


def test_detection_des_adresses_reservees():
    assert is_reserved_email(SYSTEM_ACTOR_EMAIL)
    assert is_reserved_email("  SYSTEME@Vesta.INVALID ")
    assert is_reserved_email("x@sub.domaine.invalid")
    assert not is_reserved_email("joueur@example.com")
    assert not is_reserved_email("invalid@example.com")


@pytest.mark.django_db
class TestRefusAdresseReservee:
    def test_ajout_de_joueur_refuse(self):
        club = ClubFactory()
        president = MembershipFactory(club=club)
        for email in (SYSTEM_ACTOR_EMAIL, "quelquun@autre.invalid"):
            with pytest.raises(ValidationError) as exc:
                clubs_services.create_or_update_player(
                    club=club, email=email, first_name="A", last_name="B", added_by=president.user
                )
            assert "réservée" in exc.value.messages[0]
        assert not User.objects.filter(email=SYSTEM_ACTOR_EMAIL).exists()

    def test_ajout_ne_prend_pas_le_controle_du_compte_systeme_existant(self):
        system = treasury_services.get_system_actor()
        club = ClubFactory()
        president = MembershipFactory(club=club)
        with pytest.raises(ValidationError):
            clubs_services.create_or_update_player(
                club=club, email=SYSTEM_ACTOR_EMAIL, first_name="A", last_name="B", added_by=president.user
            )
        system.refresh_from_db()
        assert not system.has_usable_password() and not system.is_active
        assert not system.memberships.exists()

    def test_import_csv_refuse_la_ligne_avec_message_francais(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        club = ClubFactory()
        importer = MembershipFactory(club=club)
        content = f"email,prenom,nom\n{SYSTEM_ACTOR_EMAIL},A,B\n"
        summary = clubs_services.import_players_from_csv(
            club=club,
            imported_by=importer.user,
            csv_file=SimpleUploadedFile("i.csv", content.encode(), content_type="text/csv"),
        )
        assert summary.rows[0].outcome == "failed"
        assert "réservée" in summary.rows[0].message
        assert not User.objects.filter(email=SYSTEM_ACTOR_EMAIL).exists()

    def test_changement_d_email_refuse(self):
        user = UserFactory()
        before = user.email
        with pytest.raises(ValidationError):
            accounts_services.update_credentials(
                user=user, current_password="MotDePasse123", new_email=SYSTEM_ACTOR_EMAIL
            )
        user.refresh_from_db()
        assert user.email == before


@pytest.mark.django_db
class TestCompteSystemeMasque:
    def test_absent_de_la_recherche_superuser(self):
        treasury_services.get_system_actor()
        UserFactory(email="visible@example.com")
        emails = [row["email"] for row in accounts_services.search_accounts(query="")]
        assert SYSTEM_ACTOR_EMAIL not in emails
        assert "visible@example.com" in emails
        assert accounts_services.search_accounts(query="systeme") == []

    def test_reinitialisation_refusee(self):
        system = treasury_services.get_system_actor()
        superuser = SuperuserFactory()
        with pytest.raises(User.DoesNotExist):
            accounts_services.reset_password_by_superuser(superuser=superuser, target_email=SYSTEM_ACTOR_EMAIL)
        system.refresh_from_db()
        assert not system.has_usable_password()

    def test_demande_mot_de_passe_oublie_sans_effet(self):
        from apps.accounts.models import PasswordResetRequest

        treasury_services.get_system_actor()
        accounts_services.request_password_reset(email=SYSTEM_ACTOR_EMAIL)
        assert not PasswordResetRequest.objects.exists()
