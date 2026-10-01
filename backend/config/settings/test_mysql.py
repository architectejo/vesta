"""Configuration pour rejouer la suite de tests sur MySQL/MariaDB.

CLAUDE.md section 9 : « avant chaque fin de lot [...] la suite de tests
complete passe aussi sur MySQL/MariaDB, pas seulement sur SQLite ». Ce
module n'est jamais utilise en developpement ni en production (voir
`dev.py`/`prod.py`) : uniquement pour cette verification ponctuelle, via

    DJANGO_SETTINGS_MODULE=config.settings.test_mysql pytest

contre un serveur MySQL/MariaDB local (ex. conteneur Docker jetable),
jamais contre une base contenant de vraies donnees.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("TEST_MYSQL_DB_NAME", default="vesta_test"),
        "USER": env("TEST_MYSQL_DB_USER", default="root"),
        "PASSWORD": env("TEST_MYSQL_DB_PASSWORD", default="root"),
        "HOST": env("TEST_MYSQL_DB_HOST", default="127.0.0.1"),
        "PORT": env("TEST_MYSQL_DB_PORT", default="3307"),
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
