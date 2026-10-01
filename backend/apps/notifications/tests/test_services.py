"""Tests des services de l'app notifications (CDC 4.17, 6.5 ; tache 1.7)."""

from __future__ import annotations

import datetime

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.notifications import services
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.tests.factories import NotificationFactory, NotificationPreferenceFactory

pytestmark = pytest.mark.django_db


class TestCreateNotification:
    def test_cree_une_notification_en_base_avec_le_bon_titre_et_message(self):
        recipient = UserFactory()

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED,
            message="Vous avez été nommé Trésorier au club X.",
        )

        assert notification.pk is not None
        assert notification.recipient_id == recipient.id
        assert notification.body == "Vous avez été nommé Trésorier au club X."
        assert notification.title == "Nomination ou révocation"
        assert notification.is_read is False
        assert notification.read_at is None

    def test_deduit_le_club_et_le_lien_depuis_la_cible(self):
        recipient = UserFactory()
        membership = MembershipFactory()

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED,
            message="Message",
            target=membership,
        )

        assert notification.club_id == membership.club_id
        assert notification.link_object_type == "Membership"
        assert notification.link_object_id == membership.id

    def test_club_explicite_none_prevaut_sur_la_cible(self):
        recipient = UserFactory()
        membership = MembershipFactory()

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.POST_REPORTED,
            message="Signalement",
            target=membership,
            club=None,
        )

        assert notification.club_id is None

    def test_evenement_in_app_seulement_ne_met_jamais_l_email_en_file(self):
        recipient = UserFactory()

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED,
            message="Message",
        )

        assert notification.email_requested is False
        assert notification.email_status == Notification.EmailStatus.NOT_APPLICABLE
        assert notification.email_sent_at is None

    def test_evenement_double_canal_met_l_email_en_file_si_preference_active(self):
        recipient = UserFactory()
        NotificationPreferenceFactory(user=recipient, email_enabled=True)

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.PAYMENT_VALIDATED,
            message="Votre paiement a ete valide.",
        )

        assert notification.email_requested is True
        assert notification.email_status == Notification.EmailStatus.PENDING

    def test_evenement_double_canal_sans_email_si_preference_desactivee(self):
        recipient = UserFactory()
        NotificationPreferenceFactory(user=recipient, email_enabled=False)

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.PAYMENT_VALIDATED,
            message="Votre paiement a ete valide.",
        )

        assert notification.email_requested is False
        assert notification.email_status == Notification.EmailStatus.NOT_APPLICABLE

    def test_preference_par_defaut_est_active_pour_un_utilisateur_sans_reglage_explicite(self):
        recipient = UserFactory()  # aucune NotificationPreference creee

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.PAYMENT_VALIDATED,
            message="Votre paiement a ete valide.",
        )

        assert notification.email_requested is True
        assert NotificationPreference.objects.filter(user=recipient, email_enabled=True).exists()

    def test_le_parametre_now_devrait_reellement_dater_la_notification(self):
        """Regression (tache 1.7t) : `Notification.created_at` n'est plus
        `auto_now_add=True` (apps/notifications/models.py), Django n'ecrase
        donc plus silencieusement la valeur explicite passee par
        `create_notification(..., now=...)`."""
        recipient = UserFactory()
        past = timezone.now() - datetime.timedelta(days=5)

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED,
            message="Message",
            now=past,
        )

        assert abs((notification.created_at - past).total_seconds()) < 2

    def test_ne_declenche_jamais_un_envoi_email_directement(self):
        recipient = UserFactory()

        services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.PAYMENT_VALIDATED,
            message="Votre paiement a ete valide.",
        )

        assert len(mail.outbox) == 0

    def test_evenement_in_app_seulement_reste_sans_objet_meme_si_la_preference_email_est_active(self):
        """Croisement des deux axes (tache 1.7t, point 3) : le canal email
        ne depend pas QUE de la preference -- il depend d'abord du type
        d'evenement (:data:`services.EMAIL_CHANNEL_EVENT_TYPES`). Une
        preference active ne doit jamais, a elle seule, mettre un email en
        file pour un evenement in-app seulement (CDC 4.17 : « Nomination ou
        revocation -- Joueur concerne -- In-app », sans canal email)."""

        recipient = UserFactory()
        NotificationPreferenceFactory(user=recipient, email_enabled=True)

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED,
            message="Vous avez ete nomme Tresorier au club X.",
        )

        assert notification.email_requested is False
        assert notification.email_status == Notification.EmailStatus.NOT_APPLICABLE

    def test_visible_en_base_avant_tout_envoi_puis_envoye_par_la_tache_cron_separee(self):
        """Critere de fin exact de la tache 1.7 : « une notification
        declenchee est visible en base avant l'envoi de l'email » (CDC
        6.5). Isole strictement la sequence : creation en base -> aucun
        email envoye a cette etape (ni en base, ni dans la boite de test)
        -> SEULEMENT ENSUITE, un appel separe et explicite de la tache cron
        (:func:`services.send_pending_notification_emails`) envoie
        l'email."""

        recipient = UserFactory(email="joueur@example.com")
        NotificationPreferenceFactory(user=recipient, email_enabled=True)

        notification = services.create_notification(
            recipient=recipient,
            event_type=Notification.EventType.PAYMENT_VALIDATED,
            message="Votre paiement a ete valide.",
        )

        # Etape 1 : visible en base, en attente -- rien envoye.
        assert Notification.objects.filter(pk=notification.pk).exists()
        notification.refresh_from_db()
        assert notification.email_status == Notification.EmailStatus.PENDING
        assert notification.email_sent_at is None
        assert len(mail.outbox) == 0

        # Etape 2, separee : seule la tache cron envoie l'email.
        result = services.send_pending_notification_emails()

        notification.refresh_from_db()
        assert result == {"sent": 1, "failed": 0}
        assert notification.email_status == Notification.EmailStatus.SENT
        assert len(mail.outbox) == 1


