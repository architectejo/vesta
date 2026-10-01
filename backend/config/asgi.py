"""Point d'entree ASGI du projet Vesta.

Non utilise en production : l'hebergement cPanel/LiteSpeed (Passenger)
ne supporte pas de processus permanent ni les WebSockets (CLAUDE.md
section 4). Ce fichier est fourni par completude du scaffolding Django
standard mais n'est pas branche par `devops-cpanel`.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
