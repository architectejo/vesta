"""Garde-fou commun aux commandes reservees au developpement.

Module prefixe par ``_`` : Django ne l'expose pas comme commande.
"""

from django.conf import settings
from django.core.management.base import CommandError

# Parametre de settings EXPLICITE (jamais lu depuis une variable
# d'environnement) qui autorise ces commandes sur un moteur autre que SQLite.
# Il n'est pose a ``True`` que dans ``config/settings/test_mysql.py`` (base de
# test MySQL/MariaDB jetable, CLAUDE.md §9) ; absent partout ailleurs, donc
# ``False`` par defaut, notamment dans ``prod.py``. Il ne leve JAMAIS la
# condition ``DEBUG`` : en production (``DEBUG=False``) le refus reste total.
ALLOW_NON_SQLITE_SETTING = "VESTA_DEV_COMMANDS_ALLOW_NON_SQLITE"


def refuse_outside_development(command_name: str) -> None:
    """Refuse l'execution hors developpement (audit de securite, M2).

    Deux conditions independantes, toutes deux bloquantes :

    1. ``DEBUG`` actif -- toujours exige, sans exception ;
    2. base SQLite (la base de developpement), SAUF si le settings
       ``VESTA_DEV_COMMANDS_ALLOW_NON_SQLITE`` vaut explicitement ``True``
       (seul ``config/settings/test_mysql.py`` le pose, pour rejouer la suite
       complete sur MySQL/MariaDB avant chaque fin de lot, CLAUDE.md §9).

    Ces commandes contournent l'authentification ou creent des donnees de
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
    # PostgreSQL, moteurs inconnus ou personnalises), sauf autorisation
    # explicite (``is True`` : une chaine « True » mal saisie ne suffit pas).
    if "sqlite" not in engine and getattr(settings, ALLOW_NON_SQLITE_SETTING, False) is not True:
        raise CommandError(
            f"{command_name} est reserve au developpement : refuse car la base n'est pas SQLite "
            f"(moteur : {settings.DATABASES['default']['ENGINE']}). "
            "Utilisez la configuration de developpement (SQLite)."
        )
