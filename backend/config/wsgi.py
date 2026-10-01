"""Point d'entree WSGI du projet Vesta.

Utilise par tout serveur WSGI (Passenger via passenger_wsgi.py,
gunicorn en local si besoin, etc). Par defaut sur la configuration de
production : `manage.py runserver` utilise la configuration de
developpement independamment de ce module (voir manage.py).
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
