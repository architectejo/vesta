"""Commande cron : lève automatiquement les suspensions purgées (CDC 4.9 ; tâche 3.4).

Enveloppe de ``apps.sport.services.advance_suspensions_for_elapsed_matches`` :
incrémente ``matches_served`` de chaque suspension active du club pour
chaque match écoulé depuis son déclenchement, et lève automatiquement la
suspension une fois le nombre de matchs prévu purgé (« la suspension est
levée automatiquement après le nombre de matchs du club prévu »).

Idempotente (``Suspension.credited_events``) : peut être rejouée chaque
jour sans compter un même match deux fois. Aucune entrée de journal
n'est écrite (pas d'acteur réel), même convention que
``apps.treasury.management.commands.generate_monthly_dues``/
``process_licence_expirations``.

Usage ::

    python manage.py advance_suspensions
    python manage.py advance_suspensions --club 4
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.core.tenant import active_club
from apps.sport.management.commands._cron import add_common_arguments, club_label, selected_clubs
from apps.sport.services import advance_suspensions_for_elapsed_matches


class Command(BaseCommand):
    help = (
        "Incrémente les suspensions actives à chaque match écoulé et les lève "
        "automatiquement une fois purgées (CDC 4.9). Idempotente."
    )

    def add_arguments(self, parser):
        add_common_arguments(parser)

    def handle(self, *args, **options):
        clubs = selected_clubs(options["club_ids"])
        total_credited = 0
        for club in clubs:
            with active_club(club):
                credited = advance_suspensions_for_elapsed_matches(club=club)
            total_credited += credited
            if credited:
                self.stdout.write(f"{club_label(club)} : {credited} match(s) crédité(s) sur les suspensions actives.")

        self.stdout.write(self.style.SUCCESS(f"Terminé : {total_credited} crédit(s) de match appliqué(s) au total."))
