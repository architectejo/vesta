"""Tests du stockage prive ``apps.core.storage.private_storage`` (CDC 6.7,
7.6 ; CLAUDE.md section 2 regle n10 ; ecart bloquant B10).

Un fichier prive ne doit jamais atterrir sous ``MEDIA_ROOT`` (dossier
potentiellement servi publiquement) et ne doit jamais avoir d'URL publique.

Note : ``backend/conftest.py`` place ``PRIVATE_MEDIA_ROOT`` dans un
SOUS-dossier de ``MEDIA_ROOT`` (``tmp_path / "private"``). Pour que
l'assertion « jamais sous MEDIA_ROOT » ait un sens, ces tests redefinissent
donc les deux racines comme deux dossiers FRERES via la fixture ``settings``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.storage import PrivateFileStorage, private_storage


@pytest.fixture
def sibling_roots(settings, tmp_path):
    public_root = tmp_path / "public_root"
    private_root = tmp_path / "private_root"
    public_root.mkdir()
    private_root.mkdir()
    settings.MEDIA_ROOT = str(public_root)
    settings.PRIVATE_MEDIA_ROOT = str(private_root)
    return public_root, private_root


class TestPrivateFileStorageLocation:
    def test_saved_file_lands_under_private_media_root(self, sibling_roots):
        _, private_root = sibling_roots

        name = private_storage.save("clubs/imports/secret.csv", ContentFile(b"email,prenom,nom\n"))

        stored = Path(private_storage.path(name)).resolve()
        assert private_root.resolve() in stored.parents
        assert stored.read_bytes() == b"email,prenom,nom\n"

    def test_saved_file_never_lands_under_media_root(self, sibling_roots):
        public_root, _ = sibling_roots

        name = private_storage.save("clubs/imports/secret.csv", ContentFile(b"donnees"))

        assert not any(public_root.rglob("*")), "aucun fichier prive ne doit apparaitre sous MEDIA_ROOT"
        assert not default_storage.exists(name)
        assert public_root.resolve() not in Path(private_storage.path(name)).resolve().parents

    def test_public_default_storage_stays_on_media_root(self, sibling_roots):
        """Contre-preuve : le stockage public (logo, photo) reste sous
        MEDIA_ROOT et n'ecrit jamais dans le dossier prive."""

        public_root, private_root = sibling_roots

        name = default_storage.save("clubs/logos/logo.png", ContentFile(b"png"))

        assert (public_root / name).exists()
        assert not any(private_root.rglob("*"))

    def test_changing_private_media_root_at_runtime_is_taken_into_account(self, settings, tmp_path):
        first_root = tmp_path / "first"
        second_root = tmp_path / "second"
        settings.PRIVATE_MEDIA_ROOT = str(first_root)
        first_name = private_storage.save("a/un.txt", ContentFile(b"1"))
        assert Path(private_storage.path(first_name)).resolve().is_relative_to(first_root.resolve())

        settings.PRIVATE_MEDIA_ROOT = str(second_root)
        second_name = private_storage.save("a/deux.txt", ContentFile(b"2"))

        assert Path(private_storage.path(second_name)).resolve().is_relative_to(second_root.resolve())
        assert (second_root / second_name).exists()
        assert not (first_root / second_name).exists()

    def test_storage_is_a_dedicated_private_instance(self):
        assert isinstance(private_storage, PrivateFileStorage)
        assert private_storage is not default_storage


class TestPrivateFileStorageUrl:
    def test_url_always_raises_value_error(self):
        with pytest.raises(ValueError):
            private_storage.url("clubs/imports/secret.csv")

    def test_url_raises_even_when_media_url_is_configured(self, settings):
        settings.MEDIA_URL = "/media/"

        with pytest.raises(ValueError):
            private_storage.url("clubs/imports/secret.csv")

    def test_url_raises_even_for_a_name_that_does_not_exist(self):
        with pytest.raises(ValueError):
            private_storage.url("n-existe-pas.csv")

    def test_error_message_is_explicit_and_never_contains_a_media_url(self, settings):
        settings.MEDIA_URL = "/media/"

        with pytest.raises(ValueError) as exc_info:
            private_storage.url("clubs/imports/secret.csv")

        assert "/media/" not in str(exc_info.value)
        assert "secret.csv" not in str(exc_info.value)


@pytest.mark.django_db
class TestPrivateFieldsUsePrivateStorage:
    """Les trois champs prives declares par B10 utilisent bien
    ``private_storage`` et leur ``.url`` est inutilisable."""

    def test_private_model_fields_declare_the_private_storage(self):
        from apps.clubs.models import ImportBatch, MembershipApplication

        assert MembershipApplication._meta.get_field("application_pdf_file").storage is private_storage
        assert ImportBatch._meta.get_field("source_file").storage is private_storage
        assert ImportBatch._meta.get_field("report_file").storage is private_storage

    def test_public_image_fields_do_not_use_the_private_storage(self):
        from apps.accounts.models import User
        from apps.clubs.models import Club

        assert Club._meta.get_field("logo").storage is not private_storage
        assert User._meta.get_field("photo").storage is not private_storage

    def test_import_batch_source_file_is_written_under_private_root_only(self, sibling_roots):
        from apps.clubs.tests.factories import ImportBatchFactory

        public_root, private_root = sibling_roots

        batch = ImportBatchFactory()

        assert Path(batch.source_file.path).resolve().is_relative_to(private_root.resolve())
        assert not any(public_root.rglob("*"))

    def test_import_batch_source_file_url_raises(self):
        from apps.clubs.tests.factories import ImportBatchFactory

        batch = ImportBatchFactory()

        with pytest.raises(ValueError):
            _ = batch.source_file.url
