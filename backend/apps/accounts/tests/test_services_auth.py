"""Tests de `apps.accounts.services` : authentification (tache 1.3, 1.3t).

Sources : CDC 4.1, 7.1 ; 10.2 n21 ; docs/ecrans/comptes-connexion.md §5, §7.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import User
from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.clubs.tests.factories import ClubFactory, MembershipFactory

RAW_PASSWORD = "MotDePasse123"


@pytest.mark.django_db
class TestAuthenticateLoginSucces:
    def test_connexion_reussie_avec_une_seule_adhesion_active(self):
        membership = MembershipFactory(status="active")
        user = membership.user

        result = services.authenticate_login(email=user.email.upper(), password=RAW_PASSWORD)

        assert result.user.pk == user.pk
        assert result.membership.pk == membership.pk
        assert AuditLog.objects.filter(actor=user, action_type="auth.login_succeeded").exists()

    def test_connexion_reussie_pour_un_superuser_sans_adhesion(self):
        superuser = SuperuserFactory()

        result = services.authenticate_login(email=superuser.email, password=RAW_PASSWORD)

        assert result.user.pk == superuser.pk
        assert result.membership is None

    def test_email_normalise_ignore_la_casse_et_les_espaces(self):
        membership = MembershipFactory(status="active")
        user = membership.user

        result = services.authenticate_login(email=f"  {user.email.upper()}  ", password=RAW_PASSWORD)

        assert result.user.pk == user.pk

    def test_succes_reinitialise_le_compteur_d_echecs(self):
        membership = MembershipFactory(status="active")
        user = membership.user
        user.failed_login_attempts = 3
        user.save(update_fields=["failed_login_attempts"])

        services.authenticate_login(email=user.email, password=RAW_PASSWORD)

        user.refresh_from_db()
        assert user.failed_login_attempts == 0
        assert user.login_locked_until is None


@pytest.mark.django_db
class TestAuthenticateLoginEchecsEtBlocage:
    def test_email_inconnu_leve_identifiants_incorrects_sans_compteur(self):
        with pytest.raises(services.InvalidCredentialsError) as exc_info:
            services.authenticate_login(email="inconnu@example.com", password="peu importe")

        assert exc_info.value.attempts_remaining is None
        # Aucun acteur reel : aucune entree de journal n'est possible ici.
        assert not AuditLog.objects.filter(action_type="auth.login_failed").exists()

    def test_mot_de_passe_incorrect_incremente_le_compteur(self):
        membership = MembershipFactory(status="active")
        user = membership.user

        with pytest.raises(services.InvalidCredentialsError) as exc_info:
            services.authenticate_login(email=user.email, password="mauvais-mot-de-passe")

        user.refresh_from_db()
        assert user.failed_login_attempts == 1
        assert exc_info.value.attempts_remaining == services.MAX_LOGIN_ATTEMPTS - 1
        entry = AuditLog.objects.get(actor=user, action_type="auth.login_failed")
        assert entry.after == {"failed_login_attempts": 1}

    def test_5e_echec_bloque_le_compte_15_minutes(self):
        membership = MembershipFactory(status="active")
        user = membership.user

        for _ in range(services.MAX_LOGIN_ATTEMPTS - 1):
            with pytest.raises(services.InvalidCredentialsError):
                services.authenticate_login(email=user.email, password="mauvais-mot-de-passe")

        with pytest.raises(services.AccountLockedError) as exc_info:
            services.authenticate_login(email=user.email, password="mauvais-mot-de-passe")

        user.refresh_from_db()
        assert user.failed_login_attempts == services.MAX_LOGIN_ATTEMPTS
        assert user.login_locked_until == exc_info.value.locked_until
        assert AuditLog.objects.filter(actor=user, action_type="auth.account_locked").exists()

    def test_compte_bloque_refuse_meme_le_bon_mot_de_passe(self):
        membership = MembershipFactory(status="active")
        user = membership.user
        user.login_locked_until = timezone.now() + timedelta(minutes=10)
        user.save(update_fields=["login_locked_until"])

        with pytest.raises(services.AccountLockedError):
            services.authenticate_login(email=user.email, password=RAW_PASSWORD)

    def test_deblocage_automatique_apres_15_minutes(self):
        membership = MembershipFactory(status="active")
        user = membership.user

        now = timezone.now()
        with patch("django.utils.timezone.now", return_value=now):
            for _ in range(services.MAX_LOGIN_ATTEMPTS):
                try:
                    services.authenticate_login(email=user.email, password="mauvais-mot-de-passe")
                except services.AuthenticationError:
                    pass

        user.refresh_from_db()
        assert user.login_locked_until == now + services.LOGIN_LOCKOUT_DURATION

        after_lockout = now + services.LOGIN_LOCKOUT_DURATION + timedelta(seconds=1)
        with patch("django.utils.timezone.now", return_value=after_lockout):
            result = services.authenticate_login(email=user.email, password=RAW_PASSWORD)

        assert result.user.pk == user.pk


@pytest.mark.django_db
class TestAuthenticateLoginCasParticuliers:
    def test_mot_de_passe_temporaire_expire_est_refuse(self):
        membership = MembershipFactory(status="active")
        user = membership.user
        user.temp_password_expires_at = timezone.now() - timedelta(hours=1)
        user.save(update_fields=["temp_password_expires_at"])

        with pytest.raises(services.TemporaryPasswordExpiredError):
            services.authenticate_login(email=user.email, password=RAW_PASSWORD)

    def test_mot_de_passe_temporaire_encore_valable_est_accepte(self):
        membership = MembershipFactory(status="active")
        user = membership.user
        user.temp_password_expires_at = timezone.now() + timedelta(hours=1)
        user.save(update_fields=["temp_password_expires_at"])

        result = services.authenticate_login(email=user.email, password=RAW_PASSWORD)

        assert result.user.pk == user.pk

    def test_compte_desactive_est_refuse_seulement_si_le_mot_de_passe_est_juste(self):
        membership = MembershipFactory(status="active")
        user = membership.user
        user.is_active = False
        user.save(update_fields=["is_active"])

        with pytest.raises(services.AccountDisabledError):
            services.authenticate_login(email=user.email, password=RAW_PASSWORD)

    def test_aucune_adhesion_active_refuse_la_connexion(self):
        user = UserFactory()

        with pytest.raises(services.NoClubMembershipError):
            services.authenticate_login(email=user.email, password=RAW_PASSWORD)

        assert AuditLog.objects.filter(actor=user, action_type="auth.login_denied_no_club").exists()


@pytest.mark.django_db
class TestDesambiguisationDuClubActif:
    def test_plusieurs_adhesions_actives_sans_slug_leve_une_erreur(self):
        user = UserFactory()
        membership_a = MembershipFactory(user=user, status="active")
        membership_b = MembershipFactory(user=user, status="active")

        with pytest.raises(services.ClubDisambiguationRequiredError) as exc_info:
            services.authenticate_login(email=user.email, password=RAW_PASSWORD)

        club_ids = {m.club_id for m in exc_info.value.candidates}
        assert club_ids == {membership_a.club_id, membership_b.club_id}
        assert AuditLog.objects.filter(
            actor=user, action_type="auth.login_denied_ambiguous_club"
        ).exists()

    def test_plusieurs_adhesions_actives_avec_slug_valide_les_desambiguise(self):
        user = UserFactory()
        membership_a = MembershipFactory(user=user, status="active")
        membership_b = MembershipFactory(user=user, status="active")

        result = services.authenticate_login(
            email=user.email, password=RAW_PASSWORD, club_slug=membership_b.club.slug
        )

        assert result.membership.pk == membership_b.pk

    def test_une_seule_adhesion_active_ignore_un_slug_qui_ne_correspond_pas(self):
        """comptes-connexion.md §2 : « Aucune erreur n'est affichee dans ce cas. »"""

        membership = MembershipFactory(status="active")
        user = membership.user
        autre_club = ClubFactory()

        result = services.authenticate_login(
            email=user.email, password=RAW_PASSWORD, club_slug=autre_club.slug
        )

        assert result.membership.pk == membership.pk

    def test_slug_invalide_avec_plusieurs_adhesions_reste_ambigu(self):
        user = UserFactory()
        MembershipFactory(user=user, status="active")
        MembershipFactory(user=user, status="active")
        autre_club = ClubFactory()

        with pytest.raises(services.ClubDisambiguationRequiredError):
            services.authenticate_login(email=user.email, password=RAW_PASSWORD, club_slug=autre_club.slug)

    def test_une_adhesion_en_attente_seule_ne_permet_pas_la_connexion(self):
        """CDC 6.3 : seule une adhesion `active` compte comme club actif.

        Un compte dont la seule adhesion est `pending` (parrainage/adhesion
        non finalises) ne doit jamais se retrouver connecte sur ce club --
        distinct du cas « aucune adhesion du tout », mais qui doit produire
        le meme refus (etancheite : pas d'acces avant que l'adhesion ne
        devienne reellement active, CDC 4.1 statuts du joueur).
        """
        membership = MembershipFactory(status=Membership.Status.PENDING)
        user = membership.user

        with pytest.raises(services.NoClubMembershipError):
            services.authenticate_login(email=user.email, password=RAW_PASSWORD)

    def test_une_adhesion_partie_seule_ne_permet_pas_la_connexion(self):
        membership = MembershipFactory(status=Membership.Status.DEPARTED)
        user = membership.user

        with pytest.raises(services.NoClubMembershipError):
            services.authenticate_login(email=user.email, password=RAW_PASSWORD)

    def test_une_adhesion_active_est_choisie_meme_si_une_autre_est_en_attente(self):
        """Une adhesion `pending` dans un autre club ne doit jamais rendre le
        club actif ambigu ni etre choisie a la place de l'adhesion `active`."""

        user = UserFactory()
        active_membership = MembershipFactory(user=user, status=Membership.Status.ACTIVE)
        MembershipFactory(user=user, status=Membership.Status.PENDING)

        result = services.authenticate_login(email=user.email, password=RAW_PASSWORD)

        assert result.membership.pk == active_membership.pk


