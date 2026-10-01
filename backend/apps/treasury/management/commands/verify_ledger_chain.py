"""Commande cron : verification quotidienne de la chaine financiere
(CDC 5.3, 5.5, 6.5 ; tache 2.3).

Pour chaque club, recalcule la chaine (``verify_chain``). Chaine saine :
rien n'est modifie. Rupture : gel des ecritures financieres du club et
alerte aux Superusers (une seule fois par gel), via
``apps.treasury.services.run_ledger_verification``. Aucun joueur n'est
penalise : le gel ne modifie ni montant du, ni paiement, ni statut.

Cle de chainage indisponible : verification impossible, signalee en
erreur, **sans gel** (incident de configuration).

Code de sortie : 0 si toutes les chaines sont saines ; 2 si au moins une
rupture est constatee (y compris sur un club deja gele) ; 1 si une
verification n'a pas pu etre menee. La sortie d'erreur d'une tache cron
cPanel est envoyee par email a l'adresse configuree dans cPanel.

Usage (cron, une fois par jour) ::

    python manage.py verify_ledger_chain
    python manage.py verify_ledger_chain --club 4 --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.tenant import active_club
from apps.treasury.management.commands._cron import (
    EXIT_CHAIN_BROKEN,
    EXIT_ERROR,
    add_common_arguments,
    club_label,
    dry_run_prefix,
    selected_clubs,
)
from apps.treasury.services import TreasuryError, run_ledger_verification


class Command(BaseCommand):
    help = (
        "Vérifie la chaîne des transactions financières de chaque club ; en cas de "
        "rupture, gèle les écritures du club et alerte les Superusers (CDC 5.3)."
    )

    def add_arguments(self, parser):
        add_common_arguments(parser)

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        prefix = dry_run_prefix(dry_run)
        clubs = selected_clubs(options["club_ids"])

        healthy = broken = errors = 0
        for club in clubs:
            label = club_label(club)
            try:
                with active_club(club):
                    outcome = run_ledger_verification(club, dry_run=dry_run)
            except TreasuryError as exc:
                errors += 1
                self.stderr.write(f"{prefix}{label} : vérification impossible — {exc}")
                continue

            result = outcome.result
            if outcome.status == "ok":
                healthy += 1
                self.stdout.write(f"{prefix}{label} : chaîne intègre ({result.checked_count} transaction(s)).")
            elif outcome.status == "error":
                errors += 1
                self.stderr.write(
                    f"{prefix}{label} : vérification impossible — {result.details} "
                    "Aucun gel appliqué ; vérifiez la configuration des clés."
                )
            else:
                broken += 1
                if outcome.newly_frozen:
                    action = (
                        f"écritures financières gelées, {outcome.alerts_sent} Superuser(s) alerté(s)"
                        if not dry_run
                        else f"le club serait gelé et {outcome.alerts_sent} Superuser(s) alerté(s)"
                    )
                else:
                    action = "club déjà gelé, aucune nouvelle alerte"
                self.stderr.write(
                    f"{prefix}{label} : RUPTURE DE CHAÎNE — {result.details} ({action}). "
                    "Aucun joueur n'est pénalisé."
                )
                if outcome.newly_frozen and outcome.alerts_sent == 0:
                    self.stderr.write(f"{prefix}{label} : aucun Superuser actif à alerter.")

        summary = f"{prefix}Chaînes intègres : {healthy} ; ruptures : {broken} ; vérifications impossibles : {errors}."
        if broken:
            raise CommandError(summary, returncode=EXIT_CHAIN_BROKEN)
        if errors:
            raise CommandError(summary, returncode=EXIT_ERROR)
        self.stdout.write(self.style.SUCCESS(summary))
