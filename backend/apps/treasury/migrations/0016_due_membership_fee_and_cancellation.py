"""Frais d'adhésion = une somme à payer (décision du client du 17/11/2026 ;
CDC 4.3, 4.4.2 ; 10.3 n° 100).

- ``Due.source`` : nouvelle valeur ``membership`` (montant dû unique des
  frais d'adhésion, échéance à la date d'entrée) ;
- ``DueCancellation`` : écriture d'annulation d'un montant dû (adhésion
  annulée), append-only — un montant dû n'est jamais supprimé.

Migration de schéma uniquement, sans reprise de données (la reprise des
adhésions existantes passe par la commande ``rebalance_membership_fee_dues``,
en simulation par défaut). Réversible : le retour arrière supprime la table
``DueCancellation`` (vide tant que la fonctionnalité n'a pas servi) et
restreint les choix de ``Due.source`` (aucune contrainte en base).
"""

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clubs", "0013_accentuate_position_label"),
        ("treasury", "0015_paymentreversal_multiple_requests"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="due",
            name="source",
            field=models.CharField(
                choices=[
                    ("scheduler", "Planificateur"),
                    ("arrival", "Arrivée"),
                    ("assignment", "Rattachement"),
                    ("import", "Import"),
                    ("membership", "Adhésion"),
                ],
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="DueCancellation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.TextField()),
                ("cancelled_at", models.DateTimeField()),
                (
                    "cancelled_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "club",
                    models.ForeignKey(
                        help_text="Isolation multi-tenant (CLAUDE.md regle n8).",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="treasury_due_cancellations",
                        to="clubs.club",
                    ),
                ),
                (
                    "due",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cancellation",
                        to="treasury.due",
                    ),
                ),
            ],
            options={
                "verbose_name": "Annulation de montant dû",
                "verbose_name_plural": "Annulations de montants dus",
                "abstract": False,
                "base_manager_name": "all_objects",
                "default_manager_name": "all_objects",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("reason", ""), _negated=True), name="duecancellation_reason_required"
                    )
                ],
            },
            managers=[
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
    ]
