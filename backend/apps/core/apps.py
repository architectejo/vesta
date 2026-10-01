from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuration de l'application "core".

    Cette app est volontairement vide au Lot 1, tache 1.0 (scaffolding).
    Les modeles, services et vues metier sont ajoutes par les taches
    suivantes du plan de lots (voir docs/lot0/plan-lots.md).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Socle commun"
