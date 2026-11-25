"""Rééquilibrage des frais d'adhésion déjà payés (décision du client du
17/11/2026 ; CDC 4.3, 4.4.2 ; 10.3 n° 100).

Avant cette décision, le paiement des frais d'adhésion devenait un crédit
(aucun montant dû d'adhésion). Pour chaque adhésion du club dont les frais
ont été payés (net des annulations) sans montant dû d'adhésion, la commande
crée le montant dû manquant (tarif à la date d'entrée, échéance à la date
d'entrée) et recalcule la répartition, via
``apps.treasury.services.rebalance_membership_fee_dues``. Idempotente.

**Simulation par défaut** : rien n'est écrit sans ``--apply``. La sortie
liste les adhésions concernées (identifiants uniquement, aucune donnée
personnelle) avec leur solde avant/après : un joueur dont le crédit
d'adhésion masquait une mensualité impayée repasse « En dette ».

Usage ::

    python manage.py rebalance_membership_fee_dues --club 3            # simulation
    python manage.py rebalance_membership_fee_dues --club 3 --dry-run  # simulation
    python manage.py rebalance_membership_fee_dues --club 3 --apply    # écriture
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.core.tenant import active_club
from apps.treasury.management.commands._cron import club_label, dry_run_prefix, selected_clubs
from apps.treasury.services import TreasuryError, rebalance_membership_fee_dues


class Command(BaseCommand):
    help = (
        "Crée le montant dû d'adhésion manquant des adhésions dont les frais ont été payés "
        "en crédit (simulation par défaut)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--club",
            dest="club_ids",
            action="append",
            type=int,
            required=True,
            metavar="ID",
            help="Identifiant du club à traiter (obligatoire, répétable).",
        )
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulation (comportement par défaut) : aucune écriture.",
        )
        mode.add_argument(
            "--apply",
            action="store_true",
            help="Écrit réellement les montants dus manquants et recalcule la répartition.",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        prefix = dry_run_prefix(not apply)
        total = 0
        for club in selected_clubs(options["club_ids"]):
            with active_club(club):
                try:
                    lines = rebalance_membership_fee_dues(club, apply=apply)
                except TreasuryError as exc:
                    raise CommandError(f"{club_label(club)} : {exc}") from exc
            back_in_debt = [line for line in lines if line.balance_before >= 0 > line.balance_after]
            for line in lines:
                self.stdout.write(
                    f"{club_label(club)} : adhésion n° {line.membership_id} — dû de {line.amount} créé ; "
                    f"solde {line.balance_before} → {line.balance_after}"
                )
            self.stdout.write(
                f"{prefix}{club_label(club)} : {len(lines)} adhésion(s) rééquilibrée(s), "
                f"dont {len(back_in_debt)} repasse(nt) en dette."
            )
            total += len(lines)
        self.stdout.write(self.style.SUCCESS(f"{prefix}Terminé : {total} adhésion(s) au total."))
