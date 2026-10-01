from django.apps import AppConfig


class SportConfig(AppConfig):
    """Configuration de l'application "sport".

    Squelette vide au Lot 1 (tache 1.0). Modeles, services,
    verrouillage a minuit et suspensions automatiques construits aux
    taches 3.2-3.4 (Lot 3, voir docs/lot0/plan-lots.md) : voir
    apps.sport.models/services. Les vues/serializers/URLs restent a
    construire (tache 3.7 et suivantes).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sport"
    verbose_name = "Sportif"
