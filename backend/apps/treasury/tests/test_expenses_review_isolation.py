"""Revue indépendante : étanchéité entre clubs au niveau des services et des managers.

Complète ``test_expenses_isolation.py`` (qui ne couvrait que la lecture de
``Expense`` et quelques écritures) : chaque service d'écriture, chaque modèle
privé de dépenses / assistance, lecture, création, modification, suppression.
"""

from __future__ import annotations

import datetime

import pytest

from apps.core.tenant import NoActiveClubError, TenantMismatchError, active_club
from apps.treasury import services
from apps.treasury.models import (
    Expense,
    ExpenseAttachment,
    ExpenseCategory,
    ExpenseDerogation,
    LedgerImmutableError,
    SocialAssistanceEvent,
    SocialAssistanceRequest,
    SocialAssistanceScale,
    Transaction,
)
from apps.treasury.tests.conftest import PIN
from apps.treasury.tests.expense_helpers import (
    club_today,
    days_ago,
    make_category,
    make_expense,
    pdf_file,
    release,
)
from apps.treasury.tests.expense_review_helpers import treasury_logs

pytestmark = pytest.mark.django_db

PRIVATE_MODELS = [
    Expense,
    ExpenseCategory,
    ExpenseAttachment,
    ExpenseDerogation,
    SocialAssistanceScale,
    SocialAssistanceRequest,
    Transaction,
]


def populate(ctx):
    """Une ligne de chaque modèle privé (dérogation et demande comprises)."""

    assistance = make_category(ctx, name="Assistance", good_standing_only=True)
    scale = services.create_social_assistance_scale(
        club=ctx.club,
        created_by=ctx.president.user,
        event_type=SocialAssistanceEvent.DEATH,
        amount="50",
        processing_days=7,
        expense_category=assistance,
    )
    late = release(ctx, make_expense(ctx, make_category(ctx, name="Transport"), attachment=pdf_file()), now=days_ago(10))
    urgent = make_expense(ctx, make_category(ctx, name="Urgence"))
    services.release_expense_with_derogation(expense=urgent, president=ctx.president.user, reason="Urgence", pin=PIN)
    request_obj = services.submit_social_assistance_request(
        membership=ctx.player,
        submitted_by=ctx.player.user,
        event_type=SocialAssistanceEvent.DEATH,
        event_date=club_today(ctx) - datetime.timedelta(days=1),
        description="Décès",
        attachment=pdf_file(),
    )
    return {"scale": scale, "late": late, "urgent": urgent, "request": request_obj, "assistance": assistance}


class TestManagers:
    @pytest.mark.parametrize("model", PRIVATE_MODELS)
    def test_reading_without_an_active_club_is_refused_on_every_private_model(self, ctx, model):
        populate(ctx)
        with pytest.raises(NoActiveClubError):
            list(model.objects.all())
        with pytest.raises(NoActiveClubError):
            model.objects.count()

    @pytest.mark.parametrize("model", PRIVATE_MODELS)
    def test_under_the_active_club_only_its_own_rows_are_visible_and_foreign_pks_are_unreachable(
        self, ctx, other_ctx, model
    ):
        populate(ctx)
        populate(other_ctx)
        own_pks = set(model.all_objects.filter(club=ctx.club).values_list("pk", flat=True))
        foreign_pks = set(model.all_objects.filter(club=other_ctx.club).values_list("pk", flat=True))
        assert own_pks and foreign_pks and not own_pks & foreign_pks
        with active_club(ctx.club):
            assert set(model.objects.values_list("pk", flat=True)) == own_pks
            for pk in foreign_pks:
                assert not model.objects.filter(pk=pk).exists()
                with pytest.raises(model.DoesNotExist):
                    model.objects.get(pk=pk)

    def test_same_category_name_can_exist_in_two_clubs(self, ctx, other_ctx):
        assert make_category(ctx, name="Transport").pk != make_category(other_ctx, name="Transport").pk

    def test_a_row_cannot_be_written_under_another_active_club(self, ctx, other_ctx):
        data = populate(other_ctx)
        with active_club(ctx.club):
            with pytest.raises(TenantMismatchError):
                make_category(other_ctx, name="Piratée")
            with pytest.raises(TenantMismatchError):
                services.refuse_expense(
                    expense=Expense.all_objects.get(pk=data["urgent"].pk),
                    refused_by=other_ctx.president.user,
                    reason="Piraté",
                )

    def test_deleting_foreign_rows_is_impossible_whatever_the_route(self, ctx, other_ctx):
        data = populate(other_ctx)
        with active_club(ctx.club):
            assert Expense.objects.count() == 0
            with pytest.raises(LedgerImmutableError):
                Expense.objects.all().delete()
            with pytest.raises(LedgerImmutableError):
                Expense.all_objects.filter(club=other_ctx.club).delete()
            with pytest.raises(LedgerImmutableError):
                data["urgent"].delete()
        assert Expense.all_objects.filter(club=other_ctx.club).count() == 2


