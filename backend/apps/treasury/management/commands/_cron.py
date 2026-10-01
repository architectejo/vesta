"""Outils communs aux commandes cron de la tresorerie (tache 2.3).

Module prefixe par ``_`` : Django ne l'expose pas comme commande.

Conventions (CLAUDE.md §4, CDC 6.5 -- pas de processus permanent, tout
traitement periodique est une commande cron) :

- fines enveloppes autour de ``apps.treasury.services`` (les regles
  metier restent dans les services), comme les commandes de licences ;
- boucle sur les clubs, **chacun traite dans son propre contexte de club
  explicite** (``apps.core.tenant.active_club``) : un service appele pour
  un club ne peut pas ecrire dans un autre (``TenantMismatchError``) ;
- l'echec d'un club n'empeche pas le traitement des autres ; il est
  signale sur la sortie d'erreur et rend un code de sortie non nul ;
- ``--dry-run`` : execution complete puis annulation, aucune ecriture ;
- ``--club ID`` (repetable) : limiter le traitement a certains clubs ;
- messages en francais clair (CLAUDE.md regle n20), sans donnee
  personnelle de joueur.

Codes de sortie : 0 = tout s'est bien passe ; 1 = au moins un club en
erreur ; 2 = rupture de chaine detectee (``verify_ledger_chain``).
"""

from __future__ import annotations

import datetime

from django.core.management.base import CommandError

from apps.clubs.models import Club

EXIT_ERROR = 1
EXIT_CHAIN_BROKEN = 2


def add_common_arguments(parser) -> None:
    parser.add_argument(
        "--club",
        dest="club_ids",
        action="append",
        type=int,
        default=None,
        metavar="ID",
        help="Identifiant du club à traiter (répétable). Par défaut : tous les clubs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulation : exécute le traitement puis l'annule, sans aucune écriture.",
    )


def selected_clubs(club_ids) -> list:
    """Clubs a traiter, dans un ordre stable. Refuse un identifiant inconnu."""

    queryset = Club.objects.order_by("pk")
    if club_ids:
        clubs = list(queryset.filter(pk__in=club_ids))
        missing = sorted(set(club_ids) - {club.pk for club in clubs})
        if missing:
            raise CommandError(
                f"Club introuvable : {', '.join(str(pk) for pk in missing)}.", returncode=EXIT_ERROR
            )
        return clubs
    return list(queryset)


def club_label(club) -> str:
    return f"Club {club.pk} « {club.name} »"


def parse_period(value: str) -> datetime.date:
    """Convertit ``AAAA-MM`` en premier jour du mois."""

    try:
        parsed = datetime.datetime.strptime(value.strip(), "%Y-%m")
    except (ValueError, AttributeError):
        raise CommandError(
            f"Période invalide « {value} » : utilisez le format AAAA-MM (par exemple 2026-03).",
            returncode=EXIT_ERROR,
        ) from None
    return datetime.date(parsed.year, parsed.month, 1)


def dry_run_prefix(dry_run: bool) -> str:
    return "[simulation] " if dry_run else ""
