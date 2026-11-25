#!/usr/bin/env python
"""Utilitaire en ligne de commande de Django pour les tâches d'administration."""
import os
import sys


def _settings_module_from_env_file(env_path):
    """Lit `DJANGO_SETTINGS_MODULE` dans backend/.env s'il y figure.

    Sur le serveur, `.env` contient `DJANGO_SETTINGS_MODULE=config.settings.prod` :
    `migrate`, `collectstatic` ou toute commande lancee en SSH/cron sans variable
    d'environnement n'atterrit donc jamais en SQLite/DEBUG (audit M2).
    """
    try:
        with open(env_path, encoding="utf-8") as handle:
            for line in handle:
                key, sep, value = line.strip().partition("=")
                if sep and key.strip() == "DJANGO_SETTINGS_MODULE":
                    return value.strip().strip("\"'") or None
    except OSError:
        return None
    return None


def main():
    """Exécute les tâches d'administration."""
    # Par défaut on démarre en configuration de développement (SQLite).
    # La configuration de production est sélectionnée explicitement via
    # la variable d'environnement DJANGO_SETTINGS_MODULE=config.settings.prod
    # (voir backend/passenger_wsgi.py et devops-cpanel au Lot 5).
    # Ordre : variable d'environnement > backend/.env > developpement.
    if not os.environ.get('DJANGO_SETTINGS_MODULE'):
        from_file = _settings_module_from_env_file(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        )
        os.environ['DJANGO_SETTINGS_MODULE'] = from_file or 'config.settings.dev'
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Impossible d'importer Django. Vérifiez qu'il est installé et "
            "disponible dans votre variable d'environnement PYTHONPATH. "
            "Avez-vous oublié d'activer un environnement virtuel ?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
