"""Correctif D-A4 (13/11/2026) : nouvelle demande d'annulation apres un refus.

``PaymentReversal.payment`` passe de OneToOne a ForeignKey (plusieurs
demandes par paiement, les refusees restent conservees). Unicite portable
(sans index partiel, non pris en charge par MySQL/MariaDB) : le champ derive
``open_for_payment`` vaut ``payment`` tant que la demande est en attente ou
approuvee, NULL une fois refusee, et il est unique.

Reversible : le retour arriere echoue volontairement (contrainte unique) si
un paiement porte deja plusieurs demandes ; aucune donnee n'est alors
supprimee (CDC 5.3).
"""

import django.db.models.deletion
from django.db import migrations, models


def fill_open_for_payment(apps, schema_editor):
    PaymentReversal = apps.get_model("treasury", "PaymentReversal")
    PaymentReversal._base_manager.exclude(status="rejected").update(open_for_payment_id=models.F("payment_id"))


class Migration(migrations.Migration):

    dependencies = [
        ("treasury", "0014_remove_cashsession_pin_verified_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentreversal",
            name="open_for_payment",
            field=models.OneToOneField(
                blank=True,
                editable=False,
                error_messages={
                    "unique": "Une demande d'annulation est déjà en attente ou approuvée pour ce paiement."
                },
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="treasury.payment",
            ),
        ),
        migrations.AlterField(
            model_name="paymentreversal",
            name="payment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reversals",
                related_query_name="reversal",
                to="treasury.payment",
            ),
        ),
        migrations.RunPython(fill_open_for_payment, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="paymentreversal",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("status", "rejected"), ("open_for_payment__isnull", True)),
                    models.Q(models.Q(("status", "rejected"), _negated=True), ("open_for_payment", models.F("payment"))),
                    _connector="OR",
                ),
                name="paymentreversal_open_for_payment_consistent",
                violation_error_message="Demande d'annulation incohérente avec son paiement.",
            ),
        ),
    ]
