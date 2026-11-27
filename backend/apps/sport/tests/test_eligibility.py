"""Éligibilité (CLAUDE.md règle n° 5 ; CDC 4.7-4.9, 4.11 ; 10.2 n° 16, n° 29)."""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.sport import services
from apps.sport.models import Incident, Suspension
from apps.sport.tests.conftest import make_member
from apps.sport.tests.factories import EventFactory

pytestmark = pytest.mark.django_db


def test_player_in_good_standing_is_eligible(ctx):
    playability = services.get_playability(ctx.player)
    assert playability.eligible is True
    assert playability.reason_code == ""


def test_debtor_is_not_eligible_with_amount(ctx):
    playability = services.get_playability(ctx.debtor)
    assert playability.eligible is False
    assert playability.reason_code == "debt"
    assert playability.detail == "En dette : 10 $."
    assert playability.amount_due == pytest.approx(10)


@pytest.mark.parametrize(
    "amount,currency,expected",
    [
        ("10.00", "USD", "En dette : 10 $."),
        ("12.50", "USD", "En dette : 12,50 $."),
        ("1250.00", "USD", "En dette : 1 250 $."),
        ("25000", "CDF", "En dette : 25 000 FC."),
    ],
)
def test_debt_detail_uses_club_money_format(amount, currency, expected):
    """Montant au format monétaire du club (reçus et notifications de la
    trésorerie, annexe D §1.7), en Decimal, jamais « 10.00 USD »."""

    from decimal import Decimal

    assert services._debt_detail(Decimal(amount), currency) == expected


def test_pending_membership_is_not_eligible(ctx):
    playability = services.get_playability(ctx.pending_member)
    assert playability.eligible is False
    assert playability.reason_code == "pending_membership"
    assert playability.detail == "En attente d'adhésion."


def test_suspended_player_is_not_eligible(ctx):
    event = EventFactory(club=ctx.club, season=ctx.season)
    Suspension.all_objects.create(
        club=ctx.club, membership=ctx.player, reason=Suspension.Reason.RED_CARD, season=ctx.season,
        matches_total=1, matches_served=0, starts_event=event,
    )
    playability = services.get_playability(ctx.player)
    assert playability.eligible is False
    assert playability.reason_code == "suspension"
    assert "Suspendu" in playability.detail


def test_lifted_suspension_no_longer_blocks(ctx):
    event = EventFactory(club=ctx.club, season=ctx.season)
    Suspension.all_objects.create(
        club=ctx.club, membership=ctx.player, reason=Suspension.Reason.RED_CARD, season=ctx.season,
        matches_total=1, matches_served=1, lifted_at=timezone.now(), starts_event=event,
    )
    assert services.get_playability(ctx.player).eligible is True


def test_medical_integration_pending_does_not_block(ctx):
    """apps.medical est un squelette vide au Lot 3 : aucun blocage médical
    n'est inventé tant que apps.medical.services.get_unfitness_reason
    n'existe pas (point d'intégration en attente, voir services.py)."""

    assert services._get_medical_unfitness(ctx.player) is None


def test_describe_reason_for_viewer_debt_filtered_by_role(ctx):
    playability = services.get_playability(ctx.debtor)

    # Président/VP/le joueur lui-même voient le montant.
    # 10.3 n° 188 : le Coach ne sait rien de la dette, seulement « Non éligible. ».
    assert services.describe_reason_for_viewer(playability, viewer=ctx.coach.user, membership=ctx.debtor) == "Non éligible."
    assert "En dette" in services.describe_reason_for_viewer(playability, viewer=ctx.vice_president.user, membership=ctx.debtor)
    assert "En dette" in services.describe_reason_for_viewer(playability, viewer=ctx.president.user, membership=ctx.debtor)
    assert "En dette" in services.describe_reason_for_viewer(playability, viewer=ctx.debtor.user, membership=ctx.debtor)

    # DS/Médecin/Capitaine/autres joueurs ne voient que « Indisponible » pour une dette (10.2 n° 16).
    assert services.describe_reason_for_viewer(playability, viewer=ctx.sports_director.user, membership=ctx.debtor) == "Indisponible"
    assert services.describe_reason_for_viewer(playability, viewer=ctx.doctor.user, membership=ctx.debtor) == "Indisponible"
    assert services.describe_reason_for_viewer(playability, viewer=ctx.captain.user, membership=ctx.debtor) == "Indisponible"
    assert services.describe_reason_for_viewer(playability, viewer=ctx.player.user, membership=ctx.debtor) == "Indisponible"


def test_describe_reason_for_viewer_suspension_full_detail_for_medical_staff(ctx):
    event = EventFactory(club=ctx.club, season=ctx.season)
    Suspension.all_objects.create(
        club=ctx.club, membership=ctx.player, reason=Suspension.Reason.RED_CARD, season=ctx.season,
        matches_total=2, matches_served=0, starts_event=event,
    )
    playability = services.get_playability(ctx.player)

    # DS/Médecin voient le motif complet (aptitude/suspension), pas la dette (10.2 n° 16).
    assert "Suspendu" in services.describe_reason_for_viewer(playability, viewer=ctx.sports_director.user, membership=ctx.player)
    assert "Suspendu" in services.describe_reason_for_viewer(playability, viewer=ctx.doctor.user, membership=ctx.player)
    # Capitaine et autres joueurs : « Indisponible » seul.
    assert services.describe_reason_for_viewer(playability, viewer=ctx.captain.user, membership=ctx.player) == "Indisponible"


def test_eligible_player_reason_is_empty(ctx):
    playability = services.get_playability(ctx.player)
    assert services.describe_reason_for_viewer(playability, viewer=ctx.coach.user, membership=ctx.player) == ""
