"""Tests de `apps.accounts.services` : code PIN (CDC 7.2).

Mecanisme generique de securite de compte, construit une seule fois pour
etre reutilise par toute app hors `accounts` (signature du parrain --
tache 1.4b --, validation d'un paiement/depense par `finance-engine`,
derogation, signature de PV, annulation, y compris l'annulation d'une
adhesion avec remboursement -- 10.2 n36). Cette tache ne construit QUE la
couche service (CLAUDE.md §5) ; aucun endpoint HTTP n'est teste ici.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import check_password
from django.utils import timezone

from apps.accounts import services
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog

RAW_PASSWORD = "MotDePasse123"
PIN = "1234"
OTHER_PIN = "5678"


@pytest.mark.django_db
class TestDefinePin:
    def test_definit_le_pin_si_aucun_pin_existant(self):
        user = UserFactory()

        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        user.refresh_from_db()
        assert user.pin_hash
        assert check_password(PIN, user.pin_hash)
        assert user.pin_failed_attempts == 0
        assert user.pin_locked_until is None
        assert AuditLog.objects.filter(actor=user, action_type="accounts.pin.defined").exists()

    def test_refuse_si_un_pin_est_deja_defini(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        with pytest.raises(services.PinAlreadySetError):
            services.define_pin(user=user, pin=OTHER_PIN, confirm_pin=OTHER_PIN)

    def test_refuse_si_les_deux_saisies_ne_correspondent_pas(self):
        user = UserFactory()

        with pytest.raises(services.PinMismatchError):
            services.define_pin(user=user, pin=PIN, confirm_pin=OTHER_PIN)

        user.refresh_from_db()
        assert user.pin_hash == ""

    @pytest.mark.parametrize("bad_pin", ["123", "1234567", "abcd", "12 34", ""])
    def test_refuse_un_format_invalide(self, bad_pin):
        user = UserFactory()

        with pytest.raises(services.InvalidPinFormatError):
            services.define_pin(user=user, pin=bad_pin, confirm_pin=bad_pin)

    def test_accepte_un_pin_a_6_chiffres(self):
        user = UserFactory()

        services.define_pin(user=user, pin="123456", confirm_pin="123456")

        user.refresh_from_db()
        assert check_password("123456", user.pin_hash)

    def test_ne_journalise_jamais_le_pin_en_clair(self):
        user = UserFactory()

        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        entry = AuditLog.objects.get(actor=user, action_type="accounts.pin.defined")
        assert PIN not in str(entry.before)
        assert PIN not in str(entry.after)


@pytest.mark.django_db
class TestRedefinePin:
    def test_redefinit_apres_le_bon_mot_de_passe(self):
        user = UserFactory()

        services.redefine_pin(
            user=user, password=RAW_PASSWORD, new_pin=PIN, confirm_new_pin=PIN
        )

        user.refresh_from_db()
        assert check_password(PIN, user.pin_hash)
        assert AuditLog.objects.filter(actor=user, action_type="accounts.pin.reset").exists()

    def test_refuse_un_mot_de_passe_incorrect(self):
        user = UserFactory()

        with pytest.raises(services.PinResetPasswordIncorrectError):
            services.redefine_pin(
                user=user, password="mauvais-mot-de-passe", new_pin=PIN, confirm_new_pin=PIN
            )

        user.refresh_from_db()
        assert user.pin_hash == ""

    def test_reinitialise_le_compteur_et_le_blocage_en_cours(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)
        user.pin_failed_attempts = services.MAX_PIN_ATTEMPTS
        user.pin_locked_until = timezone.now() + timedelta(minutes=20)
        user.save(update_fields=["pin_failed_attempts", "pin_locked_until"])

        services.redefine_pin(
            user=user, password=RAW_PASSWORD, new_pin=OTHER_PIN, confirm_new_pin=OTHER_PIN
        )

        user.refresh_from_db()
        assert user.pin_failed_attempts == 0
        assert user.pin_locked_until is None
        assert check_password(OTHER_PIN, user.pin_hash)

    def test_refuse_si_les_deux_saisies_ne_correspondent_pas(self):
        user = UserFactory()

        with pytest.raises(services.PinMismatchError):
            services.redefine_pin(
                user=user, password=RAW_PASSWORD, new_pin=PIN, confirm_new_pin=OTHER_PIN
            )

    def test_refuse_un_format_invalide(self):
        user = UserFactory()

        with pytest.raises(services.InvalidPinFormatError):
            services.redefine_pin(
                user=user, password=RAW_PASSWORD, new_pin="12", confirm_new_pin="12"
            )


@pytest.mark.django_db
class TestVerifyPin:
    def test_leve_pin_not_set_error_si_jamais_defini(self):
        user = UserFactory()

        with pytest.raises(services.PinNotSetError) as exc_info:
            services.verify_pin(user=user, pin=PIN)

        assert str(exc_info.value) == "Vous devez definir votre code PIN avant de continuer."

    def test_renvoie_true_pour_un_bon_pin_et_reinitialise_le_compteur(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)
        user.pin_failed_attempts = 2
        user.save(update_fields=["pin_failed_attempts"])

        assert services.verify_pin(user=user, pin=PIN) is True

        user.refresh_from_db()
        assert user.pin_failed_attempts == 0
        assert user.pin_locked_until is None

    def test_renvoie_false_et_incremente_le_compteur_pour_un_mauvais_pin(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        assert services.verify_pin(user=user, pin="0000") is False

        user.refresh_from_db()
        assert user.pin_failed_attempts == 1
        entry = AuditLog.objects.get(actor=user, action_type="accounts.pin.verification_failed")
        assert entry.after == {"pin_failed_attempts": 1}

    def test_3e_echec_bloque_30_minutes(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        for _ in range(services.MAX_PIN_ATTEMPTS - 1):
            assert services.verify_pin(user=user, pin="0000") is False

        with pytest.raises(services.PinLockedError) as exc_info:
            services.verify_pin(user=user, pin="0000")

        user.refresh_from_db()
        assert user.pin_failed_attempts == services.MAX_PIN_ATTEMPTS
        assert user.pin_locked_until == exc_info.value.locked_until
        assert AuditLog.objects.filter(actor=user, action_type="accounts.pin.locked").exists()

    def test_pin_bloque_refuse_meme_le_bon_pin(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)
        user.pin_locked_until = timezone.now() + timedelta(minutes=10)
        user.save(update_fields=["pin_locked_until"])

        with pytest.raises(services.PinLockedError):
            services.verify_pin(user=user, pin=PIN)

        user.refresh_from_db()
        assert user.pin_failed_attempts == 0

    def test_deblocage_automatique_apres_30_minutes(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        now = timezone.now()
        with patch("django.utils.timezone.now", return_value=now):
            for _ in range(services.MAX_PIN_ATTEMPTS):
                try:
                    services.verify_pin(user=user, pin="0000")
                except services.PinLockedError:
                    pass

        user.refresh_from_db()
        assert user.pin_locked_until == now + services.PIN_LOCKOUT_DURATION

        after_lockout = now + services.PIN_LOCKOUT_DURATION + timedelta(seconds=1)
        with patch("django.utils.timezone.now", return_value=after_lockout):
            assert services.verify_pin(user=user, pin=PIN) is True

    def test_ne_journalise_jamais_le_pin_en_clair(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        services.verify_pin(user=user, pin="0000")

        entry = AuditLog.objects.get(actor=user, action_type="accounts.pin.verification_failed")
        assert "0000" not in str(entry.after)
        assert PIN not in str(entry.after)


@pytest.mark.django_db
class TestRequireValidPin:
    def test_ne_leve_rien_si_le_pin_est_correct(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        services.require_valid_pin(user=user, pin=PIN)  # ne doit pas lever

    def test_leve_pin_not_set_error_si_jamais_defini(self):
        user = UserFactory()

        with pytest.raises(services.PinNotSetError):
            services.require_valid_pin(user=user, pin=PIN)

    def test_leve_invalid_pin_error_avec_les_tentatives_restantes(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        with pytest.raises(services.InvalidPinError) as exc_info:
            services.require_valid_pin(user=user, pin="0000")

        assert exc_info.value.attempts_remaining == services.MAX_PIN_ATTEMPTS - 1

    def test_leve_pin_locked_error_au_seuil_de_blocage(self):
        user = UserFactory()
        services.define_pin(user=user, pin=PIN, confirm_pin=PIN)

        for _ in range(services.MAX_PIN_ATTEMPTS - 1):
            with pytest.raises(services.InvalidPinError):
                services.require_valid_pin(user=user, pin="0000")

        with pytest.raises(services.PinLockedError) as exc_info:
            services.require_valid_pin(user=user, pin="0000")

        assert exc_info.value.locked_until is not None
