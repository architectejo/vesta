"""Commande de gestion `process_sponsor_reminders` (CDC 4.3, cas limite
« le parrain ne repond pas » ; tache 1.4b).

CLAUDE.md (section 4) : tache periodique = commande de gestion Django
appelee par cron, jamais un processus permanent. Ce test verifie
uniquement le cablage de la commande vers
``apps.clubs.services.process_sponsor_reminders_and_alerts`` (deja testee
en detail dans ``test_membership_application.py``).
"""

from __future__ import annotations

import datetime
import io

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.clubs.models import MembershipApplication
from apps.clubs.tests.test_membership_application import add_player, build_context

pytestmark = pytest.mark.django_db


def test_la_commande_envoie_le_rappel_et_rapporte_le_resultat():
    ctx = build_context()
    _membership, application = add_player(ctx)
    application.sponsor_notified_at = timezone.now() - datetime.timedelta(days=4)
    application.save()

    out = io.StringIO()
    call_command("process_sponsor_reminders", stdout=out)

    application.refresh_from_db()
    assert application.sponsor_reminder_sent_at is not None
    assert "1" in out.getvalue()


def test_la_commande_est_sans_effet_si_rien_a_faire():
    ctx = build_context()
    add_player(ctx)  # jamais notifie

    out = io.StringIO()
    call_command("process_sponsor_reminders", stdout=out)

    assert not MembershipApplication.all_objects.filter(sponsor_reminder_sent_at__isnull=False).exists()


def test_appeler_la_commande_deux_fois_le_meme_jour_n_envoie_pas_un_second_rappel():
    """Complement demande en revue independante (tache 1.4bt), point 4 :
    l'idempotence est deja testee au niveau du service
    (``test_idempotent_ne_renvoie_jamais_deux_fois`` dans
    ``test_membership_application.py``), mais pas au niveau de la commande
    elle-meme (cron declenche potentiellement plusieurs fois le meme jour,
    ex. reprise apres echec) -- ce test verifie le cablage bout en bout :
    la deuxieme execution ne doit rapporter aucun nouveau rappel/alerte."""

    ctx = build_context()
    _membership, application = add_player(ctx)
    application.sponsor_notified_at = timezone.now() - datetime.timedelta(days=10)
    application.save()

    first_out = io.StringIO()
    call_command("process_sponsor_reminders", stdout=first_out)
    application.refresh_from_db()
    first_reminder_at = application.sponsor_reminder_sent_at
    first_alert_at = application.president_alerted_at
    assert first_reminder_at is not None
    assert first_alert_at is not None
    assert "1" in first_out.getvalue()

    second_out = io.StringIO()
    call_command("process_sponsor_reminders", stdout=second_out)

    application.refresh_from_db()
    assert application.sponsor_reminder_sent_at == first_reminder_at
    assert application.president_alerted_at == first_alert_at
    assert "Rappels envoyes : 0" in second_out.getvalue()
    assert "alertes au President envoyees : 0" in second_out.getvalue()
