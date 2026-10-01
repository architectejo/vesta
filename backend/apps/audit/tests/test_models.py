"""Tests du modele `AuditLog` : inalterabilite (tache 1.6, 1.6t).

Sources : CDC 5.3 (« Le journal fonctionne en ajout seul [...] aucune
interface [...] ne permet de modifier ou supprimer une entree ») ;
docs/lot0/schema-donnees.md §12.2.
"""

from __future__ import annotations

import pytest
from django.db import transaction

from apps.audit.models import AuditLog, AuditLogImmutableError
from apps.audit.tests.factories import AuditLogFactory


@pytest.mark.django_db
class TestAppendOnly:
    def test_modifier_une_instance_existante_echoue(self):
        """Reaffecter un champ puis rappeler `save()` doit echouer."""

        entry = AuditLogFactory()
        entry.action_type = "test.action.modifie"

        with pytest.raises(AuditLogImmutableError):
            entry.save()

    def test_supprimer_une_instance_existante_echoue(self):
        entry = AuditLogFactory()

        with pytest.raises(AuditLogImmutableError):
            entry.delete()

        assert AuditLog.objects.filter(pk=entry.pk).exists()

    def test_update_en_masse_sur_le_queryset_echoue(self):
        AuditLogFactory()

        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.all().update(action_type="modifie")

    def test_delete_en_masse_sur_le_queryset_echoue(self):
        entry = AuditLogFactory()

        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(pk=entry.pk).delete()

        assert AuditLog.objects.filter(pk=entry.pk).exists()

    def test_bulk_update_echoue(self):
        """`QuerySet.bulk_update()` : chemin distinct de `update()`/`save()`.

        Django construit une requete `CASE WHEN ... THEN ...` puis appelle
        en interne `queryset.filter(pk__in=...).update(...)` -- ce test
        verifie que ce chemin, lui aussi, est reellement bloque (pas
        seulement les deux ou trois chemins les plus evidents), CDC 5.3.
        """

        entry = AuditLogFactory()
        entry.action_type = "test.action.bulk_update"

        # `bulk_update()` s'execute dans son propre `transaction.atomic(
        # savepoint=False)` : sans notre propre savepoint explicite ici,
        # l'exception laisserait la transaction (celle du test) dans un
        # etat irrecuperable pour la suite du test (SQLite comme MySQL).
        with pytest.raises(AuditLogImmutableError):
            with transaction.atomic():
                AuditLog.objects.bulk_update([entry], ["action_type"])

        assert AuditLog.objects.get(pk=entry.pk).action_type != "test.action.bulk_update"

    def test_save_avec_update_fields_sur_instance_existante_echoue(self):
        """`save(update_fields=[...])` ne doit pas contourner le blocage sur `pk` existant."""

        entry = AuditLogFactory()
        entry.action_type = "test.action.update_fields"

        with pytest.raises(AuditLogImmutableError):
            entry.save(update_fields=["action_type"])

    def test_update_or_create_sur_entree_existante_echoue(self):
        """`update_or_create()` appelle `save()` sur l'instance trouvee si elle existe deja."""

        entry = AuditLogFactory()

        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.update_or_create(
                pk=entry.pk, defaults={"action_type": "test.action.update_or_create"}
            )

    def test_delete_en_masse_sur_queryset_filtre_par_club_echoue(self):
        """Meme via un filtre different (`club=...`), `delete()` en masse reste bloque."""

        entry = AuditLogFactory()

        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(club=entry.club).delete()

        assert AuditLog.objects.filter(pk=entry.pk).exists()

    def test_aucune_route_admin_django_nest_enregistree(self):
        """CDC 5.3 : aucune action d'edition/suppression accessible, y compris admin.

        Le modele n'est enregistre dans aucun `admin.py` de l'app audit
        (verifie ici par l'absence d'enregistrement dans le registre
        d'admin de Django).
        """

        from django.contrib import admin

        assert AuditLog not in admin.site._registry


@pytest.mark.django_db
def test_creation_simple_fonctionne():
    """La creation (l'ajout) elle-meme n'est pas bloquee, seule la modification l'est."""

    entry = AuditLogFactory()
    assert entry.pk is not None
    assert AuditLog.objects.filter(pk=entry.pk).exists()