class TestPreference:
    def test_get_or_create_preference_cree_avec_la_valeur_par_defaut(self):
        user = UserFactory()

        preference = services.get_or_create_preference(user)

        assert preference.email_enabled is True
        assert NotificationPreference.objects.filter(user=user).count() == 1

    def test_set_email_preference_modifie_le_reglage_existant(self):
        user = UserFactory()
        services.get_or_create_preference(user)

        services.set_email_preference(user=user, email_enabled=False)

        preference = NotificationPreference.objects.get(user=user)
        assert preference.email_enabled is False


class TestMarquerCommeLue:
    def test_mark_notification_read_par_le_destinataire(self):
        user = UserFactory()
        notification = NotificationFactory(recipient=user, is_read=False)

        updated = services.mark_notification_read(notification=notification, user=user)

        assert updated.is_read is True
        assert updated.read_at is not None

    def test_mark_notification_read_refuse_un_autre_utilisateur(self):
        owner = UserFactory()
        someone_else = UserFactory()
        notification = NotificationFactory(recipient=owner, is_read=False)

        with pytest.raises(PermissionError):
            services.mark_notification_read(notification=notification, user=someone_else)

    def test_mark_notification_read_refuse_un_autre_membre_du_meme_club(self):
        """Tache 1.7t, point 2 : l'isolation par destinataire tient meme
        quand les deux utilisateurs appartiennent au MEME club --
        ``Notification`` n'est pas un ``TenantModel``, le filtrage par
        ``club`` seul ne suffirait pas a proteger ce cas."""

        club = ClubFactory()
        owner = MembershipFactory(club=club).user
        colleague = MembershipFactory(club=club).user
        notification = NotificationFactory(recipient=owner, club=club, is_read=False)

        with pytest.raises(PermissionError):
            services.mark_notification_read(notification=notification, user=colleague)

        notification.refresh_from_db()
        assert notification.is_read is False

    def test_mark_all_notifications_read(self):
        user = UserFactory()
        NotificationFactory.create_batch(3, recipient=user, is_read=False)
        NotificationFactory(recipient=user, is_read=True)
        other_user = UserFactory()
        NotificationFactory(recipient=other_user, is_read=False)

        updated = services.mark_all_notifications_read(user=user)

        assert updated == 3
        assert services.unread_count(user=user) == 0
        assert services.unread_count(user=other_user) == 1

    def test_unread_count_ne_compte_que_les_notifications_du_destinataire(self):
        user = UserFactory()
        other_user = UserFactory()
        NotificationFactory.create_batch(2, recipient=user, is_read=False)
        NotificationFactory(recipient=other_user, is_read=False)

        assert services.unread_count(user=user) == 2


