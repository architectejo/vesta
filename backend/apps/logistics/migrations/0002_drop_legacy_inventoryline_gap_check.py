"""Réalignement du schéma : supprime l'ancien CHECK ``inventoryline_reason_required_if_gap``.

La migration 0001 a été modifiée après avoir été appliquée sur certaines bases
de développement : celles-ci conservent un CHECK « écart -> cause obligatoire »
que le modèle n'a plus (règle de workflow, pas invariant de données).
Sur une base neuve la contrainte n'existe pas : l'opération est alors sans effet.
L'opération inverse est volontairement un no-op (le modèle ne porte plus cette contrainte).
"""

from django.db import migrations, models

LEGACY_NAME = "inventoryline_reason_required_if_gap"


def drop_legacy_check(apps, schema_editor):
    model = apps.get_model("logistics", "InventoryLine")
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
    if LEGACY_NAME not in constraints:
        return
    legacy = models.CheckConstraint(condition=models.Q(pk__isnull=False), name=LEGACY_NAME)
    # SQLite : reconstruction de la table à partir de l'état du modèle (sans l'ancien CHECK).
    schema_editor.remove_constraint(model, legacy)


class Migration(migrations.Migration):
    dependencies = [("logistics", "0001_initial")]

    operations = [migrations.RunPython(drop_legacy_check, migrations.RunPython.noop)]
