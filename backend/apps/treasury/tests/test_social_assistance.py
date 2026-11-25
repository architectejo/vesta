"""Assistance sociale (tâche 2.2 ; CDC 4.5.3 ; 10.2 n° 33 et 37 ; invariant 9).

Invariant 9 : assistance réservée aux joueurs en ordre à la date de
l'événement. 10.2 n° 33 : la demande reste envoyable sans être éligible.
10.2 n° 37 : un joueur toujours en dette ne peut être ni approuvé ni libéré.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import (
    Expense,
    LedgerImmutableError,
    SocialAssistanceEvent,
    SocialAssistanceRequest,
    SocialAssistanceScale,
)
from apps.treasury.tests.conftest import make_member
from apps.treasury.tests.expense_helpers import (
    club_today,
    days_ago,
    make_category,
    make_expense,
    pay_mandatory,
    pdf_file,
    put_in_debt,
    release,
)

pytestmark = pytest.mark.django_db


def assistance_category(ctx, name="Assistance sociale"):
    return make_category(ctx, name=name, good_standing_only=True)


def make_scale(ctx, event=SocialAssistanceEvent.DEATH, amount="50", days=7, category=None, by=None):
    return services.create_social_assistance_scale(
        club=ctx.club,
        created_by=(by or ctx.treasurer).user,
        event_type=event,
        amount=amount,
        processing_days=days,
        expense_category=category or assistance_category(ctx),
    )


def submit(ctx, membership=None, *, event=SocialAssistanceEvent.DEATH, event_date=None, by=None, **kwargs):
    membership = membership or ctx.player
    return services.submit_social_assistance_request(
        membership=membership,
        submitted_by=(by or membership).user,
        event_type=event,
        event_date=event_date or club_today(ctx) - datetime.timedelta(days=3),
        description=kwargs.pop("description", "Décès de mon père."),
        attachment=kwargs.pop("attachment", pdf_file("acte.pdf")),
    )


class TestScale:
    def test_no_scale_by_default(self, ctx):
        assert not SocialAssistanceScale.all_objects.filter(club=ctx.club).exists()

    @pytest.mark.parametrize("role", ["president", "treasurer"])
    def test_president_and_treasurer_define_the_scale(self, ctx, role):
        scale = make_scale(ctx, by=getattr(ctx, role))
        assert (scale.amount, scale.processing_days) == (Decimal("50.00"), 7)
        assert AuditLog.objects.filter(action_type="treasury.social_assistance_scale.created").count() == 1

    @pytest.mark.parametrize("role", ["vice_president", "assistant_treasurer", "player"])
    def test_other_roles_cannot_define_the_scale(self, ctx, role):
        category = assistance_category(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            make_scale(ctx, category=category, by=getattr(ctx, role))

    def test_scale_rules(self, ctx):
        with pytest.raises(services.TreasuryValidationError, match="réservée aux membres en ordre"):
            make_scale(ctx, category=make_category(ctx, name="Libre"))
        category = assistance_category(ctx)
        with pytest.raises(services.InvalidAmountError):
            make_scale(ctx, category=category, amount="0")
        with pytest.raises(services.TreasuryValidationError, match="délai"):
            make_scale(ctx, category=category, days=0)
        with pytest.raises(services.TreasuryValidationError, match="Événement inconnu"):
            make_scale(ctx, category=category, event="divorce")
        scale = make_scale(ctx, category=category)
        with pytest.raises(services.TreasuryValidationError, match="barème actif existe déjà"):
            make_scale(ctx, category=category)
        with pytest.raises(services.TreasuryValidationError, match="barème d'assistance sociale"):
            services.update_expense_category(category=category, updated_by=ctx.president.user, good_standing_only=False)
        with pytest.raises(services.TreasuryValidationError, match="barème d'assistance sociale actif"):
            services.archive_expense_category(category=category, archived_by=ctx.president.user)

        services.archive_social_assistance_scale(scale=scale, archived_by=ctx.president.user)
        assert make_scale(ctx, category=category, amount="60").amount == Decimal("60.00")
        with pytest.raises(LedgerImmutableError):
            scale.delete()

    def test_update_does_not_change_requests_already_sent(self, ctx):
        scale = make_scale(ctx)
        request_obj = submit(ctx)
        services.update_social_assistance_scale(scale=scale, updated_by=ctx.president.user, amount="80", processing_days=3)
        request_obj.refresh_from_db()
        assert (request_obj.planned_amount, request_obj.processing_days) == (Decimal("50.00"), 7)


class TestSubmission:
    def test_player_in_good_standing_submits_an_eligible_request(self, ctx):
        make_scale(ctx)
        request_obj = submit(ctx)

        assert request_obj.status == SocialAssistanceRequest.Status.SUBMITTED
        assert request_obj.eligible_at_submission is True
        assert request_obj.amount_to_regularize == Decimal("0.00")
        assert (request_obj.planned_amount, request_obj.currency, request_obj.processing_days) == (
            Decimal("50.00"),
            "USD",
            7,
        )
        entry = AuditLog.objects.get(action_type="treasury.social_assistance.submitted")
        assert "description" not in entry.after  # donnée personnelle, jamais copiée au journal
        notified = Notification.objects.filter(event_type=Notification.EventType.SOCIAL_ASSISTANCE_REQUEST)
        assert {n.recipient_id for n in notified} == {ctx.president.user_id, ctx.vice_president.user_id}

    def test_player_in_debt_can_still_submit_with_amount_to_regularize(self, ctx):
        """10.2 n° 33 : envoyable sans être éligible, avec le montant à régulariser."""

        make_scale(ctx)
        put_in_debt(ctx, ctx.player, amount="15", due_date=club_today(ctx) - datetime.timedelta(days=30))
        request_obj = submit(ctx)
        assert request_obj.eligible_at_submission is False
        assert request_obj.amount_to_regularize == Decimal("15.00")

    def test_submission_rules(self, ctx):
        with pytest.raises(services.TreasuryValidationError, match="pas encore défini de barème"):
            submit(ctx)
        make_scale(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            submit(ctx, ctx.player, by=ctx.president)
        with pytest.raises(services.TreasuryValidationError, match="futur"):
            submit(ctx, event_date=club_today(ctx) + datetime.timedelta(days=1))
        with pytest.raises(services.TreasuryValidationError, match="description"):
            submit(ctx, description="  ")
        with pytest.raises(services.TreasuryValidationError, match="pièce justificative"):
            submit(ctx, attachment=None)
        with pytest.raises(services.TreasuryValidationError, match="inscrit"):
            submit(ctx, ctx.pending_member)
        with pytest.raises(services.TreasuryValidationError, match="barème"):
            submit(ctx, event=SocialAssistanceEvent.BIRTH)
        assert not SocialAssistanceRequest.all_objects.exists()

    def test_preview_shows_scale_and_eligibility(self, ctx):
        put_in_debt(ctx, ctx.player, amount="10")
        preview = services.get_social_assistance_preview(
            membership=ctx.player, event_type=SocialAssistanceEvent.DEATH, event_date=club_today(ctx)
        )
        assert preview.scale is None
        assert preview.eligibility.amount_to_regularize == Decimal("10.00")
        make_scale(ctx)
        preview = services.get_social_assistance_preview(
            membership=ctx.player, event_type=SocialAssistanceEvent.DEATH, event_date=club_today(ctx)
        )
        assert preview.scale.amount == Decimal("50.00")


class TestEligibility:
    def test_in_order_at_event_date(self, ctx):
        eligibility = services.get_social_assistance_eligibility(ctx.player, club_today(ctx))
        assert eligibility.eligible and eligibility.can_be_approved
        assert eligibility.was_in_good_standing_at_event

    def test_in_debt_at_event_then_regularized_becomes_eligible(self, ctx):
        """Q12 (provisoire) : un paiement validé après l'événement régularise."""

        today = club_today(ctx)
        ctype = put_in_debt(ctx, ctx.player, amount="10", due_date=today - datetime.timedelta(days=30))
        event_date = today - datetime.timedelta(days=5)
        before = services.get_social_assistance_eligibility(ctx.player, event_date)
        assert (before.eligible, before.can_be_approved) == (False, False)
        assert before.amount_to_regularize == Decimal("10.00")
        assert "n'était pas en ordre à la date de l'événement" in before.reason

        pay_mandatory(ctx, ctx.player, ctype, amount="10", paid_on=today)
        after = services.get_social_assistance_eligibility(ctx.player, event_date)
        assert after.was_in_good_standing_at_event is False  # historique strict conservé
        assert (after.eligible, after.can_be_approved) == (True, True)
        assert after.amount_to_regularize == Decimal("0.00")

    def test_in_order_at_event_but_in_debt_now_cannot_be_approved(self, ctx):
        today = club_today(ctx)
        event_date = today - datetime.timedelta(days=20)
        put_in_debt(ctx, ctx.player, amount="10", due_date=today - datetime.timedelta(days=5))
        eligibility = services.get_social_assistance_eligibility(ctx.player, event_date)
        assert eligibility.eligible is True
        assert eligibility.can_be_approved is False
        assert "toujours en dette" in eligibility.reason

    def test_free_contributions_never_count(self, ctx):
        """Invariant 2 : un type libre ne crée jamais de dette."""

        from django.core.exceptions import ValidationError

        from apps.treasury.models import ContributionType, Due
        from apps.treasury.tests.factories import ContributionTypeFactory

        free = ContributionTypeFactory(club=ctx.club, nature=ContributionType.Nature.FREE, created_by=ctx.president.user)
        with pytest.raises(ValidationError, match="type libre"):
            Due(
                club=ctx.club, membership=ctx.player, contribution_type=free, period=datetime.date(2026, 1, 1),
                amount=Decimal("5"), due_date=datetime.date(2026, 1, 10), source=Due.Source.SCHEDULER,
                created_at=days_ago(1),
            ).save()
        assert services.get_social_assistance_eligibility(ctx.player, club_today(ctx)).can_be_approved


