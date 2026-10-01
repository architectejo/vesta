"""Commande cron : montants dus mensuels (CDC 4.4.2, 6.5 ; tache 2.3).

« Chaque premier du mois, une tache automatique cree le montant du du mois
pour chaque joueur actif, selon son type mensuel. » Enveloppe de
``apps.treasury.services.run_monthly_dues`` (voir ce service pour les
regles : fuseau du club, joueurs concernes, mois d'arrivee, clubs bloques).

- Sans ``--period`` : mois en cours **dans le fuseau de chaque club**.
  Idempotente : peut tourner chaque heure ou chaque jour ; seul le premier
  passage du mois local cree des lignes.
- ``--period AAAA-MM`` (repetable) : rattrapage d'un mois manque.
- Ne cree aucune dette : le passage en dette apres echeance + tolerance
  est calcule a la lecture (aucune commande « passage en dette »).
- Mois d'arrivee : mois entier du (proposition par defaut 10.2 n° 5, non
  tranchee par le client), echeance selon la regle normale.
- Aucune entree de journal d'activite : pas d'acteur reel (meme
  convention que ``process_licence_expirations``, point ouvert).

Usage ::

    python manage.py generate_monthly_dues
    python manage.py generate_monthly_dues --period 2026-03 --club 4
    python manage.py generate_monthly_dues --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.tenant import active_club
from apps.treasury.management.commands._cron import (
    EXIT_ERROR,
    add_common_arguments,
    club_label,
    dry_run_prefix,
    parse_period,
    selected_clubs,
)
from apps.treasury.services import TreasuryError, run_monthly_dues


class Command(BaseCommand):
    help = (
        "Crée les montants dus mensuels de chaque joueur actif, le 1er du mois "
        "dans le fuseau du club (CDC 4.4.2). Idempotente."
    )

    def add_arguments(self, parser):
        add_common_arguments(parser)
        parser.add_argument(
            "--period",
            dest="periods",
            action="append",
            default=None,
            metavar="AAAA-MM",
            help="Mois à (re)générer, pour rattraper un mois manqué (répétable). "
            "Par défaut : mois en cours dans le fuseau de chaque club.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        prefix = dry_run_prefix(dry_run)
        periods = [parse_period(value) for value in options["periods"] or []] or [None]
        clubs = selected_clubs(options["club_ids"])

        total_created = 0
        errors = 0
        for club in clubs:
            for period in periods:
                try:
                    with active_club(club):
                        run = run_monthly_dues(club, period=period, dry_run=dry_run)
                except TreasuryError as exc:
                    errors += 1
                    self.stderr.write(f"{prefix}{club_label(club)} : échec de la génération — {exc}")
                    continue
                month = f"{run.period:%m/%Y}" if run.period else "mois en cours"
                if run.skipped:
                    self.stdout.write(f"{prefix}{club_label(club)} — {month} : ignoré, {run.skipped_reason}")
                    continue
                total_created += run.created_count
                self.stdout.write(
                    f"{prefix}{club_label(club)} — {month} : {run.created_count} montant(s) dû(s) créé(s)."
                )
                if run.arrival_count:
                    self.stdout.write(
                        f"{prefix}{club_label(club)} — {month} : dont {run.arrival_count} montant(s) dû(s) de "
                        "mois d'arrivée (mois entier dû, proposition par défaut 10.2 n° 5)."
                    )

        summary = f"{prefix}Montants dus créés : {total_created} ; clubs en erreur : {errors}."
        if errors:
            raise CommandError(summary, returncode=EXIT_ERROR)
        self.stdout.write(self.style.SUCCESS(summary))
