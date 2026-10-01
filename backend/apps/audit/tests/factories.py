"""Factories factory_boy de l'app audit (tache 1.6).

`AuditLog` n'est pas un `TenantModel` (club facultatif, schema §1.2) :
cette factory utilise directement `AuditLog.objects` (pas de manager
d'echappement necessaire), mais passe par le service
`apps.audit.services.create_audit_log` plutot que par
`factory.django.DjangoModelFactory` classique, pour que chaque entree de
test passe par les memes garde-fous qu'en production (append-only des
la creation, garde-fou medical).
"""

from __future__ import annotations

import factory

from apps.accounts.tests.factories import UserFactory
from apps.audit.services import create_audit_log
from apps.clubs.tests.factories import ClubFactory


class AuditLogFactory(factory.Factory):
    class Meta:
        model = dict  # placeholder ; voir _create() ci-dessous.

    club = factory.SubFactory(ClubFactory)
    actor = factory.SubFactory(UserFactory)
    action_type = "test.action.created"
    object_type = "TestObject"
    object_id = factory.Sequence(lambda n: str(n + 1))
    before = None
    after = factory.LazyFunction(lambda: {"champ": "valeur"})

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return create_audit_log(**kwargs)
