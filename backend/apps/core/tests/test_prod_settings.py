"""Garde-fous de `config.settings.prod` (audit de securite : B3, M1, M2).

`prod.py` est importe dans un module frais a chaque test, avec un
environnement controle ; `django.conf.settings` n'est jamais touche.
"""

import importlib
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

BACKEND_DIR = Path(__file__).resolve().parents[3]
VALID_SECRET_KEY = "k9Zr2vQx7LmT4pWb8NcY1dHs6JfGa3UeXo5RiVt0BnMq7ClPzKyD2wEhSgAu4Fj"


@pytest.fixture
def prod_env(monkeypatch, tmp_path):
    """Environnement de production valide, sans PRIVATE_MEDIA_ROOT."""
    monkeypatch.setenv("DJANGO_SECRET_KEY", VALID_SECRET_KEY)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://vesta.example.test")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "api.example.test")
    monkeypatch.setenv("DB_NAME", "x")
    monkeypatch.setenv("DB_USER", "x")
    monkeypatch.setenv("DB_PASSWORD", "x")
    monkeypatch.delenv("PRIVATE_MEDIA_ROOT", raising=False)
    monkeypatch.delenv("DJANGO_MEDIA_ROOT", raising=False)
    monkeypatch.setattr("environ.Env.read_env", classmethod(lambda cls, *a, **k: None), raising=False)
    return monkeypatch


def _import_prod():
    sys.modules.pop("config.settings.prod", None)
    try:
        return importlib.import_module("config.settings.prod")
    finally:
        sys.modules.pop("config.settings.prod", None)


def test_private_media_root_absent_refuse(prod_env):
    with pytest.raises(ImproperlyConfigured, match="PRIVATE_MEDIA_ROOT est obligatoire"):
        _import_prod()


def test_private_media_root_vide_refuse(prod_env):
    prod_env.setenv("PRIVATE_MEDIA_ROOT", "   ")
    with pytest.raises(ImproperlyConfigured, match="obligatoire"):
        _import_prod()


def test_private_media_root_relatif_refuse(prod_env):
    prod_env.setenv("PRIVATE_MEDIA_ROOT", "private_media")
    with pytest.raises(ImproperlyConfigured, match="absolu"):
        _import_prod()


@pytest.mark.parametrize("suffix", ["", "private_media", "a/b/c"])
def test_private_media_root_sous_base_dir_refuse(prod_env, suffix):
    prod_env.setenv("PRIVATE_MEDIA_ROOT", str(BACKEND_DIR / suffix))
    with pytest.raises(ImproperlyConfigured, match="BASE_DIR"):
        _import_prod()


def test_private_media_root_sous_media_root_refuse(prod_env, tmp_path):
    media = tmp_path / "public" / "media"
    prod_env.setenv("DJANGO_MEDIA_ROOT", str(media))
    prod_env.setenv("PRIVATE_MEDIA_ROOT", str(media / "prive"))
    with pytest.raises(ImproperlyConfigured, match="MEDIA_ROOT"):
        _import_prod()


def test_private_media_root_valide_accepte(prod_env, tmp_path):
    private = tmp_path / "vesta-private"
    prod_env.setenv("PRIVATE_MEDIA_ROOT", str(private))
    module = _import_prod()
    assert module.PRIVATE_MEDIA_ROOT == private.resolve()
    assert module.DEBUG is False
    assert module.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert module.SECURE_SSL_REDIRECT is True


@pytest.fixture
def prod_env_valid(prod_env, tmp_path):
    prod_env.setenv("PRIVATE_MEDIA_ROOT", str(tmp_path / "vesta-private"))
    return prod_env


@pytest.mark.parametrize("value", ["", "http://vesta.example.test", "https://*.example.test", "*",
                                   "https://ok.example.test,http://ko.example.test"])
def test_cors_invalide_refuse(prod_env_valid, value):
    prod_env_valid.setenv("CORS_ALLOWED_ORIGINS", value)
    with pytest.raises(ImproperlyConfigured, match="CORS_ALLOWED_ORIGINS"):
        _import_prod()


def test_cors_absent_refuse(prod_env_valid):
    prod_env_valid.delenv("CORS_ALLOWED_ORIGINS")
    with pytest.raises(ImproperlyConfigured, match="obligatoire"):
        _import_prod()


def test_cors_https_accepte(prod_env_valid):
    prod_env_valid.setenv("CORS_ALLOWED_ORIGINS", "https://a.example.test,https://b.example.test")
    assert _import_prod().CORS_ALLOWED_ORIGINS == ["https://a.example.test", "https://b.example.test"]


@pytest.mark.parametrize(
    "value",
    [
        "court",
        "x" * 49,
        "changeme" + "aZ3" * 20,
        "Change-Me-" + "qW7rT9yU" * 8,
        "django-insecure-" + "aB3dE5gH7jK9mN1pQ3sT5vX7zC9" * 2,
        "a" * 60,
    ],
)
def test_secret_key_faible_refusee(prod_env_valid, value):
    prod_env_valid.setenv("DJANGO_SECRET_KEY", value)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        _import_prod()


def test_secret_key_forte_acceptee(prod_env_valid):
    assert _import_prod().SECRET_KEY == VALID_SECRET_KEY


def test_manage_py_lit_le_module_de_settings_dans_env(tmp_path):
    sys.path.insert(0, str(BACKEND_DIR))
    try:
        import manage
    finally:
        sys.path.remove(str(BACKEND_DIR))
    env_file = tmp_path / ".env"
    env_file.write_text('# commentaire\nDJANGO_SETTINGS_MODULE="config.settings.prod"\n', encoding="utf-8")
    assert manage._settings_module_from_env_file(env_file) == "config.settings.prod"
    env_file.write_text("DJANGO_SECRET_KEY=x\n", encoding="utf-8")
    assert manage._settings_module_from_env_file(env_file) is None
    assert manage._settings_module_from_env_file(tmp_path / "absent") is None


def test_commandes_de_simulation_refusees_sur_mysql(settings):
    from django.core.management.base import CommandError

    from apps.core.management.commands._guards import refuse_outside_development

    settings.DEBUG = True
    refuse_outside_development("seed_simulation")  # SQLite + DEBUG : autorise
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.mysql"}}
    with pytest.raises(CommandError, match="pas SQLite"):
        refuse_outside_development("seed_simulation")
    for engine in ("django.db.backends.postgresql", "mysql.connector.django", "custom.engine"):
        settings.DATABASES = {"default": {"ENGINE": engine}}
        with pytest.raises(CommandError, match="pas SQLite"):
            refuse_outside_development("seed_simulation")
    settings.DEBUG = False
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3"}}
    with pytest.raises(CommandError, match="DEBUG=False"):
        refuse_outside_development("issue_e2e_session")
