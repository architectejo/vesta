"""Commande cron : depenses non justifiees (CDC 4.5.2, 4.17 ; tache 2.3).

Passe « Non justifiee » toute depense liberee dont le delai de
justification est depasse (date du jour dans le fuseau du club) et
alerte le Tresorier, l'adjoint et le President (alerte rouge), via
``apps.treasury.services.run_unjustified_expenses`` (idempotente : une
depense deja « Non justifiee » n'est ni retraitee ni realertee).

Le **blocage** des liberations ne depend pas de cette commande : il est
evalue a la volee par ``can_release_expense``. Aucune entree de journal
d'activite (pas d'acteur reel, meme convention que les commandes de
licences -- point ouvert) ; la transition est tracee par
``Expense.unjustified_at``.

Usage (cron, une fois par jour) ::

    python manage.py mark_unjustified_expenses
    python manage.py mark_unjustified_expenses --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.tenant import active_club
from apps.treasury.management.commands._cron import (
    EXIT_ERROR,
    add_common_arguments,
    club_label,
    dry_run_prefix,
    selected_clubs,
)
from apps.treasury.services import TreasuryError, run_unjustified_expenses


class Command(BaseCommand):
    help = (
        "Passe « Non justifiée » les dépenses libérées dont le délai de justification "
        "est dépassé et alerte le Trésorier, l'adjoint et le Président (CDC 4.5.2)."
    )

    def add_arguments(self, parser):
        add_common_arguments(parser)

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        prefix = dry_run_prefix(dry_run)
        clubs = selected_clubs(options["club_ids"])

        total = errors = 0
        for club in clubs:
            try:
                with active_club(club):
                    changed = run_unjustified_expenses(club, dry_run=dry_run)
            except TreasuryError as exc:
                errors += 1
                self.stderr.write(f"{prefix}{club_label(club)} : échec du traitement — {exc}")
                continue
            if changed:
                total += len(changed)
                self.stdout.write(
                    f"{prefix}{club_label(club)} : {len(changed)} dépense(s) passée(s) « Non justifiée »."
                )

        summary = f"{prefix}Dépenses passées « Non justifiée » : {total} ; clubs en erreur : {errors}."
        if errors:
            raise CommandError(summary, returncode=EXIT_ERROR)
        self.stdout.write(self.style.SUCCESS(summary))