class TestDecision:
    @pytest.mark.parametrize("role", ["president", "vice_president"])
    def test_approval_creates_a_pending_expense_of_the_scale_category(self, ctx, role):
        scale = make_scale(ctx)
        request_obj = submit(ctx)

        expense = services.approve_social_assistance_request(request_obj=request_obj, approved_by=getattr(ctx, role).user)

        request_obj.refresh_from_db()
        assert request_obj.status == SocialAssistanceRequest.Status.APPROVED
        assert request_obj.decided_by_id == getattr(ctx, role).user_id
        assert expense.status == Expense.Status.PENDING
        assert expense.category_id == scale.expense_category_id
        assert expense.amount == Decimal("50.00")
        assert expense.beneficiary_membership_id == ctx.player.pk
        assert expense.social_assistance_request_id == request_obj.pk
        assert request_obj.expense == expense
        assert AuditLog.objects.filter(action_type="treasury.social_assistance.approved").count() == 1
        assert AuditLog.objects.filter(action_type="treasury.expense.created").count() == 1

        with pytest.raises(services.TreasuryValidationError, match="déjà été traitée"):
            services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        request_obj.rejection_reason = "modifié"
        with pytest.raises(LedgerImmutableError):
            request_obj.save()

        released = release(ctx, expense)
        assert released.status == Expense.Status.RELEASED

    def test_player_still_in_debt_cannot_be_approved(self, ctx):
        """10.2 n° 37."""

        make_scale(ctx)
        ctype = put_in_debt(ctx, ctx.player, amount="10", due_date=club_today(ctx) - datetime.timedelta(days=30))
        request_obj = submit(ctx)
        with pytest.raises(services.TreasuryValidationError, match="Demande non approuvable"):
            services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        assert not Expense.all_objects.exists()
        request_obj.refresh_from_db()
        assert request_obj.status == SocialAssistanceRequest.Status.SUBMITTED

        pay_mandatory(ctx, ctx.player, ctype, amount="10")
        expense = services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        assert expense.status == Expense.Status.PENDING

    def test_release_refused_if_player_fell_into_debt_even_by_derogation(self, ctx):
        """10.2 n° 37 : ni approuvée ni libérée ; la dérogation ne contourne pas."""

        make_scale(ctx)
        request_obj = submit(ctx)
        expense = services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        put_in_debt(ctx, ctx.player, amount="10", due_date=club_today(ctx) - datetime.timedelta(days=1))

        with pytest.raises(services.TreasuryValidationError, match="Assistance sociale non libérable"):
            release(ctx, expense)
        release(ctx, make_expense(ctx, make_category(ctx, name="Autre")), now=days_ago(10))
        with pytest.raises(services.TreasuryValidationError, match="Assistance sociale non libérable"):
            services.release_expense_with_derogation(
                expense=expense, president=ctx.president.user, reason="Urgence"
            )
        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.PENDING

    def test_decision_rules(self, ctx):
        make_scale(ctx)
        request_obj = submit(ctx)
        for role in ("treasurer", "assistant_treasurer", "player"):
            with pytest.raises(services.TreasuryPermissionError):
                services.approve_social_assistance_request(request_obj=request_obj, approved_by=getattr(ctx, role).user)
            with pytest.raises(services.TreasuryPermissionError):
                services.reject_social_assistance_request(
                    request_obj=request_obj, rejected_by=getattr(ctx, role).user, reason="Non"
                )
        with pytest.raises(services.TreasuryValidationError, match="motif du refus"):
            services.reject_social_assistance_request(request_obj=request_obj, rejected_by=ctx.president.user, reason="")

        rejected = services.reject_social_assistance_request(
            request_obj=request_obj, rejected_by=ctx.vice_president.user, reason="Pièce illisible"
        )
        assert rejected.status == SocialAssistanceRequest.Status.REJECTED
        assert rejected.rejection_reason == "Pièce illisible"
        assert AuditLog.objects.filter(action_type="treasury.social_assistance.rejected").count() == 1
        with pytest.raises(services.TreasuryValidationError, match="déjà été traitée"):
            services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        with pytest.raises(LedgerImmutableError):
            rejected.delete()

    def test_ceiling_of_the_scale_category_applies(self, ctx):
        category = make_category(ctx, name="Assistance plafonnée", good_standing_only=True, ceiling="40")
        make_scale(ctx, category=category, amount="50")
        request_obj = submit(ctx)
        with pytest.raises(services.TreasuryValidationError, match="plafond"):
            services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)

    def test_departed_player_cannot_submit(self, ctx):
        make_scale(ctx)
        departed = make_member(ctx.club, status=Membership.Status.DEPARTED)
        with pytest.raises(services.TreasuryValidationError, match="inscrit"):
            submit(ctx, departed)
