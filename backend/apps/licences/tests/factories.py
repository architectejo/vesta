"""Factories factory_boy de l'app licences (taches 1.2, 1.8)."""

from __future__ import annotations

import datetime

import factory
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.tests.factories import ClubFactory
from apps.licences.models import Licence, LicenceEvent, SupportSession


class LicenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Licence

    club = factory.SubFactory(ClubFactory)
    status = Licence.Status.TRIAL
    start_date = factory.LazyFunction(datetime.date.today)
    end_date = factory.LazyFunction(lambda: datetime.date.today() + datetime.timedelta(days=30))
    created_by = factory.SubFactory(SuperuserFactory)


class LicenceEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LicenceEvent

    licence = factory.SubFactory(LicenceFactory)
    event_type = LicenceEvent.EventType.CREATED
    event_date = factory.LazyFunction(timezone.now)
    actor = factory.SubFactory(SuperuserFactory)


class SupportSessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SupportSession

    club = factory.SubFactory(ClubFactory)
    superuser = factory.SubFactory(SuperuserFactory)
    reason = "Correction d'un paiement (test)."
    started_at = factory.LazyFunction(timezone.now)
