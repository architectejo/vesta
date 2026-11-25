"""Declaration explicite des permissions de l'export des donnees personnelles
(CLAUDE.md §7 ; audit m8). Comportement inchange : memes garde-fous que les
valeurs globales par defaut."""

from django.conf import settings
from django.utils.module_loading import import_string
from rest_framework.permissions import IsAuthenticated

from apps.accounts.views import MyPersonalDataExportView


def test_export_declares_permission_classes_equal_to_global_defaults():
    declared = MyPersonalDataExportView.__dict__["permission_classes"]
    defaults = [import_string(p) for p in settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]]
    assert list(declared) == defaults
    assert declared[0] is IsAuthenticated
