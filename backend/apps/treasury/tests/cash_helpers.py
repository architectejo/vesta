"""Outils communs aux tests de l'enregistrement des paiements et de la
Caisse Terrain Express (tâche 2.4 ; CDC 4.4.3-4.4.5, 6.6, 10.2 n° 22).

Les types de cotisation passent par les services (tarif créé comme en
production) ; les dettes par un montant dû échu (`Due`), comme la
génération mensuelle : le solde reste toujours calculé par
`apps.treasury.services`.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership
from apps.clubs.tests.factories import MembershipFactory
from apps.treasury import services
from apps.treasury.models import ContributionType, Due
from apps.treasury.tests.conftest import PIN

TYPE_CREATED_AT = datetime.datetime(2025, 1, 5, 12, 0, tzinfo=datetime.timezone.utc)


def club_tz(ctx) -> ZoneInfo:
    return ZoneInfo(ctx.club.settings.timezone)


def club_today(ctx) -> datetime.date:
    return services.get_club_today(ctx.club)


def local_dt(ctx, day: datetime.date, hour: int, minute: int = 0) -> datetime.datetime:
    """Instant ``day hour:minute`` dans le fuseau du club (aware)."""

    return datetime.datetime.combine(day, datetime.time(hour, minute), tzinfo=club_tz(ctx))


def monthly_type(ctx, *, name="Mensuelle 10", amount="10", scope=ContributionType.Scope.ALL):
    """Type mensuel obligatoire, tarif effectif depuis janvier 2025."""

    return services.create_contribution_type(
        club=ctx.club,
        created_by=ctx.president.user,
        name=name,
        nature=ContributionType.Nature.MANDATORY,
        periodicity=ContributionType.Periodicity.MONTHLY,
        amount=amount,
        scope=scope,
        now=TYPE_CREATED_AT,
    )


def free_type(ctx, *, name="Vestiaire"):
    return services.create_contribution_type(
        club=ctx.club,
        created_by=ctx.president.user,
        name=name,
        nature=ContributionType.Nature.FREE,
        periodicity=ContributionType.Periodicity.MONTHLY,
        amount="2",
        now=TYPE_CREATED_AT,
    )


def named_member(ctx, *, first_name, last_name, jersey_number=None, status=Membership.Status.ACTIVE, joined_on=None):
    user = UserFactory(first_name=first_name, last_name=last_name, pin_hash=make_password(PIN))
    return MembershipFactory(
        club=ctx.club,
        user=user,
        status=status,
        jersey_number=jersey_number,
        joined_on=joined_on or datetime.date(2025, 1, 1),
    )


def put_in_debt(ctx, membership, ctype, *, amount="10", months_ago=2):
    """Montant dû échu depuis ``months_ago`` mois : le joueur doit ``amount``."""

    today = club_today(ctx)
    period = datetime.date(today.year, today.month, 1)
    for _ in range(months_ago):
        period = (period - datetime.timedelta(days=1)).replace(day=1)
    Due(
        club=ctx.club,
        membership=membership,
        contribution_type=ctype,
        period=period,
        amount=Decimal(amount),
        due_date=period.replace(day=10),
        source=Due.Source.SCHEDULER,
        created_at=timezone.now(),
    ).save()


def open_session(ctx, member=None, *, now=None):
    session, _ = services.open_cash_session(
        club=ctx.club, user=(member or ctx.treasurer).user, pin=PIN, now=now or timezone.now()
    )
    return session


def cash_pay(ctx, session, membership, *, amount="10", recorded_at=None, client_uuid=None, now=None, user=None, **extra):
    """Encaissement de caisse ; ``user`` : adhésion de l'auteur (par défaut
    celle qui a ouvert la session)."""

    now = now or timezone.now()
    return services.record_cash_payment(
        club=ctx.club,
        user=(user or session.opened_by).user,
        public_id=session.public_id,
        membership=membership,
        amount=amount,
        client_uuid=client_uuid or uuid.uuid4(),
        client_recorded_at=recorded_at or now,
        now=now,
        **extra,
    )
