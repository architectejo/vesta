"""Étanchéité entre clubs des dépenses et de l'assistance sociale (tâche 2.2 ;
CLAUDE.md règles n° 8 et 9 ; CDC 6.3 ; schema-treasury.md §1.2)."""

from __future__ import annotations

import pytest

from apps.core.tenant import NoActiveClubError, TenantMismatchError, active_club
from apps.treasury import services
from apps.treasury.models import (
    Expense,
    ExpenseAttachment,
    ExpenseCategory,
    ExpenseDerogation,
    SocialAssistanceEvent,
    SocialAssistanceRequest,
    SocialAssistanceScale,
)
from apps.treasury.tests.expense_helpers import (
    club_today,
    days_ago,
    make_category,
    make_expense,
    pdf_file,
    release,
)

pytestmark = pytest.mark.django_db


def test_reads_without_active_club_are_refused(ctx):
    make_expense(ctx)
    for model in (
        Expense,
        ExpenseCategory,
        ExpenseAttachment,
        ExpenseDerogation,
        SocialAssistanceScale,
        SocialAssistanceRequest,
    ):
        with pytest.raises(NoActiveClubError):
            list(model.objects.all())


def test_reads_are_scoped_to_the_active_club(ctx, other_ctx):
    mine = make_expense(ctx)
    theirs = make_expense(other_ctx)
    with active_club(ctx.club):
        assert list(Expense.objects.all()) == [mine]
    with active_club(other_ctx.club):
        assert list(Expense.objects.all()) == [theirs]


def test_treasurer_of_club_a_cannot_act_in_club_b(ctx, other_ctx):
    category_b = make_category(other_ctx)
    with pytest.raises(services.TreasuryPermissionError):
        services.create_expense(
            club=other_ctx.club,
            created_by=ctx.treasurer.user,
            category=category_b,
            amount="10",
            beneficiary_name="X",
            reason="Y",
            expense_date=club_today(other_ctx),
        )
    expense_b = make_expense(other_ctx, category_b)
    with pytest.raises(services.TreasuryPermissionError):
        release(ctx, expense_b, by=ctx.president)
    with pytest.raises(services.TreasuryPermissionError):
        services.create_expense_category(club=other_ctx.club, created_by=ctx.president.user, name="Intrus")


def test_foreign_category_or_beneficiary_refused(ctx, other_ctx):
    category_b = make_category(other_ctx)
    with pytest.raises(services.TreasuryValidationError, match="n'appartient pas à ce club"):
        make_expense(ctx, category_b)
    with pytest.raises(services.TreasuryValidationError, match="n'appartient pas à ce club"):
        make_expense(ctx, beneficiary_membership=other_ctx.player)
    assert not Expense.all_objects.filter(club=ctx.club).exists()


def test_writing_into_another_club_than_the_active_one_is_refused(ctx, other_ctx):
    expense_b = make_expense(other_ctx)
    with active_club(ctx.club):
        with pytest.raises(TenantMismatchError):
            make_expense(other_ctx)
        with pytest.raises(TenantMismatchError):
            release(other_ctx, expense_b)
    assert Expense.all_objects.get(pk=expense_b.pk).status == Expense.Status.PENDING


def test_blocking_is_per_club(ctx, other_ctx):
    release(ctx, make_expense(ctx), now=days_ago(10))
    assert services.can_release_expense(ctx.club).allowed is False
    assert services.can_release_expense(other_ctx.club).allowed is True
    assert release(other_ctx, make_expense(other_ctx)).status == Expense.Status.RELEASED


def test_available_cash_is_per_club(ctx, other_ctx):
    release(ctx, make_expense(ctx, amount="10"))
    assert services.get_available_cash(ctx.club) == -10
    assert services.get_available_cash(other_ctx.club) == 0


def test_assistance_scale_category_must_belong_to_the_club(ctx, other_ctx):
    category_b = make_category(other_ctx, good_standing_only=True)
    with pytest.raises(services.TreasuryValidationError, match="n'appartient pas à ce club"):
        services.create_social_assistance_scale(
            club=ctx.club,
            created_by=ctx.president.user,
            event_type=SocialAssistanceEvent.BIRTH,
            amount="20",
            processing_days=5,
            expense_category=category_b,
        )


def test_president_of_club_a_cannot_decide_a_request_of_club_b(ctx, other_ctx):
    services.create_social_assistance_scale(
        club=other_ctx.club,
        created_by=other_ctx.president.user,
        event_type=SocialAssistanceEvent.BIRTH,
        amount="20",
        processing_days=5,
        expense_category=make_category(other_ctx, good_standing_only=True),
    )
    request_b = services.submit_social_assistance_request(
        membership=other_ctx.player,
        submitted_by=other_ctx.player.user,
        event_type=SocialAssistanceEvent.BIRTH,
        event_date=club_today(other_ctx),
        description="Naissance",
        attachment=pdf_file(),
    )
    with pytest.raises(services.TreasuryPermissionError):
        services.approve_social_assistance_request(request_obj=request_b, approved_by=ctx.president.user)
    with pytest.raises(services.TreasuryPermissionError):
        services.submit_social_assistance_request(
            membership=other_ctx.player,
            submitted_by=ctx.player.user,
            event_type=SocialAssistanceEvent.BIRTH,
            event_date=club_today(other_ctx),
            description="Usurpation",
            attachment=pdf_file(),
        )
