"""Factories factory_boy de l'app sport (taches 3.2-3.4)."""

from __future__ import annotations

import datetime

import factory
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory
from apps.clubs.tests.factories import ClubFactory, SeasonFactory
from apps.core.tests.factories import TenantDjangoModelFactory
from apps.sport.models import Event, Match, Session


class EventFactory(TenantDjangoModelFactory):
    class Meta:
        model = Event

    club = factory.SubFactory(ClubFactory)
    kind = Event.Kind.SESSION
    event_date = factory.LazyFunction(lambda: timezone.now().date())
    season = factory.SubFactory(SeasonFactory, club=factory.SelfAttribute("..club"))
    created_by = factory.SubFactory(SuperuserFactory)


class SessionFactory(TenantDjangoModelFactory):
    class Meta:
        model = Session

    event = factory.SubFactory(EventFactory, kind=Event.Kind.SESSION)
    club = factory.SelfAttribute("event.club")
    gathering_time = datetime.time(7, 30)
    late_arrival_cutoff = datetime.time(8, 0)
    location = "Terrain municipal"
    team_a_color = "#0000FF"
    team_b_color = "#FF0000"


class MatchFactory(TenantDjangoModelFactory):
    class Meta:
        model = Match

    event = factory.SubFactory(EventFactory, kind=Event.Kind.MATCH)
    club = factory.SelfAttribute("event.club")
    opponent_name = factory.Sequence(lambda n: f"Adversaire {n}")
    match_type = Match.MatchType.FRIENDLY
    venue = Match.Venue.HOME
    kickoff_time = datetime.time(15, 0)
    location = "Stade municipal"
