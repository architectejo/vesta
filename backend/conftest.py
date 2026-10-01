"""Configuration pytest partagee (racine `backend/`).

Redirige `MEDIA_ROOT` vers un dossier temporaire pour toute la duree de
chaque test : les modeles de la tache 1.2 utilisent des champs `Image`
et `File` (ex. `User.photo`, `ImportBatch.source_file`) qui ecrivent
reellement sur le stockage configure quand un fichier leur est
assigne. Sans cette fixture, les tests laisseraient des fichiers dans
`backend/media/` (jamais souhaite : CLAUDE.md interdit tout fichier
inutile, et aucune donnee de test ne doit persister dans le depot).

Meme principe pour `PRIVATE_MEDIA_ROOT` (``apps.core.storage.private_storage``,
tache B10) : sans cette seconde fixture, les fichiers prives (fiches
d'adhesion, fichiers d'import CSV) ecrits par les tests persisteraient
dans `backend/private_media/`.
"""

import pytest


@pytest.fixture(autouse=True)
def _media_root_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture(autouse=True)
def _private_media_root_tmp(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = str(tmp_path / "private")


@pytest.fixture(autouse=True)
def _fast_password_hasher(settings):
    # Observation de test-engineer (revue 1.4t) : la suite complete est tres
    # ralentie par le hasher de mot de passe de production (PBKDF2, iterations
    # elevees) applique a chaque `User` cree par une factory. Ce reglage ne
    # touche que le processus pytest (jamais `config.settings.dev`/`prod`) :
    # aucun impact sur le hachage reel en developpement ou en production.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def _ledger_hmac_test_key(settings):
    # Cle de chainage du grand livre financier (CDC 5.3, tache 1.4b) : en
    # production elle vient uniquement des variables d'environnement
    # `LEDGER_HMAC_KEYS`/`LEDGER_HMAC_ACTIVE_KEY_ID` (CLAUDE.md regle n12),
    # jamais du code. Ici, cle factice propre au processus pytest, pour que
    # toute app (clubs, tresorerie...) puisse sceller un paiement dans ses
    # tests sans dependre du fichier `.env` local du developpeur.
    settings.LEDGER_HMAC_KEYS = {"test-v1": "cle-factice-de-test-uniquement-" + "0" * 40}
    settings.LEDGER_HMAC_ACTIVE_KEY_ID = "test-v1"
