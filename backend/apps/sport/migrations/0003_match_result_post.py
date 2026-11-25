import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sport", "0002_session_team_a_formation_session_team_b_formation_and_more"),
        ("social", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="result_post",
            field=models.OneToOneField(
                blank=True,
                help_text="Publication du résultat sur le fil (une seule par match, CDC 4.8).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="social.post",
            ),
        ),
    ]
