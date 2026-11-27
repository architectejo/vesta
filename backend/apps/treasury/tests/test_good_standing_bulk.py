"""Statut « En ordre » groupe pour tout un club (CDC 4.4.2 ; 10.3 n° 182).

``get_good_standing_membership_ids`` est la version groupee de
``is_in_good_standing`` : meme regle (types obligatoires seulement, montants
dus echus apres tolerance, paiements valides, annulations, cotisations libres
sans dette), nombre de requetes constant, etancheite entre clubs.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.clubs.models import Membership
from apps.clubs.tests.factories import ClubFactory, MembershipFactory
from apps.core.tenant import TenantMismatchError, active_club
from apps.treasury import services
from apps.treasury.models import ContributionType, Due
from apps.treasury.tests.conftest import make_member
from apps.treasury.tests.factories import ContributionTypeFactory
from apps.treasury.tests.test_balances_and_allocations import make_monthly_type, make_payment

pytestmark = pytest.mark.django_db

AT = datetime.date(2026, 3, 20)
JOINED = datetime.date(2025, 12, 1)


def _member(ctx, **kwargs) -> Membership:
    membership = make_member(ctx.club, **kwargs)
    membership.joined_on = JOINED
    membership.save(update_fields=["joined_on"])
    return membership


def _due(ctx, membership, ctype, *, period, due_date, amount="10.00") -> Due:
    due = Due(
        club=ctx.club,
        membership=membership,
        contribution_type=ctype,
        period=period,
        amount=Decimal(amount),
        due_date=due_date,
        source=Due.Source.SCHEDULER,
        created_at=timezone.now(),
    )
    due.save()
    return due


def _free_type(ctx):
    return ContributionTypeFactory(
        club=ctx.club,
        created_by=ctx.president.user,
        nature=ContributionType.Nature.FREE,
        periodicity=ContributionType.Periodicity.ONE_OFF,
        amount=None,
        due_day=None,
        deadline=datetime.date(2026, 3, 31),
    )


def build_varied_club(ctx, ctype=None) -> dict[str, Membership]:
    """Jeu varie : en ordre, en dette, cotisation libre seule, paiement
    annule, echeance non echue (tolerance), paiement anticipe, en attente."""

    ctx.club.settings.debt_tolerance_days = 2
    ctx.club.settings.save()
    ctype = ctype or make_monthly_type(ctx)  # ctx.player.joined_on = JOINED
    february = datetime.date(2026, 2, 1)

    people = {
        "paid": ctx.player,
        "debtor": _member(ctx),
        "free_only": _member(ctx),
        "reversed": _member(ctx),
        "not_matured": _member(ctx),
        "within_tolerance": _member(ctx),
        "overpaid": _member(ctx),
        "pending_debtor": _member(ctx, status=Membership.Status.PENDING),
        "pending_clear": ctx.pending_member,
        "president": ctx.president,
    }

    _due(ctx, people["paid"], ctype, period=february, due_date=datetime.date(2026, 2, 10))
    make_payment(ctx, ctype, amount="10", paid_on=datetime.date(2026, 2, 9), membership=people["paid"])

    _due(ctx, people["debtor"], ctype, period=february, due_date=datetime.date(2026, 2, 10))

    # Cotisation libre : jamais de montant du (refuse par le modele) et son
    # paiement n'entre pas dans le solde (CLAUDE.md regle 3) ; le debiteur
    # qui ne paie que du libre reste en dette.
    free = _free_type(ctx)
    make_payment(ctx, free, amount="7", paid_on=datetime.date(2026, 3, 15), membership=people["free_only"])
    make_payment(ctx, free, amount="50", paid_on=datetime.date(2026, 3, 15), membership=people["debtor"])

    _due(ctx, people["reversed"], ctype, period=february, due_date=datetime.date(2026, 2, 10))
    payment = make_payment(
        ctx, ctype, amount="10", paid_on=datetime.date(2026, 2, 9), membership=people["reversed"]
    )
    reversal = services.request_payment_reversal(
        payment=payment, reason="Saisie incorrecte", requested_by=ctx.treasurer.user
    )
    services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)

    # Echeance future et echeance dans la tolerance (18 + 2 = 20, pas < 20).
    _due(ctx, people["not_matured"], ctype, period=datetime.date(2026, 3, 1), due_date=datetime.date(2026, 3, 25))
    _due(ctx, people["within_tolerance"], ctype, period=datetime.date(2026, 3, 1), due_date=datetime.date(2026, 3, 18))

    _due(ctx, people["overpaid"], ctype, period=february, due_date=datetime.date(2026, 2, 10))
    make_payment(ctx, ctype, amount="40", paid_on=datetime.date(2026, 2, 9), membership=people["overpaid"])

    _due(ctx, people["pending_debtor"], ctype, period=february, due_date=datetime.date(2026, 2, 10))
    return people


class TestSameRuleAsIsInGoodStanding:
    @pytest.mark.parametrize("at_date", [AT, None], ids=["date_explicite", "aujourd_hui_fuseau_club"])
    def test_matches_is_in_good_standing_for_every_membership(self, ctx, at_date):
        build_varied_club(ctx)

        ids = services.get_good_standing_membership_ids(ctx.club, at_date=at_date)

        memberships = list(Membership.all_objects.filter(club=ctx.club))
        assert len(memberships) >= 10
        for membership in memberships:
            expected = services.is_in_good_standing(membership, at_date=at_date)[0]
            assert (membership.pk in ids) is expected, membership

    def test_expected_status_of_each_case(self, ctx):
        people = build_varied_club(ctx)

        ids = services.get_good_standing_membership_ids(ctx.club, at_date=AT)

        in_order = {name for name, membership in people.items() if membership.pk in ids}
        assert in_order == {
            "paid",
            "free_only",
            "not_matured",
            "within_tolerance",
            "overpaid",
            "pending_clear",
            "president",
        }

    def test_tolerance_boundary_follows_is_in_good_standing(self, ctx):
        people = build_varied_club(ctx)
        member = people["within_tolerance"]

        day_after = datetime.date(2026, 3, 21)
        assert member.pk not in services.get_good_standing_membership_ids(ctx.club, at_date=day_after)
        assert services.is_in_good_standing(member, at_date=day_after)[0] is False

    def test_membership_ids_restricts_the_result(self, ctx):
        people = build_varied_club(ctx)

        ids = services.get_good_standing_membership_ids(
            ctx.club, at_date=AT, membership_ids=[people["paid"].pk, people["debtor"].pk]
        )

        assert ids == {people["paid"].pk}

    def test_club_without_settings_raises_like_is_in_good_standing(self, db):
        club = ClubFactory()
        membership = MembershipFactory(club=club)

        with pytest.raises(services.TreasuryValidationError) as single:
            services.is_in_good_standing(membership)
        with pytest.raises(services.TreasuryValidationError) as bulk:
            services.get_good_standing_membership_ids(club)
        assert str(bulk.value) == str(single.value)

        with pytest.raises(services.TreasuryValidationError):
            services.is_in_good_standing(membership, at_date=AT)
        with pytest.raises(services.TreasuryValidationError):
            services.get_good_standing_membership_ids(club, at_date=AT)


class TestConstantQueries:
    def _count(self, club, at_date):
        with CaptureQueriesContext(connection) as captured:
            services.get_good_standing_membership_ids(club, at_date=at_date)
        return len(captured)

    @pytest.mark.parametrize("at_date", [AT, None], ids=["date_explicite", "aujourd_hui_fuseau_club"])
    def test_query_count_does_not_grow_with_club_size(self, ctx, at_date):
        ctype = make_monthly_type(ctx)
        small = self._count(ctx.club, at_date)

        build_varied_club(ctx, ctype)
        for _ in range(15):
            _member(ctx)
        large = self._count(ctx.club, at_date)

        with CaptureQueriesContext(connection) as balances:
            services.get_balances(ctx.club, at_date=at_date)
        assert small == large == len(balances)

    def test_fixed_number_of_queries_with_explicit_date(self, ctx, django_assert_num_queries):
        build_varied_club(ctx)

        with django_assert_num_queries(4):
            services.get_good_standing_membership_ids(ctx.club, at_date=AT)


class TestTenantIsolation:
    def test_never_returns_another_club_membership(self, ctx, other_ctx):
        build_varied_club(ctx)
        other_ids = set(Membership.all_objects.filter(club=other_ctx.club).values_list("pk", flat=True))

        ids = services.get_good_standing_membership_ids(ctx.club, at_date=AT)
        restricted = services.get_good_standing_membership_ids(
            ctx.club, at_date=AT, membership_ids=other_ids | {ctx.player.pk}
        )
        other = services.get_good_standing_membership_ids(other_ctx.club, at_date=AT)

        assert ids.isdisjoint(other_ids)
        assert restricted == {ctx.player.pk}
        assert other == other_ids  # aucun du dans l'autre club : tous en ordre
        assert other.isdisjoint(ids)

    def test_other_club_debt_does_not_leak(self, ctx, other_ctx):
        people = build_varied_club(ctx)
        # Un paiement dans l'autre club ne regularise pas un debiteur du club.
        other_type = make_monthly_type(other_ctx)
        make_payment(other_ctx, other_type, amount="50", paid_on=datetime.date(2026, 2, 9))

        assert people["debtor"].pk not in services.get_good_standing_membership_ids(ctx.club, at_date=AT)
        assert other_ctx.player.pk in services.get_good_standing_membership_ids(other_ctx.club, at_date=AT)

    def test_refuses_a_different_active_club(self, ctx, other_ctx):
        with active_club(other_ctx.club):
            with pytest.raises(TenantMismatchError):
                services.get_good_standing_membership_ids(ctx.club, at_date=AT)
