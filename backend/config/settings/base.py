"""Settings communs a tous les environnements.

Ce module n'est jamais utilise directement comme DJANGO_SETTINGS_MODULE :
il est importe par `config.settings.dev` ou `config.settings.prod`, qui
completent/surchargent ce qui doit differer entre developpement et
production (base de donnees, DEBUG, emails, securite HTTP).

Aucun secret n'est ecrit ici : toute valeur sensible vient d'une
variable d'environnement (voir backend/.env.example). CLAUDE.md
section 2, regle 12.
"""

from datetime import timedelta
from pathlib import Path

import environ

# BASE_DIR = dossier backend/ (racine du projet Django, la ou vit manage.py).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# En developpement, les variables sont lues depuis backend/.env (non
# commite, cf. .env.example). En production, `devops-cpanel` injecte les
# variables d'environnement reelles (Passenger) ; le fichier .env est
# alors optionnel mais lu s'il existe, sans jamais ecraser une variable
# deja presente dans l'environnement du processus.
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY")

# Surchage obligatoire par chaque environnement (dev.py force True,
# prod.py force False). Valeur sure par defaut si jamais un module
# oublie de la definir explicitement.
DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

# Nombre de proxys de confiance entre le client et ce processus Django
# (LiteSpeed/Passenger en production, CDC 5.1 ; audit de securite du Lot
# 1, ecart bloquant B1). Par defaut 0 : n'accorder AUCUNE confiance a
# l'en-tete `X-Forwarded-For` (choisi librement par le client qui
# l'envoie) -- seule `REMOTE_ADDR` (l'adresse vue directement par ce
# processus) est utilisee, pour la limitation de requetes
# (`REST_FRAMEWORK["NUM_PROXIES"]` ci-dessous) comme pour l'IP
# journalisee (`apps.core.middleware.RequestContextMiddleware._client_ip`).
# Le nombre reel de proxys derriere LiteSpeed/Passenger en production
# reste a confirmer par `devops-cpanel` (tache 1.SEC-A, ecart M8) : ce
# n'est pas a backend-dev de deviner cette valeur, seulement de rendre
# le comportement sur par defaut et configurable par variable
# d'environnement.
#
# Revue independante de test-engineer (ecart residuel de B1, confirme par
# `apps.core.tests.test_num_proxies_misconfiguration`) : une valeur
# NEGATIVE de cette variable d'environnement (erreur de saisie) rendrait
# `REST_FRAMEWORK["NUM_PROXIES"]` negatif lui aussi. `_client_ip`
# ci-dessous traite deja tout nombre `<= 0` comme "aucun proxy de
# confiance", mais `SimpleRateThrottle.get_ident` de DRF (code tiers, non
# modifie ici) ne s'en protege pas : avec `NUM_PROXIES=-1`, son expression
# interne lit le DEUXIEME element de `X-Forwarded-For` -- choisi librement
# par le client, pas une IP de proxy valide -- ce qui rendrait a nouveau
# `LoginRateThrottle`/`PasswordResetRateThrottle` contournables. On borne
# donc cette valeur a `>= 0` ici, au plus pres de la lecture de la
# variable d'environnement : choix du correctif SILENCIEUX (`max(0, ...)`)
# plutot que `ImproperlyConfigured`, parce que 0 est deja la valeur la
# plus restrictive et la plus sure (aucune confiance a `X-Forwarded-For`)
# -- ce n'est donc PAS une degradation silencieuse d'un comportement de
# securite (CLAUDE.md section 2), au contraire : une valeur negative est
# une erreur de configuration qui n'a aucun sens metier (un nombre de
# proxys ne peut pas etre negatif), et la corriger vers le defaut sur
# plutot que de faire echouer tout le processus Django au demarrage
# (`ImproperlyConfigured` au niveau module aurait mis l'API entierement
# hors service pour une simple faute de frappe de variable d'environnement
# -- disproportionne face a un ecart qui reste sans consequence une fois
# borne). Defense en profondeur complementaire, au cas ou
# `REST_FRAMEWORK["NUM_PROXIES"]` deviendrait negatif par une autre voie
# que cette variable d'environnement : voir
# `apps.accounts.throttling.HardenedIdentThrottle`, qui applique le meme
# bornage directement dans `get_ident` avant chaque requete.
TRUSTED_PROXY_COUNT = max(0, env.int("TRUSTED_PROXY_COUNT", default=0))

