"""Commande cron : notification « Vos mesures sont disponibles » (tests de
performance, sport-statistiques-seance.md C7, question C-Q9 provisoire).

Une notification in-app par joueur et par séance, envoyée une heure après la
dernière mesure de la séance. Idempotente : peut être appelée toutes les 5 à
15 minutes sans jamais notifier deux fois le même joueur pour la même séance.
Aucune entrée de journal (pas d'acteur réel), comme les autres commandes cron
du module.

Usage ::

    python manage.py notify_performance_results
    python manage.py notify_performance_results --club 4
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.core.tenant import active_club
from apps.sport.management.commands._cron import add_common_arguments, club_label, selected_clubs
from apps.sport.performance import notify_performance_results


class Command(BaseCommand):
    help = "Notifie les joueurs mesurés, une heure après la dernière mesure de la séance. Idempotente."

    def add_arguments(self, parser):
        add_common_arguments(parser)

    def handle(self, *args, **options):
        total = 0
        for club in selected_clubs(options["club_ids"]):
            with active_club(club):
                sent = notify_performance_results(club=club)
            total += sent
            if sent:
                self.stdout.write(f"{club_label(club)} : {sent} notification(s) envoyée(s).")
        self.stdout.write(self.style.SUCCESS(f"Terminé : {total} notification(s) créée(s) au total."))
