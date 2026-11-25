"""Commande cron : dette constatée à l'échéance (CDC 4.17, 4.4.2).

Pour chaque club, constate les montants dus devenus dette (échéance du type
+ tolérance du club dépassées, joueur « En dette ») et prévient le joueur,
le Trésorier et l'adjoint (in-app), via
``apps.treasury.services.run_debt_due_notifications``.

**Idempotente** : une échéance déjà traitée ne l'est jamais une seconde fois
(constat unique par montant dû, garanti en base) ; la commande peut donc
tourner plusieurs fois par jour sans doublon. Chaque club est traité dans
son propre contexte de club ; l'échec d'un club n'empêche pas les autres.
Aucune donnée personnelle de joueur n'est écrite sur la sortie.

Usage (cron, une fois par jour, après ``generate_monthly_dues``) ::

    python manage.py notify_debt_due
    python manage.py notify_debt_due --club 3 --dry-run
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
from apps.treasury.services import TreasuryError, run_debt_due_notifications


class Command(BaseCommand):
    help = (
        "Constate les dettes nées à l'échéance (échéance + tolérance du club) et prévient "
        "le joueur, le Trésorier et l'adjoint (CDC 4.17)."
    )

    def add_arguments(self, parser):
        add_common_arguments(parser)

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        prefix = dry_run_prefix(dry_run)

        total = errors = 0
        for club in selected_clubs(options["club_ids"]):
            try:
                with active_club(club):
                    outcome = run_debt_due_notifications(club, dry_run=dry_run)
            except TreasuryError as exc:
                errors += 1
                self.stderr.write(f"{prefix}{club_label(club)} : échec du traitement — {exc}")
                continue
            if outcome.skipped:
                self.stdout.write(f"{prefix}{club_label(club)} : ignoré — {outcome.skipped_reason}")
                continue
            if outcome.notified_count:
                total += outcome.notified_count
                self.stdout.write(
                    f"{prefix}{club_label(club)} : {outcome.notified_count} dette(s) constatée(s), "
                    f"{outcome.notifications_sent} notification(s)."
                )

        summary = f"{prefix}{total} dette(s) constatée(s) ; clubs en erreur : {errors}."
        if errors:
            raise CommandError(summary, returncode=EXIT_ERROR)
        self.stdout.write(self.style.SUCCESS(summary))
