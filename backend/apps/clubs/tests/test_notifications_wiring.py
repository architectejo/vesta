"""Cablage reel des points d'accroche de notification laisses par les
taches 1.4b/1.5 (CDC 2.3, 4.3, 4.17 ; tache 1.7).

Complete ``test_membership_application.py``/``test_services_roles.py``
(logique metier deja testee) : verifie ici que chaque evenement produit
par ``apps.clubs.services`` ecrit reellement une ``Notification``, avec
le bon destinataire, le bon type d'evenement et un message en francais.
"""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.clubs import services as clubs_services
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import MembershipRoleFactory
from apps.clubs.tests.test_membership_application import add_player, build_context, pay
from apps.notifications.models import Notification
from apps.treasury.tests.conftest import PIN, make_member

pytestmark = pytest.mark.django_db


class TestNotificationFicheASignerEtRappel:
    def test_le_paiement_complet_notifie_le_parrain_a_signer(self):
        ctx = build_context()
        _membership, application = add_player(ctx)

        pay(ctx, application, amount="5")

        notification = Notification.objects.get(recipient=ctx.sponsor.user)
        assert notification.event_type == Notification.EventType.MEMBERSHIP_SIGNATURE_PENDING
        assert notification.title == "Fiche d'adhésion à signer"
        recruit_name = (
            f"{application.membership.user.first_name} {application.membership.user.last_name}".strip()
        )
        assert notification.body == (
            f"{recruit_name} attend votre parrainage. Ouvrez sa fiche d'adhésion "
            "pour la signer avec votre code PIN, ou pour refuser en indiquant un "
            "motif."
        )
        assert notification.club_id == ctx.club.id
        assert notification.link_object_type == "MembershipApplication"
        assert notification.link_object_id == application.id

    def test_le_rappel_a_3_jours_notifie_a_nouveau_le_parrain_avec_un_type_different(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        pay(ctx, application, amount="5")
        Notification.objects.all().delete()  # ne garder que la notification du rappel

        application.refresh_from_db()
        application.sponsor_notified_at = timezone.now() - datetime.timedelta(days=4)
        application.save()

        clubs_services.process_sponsor_reminders_and_alerts()

        notification = Notification.objects.get(recipient=ctx.sponsor.user)
        assert notification.event_type == Notification.EventType.SPONSOR_REMINDER
        assert notification.title == "Rappel : fiche d'adhésion à signer"
        recruit_name = (
            f"{application.membership.user.first_name} {application.membership.user.last_name}".strip()
        )
        assert notification.body == (
            f"La fiche d'adhésion de {recruit_name} attend votre réponse "
            "depuis 3 jours. Signez-la avec votre code PIN, ou refusez en "
            "indiquant un motif."
        )

    def test_le_silence_a_7_jours_alerte_le_president(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        pay(ctx, application, amount="5")

        application.refresh_from_db()
        application.sponsor_notified_at = timezone.now() - datetime.timedelta(days=8)
        application.save()

        clubs_services.process_sponsor_reminders_and_alerts()

        notification = Notification.objects.get(
            recipient=ctx.president.user, event_type=Notification.EventType.SPONSOR_ALERT_PRESIDENT
        )
        assert "7 jours" in notification.body

    def test_rappel_et_alerte_ne_sont_jamais_confondus_meme_declenches_dans_le_meme_appel(self):
        """Tache 1.7t, point 5 : si le cron n'a pas tourne depuis longtemps
        (dossier a 8 jours SANS rappel a 3 jours prealable), les deux
        conditions se declenchent au meme appel de
        ``process_sponsor_reminders_and_alerts``. Le rappel doit toujours
        aller au PARRAIN (jamais au President) et l'alerte au PRESIDENT
        (jamais au parrain) -- aucune confusion de destinataire ni de type
        d'evenement."""

        ctx = build_context()
        _membership, application = add_player(ctx)
        pay(ctx, application, amount="5")

        application.refresh_from_db()
        application.sponsor_notified_at = timezone.now() - datetime.timedelta(days=8)
        application.save()

        result = clubs_services.process_sponsor_reminders_and_alerts()

        assert result == {"reminders_sent": 1, "alerts_sent": 1}

        sponsor_notifications = Notification.objects.filter(recipient=ctx.sponsor.user)
        president_notifications = Notification.objects.filter(recipient=ctx.president.user)

        assert sponsor_notifications.filter(event_type=Notification.EventType.SPONSOR_REMINDER).exists()
        assert not sponsor_notifications.filter(
            event_type=Notification.EventType.SPONSOR_ALERT_PRESIDENT
        ).exists()
        assert president_notifications.filter(
            event_type=Notification.EventType.SPONSOR_ALERT_PRESIDENT
        ).exists()
        assert not president_notifications.filter(event_type=Notification.EventType.SPONSOR_REMINDER).exists()

    def test_l_alerte_a_7_jours_est_omise_sans_president_actif_sans_faire_planter_le_cron(self):
        """Meme cas limite que ``test_aucun_president_actif_ne_leve_aucune_exception``
        (classe ``TestNotificationRefusDuParrain``), mais pour le SECOND
        point d'accroche qui appelle ``_active_president_membership``
        (``notify_president_of_no_response``, tache 1.7t point 6) : le
        traitement cron ne doit jamais planter pour cette seule raison."""

        ctx = build_context()
        _membership, application = add_player(ctx)
        pay(ctx, application, amount="5")

        application.refresh_from_db()
        application.sponsor_notified_at = timezone.now() - datetime.timedelta(days=8)
        application.save()

        MembershipRole.all_objects.filter(
            club=ctx.club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())

        result = clubs_services.process_sponsor_reminders_and_alerts()

        assert result == {"reminders_sent": 1, "alerts_sent": 1}
        assert not Notification.objects.filter(
            event_type=Notification.EventType.SPONSOR_ALERT_PRESIDENT
        ).exists()
        # Le rappel au parrain, lui, ne depend pas du President : il a bien lieu.
        assert Notification.objects.filter(
            recipient=ctx.sponsor.user, event_type=Notification.EventType.SPONSOR_REMINDER
        ).exists()


class TestNotificationRefusDuParrain:
    def test_le_refus_du_parrain_notifie_le_president(self):
        ctx = build_context()
        _membership, application = add_player(ctx)
        pay(ctx, application, amount="5")

        clubs_services.refuse_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user, reason="Je ne le connais pas"
        )

        notification = Notification.objects.get(
            recipient=ctx.president.user, event_type=Notification.EventType.SPONSOR_REFUSED
        )
        assert "Je ne le connais pas" in notification.body
        assert notification.club_id == ctx.club.id

    def test_aucun_president_actif_ne_leve_aucune_exception(self):
        """Cas limite : si aucun President n'est en poste au moment du
        refus (situation anormale mais possible pendant une passation),
        la notification est simplement omise -- le refus du parrain ne
        doit jamais echouer pour cette seule raison."""

        ctx = build_context()
        _membership, application = add_player(ctx)
        pay(ctx, application, amount="5")

        MembershipRole.all_objects.filter(
            club=ctx.club, role=MembershipRole.Role.PRESIDENT, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())

        clubs_services.refuse_sponsor_application(
            application=application, sponsor_user=ctx.sponsor.user, reason="Motif"
        )

        assert not Notification.objects.filter(event_type=Notification.EventType.SPONSOR_REFUSED).exists()


class TestNotificationNominationRevocation:
    def test_la_nomination_d_un_role_notifie_le_joueur(self):
        ctx = build_context()
        target = make_member(ctx.club)

        clubs_services.appoint_president_nominated_role(
            president_user=ctx.president.user,
            target_membership=target,
            role=MembershipRole.Role.VICE_PRESIDENT,
        )

        notification = Notification.objects.get(
            recipient=target.user, event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED
        )
        assert notification.title == "Nouveau rôle"
        assert notification.body == (
            f"Vous avez désormais le rôle « Vice-président » au sein de {ctx.club.name}."
        )

    def test_la_nomination_notifie_le_joueur_concerne_jamais_l_acteur_qui_nomme(self):
        """CDC 2.3 : « notification au joueur concerne » -- pas a l'acteur
        (le President qui effectue la nomination). Tache 1.7t, point 5."""

        ctx = build_context()
        target = make_member(ctx.club)

        clubs_services.appoint_president_nominated_role(
            president_user=ctx.president.user,
            target_membership=target,
            role=MembershipRole.Role.VICE_PRESIDENT,
        )

        assert not Notification.objects.filter(
            recipient=ctx.president.user, event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED
        ).exists()
        assert Notification.objects.filter(
            recipient=target.user, event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED
        ).count() == 1

    def test_la_revocation_d_un_role_notifie_le_joueur(self):
        ctx = build_context()
        target = make_member(ctx.club)
        role = MembershipRoleFactory(
            membership=target, club=ctx.club, role=MembershipRole.Role.VICE_PRESIDENT
        )

        clubs_services.revoke_president_nominated_role(president_user=ctx.president.user, role=role)

        notification = Notification.objects.get(
            recipient=target.user, event_type=Notification.EventType.ROLE_APPOINTED_OR_REVOKED
        )
        assert "plus" in notification.body.lower()
