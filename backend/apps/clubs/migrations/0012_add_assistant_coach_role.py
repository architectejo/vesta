# Assistant du Coach (CDC 10.3 n179) : nouveau choix de role, aucune donnee migree.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clubs', '0011_add_secretary_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='membershiprole',
            name='role',
            field=models.CharField(choices=[('president', 'Président'), ('vice_president', 'Vice-président'), ('sports_director', 'Directeur sportif'), ('treasurer', 'Trésorier'), ('assistant_treasurer', 'Trésorier adjoint'), ('steward', 'Intendant'), ('secretary', 'Secrétaire'), ('coach', 'Coach'), ('assistant_coach', 'Assistant du Coach'), ('captain', 'Capitaine'), ('doctor', 'Médecin'), ('player_recruiter', 'Joueur autorisé à ajouter des joueurs')], max_length=20),
        ),
    ]
