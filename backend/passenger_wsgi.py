"""Stub minimal Passenger (cPanel/LiteSpeed).

Ce fichier n'est qu'un point d'entree minimal pour prouver que la
structure du projet est compatible Passenger. La configuration
complete (chemin de l'interpreteur Python/virtualenv Passenger,
variables d'environnement reelles, restart.txt, logs) est du ressort
de `devops-cpanel` au Lot 5 (CLAUDE.md section 8).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

from config.wsgi import application  # noqa: E402,F401
