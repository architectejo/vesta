"""Commande de gestion : transition automatique des licences expirees
(CDC 1.4 ; 10.2 n19 ; tache 1.8).

CLAUDE.md (section 4, contraintes d'hebergement cPanel/LiteSpeed) : pas de
processus permanent -- les taches periodiques sont des commandes de
gestion Django appelees par cron, jamais par un scheduler interne. Cette
commande est une fine enveloppe autour de
``apps.licences.services.process_licence_expirations`` (idempotente) : le
branchement reel du crontab (frequence, heure d'execution) reste hors
perimetre de cette tache -- `devops-cpanel` a la mise en production, meme
limite que ``process_sponsor_reminders`` (tache 1.4b).

Usage (cron, une fois par jour par exemple) ::

    python manage.py process_licence_expirations
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.licences.services import process_licence_expirations


class Command(BaseCommand):
    help = (
        "Fait passer EXPIREE toute licence active/en essai dont la periode de "
        "grace est depassee, et passe le club correspondant en lecture seule "
        "(CDC 1.4, 10.2 n19)."
    )

    def handle(self, *args, **options):
        result = process_licence_expirations()
        self.stdout.write(
            self.style.SUCCESS(
                f"Licences passees EXPIREE : {result['expired']} ; "
                f"clubs passes en lecture seule : {result['clubs_set_read_only']}."
            )
        )
