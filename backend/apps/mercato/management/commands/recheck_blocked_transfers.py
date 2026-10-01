"""Commande cron : filet de sécurité pour le déblocage automatique des
transferts (10.2 n° 30 ; fiche d'écran mercato.md §5.1).

Le déblocage est normalement déclenché à chaque paiement validé
(``apps.mercato.services.recheck_transfers_for_membership``, hook exposé
pour ``finance-engine``) et à chaque relecture de l'interface (§5.1). Cette
commande balaie néanmoins périodiquement toutes les offres bloquées, en
filet de sécurité (le 4.14 §5.1 précise explicitement que la vérification
n'est « pas seulement » déclenchée par un cron périodique).

Usage (cron, par exemple toutes les heures) ::

    python manage.py recheck_blocked_transfers
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.mercato.services import recheck_all_blocked_transfers


class Command(BaseCommand):
    help = "Relit le solde des offres « Bloquée (dette) » et débloque automatiquement celles redevenues en ordre."

    def handle(self, *args, **options):
        completed = recheck_all_blocked_transfers(now=timezone.now())
        self.stdout.write(self.style.SUCCESS(f"Transferts débloqués automatiquement : {completed}."))
