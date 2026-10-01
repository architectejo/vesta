"""Commande de gestion : relances de licence a 30/7/1 jour (CDC 1.4 ; tache 1.8).

Meme limite de perimetre que ``process_licence_expirations`` et
``process_sponsor_reminders`` : cette commande est une fine enveloppe
autour de ``apps.licences.services.process_licence_reminders``
(idempotente) -- le branchement reel du crontab reste hors perimetre de
cette tache (`devops-cpanel`).

Usage (cron, une fois par jour par exemple) ::

    python manage.py process_licence_reminders
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.licences.services import process_licence_reminders


class Command(BaseCommand):
    help = "Envoie les relances de licence a 30, 7 et 1 jour avant expiration au President du club (CDC 1.4)."

    def handle(self, *args, **options):
        result = process_licence_reminders()
        self.stdout.write(self.style.SUCCESS(f"Relances envoyees : {result['reminders_sent']}."))
