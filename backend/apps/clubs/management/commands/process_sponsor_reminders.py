"""Commande de gestion : rappels et alertes de parrainage (CDC 4.3, cas
limite « le parrain ne repond pas » -- tache 1.4b).

CLAUDE.md (section 4, contraintes d'hebergement cPanel/LiteSpeed) : pas de
processus permanent -- les taches periodiques sont des commandes de
gestion Django appelees par cron, jamais par un scheduler interne. Cette
commande est une fine enveloppe autour de
``apps.clubs.services.process_sponsor_reminders_and_alerts`` (idempotente) :
le branchement reel du crontab (fréquence, heure d'exécution) reste hors
perimetre de cette tache -- `devops-cpanel` a la mise en production, meme
limite que la verification quotidienne de la chaine financiere laissee
ouverte par `finance-engine`.

Usage (cron, une fois par jour par exemple) ::

    python manage.py process_sponsor_reminders
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.clubs.services import process_sponsor_reminders_and_alerts


class Command(BaseCommand):
    help = (
        "Envoie le rappel a 3 jours et l'alerte au President a 7 jours pour "
        "les dossiers d'adhesion dont le parrain n'a pas encore repondu "
        "(CDC 4.3)."
    )

    def handle(self, *args, **options):
        result = process_sponsor_reminders_and_alerts()
        self.stdout.write(
            self.style.SUCCESS(
                f"Rappels envoyes : {result['reminders_sent']} ; "
                f"alertes au President envoyees : {result['alerts_sent']}."
            )
        )
