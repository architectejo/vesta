#!/usr/bin/env python
"""Utilitaire en ligne de commande de Django pour les tâches d'administration."""
import os
import sys


def main():
    """Exécute les tâches d'administration."""
    # Par défaut on démarre en configuration de développement (SQLite).
    # La configuration de production est sélectionnée explicitement via
    # la variable d'environnement DJANGO_SETTINGS_MODULE=config.settings.prod
    # (voir backend/passenger_wsgi.py et devops-cpanel au Lot 5).
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
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
