"""Base commune pour les factories factory_boy des modeles `TenantModel`.

`TenantModel.objects` (manager par defaut) est tenant-aware : il exige
un club actif dans le contexte courant (voir `apps.core.tenant`), ce qui
n'est pas souhaitable pendant la construction d'un jeu de donnees de
test (on cree souvent des objets de plusieurs clubs differents dans le
meme test, notamment pour les tests d'etancheite). Les factories des
modeles `TenantModel` heritent donc de `TenantDjangoModelFactory`, qui
utilise explicitement `all_objects` (non filtre) pour la creation --
exactement l'usage documente et attendu de ce manager d'echappement
(CLAUDE.md regle n8 : reserve aux usages explicitement multi-clubs).
"""

from __future__ import annotations

import factory


class TenantDjangoModelFactory(factory.django.DjangoModelFactory):
    class Meta:
        abstract = True

    @classmethod
    def _get_manager(cls, model_class):
        return model_class.all_objects
