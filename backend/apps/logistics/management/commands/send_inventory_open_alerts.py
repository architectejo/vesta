"""Commande cron : alerte hebdomadaire « inventaire non clôturé » (CDC 4.13 ;
schema-donnees.md §17 ``inventory_open_alert`` ; fiche d'écran logistique.md §6.3).

N'écrit jamais sur ``Inventory`` (schema §17) : seule une ``Notification``
est créée, au plus une fois par semaine et par club, tant que l'inventaire
bloquant (§12 point ouvert n° 11 : son propre trimestre est terminé) reste
ouvert.

Usage (cron, une fois par semaine, ou plus souvent : la commande est
elle-même idempotente sur la fenêtre de 7 jours) ::

    python manage.py send_inventory_open_alerts
    python manage.py send_inventory_open_alerts --club 1
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.tenant import active_club
from apps.logistics import services
from apps.logistics.management.commands._cron import EXIT_ERROR, add_common_arguments, club_label, selected_clubs


class Command(BaseCommand):
    help = "Alerte hebdomadaire au Président tant que l'inventaire bloquant reste ouvert (CDC 4.13)."

    def add_arguments(self, parser):
        add_common_arguments(parser)

    def handle(self, *args, **options):
        clubs = selected_clubs(options["club_ids"])
        now = timezone.now()

        sent = errors = 0
        for club in clubs:
            try:
                with active_club(club):
                    sent += services.send_inventory_open_alerts(club=club, now=now)
            except services.LogisticsError as exc:
                errors += 1
                self.stderr.write(f"{club_label(club)} : échec du traitement — {exc}")
                continue

        summary = f"Alertes d'inventaire envoyées : {sent} ; clubs en erreur : {errors}."
        if errors:
            raise CommandError(summary, returncode=EXIT_ERROR)
        self.stdout.write(self.style.SUCCESS(summary))
