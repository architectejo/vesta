"""Point d'entree Passenger (cPanel « Setup Python App », LiteSpeed).

- Les parametres de production sont TOUJOURS ceux de `config.settings.prod` :
  la variable est forcee ici (affectation, pas `setdefault`) pour qu'une
  variable d'environnement egaree ne puisse pas faire demarrer l'API avec
  les parametres de developpement (SQLite, DEBUG), audit de securite M2.
- Les secrets viennent des variables d'environnement de l'application
  (interface cPanel) ou, a defaut, de `backend/.env` (lu par
  `config.settings.base`, jamais ecrase une variable deja definie).
- Virtualenv : cPanel demarre normalement deja l'application dans le
  virtualenv cree par « Setup Python App ». Si ce n'est pas le cas, definir
  `VESTA_PYTHON` (chemin absolu de l'interpreteur du virtualenv, affiche par
  cPanel) : le processus se relance alors une fois avec cet interpreteur.
  Aucun chemin n'est ecrit en dur ici.
"""

import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))

_interpreter = os.environ.get("VESTA_PYTHON", "").strip()
if _interpreter and os.path.realpath(sys.executable) != os.path.realpath(_interpreter):
    if not os.path.isfile(_interpreter):
        raise RuntimeError("VESTA_PYTHON ne designe pas un interpreteur existant.")
    os.execl(_interpreter, _interpreter, *sys.argv)

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# ESSAI SUR CPANEL (demande du client, 16/10/2026) : SQLite et valeurs ecrites en
# clair dans config/settings/cpanel_test.py, qui reprend prod.py pour tout le
# reste. A REMETTRE A "config.settings.prod" (MySQL/MariaDB) apres la
# demonstration : CLAUDE.md section 3 interdit SQLite en production.
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.cpanel_test"

from config.wsgi import application  # noqa: E402,F401
