"""Suppression de ``CashSession.pin_verified_at`` et de sa contrainte (decision client du 13/11/2026).

La colonne etait dormante depuis le 11/10/2026 (elle reprenait ``opened_at``).
Les valeurs existantes disparaissent avec la colonne, volontairement.

Ordre : la contrainte ``cashsession_pin_verified_before_opening`` est supprimee
d'abord, puis le champ.

Reversible : pour que le retour arriere fonctionne sur une table non vide, la
colonne est d'abord rendue nullable, puis (au retour arriere) recreee nullable,
remplie avec ``opened_at`` (valide pour la contrainte pin_verified_at <=
opened_at), puis remise NOT NULL.
"""

from django.db import migrations, models


def _noop(apps, schema_editor):
    pass


def _fill_from_opened_at(apps, schema_editor):
    CashSession = apps.get_model("treasury", "CashSession")
    manager = getattr(CashSession, "_base_manager")
    manager.filter(pin_verified_at__isnull=True).update(pin_verified_at=models.F("opened_at"))


class Migration(migrations.Migration):
    dependencies = [
        ("treasury", "0013_payment_client_uuid_online_entry"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cashsession",
            name="pin_verified_at",
            field=models.DateTimeField(
                null=True, help_text="Vérification serveur du code PIN à l'ouverture."
            ),
        ),
        migrations.RunPython(_noop, _fill_from_opened_at),
        migrations.RemoveConstraint(
            model_name="cashsession",
            name="cashsession_pin_verified_before_opening",
        ),
        migrations.RemoveField(model_name="cashsession", name="pin_verified_at"),
    ]