@pytest.mark.django_db
class TestConcurrenceSurLeCompteurDEchecs:
    """CDC 7.1 : « Apres 5 echecs de connexion, le compte est bloque 15 minutes. »

    ``authenticate_login`` lit ``failed_login_attempts`` en Python puis le
    reecrit (``user.save(update_fields=["failed_login_attempts"])``), sans
    ``select_for_update`` ni expression atomique ``F()``. Sous MySQL/MariaDB
    en production (contrairement a SQLite, ou ``select_for_update`` est un
    no-op silencieux, voir backend/README.md), deux requetes de connexion
    strictement simultanees sur le meme compte peuvent toutes deux lire
    l'ancienne valeur du compteur avant qu'aucune des deux n'ait ecrit la
    sienne : l'une des deux ecritures est perdue.

    Ce test reproduit deterministiquement cette consequence, sans dependre
    du minutage reel de deux threads (pour rester non-flaky, conformement a
    la consigne « pas de test dependant ... du reseau/minutage ») : il force
    deux appels successifs de ``authenticate_login`` a travailler chacun sur
    sa propre copie « perimee » de l'utilisateur, exactement comme le
    ferait deux requetes HTTP dont les lectures se chevauchent.

    BUG REEL A SIGNALER A backend-dev (pas corrige ici, conformement a la
    consigne du projet) : voir le compte rendu de cette revue de tests.
    """

    def test_deux_echecs_simultanes_ne_doivent_perdre_aucune_ecriture(self):
        membership = MembershipFactory(status=Membership.Status.ACTIVE)
        user = membership.user

        # Deux copies Python independantes de la meme ligne, chacune lue
        # avant qu'aucune des deux requetes n'ait encore ecrit -- exactement
        # ce qui se produit sous une vraie concurrence sans verrou de ligne.
        stale_copy_for_request_a = User.objects.get(pk=user.pk)
        stale_copy_for_request_b = User.objects.get(pk=user.pk)
        assert stale_copy_for_request_a.failed_login_attempts == 0
        assert stale_copy_for_request_b.failed_login_attempts == 0

        with patch("apps.accounts.services.User.objects") as mocked_manager:
            mocked_manager.filter.return_value.first.side_effect = [
                stale_copy_for_request_a,
                stale_copy_for_request_b,
            ]

            with pytest.raises(services.InvalidCredentialsError):
                services.authenticate_login(email=user.email, password="mauvais-mot-de-passe")
            with pytest.raises(services.InvalidCredentialsError):
                services.authenticate_login(email=user.email, password="mauvais-mot-de-passe")

        user.refresh_from_db()
        assert user.failed_login_attempts == 2, (
            "Deux echecs de connexion reels ont ete comptabilises comme un "
            "seul (ecriture perdue) : `authenticate_login` lit puis reecrit "
            "`failed_login_attempts` sans verrou de ligne (`select_for_update`) "
            "ni expression atomique (F()). Sous MySQL/MariaDB en production, "
            "deux requetes de connexion vraiment simultanees sur le meme "
            "compte peuvent ainsi sous-compter les echecs et retarder, voire "
            "contourner completement, le blocage apres 5 echecs (CDC 7.1)."
        )
