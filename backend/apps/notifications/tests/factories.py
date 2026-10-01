"""Factories factory_boy de l'app notifications (tache 1.7).

``Notification``/``NotificationPreference`` ne sont pas des
``TenantModel`` (voir leur docstring) : factories classiques
(``factory.django.DjangoModelFactory``), pas
``apps.core.tests.factories.TenantDjangoModelFactory``.
"""

from __future__ import annotations

import factory

from apps.accounts.tests.factories import UserFactory
from apps.notifications.models import Notification, NotificationPreference


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    recipient = factory.SubFactory(UserFactory)
    event_type = Notification.EventType.ROLE_APPOINTED_OR_REVOKED
    title = "Nomination ou révocation"
    body = "Vous avez été nommé Trésorier au club Club de test."


class NotificationPreferenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NotificationPreference

    user = factory.SubFactory(UserFactory)
    email_enabled = True
