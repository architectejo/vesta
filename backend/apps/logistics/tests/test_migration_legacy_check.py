import importlib

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.logistics.models import InventoryLine

mig = importlib.import_module("apps.logistics.migrations.0002_drop_legacy_inventoryline_gap_check")
LEGACY = mig.LEGACY_NAME


def _names():
    with connection.cursor() as c:
        return set(connection.introspection.get_constraints(c, InventoryLine._meta.db_table))


def _add_legacy():
    """Reproduit l'ancien schéma (SQLite, table vide) : recrée la table avec l'ancien CHECK."""
    table = InventoryLine._meta.db_table
    with connection.cursor() as c:
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=%s", [table])
        create = c.fetchone()[0]
        c.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=%s AND sql IS NOT NULL", [table])
        indexes = [r[0] for r in c.fetchall()]
        legacy = f', CONSTRAINT "{LEGACY}" CHECK (("discrepancy" = 0 OR NOT ("discrepancy_reason" = {chr(39)}{chr(39)})))'
        c.execute(f'DROP TABLE "{table}"')
        c.execute(create[:-1] + legacy + ")")
        for sql in indexes:
            c.execute(sql)
        c.execute("PRAGMA foreign_keys=ON")


@pytest.mark.skipif(connection.vendor != "sqlite", reason="reproduction du schéma legacy propre à SQLite")
@pytest.mark.django_db(transaction=True)
def test_drops_legacy_check_on_existing_db_and_noop_on_fresh_db():
    from django.apps import apps as global_apps

    assert LEGACY not in _names()
    with connection.schema_editor() as editor:  # base neuve : sans effet
        mig.drop_legacy_check(global_apps, editor)
    assert LEGACY not in _names()

    _add_legacy()
    assert LEGACY in _names()
    with connection.schema_editor() as editor:  # base existante : contrainte retirée
        mig.drop_legacy_check(global_apps, editor)
    names = _names()
    assert LEGACY not in names
    assert "inventoryline_physical_gte_0" in names


@pytest.mark.django_db(transaction=True)
def test_migration_roundtrip():
    # Revenir a 0001 deroule aussi logistics 0003+ et les migrations dependantes
    # des autres apps : on reapplique toutes les feuilles du graphe (finally)
    # pour que la base de test reste complete pour les tests suivants.
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([("logistics", "0001_initial")])
        executor = MigrationExecutor(connection)
        executor.migrate([("logistics", "0002_drop_legacy_inventoryline_gap_check")])
        assert LEGACY not in _names()
    finally:
        MigrationExecutor(connection).migrate(leaves)