# Cle(s) de chainage du grand livre financier (CDC 5.3 : « La cle de calcul
# est conservee hors de la base de donnees » ; CLAUDE.md regle n12 ;
# schema-treasury.md §6.4). Format : `LEDGER_HMAC_KEYS=v1=<secret>,v2=<secret>`
# (identifiant court -> secret d'au moins 32 caracteres, de preference
# hexadecimal pour eviter `=` et `,`), et `LEDGER_HMAC_ACTIVE_KEY_ID=v2` pour
# la cle utilisee par les nouveaux scellements. Une ancienne cle doit rester
# presente tant que des transactions scellees avec elle existent (la
# verification de la chaine en a besoin). Aucune valeur par defaut : sans
# cle, toute ecriture financiere est refusee avec un message clair
# (`apps.treasury.services.LedgerKeyError`), le reste de l'API fonctionne.
LEDGER_HMAC_KEYS = env.dict("LEDGER_HMAC_KEYS", default={})
LEDGER_HMAC_ACTIVE_KEY_ID = env("LEDGER_HMAC_ACTIVE_KEY_ID", default="")


DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    # Necessaire pour SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] ci-dessous.
    "rest_framework_simplejwt.token_blacklist",
]

# Apps metier Vesta (CLAUDE.md section 5). Toutes vides au Lot 1 / tache
# 1.0 (scaffolding) : aucun modele, aucune vue, aucune route.
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.clubs",
    "apps.licences",
    "apps.treasury",
    "apps.sport",
    "apps.medical",
    "apps.logistics",
    "apps.mercato",
    "apps.assemblies",
    "apps.social",
    "apps.notifications",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# CORS restreint a l'origine du frontend (CDC 7.6 ; CLAUDE.md regle n12) :
# jamais de nom de domaine en dur, toujours depuis la variable
# d'environnement. Voir `apps.core.middleware.RestrictedCorsMiddleware`
# (implementation maison : `django-cors-headers` n'a pas pu etre
# installe hors ligne pour cette tache -- point ouvert signale au compte
# rendu de la tache 1.3).
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RestrictedCorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # En dernier (le plus proche de la vue) : positionne l'IP/le
    # user-agent juste avant que Django n'appelle la vue, et nettoie le
    # contexte (y compris le club actif positionne par l'authentification
    # DRF, qui s'execute a l'interieur de la vue) juste apres son retour,
    # quelle que soit l'issue -- avant tout autre middleware de la liste
    # (CLAUDE.md regles n8/n9 ; CDC 5.1).
    "apps.core.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de donnees : definie uniquement par dev.py (SQLite) ou prod.py
# (MySQL/MariaDB). CLAUDE.md interdit SQLite en production et impose de
# ne jamais dependre d'un comportement propre a SQLite (voir
# backend/README.md pour le detail des ecarts connus).
DATABASES = {}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Interface et messages en francais clair (CLAUDE.md section 2, regle 20).
LANGUAGE_CODE = "fr-fr"

# Dates stockees en UTC, affichees dans le fuseau du club cote interface
# (CLAUDE.md section 7). Le fuseau du club sera applique explicitement
# dans les services metier (ex. verrouillage des seances le jour meme).
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Stockage des fichiers uploades (photos, logos, documents). Emplacement
# **public** (Image : logos, photos, marque blanche -- CDC 3.5), servi
# directement par le serveur web.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Emplacement **prive** (justificatifs, fiches d'adhesion, fichiers
# d'import CSV, documents medicaux -- CDC 6.7, 7.6 ; CLAUDE.md section 2
# regle 10 ; audit de conformite du Lot 1, ecart bloquant B10). Jamais
# servi directement par le serveur web : lu uniquement par l'API, via
# une vue authentifiee qui revalide le club et le role avant de streamer
# le contenu (voir `apps.core.storage.private_storage`). Aucun `MEDIA_URL`
# equivalent ici, volontairement : ce dossier n'est jamais expose par une
# URL publique.
#
# En production (cPanel/LiteSpeed, CDC 8.2), `devops-cpanel` doit faire
# pointer cette variable vers un dossier reellement hors de `public_html`
# (variable d'environnement `PRIVATE_MEDIA_ROOT`, chemin absolu). En
# developpement, un simple dossier separe de `MEDIA_ROOT` suffit (decision
# du 25/09/2026, meme principe que SQLite : rapidite des cycles locaux).
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", default=str(BASE_DIR / "private_media")))

