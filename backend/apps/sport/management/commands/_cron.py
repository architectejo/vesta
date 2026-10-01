"""Outils communs aux commandes cron de l'app sport (tache 3.4).

Module prefixe par ``_`` : Django ne l'expose pas comme commande. Memes
conventions que ``apps.treasury.management.commands._cron`` (CLAUDE.md
section 4, CDC 6.5 -- pas de processus permanent, tout traitement
periodique est une commande cron appelee par cron cPanel) : pas de
duplication du contenu, seulement de la structure, pour ne pas creer une
dependance inter-app fragile entre deux domaines distincts.
"""

from __future__ import annotations

from django.core.management.base import CommandError

from apps.clubs.models import Club

EXIT_ERROR = 1


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


def selected_clubs(club_ids) -> list:
    """Clubs à traiter, dans un ordre stable. Refuse un identifiant inconnu."""

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
