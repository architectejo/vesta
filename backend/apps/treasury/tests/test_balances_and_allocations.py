"""Soldes, montants dus et repartition (CDC 4.4.2-4.4.4 ; schema §4-5, §9)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.core.tenant import TenantMismatchError, active_club
from apps.treasury import services
from apps.treasury.models import (
    ContributionAssignment,
    ContributionSuspension,
    ContributionType,
    ContributionTypeRate,
    Due,
    Payment,
    PaymentAllocation,
    PaymentReversal,
    Transaction,
)
from apps.treasury.tests.factories import ContributionTypeFactory

pytestmark = pytest.mark.django_db


def make_monthly_type(ctx, *, name="Mensuelle", amount="10", scope=ContributionType.Scope.ALL, now=None):
    ctx.player.joined_on = datetime.date(2025, 12, 1)
    ctx.player.save(update_fields=["joined_on"])
    return services.create_contribution_type(
        club=ctx.club,
        created_by=ctx.president.user,
        name=name,
        nature=ContributionType.Nature.MANDATORY,
        periodicity=ContributionType.Periodicity.MONTHLY,
        amount=amount,
        scope=scope,
        now=now or datetime.datetime(2026, 1, 5, tzinfo=datetime.timezone.utc),
    )


def make_payment(ctx, ctype, *, amount="10", paid_on=datetime.date(2026, 3, 10), membership=None):
    now = timezone.now()
    payment = Payment(
        club=ctx.club,
        membership=membership or ctx.player,
        contribution_type=ctype,
        amount=Decimal(amount),
        currency=ctx.club.settings.currency,
        method=Payment.Method.CASH,
        paid_on=paid_on,
        source=Payment.Source.TREASURER_ENTRY,
        submitted_by=ctx.treasurer.user,
        submitted_at=now,
        validated_by=ctx.treasurer.user,
        validated_at=now,
    )
    payment.save()
    transaction_obj = services.open_payment_transaction(payment=payment, provider=Transaction.Provider.MANUAL)
    services.advance_transaction(transaction_obj=transaction_obj, status=Transaction.Status.SUCCEEDED)
    return payment


class TestDueGenerationAndAssignments:
    def test_generates_month_due_idempotently_with_rate_snapshot_and_audit(self, ctx):
        ctype = make_monthly_type(ctx)

        created = services.generate_dues_for_period(
            club=ctx.club,
            period=datetime.date(2026, 3, 1),
            actor=ctx.treasurer.user,
        )
        repeated = services.generate_dues_for_period(
            club=ctx.club,
            period=datetime.date(2026, 3, 1),
            actor=ctx.treasurer.user,
        )

        assert len(created) == 1
        assert repeated == []
        due = created[0]
        assert due.membership_id == ctx.player.id
        assert due.contribution_type_id == ctype.id
        assert due.period == datetime.date(2026, 3, 1)
        assert due.amount == Decimal("10.00")
        assert due.due_date == datetime.date(2026, 3, 10)
        assert due.source == Due.Source.SCHEDULER
        assert AuditLog.objects.filter(action_type="treasury.due.generated").count() == 1

    def test_arrival_creates_full_month_amount_with_explicit_due_date(self, ctx):
        ctype = make_monthly_type(ctx)
        ctx.player.joined_on = datetime.date(2026, 3, 20)
        ctx.player.save()

        created = services.generate_dues_for_period(
            club=ctx.club,
            period=datetime.date(2026, 3, 1),
            actor=ctx.treasurer.user,
            arrival_due_date=datetime.date(2026, 3, 20),
        )

        assert len(created) == 1
        assert created[0].amount == Decimal("10.00")
        assert created[0].source == Due.Source.ARRIVAL
        assert created[0].due_date == datetime.date(2026, 3, 20)
        assert created[0].contribution_type_id == ctype.id

    def test_assignment_required_for_selected_scope_and_is_journalled(self, ctx):
        ctype = make_monthly_type(ctx, scope=ContributionType.Scope.SELECTED)
        assignment = services.create_contribution_assignment(
            membership=ctx.player,
            contribution_type=ctype,
            starts_on=datetime.date(2026, 2, 1),
            created_by=ctx.president.user,
        )

        assert assignment.club_id == ctx.club.id
        assert ContributionAssignment.all_objects.filter(pk=assignment.pk).exists()
        assert AuditLog.objects.filter(action_type="treasury.contribution_assignment.created").count() == 1

        created = services.generate_dues_for_period(
            club=ctx.club,
            period=datetime.date(2026, 2, 1),
            actor=ctx.treasurer.user,
        )
        assert [due.membership_id for due in created] == [ctx.player.id]

    def test_assignment_periods_cannot_overlap(self, ctx):
        ctype = make_monthly_type(ctx, scope=ContributionType.Scope.ATTACHED)
        services.create_contribution_assignment(
            membership=ctx.player,
            contribution_type=ctype,
            starts_on=datetime.date(2026, 1, 1),
            ends_on=datetime.date(2026, 4, 30),
            created_by=ctx.president.user,
        )

        with pytest.raises(services.TreasuryValidationError):
            services.create_contribution_assignment(
                membership=ctx.player,
                contribution_type=ctype,
                starts_on=datetime.date(2026, 4, 1),
                created_by=ctx.president.user,
            )

    def test_suspension_skips_only_not_yet_generated_periods(self, ctx):
        ctype = make_monthly_type(ctx)
        services.generate_dues_for_period(
            club=ctx.club, period=datetime.date(2026, 2, 1), actor=ctx.treasurer.user
        )
        suspension = services.create_contribution_suspension(
            membership=ctx.player,
            starts_on=datetime.date(2026, 2, 1),
            ends_on=datetime.date(2026, 3, 31),
            reason="Blessure longue",
            decided_by=ctx.president.user,
        )

        march_dues = services.generate_dues_for_period(
            club=ctx.club, period=datetime.date(2026, 3, 1), actor=ctx.treasurer.user
        )

        assert suspension.club_id == ctx.club.id
        assert not march_dues
        assert Due.all_objects.filter(contribution_type=ctype).count() == 1
        assert AuditLog.objects.filter(action_type="treasury.contribution_suspension.created").count() == 1


class TestBalanceAndEligibility:
    def test_bulk_balances_use_a_fixed_number_of_queries(self, ctx, django_assert_num_queries):
        make_monthly_type(ctx)

        with django_assert_num_queries(4):
            balances = services.get_balances(ctx.club, at_date=datetime.date(2026, 3, 13))

        assert balances[ctx.player.pk] == Decimal("0.00")

    def test_debt_starts_after_due_date_plus_club_tolerance(self, ctx):
        ctype = make_monthly_type(ctx)
        due = Due(
            club=ctx.club,
            membership=ctx.player,
            contribution_type=ctype,
            period=datetime.date(2026, 3, 1),
            amount=Decimal("10.00"),
            due_date=datetime.date(2026, 3, 10),
            source=Due.Source.SCHEDULER,
            created_at=timezone.now(),
        )
        due.save()
        ctx.club.settings.debt_tolerance_days = 2
        ctx.club.settings.save()

        assert services.get_balance(ctx.player, at_date=datetime.date(2026, 3, 12)) == Decimal("0.00")
        assert services.get_balance(ctx.player, at_date=datetime.date(2026, 3, 13)) == Decimal("-10.00")
        eligible, amount_due, reason = services.is_in_good_standing(
            ctx.player, at_date=datetime.date(2026, 3, 13)
        )
        assert (eligible, amount_due) == (False, Decimal("10.00"))
        assert "10.00" in reason and "dette" in reason.lower()

    def test_free_type_payment_is_excluded_from_balance(self, ctx):
        free_type = ContributionTypeFactory(
            club=ctx.club,
            created_by=ctx.president.user,
            nature=ContributionType.Nature.FREE,
            periodicity=ContributionType.Periodicity.ONE_OFF,
            amount=None,
            due_day=None,
            deadline=datetime.date(2026, 3, 31),
        )
        payment = make_payment(ctx, free_type, amount="7", paid_on=datetime.date(2026, 3, 15))

        assert services.get_balance(ctx.player, at_date=datetime.date(2026, 3, 20)) == Decimal("0.00")
        assert list(PaymentAllocation.all_objects.filter(payment=payment).values_list("period", "amount")) == [
            (datetime.date(2026, 3, 1), Decimal("7.00"))
        ]

    def test_balance_aggregates_for_memberships_and_reversal_is_applied(self, ctx):
        ctype = make_monthly_type(ctx)
        first_due = Due(
            club=ctx.club,
            membership=ctx.player,
            contribution_type=ctype,
            period=datetime.date(2026, 2, 1),
            amount=Decimal("10.00"),
            due_date=datetime.date(2026, 2, 10),
            source=Due.Source.SCHEDULER,
            created_at=timezone.now(),
        )
        first_due.save()
        payment = make_payment(ctx, ctype, amount="10", paid_on=datetime.date(2026, 2, 9))

        assert services.get_balance(ctx.player, at_date=datetime.date(2026, 2, 11)) == Decimal("0.00")
        assert services.get_balances(ctx.club, at_date=datetime.date(2026, 2, 11))[ctx.player.pk] == Decimal("0.00")

        reversal = services.request_payment_reversal(
            payment=payment, reason="Saisie incorrecte", requested_by=ctx.treasurer.user
        )
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)

        assert services.get_balance(ctx.player, at_date=datetime.date(2026, 2, 11)) == Decimal("-10.00")
        assert not PaymentAllocation.all_objects.filter(payment=payment).exists()

    def test_rate_change_is_effective_only_for_future_due_snapshots(self, ctx):
        ctype = make_monthly_type(ctx, now=datetime.datetime(2026, 1, 5, tzinfo=datetime.timezone.utc))
        services.generate_dues_for_period(
            club=ctx.club, period=datetime.date(2026, 3, 1), actor=ctx.treasurer.user
        )
        services.update_contribution_type(
            contribution_type=ctype,
            updated_by=ctx.treasurer.user,
            now=datetime.datetime(2026, 3, 15, tzinfo=datetime.timezone.utc),
            amount="15",
        )

        march = Due.all_objects.get(contribution_type=ctype, period=datetime.date(2026, 3, 1))
        april = services.generate_dues_for_period(
            club=ctx.club, period=datetime.date(2026, 4, 1), actor=ctx.treasurer.user
        )[0]
        assert march.amount == Decimal("10.00")
        assert april.amount == Decimal("15.00")
        assert ContributionTypeRate.all_objects.filter(contribution_type=ctype).count() == 2


class TestPaymentAllocations:
    def test_advance_40_over_current_and_future_four_months(self, ctx):
        ctype = make_monthly_type(ctx)
        services.generate_dues_for_period(
            club=ctx.club, period=datetime.date(2026, 3, 1), actor=ctx.treasurer.user
        )

        payment = make_payment(ctx, ctype, amount="40", paid_on=datetime.date(2026, 3, 10))
        allocations = list(
            PaymentAllocation.all_objects.filter(payment=payment).order_by("period").values_list("period", "amount")
        )

        assert allocations == [
            (datetime.date(2026, month, 1), Decimal("10.00")) for month in (3, 4, 5, 6)
        ]
        assert services.allocate_payment(payment) == allocations
        assert PaymentAllocation.all_objects.filter(payment=payment).count() == 4

    def test_partial_payment_allocates_only_paid_amount_and_oldest_due_first(self, ctx):
        ctype = make_monthly_type(ctx)
        for month in (1, 2, 3):
            services.generate_dues_for_period(
                club=ctx.club, period=datetime.date(2026, month, 1), actor=ctx.treasurer.user
            )
        payment = make_payment(ctx, ctype, amount="15", paid_on=datetime.date(2026, 3, 10))

        assert list(
            PaymentAllocation.all_objects.filter(payment=payment)
            .order_by("period")
            .values_list("period", "amount")
        ) == [
            (datetime.date(2026, 1, 1), Decimal("10.00")),
            (datetime.date(2026, 2, 1), Decimal("5.00")),
        ]

    def test_multiple_payments_and_reversal_recompute_allocations_idempotently(self, ctx):
        ctype = make_monthly_type(ctx)
        services.generate_dues_for_period(
            club=ctx.club, period=datetime.date(2026, 3, 1), actor=ctx.treasurer.user
        )
        first = make_payment(ctx, ctype, amount="10", paid_on=datetime.date(2026, 3, 1))
        second = make_payment(ctx, ctype, amount="10", paid_on=datetime.date(2026, 3, 2))
        assert PaymentAllocation.all_objects.filter(payment=first).count() == 1
        assert PaymentAllocation.all_objects.filter(payment=second).count() == 1

        reversal = services.request_payment_reversal(
            payment=first, reason="Paiement saisi par erreur", requested_by=ctx.treasurer.user
        )
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)

        assert not PaymentAllocation.all_objects.filter(payment=first).exists()
        assert list(
            PaymentAllocation.all_objects.filter(payment=second).values_list("period", "amount")
        ) == [(datetime.date(2026, 3, 1), Decimal("10.00"))]


def test_private_models_are_tenant_scoped(ctx):
    for model in (ContributionAssignment, ContributionSuspension, Due, PaymentAllocation):
        with active_club(ctx.club):
            assert model.objects.filter(club=ctx.club).count() == 0


def test_due_generation_refuses_a_different_active_club(ctx, other_ctx):
    with active_club(other_ctx.club):
        with pytest.raises(TenantMismatchError):
            services.generate_dues_for_period(
                club=ctx.club,
                period=datetime.date(2026, 3, 1),
                actor=ctx.treasurer.user,
            )