"""Configuration de developpement.

Base de donnees : SQLite (fichier local), autorise en developpement
par decision du 25/09/2026 (CLAUDE.md section 3) pour la rapidite des
cycles locaux.

ATTENTION (a lire avant d'ecrire du code qui touche a la base) : SQLite
n'a pas le meme comportement que MySQL/MariaDB sur plusieurs points.
Voir backend/README.md pour le detail complet ; en resume :

- `select_for_update()` est un no-op silencieux sous SQLite (aucune
  erreur levee, mais aucun verrou reel pris) : aucun test de
  concurrence sur des ecritures simultanees ne peut etre considere
  comme valide sur la seule base de ce moteur. Ces tests doivent etre
  rejoues sur MySQL/MariaDB avant chaque fin de lot (CLAUDE.md section 9).
- SQLite compare les chaines de caracteres selon la locale C par
  defaut (comparaisons sensibles a la casse pour `=`/`LIKE` sur du
  texte non-ASCII, alors que MySQL/MariaDB est le plus souvent
  insensible a la casse selon le collation configure) : ne jamais
  supposer une casse particuliere lors d'une recherche/unicite sur un
  champ texte (ex. email) sans normaliser explicitement (ex. stocker
  et comparer en minuscules).
- `JSONField` est nativement supporte par SQLite >= 3.9 et par
  MySQL >= 5.7.8 / MariaDB >= 10.2.7 : verifier la version reelle de
  MySQL/MariaDB de l'hebergement cPanel avant d'utiliser ce type de
  champ en production (sinon Django leve une erreur au demarrage).
"""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"]
)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Notifications (CLAUDE.md section 2) : l'envoi email est toujours fait
# par une commande cron, jamais dans une requete. En developpement, les
# emails sont simplement affiches dans la console.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# CORS (CDC 7.6) : origine du serveur de developpement Vite par defaut,
# uniquement en developpement local -- toujours surchageable par
# `CORS_ALLOWED_ORIGINS` en variable d'environnement (jamais ecrit en
# dur pour la production, voir config.settings.prod/base.py).
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)
