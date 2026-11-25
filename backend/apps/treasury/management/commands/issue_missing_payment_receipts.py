"""Commande cron : rattrapage des reçus de paiement (CDC 4.4.4).

Émet le reçu PDF de chaque paiement validé qui n'en a pas encore, via
``apps.treasury.services.issue_payment_receipt`` (idempotent : un paiement
qui a déjà son reçu n'est jamais retraité). Cas couverts :

- incident lors de la génération qui suit la validation (le paiement reste
  validé, le reçu manque) ;
- paiements de l'import historique CSV (CDC 4.4.8), dont les reçus ne sont
  pas produits pendant la requête d'import.

Les paiements annulés sans reçu sont ignorés (aucun reçu après coup).
Si le journal d'activité ne peut pas être écrit (règle 6), le reçu n'est
pas émis (fichier supprimé) : il est compté en échec et réessayé au
passage suivant.
Chaque club est traité dans son propre contexte de club ; un reçu en échec
n'empêche pas les suivants. Aucune donnée personnelle de joueur n'est
écrite sur la sortie.

Usage (cron, une fois par jour, ou à la main après un import) ::

    python manage.py issue_missing_payment_receipts
    python manage.py issue_missing_payment_receipts --club 3 --dry-run
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
from apps.treasury.services import TreasuryError, issue_payment_receipt, payments_missing_receipt


class Command(BaseCommand):
    help = "Émet le reçu PDF des paiements validés qui n'en ont pas encore (CDC 4.4.4)."

    def add_arguments(self, parser):
        add_common_arguments(parser)

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        prefix = dry_run_prefix(dry_run)

        issued = errors = 0
        for club in selected_clubs(options["club_ids"]):
            with active_club(club):
                pending = list(payments_missing_receipt(club))
                if dry_run:
                    # Aucun fichier écrit en simulation (un rollback ne
                    # supprimerait pas un PDF déjà posé sur le disque).
                    issued += len(pending)
                    continue
                for payment in pending:
                    try:
                        issue_payment_receipt(payment=payment)
                    except TreasuryError as exc:
                        errors += 1
                        self.stderr.write(
                            f"{club_label(club)} : reçu n° {payment.receipt_number} non émis — {exc}"
                        )
                        continue
                    except OSError as exc:
                        errors += 1
                        self.stderr.write(
                            f"{club_label(club)} : reçu n° {payment.receipt_number} non écrit sur le disque — {exc}"
                        )
                        continue
                    issued += 1

        summary = f"{prefix}{issued} reçu(s) émis ; échecs : {errors}."
        if errors:
            raise CommandError(summary, returncode=EXIT_ERROR)
        self.stdout.write(self.style.SUCCESS(summary))
