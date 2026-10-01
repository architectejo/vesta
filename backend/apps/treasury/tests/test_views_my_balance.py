"""Vue « Mon solde » : simple sérialisation du service (CLAUDE.md §5, règle n° 2).

La vue ne recalcule jamais le solde : elle renvoie exactement ce que
``services.get_balance_summary`` / ``services.is_in_good_standing``
calculent (CDC 4.4.2).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from apps.treasury import services
from apps.treasury.models import ContributionType
from apps.treasury.tests.conftest import ClubContext
from apps.treasury.tests.test_views_contribution_types import client_for

pytestmark = pytest.mark.django_db


def put_player_in_debt(ctx: ClubContext) -> None:
    """Un montant dû de 10 $ pour mars 2026, échu depuis longtemps."""

    ctx.player.joined_on = datetime.date(2025, 12, 1)
    ctx.player.save(update_fields=["joined_on"])
    services.create_contribution_type(
        club=ctx.club,
        created_by=ctx.president.user,
        name="Mensuelle",
        nature=ContributionType.Nature.MANDATORY,
        periodicity=ContributionType.Periodicity.MONTHLY,
        amount="10",
        now=datetime.datetime(2026, 1, 5, tzinfo=datetime.timezone.utc),
    )
    services.generate_dues_for_period(club=ctx.club, period=datetime.date(2026, 3, 1), actor=ctx.treasurer.user)


def test_player_in_debt_sees_the_service_summary(ctx: ClubContext):
    put_player_in_debt(ctx)

    response = client_for(ctx.player.user).get(reverse("treasury:my-balance"))

    assert response.status_code == status.HTTP_200_OK, response.data
    assert response.data == {
        "membership_id": ctx.player.pk,
        "club_id": ctx.club.pk,
        "currency": "USD",
        "balance": "-10.00",
        "amount_due": "10.00",
        "is_in_good_standing": False,
        "reason": "Le joueur est en dette : 10.00 USD à régulariser.",
    }
    good, amount_due, reason = services.is_in_good_standing(ctx.player)
    assert (good, amount_due, reason) == (False, Decimal("10.00"), response.data["reason"])


def test_summary_service_is_consistent_with_is_in_good_standing(ctx: ClubContext):
    put_player_in_debt(ctx)

    summary = services.get_balance_summary(ctx.player)

    assert summary.balance == services.get_balance(ctx.player) == Decimal("-10.00")
    assert services.is_in_good_standing(ctx.player) == (
        summary.is_in_good_standing,
        summary.amount_due,
        summary.reason,
    )


def test_player_in_good_standing_gets_zero_amount_due(ctx: ClubContext):
    summary = services.get_balance_summary(ctx.player)

    assert summary.is_in_good_standing is True
    assert str(summary.amount_due) == "0.00"
    assert str(summary.balance) == "0.00"
    assert summary.reason == "Le joueur est en ordre."
