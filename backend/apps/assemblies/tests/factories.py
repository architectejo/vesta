"""Factories factory_boy de l'app assemblies (tache 4.5)."""

from __future__ import annotations

from datetime import time, timedelta

import factory
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory
from apps.assemblies.models import AgendaItem, Assembly, AssemblyAttendance, Decision
from apps.clubs.tests.factories import ClubFactory
from apps.core.tests.factories import TenantDjangoModelFactory


class AssemblyFactory(TenantDjangoModelFactory):
    class Meta:
        model = Assembly

    club = factory.SubFactory(ClubFactory)
    assembly_type = Assembly.AssemblyType.ORDINARY
    scheduled_date = factory.LazyFunction(lambda: (timezone.now() + timedelta(days=7)).date())
    scheduled_time = time(18, 0)
    location = "Terrain principal"
    created_by = factory.SubFactory(SuperuserFactory)


class AgendaItemFactory(TenantDjangoModelFactory):
    class Meta:
        model = AgendaItem

    club = factory.SelfAttribute("assembly.club")
    assembly = factory.SubFactory(AssemblyFactory)
    order = 1
    title = "Bilan de la saison"


class AssemblyAttendanceFactory(TenantDjangoModelFactory):
    class Meta:
        model = AssemblyAttendance

    club = factory.SelfAttribute("assembly.club")
    assembly = factory.SubFactory(AssemblyFactory)
    present = True


class DecisionFactory(TenantDjangoModelFactory):
    class Meta:
        model = Decision

    club = factory.SelfAttribute("assembly.club")
    assembly = factory.SubFactory(AssemblyFactory)
    agenda_item = factory.SubFactory(AgendaItemFactory, assembly=factory.SelfAttribute("..assembly"))
    outcome = "Adopte"
    recorded_by = factory.SubFactory(SuperuserFactory)
    recorded_at = factory.LazyFunction(timezone.now)
