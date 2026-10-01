"""Factories factory_boy de l'app clubs (tache 1.2)."""

from __future__ import annotations

import factory
from django.utils import timezone

from apps.accounts.tests.factories import SuperuserFactory, UserFactory
from apps.clubs.models import (
    Club,
    ClubSettings,
    ImportBatch,
    Membership,
    MembershipApplication,
    MembershipRole,
    PresidencyTransfer,
    Season,
)
from apps.core.tests.factories import TenantDjangoModelFactory


class ClubFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Club

    name = factory.Sequence(lambda n: f"Club de test {n}")
    slug = factory.Sequence(lambda n: f"club-test-{n}")
    city = "Kinshasa"
    country = "RD Congo"


class ClubSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClubSettings

    club = factory.SubFactory(ClubFactory)
    timezone = "Africa/Kinshasa"


class SeasonFactory(TenantDjangoModelFactory):
    class Meta:
        model = Season

    club = factory.SubFactory(ClubFactory)
    label = factory.Sequence(lambda n: f"20{20 + n}")
    start_date = factory.LazyFunction(lambda: timezone.now().date().replace(month=1, day=1))
    end_date = factory.LazyFunction(lambda: timezone.now().date().replace(month=12, day=31))
    created_by = factory.SubFactory(SuperuserFactory)


class MembershipFactory(TenantDjangoModelFactory):
    class Meta:
        model = Membership

    club = factory.SubFactory(ClubFactory)
    user = factory.SubFactory(UserFactory)
    status = Membership.Status.ACTIVE
    position = Membership.Position.MIDFIELDER
    joined_on = factory.LazyFunction(lambda: timezone.now().date())
    added_by = factory.SubFactory(SuperuserFactory)


class MembershipRoleFactory(TenantDjangoModelFactory):
    class Meta:
        model = MembershipRole

    membership = factory.SubFactory(MembershipFactory)
    club = factory.SelfAttribute("membership.club")
    role = MembershipRole.Role.PLAYER_RECRUITER
    appointed_by = factory.SubFactory(SuperuserFactory)
    appointed_at = factory.LazyFunction(timezone.now)


class MembershipApplicationFactory(TenantDjangoModelFactory):
    class Meta:
        model = MembershipApplication

    membership = factory.SubFactory(MembershipFactory)
    club = factory.SelfAttribute("membership.club")


class PresidencyTransferFactory(TenantDjangoModelFactory):
    class Meta:
        model = PresidencyTransfer

    from_membership = factory.SubFactory(MembershipFactory)
    club = factory.SelfAttribute("from_membership.club")
    to_membership = factory.SubFactory(
        MembershipFactory, club=factory.SelfAttribute("..from_membership.club")
    )
    method = PresidencyTransfer.Method.HANDOVER
    transferred_at = factory.LazyFunction(timezone.now)


class ImportBatchFactory(TenantDjangoModelFactory):
    class Meta:
        model = ImportBatch

    club = factory.SubFactory(ClubFactory)
    import_type = ImportBatch.ImportType.PLAYERS
    source_file = factory.django.FileField(filename="import.csv", data=b"email,prenom,nom\n")
    imported_by = factory.SubFactory(SuperuserFactory)
    imported_at = factory.LazyFunction(timezone.now)
