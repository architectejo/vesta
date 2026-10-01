"""Commande de gestion : rappel la veille d'une AG (CDC 4.17 ;
assemblees-page-ag.md §4.7).

Meme limite de perimetre que les autres commandes de rappel du projet
(``process_sponsor_reminders``, ``process_licence_reminders``) : fine
enveloppe autour de ``apps.assemblies.services.send_assembly_reminders``
(idempotente) -- le branchement reel du crontab reste hors perimetre de
cette tache (`devops-cpanel`).

Usage (cron, une fois par jour) ::

    python manage.py send_assembly_reminders
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.assemblies.services import send_assembly_reminders


class Command(BaseCommand):
    help = "Envoie le rappel la veille de chaque assemblee generale convoquee (CDC 4.17)."

    def handle(self, *args, **options):
        result = send_assembly_reminders()
        self.stdout.write(self.style.SUCCESS(f"Rappels envoyes : {result['reminders_sent']}."))
