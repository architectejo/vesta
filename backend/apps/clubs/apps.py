from django.apps import AppConfig


class ClubsConfig(AppConfig):
    """Configuration de l'application "clubs"."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.clubs"
    verbose_name = "Clubs"

    def ready(self):
        # Branche les signaux de journalisation (tache 1.6, CLAUDE.md
        # regle n6). Import tardif, dans ready(), pour eviter tout import
        # circulaire au chargement des apps.
        from apps.clubs import signals  # noqa: F401
