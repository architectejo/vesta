"""Commande de gestion `send_notification_emails` (CDC 4.17, 6.5 ; tache 1.7).

CLAUDE.md (section 4) : tache periodique = commande de gestion Django
appelee par cron, jamais un processus permanent. Ce test verifie
uniquement le cablage de la commande vers
``apps.notifications.services.send_pending_notification_emails`` (deja
testee en detail dans ``test_services.py``).
"""

from __future__ import annotations

import io

import pytest
from django.core import mail
from django.core.management import call_command

from apps.accounts.tests.factories import UserFactory
from apps.notifications.models import Notification
from apps.notifications.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db


def test_la_commande_envoie_les_emails_en_attente_et_rapporte_le_resultat():
    user = UserFactory(email="joueur@example.com")
    NotificationFactory(
        recipient=user,
        email_requested=True,
        email_status=Notification.EmailStatus.PENDING,
    )

    out = io.StringIO()
    call_command("send_notification_emails", stdout=out)

    assert len(mail.outbox) == 1
    assert "Emails envoyes : 1" in out.getvalue()
    assert "echecs : 0" in out.getvalue()


def test_la_commande_est_sans_effet_si_rien_a_envoyer():
    out = io.StringIO()
    call_command("send_notification_emails", stdout=out)

    assert len(mail.outbox) == 0
    assert "Emails envoyes : 0" in out.getvalue()
