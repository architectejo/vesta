"""Outils communs aux commandes cron de la logistique (tâche 4.3).

Même convention qu'``apps.treasury.management.commands._cron`` (CLAUDE.md
§4, CDC 6.5) : chaque club est traité dans son propre contexte explicite,
l'échec d'un club n'empêche pas le traitement des autres.
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