# Cache partage entre processus (audit de securite du Lot 1, ecart
# bloquant B1) : sous Passenger, plusieurs processus applicatifs peuvent
# tourner simultanement, chacun avec sa propre memoire -- un cache en
# memoire de processus (`LocMemCache`, defaut Django) donnerait donc a
# chaque processus son propre compteur de limitation de requetes, tres
# en-dessous du taux reellement configure. Pas de service permanent type
# Redis/Memcached disponible sur cet hebergement (CLAUDE.md section 4 :
# « pas de processus permanent »)  : le cache applicatif (limitation de
# requetes notamment) passe donc par la base de donnees elle-meme
# (`DatabaseCache`), partagee par construction entre tous les processus.
# La table necessaire est creee par une migration de donnees
# (`apps/core/migrations/0001_create_cache_table.py`), pas par
# `manage.py createcachetable` a la main : elle existe donc
# automatiquement apres un simple `manage.py migrate`, en developpement
# comme en production.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "vesta_cache",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Modele utilisateur personnalise (tache 1.2) : l'email est l'identifiant
# de connexion, aucun nom d'utilisateur distinct (CDC 4.1). Doit etre
# defini avant toute migration (voir backend/README.md).
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    # `TenantJWTAuthentication` (tache 1.3) : authentification JWT
    # standard de SimpleJWT, augmentee de la resolution du club actif
    # depuis l'adhesion en cours reelle de l'utilisateur (CLAUDE.md
    # regle n9) -- jamais un `tenant_id` fige dans le jeton.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.core.authentication.TenantJWTAuthentication",
    ),
    # Refus par defaut : chaque endpoint declare explicitement sa
    # permission selon la matrice 2.4 (CLAUDE.md section 7 ; matrice
    # complete par role hors perimetre de la tache 1.3, voir tache 1.5).
    # `HasCompletedPasswordSetup`/`HasAcceptedLatestTerms` (tache 1.3) :
    # tant que le mot de passe initial/temporaire n'est pas change, ou
    # que la derniere version des CGU n'est pas acceptee, aucun endpoint
    # ne repond -- sauf ceux qui excluent explicitement ces classes
    # (connexion, changement de mot de passe, deconnexion, CGU...).
    # `HasUsableLicence` (tache 1.8, CDC 1.4, 10.2 n19) : bloque tout acces
    # si la licence du club actif est suspendue/resiliee, ou toute
    # mutation si le club est passe en lecture seule (licence expiree
    # au-dela de la periode de grace) -- sans effet sur un Superuser
    # (jamais concerne, voir sa docstring).
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "apps.core.permissions.HasCompletedPasswordSetup",
        "apps.core.permissions.HasAcceptedLatestTerms",
        "apps.core.permissions.HasUsableLicence",
    ),
    "EXCEPTION_HANDLER": "apps.core.exceptions.vesta_exception_handler",
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    # CDC 7.6 : « Limitation du nombre de requetes sur la connexion et
    # les points sensibles. » Valeurs par defaut raisonnables (non
    # imposees par le cahier des charges, qui ne chiffre pas de seuil) :
    # a ajuster si l'usage reel du club pilote l'exige. `login_email` /
    # `password_reset_email` : defense complementaire par email vise
    # (``apps.accounts.throttling.BaseEmailKeyedThrottle``), pas par IP --
    # memes seuils que la defense par IP correspondante (audit de
    # securite du Lot 1, ecart bloquant B1).
    "DEFAULT_THROTTLE_RATES": {
        "login": "20/min",
        "login_email": "20/min",
        "password_reset": "5/min",
        "password_reset_email": "5/min",
        # Assistant de creation de club (tache 1.9, CDC 7.6) : point
        # d'acces public, avant toute authentification.
        # `club_creation_settings` (lecture seule) reste permissif ;
        # `club_creation` (creation effective d'un club, un compte et une
        # licence) est deliberement plus strict.
        "club_creation_settings": "60/min",
        "club_creation": "10/hour",
    },
    # CDC 5.1 ; audit de securite du Lot 1, ecart bloquant B1 : sans ce
    # reglage explicite, DRF fait entierement confiance a
    # `X-Forwarded-For` (choisi par le client) pour identifier qui
    # limiter -- un attaquant qui change cet en-tete a chaque requete
    # n'est alors jamais limite. Relie a `TRUSTED_PROXY_COUNT` ci-dessus
    # (defaut 0 : ignore `X-Forwarded-For`, n'utilise que l'adresse IP
    # reelle de la connexion).
    "NUM_PROXIES": TRUSTED_PROXY_COUNT,
}

# Duree des jetons imposee par le plan du Lot 1 (tache 1.3) : 15 min /
# 7 jours. Le club actif ne doit jamais etre fige dans le JWT (CLAUDE.md
# section 2, regle 9) : ceci sera applique par apps.accounts au Lot 1.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
