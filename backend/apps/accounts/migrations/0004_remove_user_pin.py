"""Suppression des colonnes du code PIN de ``User`` (decision client du 13/11/2026).

Le PIN est retire du comportement depuis le 11/10/2026 (CLAUDE.md regle 7).
Cette migration supprime les colonnes ``pin_hash``, ``pin_failed_attempts`` et
``pin_locked_until``. Les hashes existants sont PERDUS VOLONTAIREMENT : aucune
migration de donnees, aucune sauvegarde des valeurs.

Reversible : le retour arriere recree les colonnes avec leurs valeurs par
defaut (chaine vide, 0, NULL) ; les anciens hashes ne sont pas restaures.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_alter_user_photo"),
    ]

    operations = [
        migrations.RemoveField(model_name="user", name="pin_hash"),
        migrations.RemoveField(model_name="user", name="pin_failed_attempts"),
        migrations.RemoveField(model_name="user", name="pin_locked_until"),
    ]
