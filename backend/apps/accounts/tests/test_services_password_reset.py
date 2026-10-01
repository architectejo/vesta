"""Tests de `apps.accounts.services` : mot de passe oublie / reinitialisation.

Sources : CDC 4.1 ; 10.2 n21 ; docs/lot0/schema-donnees.md §13.2 ;
docs/ecrans/comptes-connexion.md §4.1.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services
from apps.accounts.models import PasswordResetRequest
from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.models import AuditLog


@pytest.mark.django_db
class TestRequestPasswordReset:
    def test_cree_une_demande_pour_un_compte_existant(self):
        user = UserFactory()

        services.request_password_reset(email=user.email)

        request = PasswordResetRequest.objects.get(user=user)
        assert request.status == PasswordResetRequest.Status.PENDING
        assert AuditLog.objects.filter(
            actor=user, action_type="accounts.password_reset.requested"
        ).exists()

    def test_email_inconnu_ne_cree_rien_et_ne_leve_rien(self):
        services.request_password_reset(email="inconnu@example.com")

        assert PasswordResetRequest.objects.count() == 0


@pytest.mark.django_db
class TestResetPasswordBySuperuser:
    def test_genere_un_mot_de_passe_temporaire_de_8_caracteres(self):
        superuser = SuperuserFactory()
        user = UserFactory()

        temp_password = services.reset_password_by_superuser(superuser=superuser, target_email=user.email)

        assert len(temp_password) == services.TEMP_PASSWORD_LENGTH

    def test_le_mot_de_passe_est_hache_avant_stockage(self):
        superuser = SuperuserFactory()
        user = UserFactory()

        temp_password = services.reset_password_by_superuser(superuser=superuser, target_email=user.email)

        user.refresh_from_db()
        assert user.password != temp_password
        assert user.check_password(temp_password)

    def test_force_le_changement_et_pose_l_echeance_48h(self):
        superuser = SuperuserFactory()
        user = UserFactory(must_change_password=False)

        before = timezone.now()
        services.reset_password_by_superuser(superuser=superuser, target_email=user.email)
        after = timezone.now()

        user.refresh_from_db()
        assert user.must_change_password is True
        assert before + timedelta(hours=48) <= user.temp_password_expires_at <= after + timedelta(hours=48)

    def test_le_mot_de_passe_temporaire_n_est_jamais_journalise(self):
        superuser = SuperuserFactory()
        user = UserFactory()

        temp_password = services.reset_password_by_superuser(superuser=superuser, target_email=user.email)

        entry = AuditLog.objects.get(actor=superuser, action_type="accounts.password_reset.completed")
        serialized = f"{entry.before}{entry.after}"
        assert temp_password not in serialized

    def test_marque_la_demande_en_attente_comme_traitee(self):
        superuser = SuperuserFactory()
        user = UserFactory()
        reset_request = PasswordResetRequest.objects.create(user=user, requested_at=timezone.now())

        services.reset_password_by_superuser(superuser=superuser, target_email=user.email)

        reset_request.refresh_from_db()
        assert reset_request.status == PasswordResetRequest.Status.DONE
        assert reset_request.handled_by_id == superuser.id
        assert reset_request.handled_at is not None
        assert AuditLog.objects.filter(
            object_type="PasswordResetRequest",
            object_id=str(reset_request.pk),
            action_type="accounts.password_reset.handled",
        ).exists()

    def test_refuse_un_acteur_non_superuser(self):
        acteur = UserFactory()
        cible = UserFactory()

        with pytest.raises(PermissionError):
            services.reset_password_by_superuser(superuser=acteur, target_email=cible.email)

    def test_refuse_un_email_inconnu(self):
        superuser = SuperuserFactory()

        from apps.accounts.models import User

        with pytest.raises(User.DoesNotExist):
            services.reset_password_by_superuser(superuser=superuser, target_email="inconnu@example.com")

    def test_reinitialise_le_blocage_de_connexion(self):
        superuser = SuperuserFactory()
        user = UserFactory()
        user.failed_login_attempts = 4
        user.login_locked_until = timezone.now() + timedelta(minutes=10)
        user.save(update_fields=["failed_login_attempts", "login_locked_until"])

        services.reset_password_by_superuser(superuser=superuser, target_email=user.email)

        user.refresh_from_db()
        assert user.failed_login_attempts == 0
        assert user.login_locked_until is None

    def test_revoque_tous_les_jetons_existants_de_la_cible(self):
        """Preuve de fermeture de l'ecart bloquant B3 (audit de securite du
        Lot 1) : une reinitialisation forcee par le Superuser doit expulser
        un attaquant deja connecte avec un jeton vole de la cible, pas
        seulement changer le mot de passe."""

        superuser = SuperuserFactory()
        user = UserFactory()
        ancien_refresh = RefreshToken.for_user(user)
        assert OutstandingToken.objects.filter(user=user).exists()

        services.reset_password_by_superuser(superuser=superuser, target_email=user.email)

        assert BlacklistedToken.objects.filter(token__jti=ancien_refresh["jti"]).exists()
        entry = AuditLog.objects.get(actor=superuser, action_type="accounts.password_reset.completed")
        assert entry.after["tokens_revoked"] == 1

    def test_compte_correctement_plusieurs_jetons_actifs_de_la_cible(self):
        """Meme constat que `apps.accounts.tests.test_services_password` :
        `tokens_revoked` doit refleter le nombre reel de jetons actifs, pas
        seulement 0 ou 1."""

        superuser = SuperuserFactory()
        user = UserFactory()
        RefreshToken.for_user(user)
        RefreshToken.for_user(user)

        services.reset_password_by_superuser(superuser=superuser, target_email=user.email)

        entry = AuditLog.objects.get(actor=superuser, action_type="accounts.password_reset.completed")
        assert entry.after["tokens_revoked"] == 2

    def test_ne_double_compte_pas_un_jeton_deja_en_liste_noire_de_la_cible(self):
        superuser = SuperuserFactory()
        user = UserFactory()
        refresh_deja_revoque = RefreshToken.for_user(user)
        refresh_deja_revoque.blacklist()
        RefreshToken.for_user(user)

        services.reset_password_by_superuser(superuser=superuser, target_email=user.email)

        entry = AuditLog.objects.get(actor=superuser, action_type="accounts.password_reset.completed")
        assert entry.after["tokens_revoked"] == 1

    def test_le_mot_de_passe_temporaire_expire_est_refuse_a_la_connexion(self):
        """Verification de bout en bout du cycle temporaire -> expiration -> refus."""

        superuser = SuperuserFactory()
        user = UserFactory()

        now = timezone.now()
        from unittest.mock import patch

        with patch("django.utils.timezone.now", return_value=now):
            temp_password = services.reset_password_by_superuser(superuser=superuser, target_email=user.email)

        after_expiry = now + timedelta(hours=48, seconds=1)
        with patch("django.utils.timezone.now", return_value=after_expiry):
            with pytest.raises(services.TemporaryPasswordExpiredError):
                services.authenticate_login(email=user.email, password=temp_password)
