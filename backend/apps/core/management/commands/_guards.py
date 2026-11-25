"""Garde-fou commun aux commandes reservees au developpement.

Module prefixe par ``_`` : Django ne l'expose pas comme commande.
"""

from django.conf import settings
from django.core.management.base import CommandError


def refuse_outside_development(command_name: str) -> None:
    """Refuse l'execution hors developpement (audit de securite, M2).

    Deux conditions independantes, toutes deux bloquantes : ``DEBUG`` actif
    ET base de donnees non MySQL/MariaDB (la base de production). Ces
    commandes contournent l'authentification ou creent des donnees de
    simulation : elles ne doivent jamais toucher une base de production,
    meme si ``DEBUG`` etait active par erreur.
    """
    if not settings.DEBUG:
        raise CommandError(
            f"{command_name} est reserve au developpement : refuse car settings.DEBUG=False "
            "(CLAUDE.md : jamais de contournement d'authentification ni de simulation en production)."
        )
    engine = settings.DATABASES["default"]["ENGINE"].lower()
    # Liste blanche : tout moteur autre que SQLite est refuse (MySQL/MariaDB,
    # PostgreSQL, moteurs inconnus ou personnalises).
    if "sqlite" not in engine:
        raise CommandError(
            f"{command_name} est reserve au developpement : refuse car la base n'est pas SQLite "
            f"(moteur : {settings.DATABASES['default']['ENGINE']}). "
            "Utilisez la configuration de developpement (SQLite)."
        )
