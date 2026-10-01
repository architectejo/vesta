"""Tests de `apps.accounts.services` : changement de mot de passe force (tache 1.3).

Sources : CDC 4.1, 7.1 ; docs/ecrans/comptes-connexion.md §4.2, §7.

Audit de securite du Lot 1 (ecart bloquant B3) : ``change_forced_password``
est desormais reserve au cas ou ``user.must_change_password`` est vrai --
tous les scenarios ci-dessous qui exercent les regles de validation du
nouveau mot de passe (correspondance, difference avec l'email/l'actuel,
longueur) utilisent donc explicitement ``UserFactory(must_change_password=True)``
(``UserFactory`` pose ``must_change_password=False`` par defaut, voir
``apps.accounts.tests.factories``) : avant cette correction, ces tests
passaient "par accident" sur un compte qui n'etait pourtant pas en
changement force, ce qui masquait precisement l'ecart trouve par
l'audit.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog

RAW_PASSWORD = "MotDePasse123"


@pytest.mark.django_db
class TestChangeForcedPassword:
    def test_changement_reussi_leve_le_blocage(self):
        user = UserFactory(must_change_password=True)

        services.change_forced_password(
            user=user, new_password="UnAutreMotDePasse9", confirm_password="UnAutreMotDePasse9"
        )

        user.refresh_from_db()
        assert user.must_change_password is False
        assert user.temp_password_expires_at is None
        assert user.check_password("UnAutreMotDePasse9")
        entry = AuditLog.objects.get(actor=user, action_type="auth.password_changed")
        assert entry.after == {"must_change_password": False, "tokens_revoked": 0}

    def test_efface_l_echeance_du_mot_de_passe_temporaire(self):
        user = UserFactory(must_change_password=True)
        user.temp_password_expires_at = timezone.now() + timedelta(hours=1)
        user.save(update_fields=["temp_password_expires_at"])

        services.change_forced_password(
            user=user, new_password="UnAutreMotDePasse9", confirm_password="UnAutreMotDePasse9"
        )

        user.refresh_from_db()
        assert user.temp_password_expires_at is None

    def test_les_deux_mots_de_passe_doivent_correspondre(self):
        user = UserFactory(must_change_password=True)

        with pytest.raises(ValidationError) as exc_info:
            services.change_forced_password(
                user=user, new_password="UnAutreMotDePasse9", confirm_password="Different1"
            )

        assert "ne correspondent pas" in " ".join(exc_info.value.messages)

    def test_mot_de_passe_identique_a_l_email_est_refuse(self):
        user = UserFactory(must_change_password=True)

        with pytest.raises(ValidationError) as exc_info:
            services.change_forced_password(user=user, new_password=user.email, confirm_password=user.email)

        assert any("email" in message for message in exc_info.value.messages)

    def test_mot_de_passe_identique_a_l_actuel_est_refuse(self):
        user = UserFactory(password=RAW_PASSWORD, must_change_password=True)

        with pytest.raises(ValidationError) as exc_info:
            services.change_forced_password(user=user, new_password=RAW_PASSWORD, confirm_password=RAW_PASSWORD)

        assert any("actuel" in message for message in exc_info.value.messages)

    def test_mot_de_passe_trop_court_est_refuse(self):
        user = UserFactory(must_change_password=True)

        with pytest.raises(ValidationError):
            services.change_forced_password(user=user, new_password="court1", confirm_password="court1")

    def test_refuse_hors_du_cas_de_changement_force(self):
        """Preuve de fermeture de l'ecart bloquant B3 : un utilisateur qui
        n'est PAS en changement force ne peut pas utiliser ce point d'acces
        pour changer son mot de passe sans connaitre l'ancien."""

        user = UserFactory(must_change_password=False)

        with pytest.raises(services.PasswordChangeNotForcedError):
            services.change_forced_password(
                user=user, new_password="UnAutreMotDePasse9", confirm_password="UnAutreMotDePasse9"
            )

        user.refresh_from_db()
        assert user.check_password("MotDePasse123")  # mot de passe d'origine inchange
        assert AuditLog.objects.filter(
            actor=user, action_type="auth.forced_password_change_denied"
        ).exists()

    def test_revoque_tous_les_jetons_existants_apres_un_changement_reussi(self):
        """Preuve de fermeture de l'ecart bloquant B3 : un jeton d'acces vole
        (15 min) ne doit pas survivre au changement de mot de passe qu'il
        vient de declencher."""

        user = UserFactory(must_change_password=True)
        ancien_refresh = RefreshToken.for_user(user)
        assert OutstandingToken.objects.filter(user=user).exists()

        services.change_forced_password(
            user=user, new_password="UnAutreMotDePasse9", confirm_password="UnAutreMotDePasse9"
        )

        assert BlacklistedToken.objects.filter(token__jti=ancien_refresh["jti"]).exists()
        entry = AuditLog.objects.get(actor=user, action_type="auth.password_changed")
        assert entry.after["tokens_revoked"] == 1

    def test_compte_correctement_plusieurs_jetons_actifs(self):
        """`tokens_revoked` doit refleter le nombre REEL de jetons actifs de
        l'utilisateur, pas seulement 0 ou 1 (les deux seuls cas exerces par
        les tests existants)."""

        user = UserFactory(must_change_password=True)
        RefreshToken.for_user(user)
        RefreshToken.for_user(user)
        RefreshToken.for_user(user)
        assert OutstandingToken.objects.filter(user=user).count() == 3

        services.change_forced_password(
            user=user, new_password="UnAutreMotDePasse9", confirm_password="UnAutreMotDePasse9"
        )

        entry = AuditLog.objects.get(actor=user, action_type="auth.password_changed")
        assert entry.after["tokens_revoked"] == 3
        assert BlacklistedToken.objects.filter(token__user=user).count() == 3

    def test_ne_double_compte_pas_un_jeton_deja_en_liste_noire(self):
        """Un jeton deja mis en liste noire par ailleurs (ex. une
        deconnexion normale anterieure) ne doit pas etre recompte dans
        `tokens_revoked` : seuls les jetons NOUVELLEMENT revoques par cet
        appel doivent l'etre (`_blacklist_all_outstanding_tokens` utilise
        `get_or_create`, dont le compteur doit refleter uniquement les
        creations reelles)."""

        user = UserFactory(must_change_password=True)
        refresh_deja_revoque = RefreshToken.for_user(user)
        refresh_deja_revoque.blacklist()
        refresh_encore_actif = RefreshToken.for_user(user)
        assert OutstandingToken.objects.filter(user=user).count() == 2

        services.change_forced_password(
            user=user, new_password="UnAutreMotDePasse9", confirm_password="UnAutreMotDePasse9"
        )

        entry = AuditLog.objects.get(actor=user, action_type="auth.password_changed")
        assert entry.after["tokens_revoked"] == 1
        assert BlacklistedToken.objects.filter(token__jti=refresh_encore_actif["jti"]).exists()
