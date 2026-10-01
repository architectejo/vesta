"""Invariant 1 (CLAUDE.md regle n2 ; schema-treasury.md I1) : aucun solde stocke."""

from __future__ import annotations

from django.apps import apps as django_apps

FORBIDDEN_FIELD_NAMES = {"balance", "solde", "in_good_standing", "is_in_good_standing", "good_standing"}


def test_aucun_champ_de_solde_n_existe_dans_aucun_modele():
    for model in django_apps.get_models():
        names = {field.name for field in model._meta.get_fields()}
        assert not names & FORBIDDEN_FIELD_NAMES, f"{model.__name__} stocke un solde : {names & FORBIDDEN_FIELD_NAMES}"
