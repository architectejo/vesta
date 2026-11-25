"""Outils communs aux tests de la grille des cotisations et de l'import
historique (tâche 2.6 ; CDC 4.4.7, 4.4.8).

Date de référence figée (``NOW`` / ``TODAY``, 15 septembre 2026 dans le
fuseau du club) pour les tests de services : l'échéance du 10 septembre
est donc passée (dette), celle d'octobre est à venir. Les tests d'API,
qui ne peuvent pas figer l'horloge, travaillent sur l'année précédant
l'année en cours (tous les mois échus).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.clubs.models import Membership
from apps.clubs.tests.factories import MembershipFactory
from apps.treasury import services
from apps.treasury.models import ContributionType, Due, Payment
from apps.treasury.tests.cash_helpers import monthly_type

NOW = datetime.datetime(2026, 9, 15, 10, 0, tzinfo=datetime.timezone.utc)
TODAY = datetime.date(2026, 9, 15)
YEAR = 2026
JAN = datetime.date(YEAR, 1, 1)

MONTH_HEADERS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def period(month: int, year: int = YEAR) -> datetime.date:
    return datetime.date(year, month, 1)


def attached_type(ctx, *, name="Mensuelle 10", amount="10"):
    """Mensuelle obligatoire « joueurs rattachés » (CDC 4.4.1 : « les
    mensuelles se rattachent joueur par joueur »), tarif depuis 2025."""

    return monthly_type(ctx, name=name, amount=amount, scope=ContributionType.Scope.ATTACHED)


def free_monthly_type(ctx, *, name="Vestiaire", amount="2"):
    return services.create_contribution_type(
        club=ctx.club,
        created_by=ctx.president.user,
        name=name,
        nature=ContributionType.Nature.FREE,
        periodicity=ContributionType.Periodicity.MONTHLY,
        amount=amount,
        scope=ContributionType.Scope.ALL,
        now=datetime.datetime(2025, 1, 5, 12, 0, tzinfo=datetime.timezone.utc),
    )


def player(
    ctx, first_name: str, last_name: str, *, email=None, jersey=None, joined_on=datetime.date(2025, 1, 1),
    status=Membership.Status.ACTIVE,
):
    kwargs = {"first_name": first_name, "last_name": last_name}
    if email:
        kwargs["email"] = email
    user = UserFactory(**kwargs)
    return MembershipFactory(
        club=ctx.club, user=user, status=status, jersey_number=jersey, joined_on=joined_on
    )


def attach(ctx, membership, ctype, *, starts_on=JAN, ends_on=None):
    return services.create_contribution_assignment(
        membership=membership,
        contribution_type=ctype,
        starts_on=starts_on,
        ends_on=ends_on,
        created_by=ctx.president.user,
        now=NOW,
    )


def make_dues(ctx, membership, ctype, months, *, year=YEAR, amount="10"):
    """Montants dus mensuels (échéance le 10), comme la génération du 1er."""

    for month in months:
        start = period(month, year)
        Due(
            club=ctx.club,
            membership=membership,
            contribution_type=ctype,
            period=start,
            amount=Decimal(amount),
            due_date=start.replace(day=10),
            source=Due.Source.SCHEDULER,
            created_at=timezone.now(),
        ).save()


def pay(ctx, membership, ctype, amount, paid_on, *, now=NOW) -> Payment:
    return services.record_payment(
        membership=membership,
        contribution_type=ctype,
        amount=amount,
        method=Payment.Method.CASH,
        paid_on=paid_on,
        recorded_by=ctx.treasurer.user,
        now=now,
    )


def grid_for(ctx, ctype, *, year=YEAR, today=TODAY, user=None, membership=None):
    return services.build_contribution_grid(
        contribution_type=ctype,
        year=year,
        requested_by=(user or ctx.treasurer).user,
        today=today,
        membership=membership,
    )


def row_of(grid, membership):
    matches = [row for row in grid.rows if row.membership.pk == membership.pk]
    assert len(matches) == 1, f"ligne absente ou en double pour {membership.pk}"
    return matches[0]


def csv_file(lines, *, header=None, delimiter=";", name="cotisations.csv") -> SimpleUploadedFile:
    header = header if header is not None else delimiter.join(["Nom"] + MONTH_HEADERS)
    text = "\n".join([header] + list(lines)) + "\n"
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def csv_line(name: str, *cells: str, delimiter=";") -> str:
    values = list(cells) + [""] * (12 - len(cells))
    return delimiter.join([name] + values)