class TestEnvoiDesEmailsEnFile:
    def test_envoie_les_notifications_en_attente_et_les_marque_envoyees(self):
        user = UserFactory(email="joueur@example.com")
        notification = NotificationFactory(
            recipient=user,
            email_requested=True,
            email_status=Notification.EmailStatus.PENDING,
            title="Paiement valide",
            body="Votre paiement a ete valide.",
        )

        result = services.send_pending_notification_emails()

        notification.refresh_from_db()
        assert result == {"sent": 1, "failed": 0}
        assert notification.email_status == Notification.EmailStatus.SENT
        assert notification.email_sent_at is not None
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["joueur@example.com"]
        assert mail.outbox[0].subject == "Paiement valide"

    def test_ignore_les_notifications_sans_email_demande(self):
        NotificationFactory(email_requested=False, email_status=Notification.EmailStatus.NOT_APPLICABLE)

        result = services.send_pending_notification_emails()

        assert result == {"sent": 0, "failed": 0}
        assert len(mail.outbox) == 0

    def test_marque_echoue_si_le_destinataire_n_a_pas_d_email(self):
        user = UserFactory()
        user.email = ""
        user.save()
        notification = NotificationFactory(
            recipient=user,
            email_requested=True,
            email_status=Notification.EmailStatus.PENDING,
        )

        result = services.send_pending_notification_emails()

        notification.refresh_from_db()
        assert result == {"sent": 0, "failed": 1}
        assert notification.email_status == Notification.EmailStatus.FAILED

    def test_n_envoie_jamais_deux_fois_la_meme_notification_deja_envoyee(self):
        user = UserFactory(email="joueur@example.com")
        NotificationFactory(
            recipient=user,
            email_requested=True,
            email_status=Notification.EmailStatus.SENT,
        )

        result = services.send_pending_notification_emails()

        assert result == {"sent": 0, "failed": 0}
        assert len(mail.outbox) == 0

    def test_executer_la_commande_deux_fois_de_suite_ne_renvoie_pas_l_email(self):
        """Tache 1.7t, point 4 : deux executions successives de la meme
        fonction (la commande cron peut etre appelee plusieurs fois, ex.
        double declenchement) ne renvoient jamais un email deja ``sent``."""

        user = UserFactory(email="joueur@example.com")
        notification = NotificationFactory(
            recipient=user,
            email_requested=True,
            email_status=Notification.EmailStatus.PENDING,
        )

        first_run = services.send_pending_notification_emails()
        second_run = services.send_pending_notification_emails()

        notification.refresh_from_db()
        assert first_run == {"sent": 1, "failed": 0}
        assert second_run == {"sent": 0, "failed": 0}
        assert notification.email_status == Notification.EmailStatus.SENT
        assert len(mail.outbox) == 1

    def test_une_notification_failed_ne_bloque_pas_le_traitement_des_pending_suivantes(self):
        """Tache 1.7t, point 4 : dans le meme lot, un echec (ex. destinataire
        sans adresse email) ne doit pas interrompre la boucle -- les
        notifications ``pending`` suivantes doivent quand meme etre
        traitees et envoyees."""

        failing_user = UserFactory()
        failing_user.email = ""
        failing_user.save()
        failing_notification = NotificationFactory(
            recipient=failing_user,
            email_requested=True,
            email_status=Notification.EmailStatus.PENDING,
        )
        succeeding_user = UserFactory(email="joueur@example.com")
        succeeding_notification = NotificationFactory(
            recipient=succeeding_user,
            email_requested=True,
            email_status=Notification.EmailStatus.PENDING,
        )

        result = services.send_pending_notification_emails()

        failing_notification.refresh_from_db()
        succeeding_notification.refresh_from_db()
        assert result == {"sent": 1, "failed": 1}
        assert failing_notification.email_status == Notification.EmailStatus.FAILED
        assert succeeding_notification.email_status == Notification.EmailStatus.SENT
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["joueur@example.com"]

    def test_re_execution_apres_un_echec_ne_retente_pas_automatiquement(self):
        """Decision par defaut documentee (pas un bug) : une notification
        ``failed`` n'est jamais reprise automatiquement par une execution
        suivante -- seule une nouvelle action explicite pourrait la
        remettre en ``pending`` (hors perimetre de la tache 1.7)."""

        user = UserFactory()
        user.email = ""
        user.save()
        notification = NotificationFactory(
            recipient=user,
            email_requested=True,
            email_status=Notification.EmailStatus.PENDING,
        )

        first_run = services.send_pending_notification_emails()
        notification.refresh_from_db()
        assert first_run == {"sent": 0, "failed": 1}
        assert notification.email_status == Notification.EmailStatus.FAILED

        second_run = services.send_pending_notification_emails()
        notification.refresh_from_db()
        assert second_run == {"sent": 0, "failed": 0}
        assert notification.email_status == Notification.EmailStatus.FAILED
