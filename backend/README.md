# Vesta — backend

API Django du projet Vesta. Voir `CLAUDE.md` (racine du depot) pour les
regles non negociables et `docs/cahier-des-charges.md` pour les regles
metier. Cette app est au stade **scaffolding** (Lot 1, tache 1.0) :
aucun modele, aucune vue, aucune regle metier n'est encore implemente.

## Demarrage local

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash) ; sous macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                # puis renseigner DJANGO_SECRET_KEY (voir commentaire dans le fichier)
python manage.py migrate
python manage.py runserver
pytest
```

> Note sur le nom du dossier de l'environnement virtuel : la section 6
> de `CLAUDE.md` illustre la commande avec `python -m venv .env`. Ce
> nom entre en collision avec le fichier `.env` (variables
> d'environnement, obligatoire ici puisque `DJANGO_SECRET_KEY` est lu
> depuis l'environnement — CLAUDE.md section 2, regle 12) : un
> dossier et un fichier ne peuvent pas partager le meme nom dans le
> meme repertoire. Ce README utilise donc `.venv` pour l'environnement
> virtuel, `.env` restant reserve au fichier de variables
> d'environnement. **Point ouvert, a confirmer avec l'equipe** : mettre
> a jour CLAUDE.md section 6 pour lever l'ambiguite.

`DJANGO_SETTINGS_MODULE` vaut `config.settings.dev` par defaut
(`manage.py`). La production utilise explicitement
`config.settings.prod` (voir `passenger_wsgi.py`, complete par
`devops-cpanel` au Lot 5).

## Base de donnees : SQLite (dev) vs MySQL/MariaDB (prod)

Decision du 25/09/2026 (CLAUDE.md section 3/4) : SQLite est autorise
en developpement pour la rapidite des cycles locaux ; MySQL/MariaDB
est obligatoire en production. **Rien dans le code applicatif ne doit
dependre d'un comportement propre a SQLite.** Ecarts connus, a garder
en tete a chaque tache :

1. **`select_for_update()` est un no-op silencieux sous SQLite.**
   Aucune erreur n'est levee, mais aucun verrou de ligne n'est reellement
   pose : deux ecritures concurrentes ne s'excluent pas mutuellement.
   Consequence : **aucun test de concurrence sur des ecritures
   simultanees (ex. validation de paiement, decompte de solde,
   suspension apres carton) ne peut etre considere comme valide sur la
   seule base de SQLite.** Ces tests doivent etre rejoues sur
   MySQL/MariaDB avant chaque fin de lot (CLAUDE.md section 9,
   `docs/lot0/plan-lots.md`).
2. **Casse des comparaisons de texte.** SQLite compare par defaut les
   chaines selon une collation sensible a la casse pour les caracteres
   non-ASCII (le comportement exact depend aussi de la collation
   choisie), alors que MySQL/MariaDB est le plus souvent insensible a
   la casse selon le collation par defaut (`utf8mb4_general_ci` /
   `utf8mb4_0900_ai_ci` selon la version). Ne jamais supposer une casse
   particuliere pour une recherche ou une contrainte d'unicite sur un
   champ texte (ex. email) : normaliser explicitement (stocker/comparer
   en minuscules) plutot que de compter sur le moteur.
3. **`JSONField`.** Nativement supporte par SQLite >= 3.9 et par
   MySQL >= 5.7.8 / MariaDB >= 10.2.7. A verifier explicitement contre
   la version reelle de MySQL/MariaDB fournie par l'hebergement cPanel
   avant tout usage en production (sinon Django refuse de demarrer/
   migrer).
4. **Isolation transactionnelle / autocommit.** Le comportement par
   defaut de Django (`ATOMIC_REQUESTS` non active ici) est le meme sur
   les deux moteurs au niveau Django, mais le niveau d'isolation par
   defaut du moteur differe (SQLite = serialisable de fait via son
   verrouillage fichier ; MySQL/MariaDB = `REPEATABLE READ` par
   defaut sous InnoDB). Ne pas ecrire de logique qui suppose un niveau
   d'isolation particulier sans le rendre explicite (ex. `select_for_update()`
   + transaction explicite quand un verrou reel est necessaire).

### Pilote MySQL retenu : PyMySQL (a confirmer par `devops-cpanel`)

`config/settings/prod.py` utilise `ENGINE = "django.db.backends.mysql"`.
Le pilote choisi par defaut est **PyMySQL** (pur Python, ne necessite
aucune compilation native), instancie via
`pymysql.install_as_MySQLdb()` dans `config/__init__.py` — ce choix
vise a garder `pip install -r requirements.txt` fonctionnel sans
outillage de compilation sur les postes de developpement (le dev
n'utilise de toute facon jamais MySQL, seulement SQLite). `mysqlclient`
reste une alternative plus performante si l'hebergement cPanel fournit
les bibliotheques natives necessaires ; ce choix technique n'est pas
tranche par le cahier des charges et est signale comme point ouvert
pour `devops-cpanel` au Lot 5.

## Point ouvert pour la tache 1.2 (`Membership`/`User`)

Ce scaffolding n'a **pas** defini `AUTH_USER_MODEL` (aucun modele
metier autorise a ce stade). La tache 1.2 devra definir le modele
`User` global dans `apps.accounts` et positionner
`AUTH_USER_MODEL = "accounts.User"` **avant** de creer ses migrations,
puis supprimer le `db.sqlite3` local (fichier gitignore, jamais
commite, aucune perte de donnees reelle possible a ce stade) avant de
relancer `python manage.py migrate` avec le nouveau modele utilisateur.

## Publier la première version des CGU

Sans CGU publiées, l'assistant « Créer votre club » refuse toute création. Tant que l'espace Superuser « Paramètres globaux » (CDC 4.18) n'existe pas :

```bash
python manage.py publish_terms_version --superuser-email <email du Superuser> --content-file cgu.txt
```

Le texte des CGU (UTF-8) est un contenu juridique **à fournir par le client** : la commande n'en embarque aucun. Option facultative : `--published-at 2026-10-01` (ISO 8601) ; `--content "..."` remplace `--content-file`. La commande affiche le numéro de version créé (ex. `2026-1`) et journalise la publication.

## Commandes utiles

```bash
pytest                     # tous les tests
pytest apps/core -x        # un module
python manage.py check     # verification de configuration Django
python manage.py migrate   # applique les migrations (SQLite en dev)
```