class TestServicesRefuseTheOtherClub:
    """Un acteur qui a TOUS les droits dans son club n'en a aucun dans l'autre."""

    def test_every_write_service_refuses_an_actor_of_another_club(self, ctx, other_ctx):
        data = populate(other_ctx)
        pending = make_expense(other_ctx, make_category(other_ctx, name="Cible"))
        blocked_before = treasury_logs(other_ctx.club).count()
        tx_before = Transaction.all_objects.filter(club=other_ctx.club).count()

        attempts = [
            lambda: services.create_expense_category(club=other_ctx.club, created_by=ctx.president.user, name="X"),
            lambda: services.update_expense_category(category=pending.category, updated_by=ctx.president.user, name="X"),
            lambda: services.archive_expense_category(category=pending.category, archived_by=ctx.treasurer.user),
            lambda: make_expense(other_ctx, pending.category, by=ctx.treasurer),
            lambda: services.refuse_expense(expense=pending, refused_by=ctx.president.user, reason="x"),
            lambda: services.release_expense(expense=pending, released_by=ctx.president.user, pin=PIN),
            lambda: services.release_expense_with_derogation(
                expense=pending, president=ctx.president.user, reason="U", pin=PIN
            ),
            lambda: services.justify_expense(expense=data["late"], uploaded_by=ctx.treasurer.user, file=pdf_file()),
            lambda: services.create_social_assistance_scale(
                club=other_ctx.club,
                created_by=ctx.president.user,
                event_type=SocialAssistanceEvent.BIRTH,
                amount="5",
                processing_days=3,
                expense_category=data["assistance"],
            ),
            lambda: services.update_social_assistance_scale(scale=data["scale"], updated_by=ctx.president.user, amount="1"),
            lambda: services.archive_social_assistance_scale(scale=data["scale"], archived_by=ctx.treasurer.user),
            lambda: services.approve_social_assistance_request(request_obj=data["request"], approved_by=ctx.president.user),
            lambda: services.reject_social_assistance_request(
                request_obj=data["request"], rejected_by=ctx.vice_president.user, reason="x"
            ),
            lambda: services.submit_social_assistance_request(
                membership=other_ctx.player,
                submitted_by=ctx.player.user,
                event_type=SocialAssistanceEvent.DEATH,
                event_date=club_today(other_ctx),
                description="x",
                attachment=pdf_file(),
            ),
        ]
        for attempt in attempts:
            with pytest.raises(services.TreasuryPermissionError):
                attempt()
        assert treasury_logs(other_ctx.club).count() == blocked_before
        assert Transaction.all_objects.filter(club=other_ctx.club).count() == tx_before
        assert Expense.all_objects.get(pk=pending.pk).status == Expense.Status.PENDING
        assert SocialAssistanceRequest.all_objects.get(pk=data["request"].pk).status == "submitted"
        assert SocialAssistanceScale.all_objects.get(pk=data["scale"].pk).status == "active"

    def test_reads_of_derived_values_do_not_mix_clubs(self, ctx, other_ctx):
        populate(ctx)
        assert services.can_release_expense(other_ctx.club).allowed is True
        assert services.get_available_cash(other_ctx.club) == 0
        assert services.get_available_cash(ctx.club) != 0
        # L'éligibilité d'un joueur du club B ignore les dettes du joueur homonyme du club A.
        assert services.get_social_assistance_eligibility(other_ctx.player, club_today(other_ctx)).can_be_approved

    def test_one_club_ledger_chain_is_not_affected_by_the_other_clubs_expenses(self, ctx, other_ctx):
        populate(ctx)
        populate(other_ctx)
        assert services.verify_chain(ctx.club).ok and services.verify_chain(other_ctx.club).ok
        first_hashes = set(Transaction.all_objects.filter(club=ctx.club).values_list("hash", flat=True))
        second_hashes = set(Transaction.all_objects.filter(club=other_ctx.club).values_list("hash", flat=True))
        assert not first_hashes & second_hashes
