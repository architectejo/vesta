from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Configuration de l'application "accounts"."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Comptes"

    def ready(self):
        # Branche les signaux de journalisation (tache 1.6, CLAUDE.md
        # regle n6). Import tardif, dans ready(), pour eviter tout import
        # circulaire au chargement des apps.
        from apps.accounts import signals  # noqa: F401
