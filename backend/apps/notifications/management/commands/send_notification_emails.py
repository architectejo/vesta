"""Commande de gestion : envoi des emails de notification en file (CDC
4.17, 6.5 -- tache 1.7).

CLAUDE.md (section 4, contraintes d'hebergement cPanel/LiteSpeed) : pas
de processus permanent -- les taches periodiques sont des commandes de
gestion Django appelees par cron, jamais un scheduler interne. Cette
commande est une fine enveloppe autour de
``apps.notifications.services.send_pending_notification_emails`` : le
branchement reel du crontab (frequence -- « toutes les 5 minutes »,
docs/lot0/schema-donnees.md §17) reste hors perimetre de cette tache --
`devops-cpanel` a la mise en production, meme limite que
``process_sponsor_reminders`` (tache 1.4b) et la verification quotidienne
de la chaine financiere laissee ouverte par `finance-engine`.

Usage (cron, toutes les 5 minutes par exemple) ::

    python manage.py send_notification_emails
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.notifications.services import send_pending_notification_emails


class Command(BaseCommand):
    help = "Envoie les emails de notification en attente (CDC 4.17, 6.5)."

    def handle(self, *args, **options):
        result = send_pending_notification_emails()
        self.stdout.write(
            self.style.SUCCESS(
                f"Emails envoyes : {result['sent']} ; echecs : {result['failed']}."
            )
        )
