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

import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

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

# Fichiers publics servis par le serveur web (jamais par Django en
# production). STATIC_ROOT recoit `collectstatic` ; MEDIA_ROOT contient les
# images publiques (logos, photos). Les deux doivent etre exposes par le
# serveur web sous /static/ et /media/ (voir docs/guides/exploitation.md).
STATIC_ROOT = Path(env("DJANGO_STATIC_ROOT", default=str(BASE_DIR / "staticfiles")))
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", default=str(BASE_DIR / "media")))


def validate_private_media_root(raw_value, base_dir, media_root):
    """Valide `PRIVATE_MEDIA_ROOT` et renvoie le chemin resolu.

    Audit de securite, ecart bloquant B3 : justificatifs, actes de
    naissance, CSV d'import et documents medicaux ne doivent JAMAIS etre
    servables par le serveur web. On exige donc un chemin absolu explicite
    (aucune valeur par defaut) et on refuse tout chemin situe dans le dossier
    de l'application (`BASE_DIR`, qui peut se trouver sous la racine web) ou
    dans `MEDIA_ROOT` (public). Echec explicite au demarrage.
    """
    if not raw_value or not str(raw_value).strip():
        raise ImproperlyConfigured(
            "PRIVATE_MEDIA_ROOT est obligatoire en production : indiquez un "
            "chemin absolu situe HORS de public_html et du dossier de l'application."
        )
    path = Path(str(raw_value).strip())
    if not path.is_absolute():
        raise ImproperlyConfigured(
            "PRIVATE_MEDIA_ROOT doit etre un chemin absolu (recu : %r)." % str(raw_value)
        )
    resolved = path.resolve()
    for label, forbidden in (("le dossier de l'application (BASE_DIR)", base_dir), ("MEDIA_ROOT", media_root)):
        forbidden_resolved = Path(forbidden).resolve()
        if resolved == forbidden_resolved or forbidden_resolved in resolved.parents:
            raise ImproperlyConfigured(
                "PRIVATE_MEDIA_ROOT ne doit pas se trouver dans %s : les fichiers "
                "prives pourraient etre servis par le serveur web (%s)." % (label, resolved)
            )
    return resolved


# Obligatoire, sans valeur par defaut (ecart B3).
PRIVATE_MEDIA_ROOT = validate_private_media_root(
    env("PRIVATE_MEDIA_ROOT", default=""), BASE_DIR, MEDIA_ROOT
)

_WEAK_SECRET_PATTERN = re.compile(r"change[-_ ]?me|django-insecure|replace[-_ ]?me|your[-_ ]?secret", re.IGNORECASE)
SECRET_KEY_MIN_LENGTH = 50


def validate_cors_allowed_origins(origins):
    """Refuse au demarrage une liste d'origines CORS vide, non-https ou avec
    joker (audit de securite, m7). Renvoie la liste nettoyee."""
    cleaned = [str(origin).strip() for origin in (origins or []) if str(origin).strip()]
    if not cleaned:
        raise ImproperlyConfigured(
            "CORS_ALLOWED_ORIGINS est obligatoire en production : listez les origines "
            "https de l'interface (ex. https://vesta.example.org)."
        )
    for origin in cleaned:
        if "*" in origin:
            raise ImproperlyConfigured(
                "CORS_ALLOWED_ORIGINS ne doit contenir aucun joker (recu : %r)." % origin
            )
        if not origin.lower().startswith("https://") or len(origin) <= len("https://"):
            raise ImproperlyConfigured(
                "CORS_ALLOWED_ORIGINS n'accepte que des origines https (recu : %r)." % origin
            )
    return cleaned


def validate_secret_key(value):
    """Refuse une DJANGO_SECRET_KEY trop courte (< 50 caracteres), de type
    « changeme » ou quasi constante (audit de securite, m7)."""
    key = str(value or "")
    if len(key) < SECRET_KEY_MIN_LENGTH:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY est trop courte pour la production (minimum %d caracteres)."
            % SECRET_KEY_MIN_LENGTH
        )
    if _WEAK_SECRET_PATTERN.search(key) or len(set(key)) < 10:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY est faible (valeur par defaut ou trop peu variee) : "
            "generez une cle aleatoire dediee a la production."
        )
    return key


# Relus depuis l'environnement (et non depuis base.py) : la validation porte
# sur la valeur reellement fournie au demarrage.
CORS_ALLOWED_ORIGINS = validate_cors_allowed_origins(env.list("CORS_ALLOWED_ORIGINS", default=[]))
SECRET_KEY = validate_secret_key(env("DJANGO_SECRET_KEY"))

# Securite HTTP (le site est servi en HTTPS derriere cPanel/LiteSpeed).
# Ecart M1 : la redirection HTTPS est d'abord faite par le .htaccess ; cote
# Django, `SECURE_PROXY_SSL_HEADER` evite la boucle de redirection si le
# serveur termine TLS puis transmet en HTTP local. Si l'en-tete
# X-Forwarded-Proto est absent, Django retombe sur le schema reel de la
# requete (comportement sur). Si une boucle est constatee malgre tout,
# mettre DJANGO_SECURE_SSL_REDIRECT=False (le .htaccess garde le HTTPS force).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Limite globale de la taille d'un corps de requete hors fichiers (Django) ;
# la limite reseau reelle est posee par le serveur web (voir .htaccess).
DATA_UPLOAD_MAX_MEMORY_SIZE = 2_621_440

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
