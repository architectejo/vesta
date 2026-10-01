"""Package racine de configuration du projet Vesta.

Le pilote MySQL de production est choisi ici plutot que dans
config/settings/prod.py afin d'etre applique avant tout import du
backend Django MySQL, quel que soit le point d'entree (manage.py,
wsgi.py, passenger_wsgi.py).

Choix par defaut (a confirmer par `devops-cpanel` au Lot 5, voir
backend/README.md) : PyMySQL, pilote pur Python, pour eviter la
compilation native de mysqlclient sur les postes de developpement
(en particulier Windows) qui n'ont pas besoin de MySQL en local
(SQLite suffit en developpement). PyMySQL n'est utilise qu'en
production : ce shim est sans effet si le paquet n'est pas installe.
"""

try:  # pragma: no cover - selection de pilote, pas de logique metier
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:
    pass
