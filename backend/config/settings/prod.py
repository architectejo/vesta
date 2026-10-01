"""Configuration de production.

Base de donnees : MySQL/MariaDB (CLAUDE.md section 3 : SQLite est
interdit en production). Toutes les valeurs sensibles viennent de
variables d'environnement (voir backend/.env.example) ; aucune valeur
reelle n'est ecrite ici.

La configuration Passenger/cPanel definitive (chemins, virtualenv,
cron, .htaccess, variables d'environnement reelles, sauvegardes) est
du ressort de `devops-cpanel` au Lot 5 : ce module se limite aux
settings Django necessaires pour tourner en production.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Obligatoire en production, aucune valeur par defaut : une deploiement
# sans DJANGO_ALLOWED_HOSTS defini doit echouer au demarrage plutot que
# d'accepter n'importe quel hote.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="3306"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "OPTIONS": {
            # utf8mb4 : necessaire pour couvrir tous les caracteres
            # (emoji du reseau social, noms avec caracteres etendus).
            "charset": "utf8mb4",
        },
    }
}

# Securite HTTP (le site est servi en HTTPS derriere cPanel/LiteSpeed).
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Notifications (CLAUDE.md section 2) : l'envoi email est toujours fait
# par une commande cron (jamais dans une requete). C'est la commande de
# gestion qui utilise ce backend SMTP pour l'envoi differe.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER)
