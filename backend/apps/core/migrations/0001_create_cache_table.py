"""Cree la table du cache partage entre processus (CACHES["default"]).

Audit de securite du Lot 1 (ecart bloquant B1) : sous Passenger,
plusieurs processus applicatifs peuvent tourner simultanement, chacun
avec sa propre memoire -- un cache en memoire de processus donnerait a
chaque processus son propre compteur de limitation de requetes
(``apps.accounts.throttling``), bien en-dessous du taux reellement
configure. Pas de service permanent type Redis/Memcached disponible sur
cet hebergement (CLAUDE.md section 4) : ``settings.CACHES["default"]``
utilise donc ``django.core.cache.backends.db.DatabaseCache``, dont la
table est creee ici -- pas a la main via ``manage.py createcachetable``
-- pour qu'elle existe automatiquement apres un simple ``manage.py
migrate``, en developpement comme en production.

Reutilise directement la commande de gestion standard
``createcachetable`` (memes SQL generes, portables SQLite/MySQL/MariaDB
via ``field.db_type(connection=...)``), plutot que de reecrire le SQL
CREATE TABLE a la main : c'est le meme mecanisme que celui documente
par Django pour ce cas precis (« Using the cache table with multiple
databases » / migrations de donnees). Migration reversible (CLAUDE.md
section 1) : la migration inverse supprime la table.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management import call_command
from django.db import migrations


def _cache_table_name() -> str | None:
    """Nom de la table du cache par defaut, ou ``None`` si ce n'est pas un `DatabaseCache`.

    Defensif : si un environnement (ex. tache future, configuration
    exotique) remplace ``CACHES["default"]`` par un autre backend, cette
    migration ne doit rien faire plutot qu'echouer.
    """

    default_cache = settings.CACHES.get("default", {})
    if default_cache.get("BACKEND") != "django.core.cache.backends.db.DatabaseCache":
        return None
    return default_cache.get("LOCATION")


def create_cache_table(apps, schema_editor):
    table_name = _cache_table_name()
    if not table_name or schema_editor.connection.alias != "default":
        return
    call_command(
        "createcachetable",
        table_name,
        database=schema_editor.connection.alias,
        verbosity=0,
    )


def drop_cache_table(apps, schema_editor):
    table_name = _cache_table_name()
    if not table_name or schema_editor.connection.alias != "default":
        return
    quoted = schema_editor.connection.ops.quote_name(table_name)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {quoted}")


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
