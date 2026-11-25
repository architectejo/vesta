"""Dépenses : catégories, circuit, blocage, dérogation, caisse (tâche 2.2).

Sources : CDC 2.4 (matrice), 4.4.6 (caisse disponible), 4.5.1, 4.5.2, 4.17,
5.3 ; invariant 8 (En attente -> Libérée (Pdt/VP) -> Justifiée ;
Non justifiée après le délai -> blocage ; dérogation Président avec motif,
journalisée). Plus aucun PIN depuis la décision client du 11/10/2026
(CLAUDE.md règle 7) : l'auteur de chaque action est journalisé. ; schema-treasury.md §7, invariant I8.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings as django_settings

from apps.audit.models import AuditLog
from apps.clubs.models import ClubSettings
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import (
    Expense,
    ExpenseAttachment,
    ExpenseCategory,
    ExpenseDerogation,
    LedgerImmutableError,
    Transaction,
)
from apps.treasury.tests.conftest import PIN, assert_logged_by
from apps.treasury.tests.expense_helpers import (
    club_today,
    days_ago,
    make_category,
    make_expense,
    pay_mandatory,
    pdf_file,
    put_in_debt,
    release,
    text_file,
)

pytestmark = pytest.mark.django_db


def logs(action_type):
    return AuditLog.objects.filter(action_type=action_type)


# ---------------------------------------------------------------------------
# Catégories (CDC 4.5.1)
# ---------------------------------------------------------------------------


class TestExpenseCategories:
    @pytest.mark.parametrize("role", ["president", "treasurer"])
    def test_president_and_treasurer_create_with_defaults(self, ctx, role):
        category = services.create_expense_category(
            club=ctx.club, created_by=getattr(ctx, role).user, name="  Matériel  "
        )

        assert category.name == "Matériel"
        assert category.receipt_required is True
        assert category.good_standing_only is False
        assert category.ceiling is None
        assert category.status == ExpenseCategory.Status.ACTIVE
        entry = logs("treasury.expense_category.created").get(object_id=str(category.pk))
        assert entry.after["receipt_required"] is True

    @pytest.mark.parametrize("role", ["vice_president", "assistant_treasurer", "player"])
    def test_other_roles_cannot_create(self, ctx, role):
        with pytest.raises(services.TreasuryPermissionError):
            services.create_expense_category(club=ctx.club, created_by=getattr(ctx, role).user, name="X")
        assert not ExpenseCategory.all_objects.exists()

    def test_duplicate_name_and_invalid_ceiling_refused(self, ctx):
        make_category(ctx, name="Transport")
        with pytest.raises(services.TreasuryValidationError, match="déjà ce nom"):
            make_category(ctx, name="Transport")
        with pytest.raises(services.InvalidAmountError):
            make_category(ctx, name="Soins", ceiling="0")
        with pytest.raises(services.InvalidAmountError):
            make_category(ctx, name="Soins", ceiling=1.5)
        with pytest.raises(services.TreasuryValidationError, match="obligatoire"):
            make_category(ctx, name="   ")

    def test_update_is_logged_and_archived_category_is_frozen(self, ctx):
        category = make_category(ctx, name="Transport")
        services.update_expense_category(
            category=category, updated_by=ctx.president.user, name="Déplacements", ceiling="50", receipt_required=False
        )
        category.refresh_from_db()
        assert (category.name, category.ceiling, category.receipt_required) == ("Déplacements", Decimal("50.00"), False)
        entry = logs("treasury.expense_category.updated").get()
        assert entry.before["name"] == "Transport" and entry.after["name"] == "Déplacements"

        with pytest.raises(services.TreasuryPermissionError):
            services.update_expense_category(category=category, updated_by=ctx.vice_president.user, name="Y")

        services.archive_expense_category(category=category, archived_by=ctx.treasurer.user)
        category.refresh_from_db()
        assert category.status == ExpenseCategory.Status.ARCHIVED and category.archived_at is not None
        assert logs("treasury.expense_category.archived").count() == 1
        with pytest.raises(services.TreasuryValidationError, match="archivée"):
            services.update_expense_category(category=category, updated_by=ctx.president.user, name="Z")
        with pytest.raises(services.TreasuryValidationError, match="déjà archivée"):
            services.archive_expense_category(category=category, archived_by=ctx.president.user)

    def test_category_is_never_deleted(self, ctx):
        category = make_category(ctx)
        with pytest.raises(LedgerImmutableError):
            category.delete()
        assert ExpenseCategory.all_objects.filter(pk=category.pk).exists()

    def test_archived_category_refused_at_entry(self, ctx):
        category = make_category(ctx)
        services.archive_expense_category(category=category, archived_by=ctx.president.user)
        with pytest.raises(services.TreasuryValidationError, match="archivée"):
            make_expense(ctx, category)


# ---------------------------------------------------------------------------
# Saisie (CDC 4.5.2)
# ---------------------------------------------------------------------------


class TestExpenseEntry:
    @pytest.mark.parametrize("role", ["treasurer", "assistant_treasurer"])
    def test_treasurer_and_assistant_enter_a_pending_expense(self, ctx, role):
        # D7 : arrondi d'une valeur Decimal ; une saisie texte à 3 décimales est refusée (D-A7).
        expense = make_expense(ctx, amount=Decimal("25.005"), by=getattr(ctx, role))

        assert expense.status == Expense.Status.PENDING
        assert expense.amount == Decimal("25.01")  # arrondi ROUND_HALF_UP
        assert expense.currency == "USD"
        assert not Transaction.all_objects.filter(club=ctx.club).exists()
        entry = logs("treasury.expense.created").get(object_id=str(expense.pk))
        assert entry.after["status"] == "pending"
        notified = Notification.objects.filter(event_type=Notification.EventType.EXPENSE_SUBMITTED)
        assert {n.recipient_id for n in notified} == {ctx.president.user_id, ctx.vice_president.user_id}

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    def test_other_roles_cannot_enter(self, ctx, role):
        category = make_category(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            make_expense(ctx, category, by=getattr(ctx, role))
        assert not Expense.all_objects.exists()

    def test_invalid_values_refused(self, ctx):
        category = make_category(ctx)
        with pytest.raises(services.InvalidAmountError, match="supérieur à 0"):
            make_expense(ctx, category, amount="0")
        with pytest.raises(services.InvalidAmountError):
            make_expense(ctx, category, amount=12.5)
        with pytest.raises(services.TreasuryValidationError, match="motif"):
            make_expense(ctx, category, reason="  ")
        with pytest.raises(services.TreasuryValidationError, match="bénéficiaire"):
            make_expense(ctx, category, beneficiary_name="")
        with pytest.raises(services.TreasuryValidationError, match="date"):
            make_expense(ctx, category, expense_date="2026-01-01")
        assert not Expense.all_objects.exists()

    def test_beneficiary_name_defaults_to_player_name(self, ctx):
        expense = make_expense(ctx, beneficiary_name="", beneficiary_membership=ctx.player)
        user = ctx.player.user
        assert expense.beneficiary_name == f"{user.first_name} {user.last_name}"

    def test_ceiling_applies_per_expense(self, ctx):
        category = make_category(ctx, ceiling="100")
        assert make_expense(ctx, category, amount="100").amount == Decimal("100.00")
        with pytest.raises(services.TreasuryValidationError, match="plafond"):
            make_expense(ctx, category, amount="100.01")

    def test_good_standing_only_category_requires_a_player_in_good_standing(self, ctx):
        category = make_category(ctx, name="Soins", good_standing_only=True)
        with pytest.raises(services.TreasuryValidationError, match="choisissez le joueur"):
            make_expense(ctx, category)

        put_in_debt(ctx, ctx.player, amount="10")
        with pytest.raises(services.TreasuryValidationError, match="en dette .10.00 USD"):
            make_expense(ctx, category, beneficiary_membership=ctx.player)

        expense = make_expense(ctx, category, beneficiary_membership=ctx.assistant_treasurer)
        assert expense.beneficiary_membership_id == ctx.assistant_treasurer.pk

    def test_supporting_document_is_private_and_real_type_checked(self, ctx):
        expense = make_expense(ctx, attachment=pdf_file())
        attachment = expense.attachments.get()
        assert attachment.kind == ExpenseAttachment.Kind.SUPPORTING
        stored = Path(attachment.file.path).resolve()
        assert Path(django_settings.PRIVATE_MEDIA_ROOT).resolve() in stored.parents
        with pytest.raises(ValueError):
            attachment.file.url  # noqa: B018 -- jamais d'URL publique

        with pytest.raises(services.TreasuryValidationError, match="Format de fichier"):
            make_expense(ctx, make_category(ctx, name="Autre"), attachment=text_file())
        assert Expense.all_objects.count() == 1


# ---------------------------------------------------------------------------
# Refus et libération (CDC 4.5.2, 7.2)
# ---------------------------------------------------------------------------


class TestRefusal:
    @pytest.mark.parametrize("role", ["president", "vice_president"])
    def test_president_or_vp_refuse_with_reason_without_pin(self, ctx, role):
        expense = make_expense(ctx)
        refused = services.refuse_expense(expense=expense, refused_by=getattr(ctx, role).user, reason="Doublon")
        assert refused.status == Expense.Status.REFUSED
        assert refused.refusal_reason == "Doublon"
        assert logs("treasury.expense.refused").count() == 1

    def test_refusal_rules(self, ctx):
        expense = make_expense(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            services.refuse_expense(expense=expense, refused_by=ctx.treasurer.user, reason="x")
        with pytest.raises(services.TreasuryValidationError, match="motif du refus"):
            services.refuse_expense(expense=expense, refused_by=ctx.president.user, reason=" ")
        services.refuse_expense(expense=expense, refused_by=ctx.president.user, reason="Non prévu")
        with pytest.raises(services.TreasuryValidationError, match="plus en attente"):
            release(ctx, expense)
        with pytest.raises(services.TreasuryValidationError, match="plus en attente"):
            services.refuse_expense(expense=expense, refused_by=ctx.president.user, reason="encore")

        stored = Expense.all_objects.get(pk=expense.pk)
        stored.amount = Decimal("1.00")
        with pytest.raises(LedgerImmutableError):
            stored.save()
        with pytest.raises(LedgerImmutableError):
            stored.delete()


class TestRelease:
    @pytest.mark.parametrize("role", ["president", "vice_president"])
    def test_release_creates_a_sealed_negative_transaction(self, ctx, role):
        expense = make_expense(ctx, amount="30")
        released = release(ctx, expense, by=getattr(ctx, role))

        assert released.status == Expense.Status.RELEASED
        assert released.released_by_id == getattr(ctx, role).user_id
        assert released.justification_deadline == club_today(ctx) + datetime.timedelta(days=7)
        txn = Transaction.all_objects.get(expense=released)
        assert txn.kind == Transaction.Kind.EXPENSE_RELEASE
        assert txn.amount == Decimal("-30.00")
        assert txn.status == Transaction.Status.SUCCEEDED and txn.is_sealed
        assert txn.provider == Transaction.Provider.MANUAL and txn.external_ref is None
        assert '"expense":%d' % released.pk in services.transaction_canonical_payload(txn)
        assert services.verify_chain(ctx.club).ok
        entry = logs("treasury.expense.released").get(object_id=str(released.pk))
        assert entry.after["transaction_amount"] == "-30.00"
        assert PIN not in str(entry.after)

    @pytest.mark.parametrize("role", ["treasurer", "assistant_treasurer", "player"])
    def test_other_roles_refused(self, ctx, role):
        expense = make_expense(ctx)
        user = getattr(ctx, role).user
        with pytest.raises(services.TreasuryPermissionError):
            services.release_expense(expense=expense, released_by=user)
        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.PENDING
        assert not Transaction.all_objects.exists()

    def test_release_without_pin_logs_the_author(self, ctx):
        """Décision client du 11/10/2026 : plus de PIN ; l'auteur est journalisé."""

        expense = make_expense(ctx)
        released = services.release_expense(expense=expense, released_by=ctx.vice_president.user)
        assert released.status == Expense.Status.RELEASED
        assert_logged_by("treasury.expense.released", ctx.vice_president.user, club=ctx.club)

    def test_justification_delay_is_configurable_per_club(self, ctx):
        ClubSettings.objects.filter(club=ctx.club).update(expense_justification_days=3)
        released = release(ctx, make_expense(ctx))
        assert released.justification_deadline == club_today(ctx) + datetime.timedelta(days=3)

    def test_without_mandatory_receipt_no_deadline_and_never_blocking(self, ctx):
        category = make_category(ctx, name="Divers", receipt_required=False)
        release(ctx, make_expense(ctx, category), now=days_ago(60))
        assert Expense.all_objects.get().justification_deadline is None
        assert services.can_release_expense(ctx.club).allowed
        assert services.mark_overdue_expenses_unjustified(ctx.club) == []

    def test_released_expense_is_immutable(self, ctx):
        released = release(ctx, make_expense(ctx))
        stored = Expense.all_objects.get(pk=released.pk)
        stored.amount = Decimal("1.00")
        with pytest.raises(LedgerImmutableError):
            stored.save()
        with pytest.raises(LedgerImmutableError):
            Expense.all_objects.get(pk=released.pk).delete()
        with pytest.raises(LedgerImmutableError):
            Expense.all_objects.filter(pk=released.pk).update(amount=1)

    def test_frozen_ledger_blocks_release(self, ctx):
        expense = make_expense(ctx)
        services.freeze_ledger(club=ctx.club, reason="Rupture de chaîne détectée", actor=ctx.president.user)
        with pytest.raises(services.LedgerFrozenError):
            release(ctx, expense)
        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.PENDING

    def test_expense_never_changes_the_beneficiary_balance(self, ctx):
        before = services.get_balance(ctx.player)
        release(ctx, make_expense(ctx, beneficiary_membership=ctx.player))
        assert services.get_balance(ctx.player) == before
        assert services.is_in_good_standing(ctx.player)[0] is True

    def test_lowered_ceiling_blocks_release(self, ctx):
        category = make_category(ctx, ceiling="100")
        expense = make_expense(ctx, category, amount="80")
        services.update_expense_category(category=category, updated_by=ctx.treasurer.user, ceiling="50")
        with pytest.raises(services.TreasuryValidationError, match="plafond"):
            release(ctx, expense)

    def test_good_standing_only_rechecked_at_release(self, ctx):
        category = make_category(ctx, name="Soins", good_standing_only=True)
        expense = make_expense(ctx, category, beneficiary_membership=ctx.player)
        ctype = put_in_debt(ctx, ctx.player, amount="10")
        with pytest.raises(services.TreasuryValidationError, match="réservée aux membres en ordre"):
            release(ctx, expense)

        pay_mandatory(ctx, ctx.player, ctype, amount="10")
        assert release(ctx, expense).status == Expense.Status.RELEASED


# ---------------------------------------------------------------------------
# Justification, blocage et dérogation (CDC 4.5.2 ; invariant 8)
# ---------------------------------------------------------------------------


class TestBlockingAndJustification:
    def test_no_blocking_on_an_empty_club(self, ctx):
        check = services.can_release_expense(ctx.club)
        assert check.allowed is True and check.blocking_expense_ids == ()
        allowed, reason, _ids = check
        assert allowed and reason

    def test_overdue_expense_blocks_immediately_even_before_the_cron(self, ctx):
        late = release(ctx, make_expense(ctx), now=days_ago(10))
        assert Expense.all_objects.get(pk=late.pk).status == Expense.Status.RELEASED

        check = services.can_release_expense(ctx.club)
        assert check.allowed is False
        assert check.blocking_expense_ids == (late.pk,)
        assert check.reason == "Une dépense n'est pas justifiée : aucune nouvelle dépense ne peut être libérée."

        other = make_expense(ctx, make_category(ctx, name="Autre"))
        with pytest.raises(services.ExpenseReleaseBlockedError, match="dérogation"):
            services.release_expense(expense=other, released_by=ctx.president.user)
        assert Expense.all_objects.get(pk=other.pk).status == Expense.Status.PENDING

    def test_deadline_day_itself_is_not_yet_overdue(self, ctx):
        released = release(ctx, make_expense(ctx))
        deadline = released.justification_deadline
        assert services.can_release_expense(ctx.club, today=deadline).allowed is True
        assert services.can_release_expense(ctx.club, today=deadline + datetime.timedelta(days=1)).allowed is False

    def test_cron_function_marks_unjustified_alerts_and_is_idempotent(self, ctx):
        on_time = release(ctx, make_expense(ctx, make_category(ctx, name="Autre")))
        late = release(ctx, make_expense(ctx), now=days_ago(10))

        changed = services.mark_overdue_expenses_unjustified(ctx.club, actor=ctx.president.user)

        assert [e.pk for e in changed] == [late.pk]
        late.refresh_from_db()
        assert late.status == Expense.Status.UNJUSTIFIED and late.unjustified_at is not None
        assert Expense.all_objects.get(pk=on_time.pk).status == Expense.Status.RELEASED
        alerts = Notification.objects.filter(event_type=Notification.EventType.EXPENSE_BLOCKING)
        assert {n.recipient_id for n in alerts} == {
            ctx.treasurer.user_id,
            ctx.assistant_treasurer.user_id,
            ctx.president.user_id,
        }
        assert logs("treasury.expense.unjustified").count() == 1
        assert services.mark_overdue_expenses_unjustified(ctx.club) == []
        assert services.can_release_expense(ctx.club).blocking_expense_ids == (late.pk,)

    def test_receipt_unblocks_releases(self, ctx):
        late = release(ctx, make_expense(ctx), now=days_ago(10))
        services.mark_overdue_expenses_unjustified(ctx.club)
        pending = make_expense(ctx, make_category(ctx, name="Autre"))

        justified = services.justify_expense(expense=late, uploaded_by=ctx.assistant_treasurer.user, file=pdf_file())

        assert justified.status == Expense.Status.JUSTIFIED
        assert justified.attachments.get().kind == ExpenseAttachment.Kind.RECEIPT
        assert logs("treasury.expense.justified").count() == 1
        assert services.can_release_expense(ctx.club).allowed is True
        assert release(ctx, pending).status == Expense.Status.RELEASED

    def test_released_expense_justified_before_the_deadline(self, ctx):
        released = release(ctx, make_expense(ctx))
        justified = services.justify_expense(expense=released, uploaded_by=ctx.treasurer.user, file=pdf_file())
        assert justified.status == Expense.Status.JUSTIFIED
        stored = Expense.all_objects.get(pk=released.pk)
        stored.reason = "modifié"
        with pytest.raises(LedgerImmutableError):
            stored.save()

    def test_justification_rules(self, ctx):
        pending = make_expense(ctx)
        with pytest.raises(services.TreasuryValidationError, match="libérée ou non justifiée"):
            services.justify_expense(expense=pending, uploaded_by=ctx.treasurer.user, file=pdf_file())
        released = release(ctx, pending)
        with pytest.raises(services.TreasuryPermissionError):
            services.justify_expense(expense=released, uploaded_by=ctx.vice_president.user, file=pdf_file())
        with pytest.raises(services.TreasuryValidationError, match="obligatoire"):
            services.justify_expense(expense=released, uploaded_by=ctx.treasurer.user, file=None)
        with pytest.raises(services.TreasuryValidationError, match="Format de fichier"):
            services.justify_expense(expense=released, uploaded_by=ctx.treasurer.user, file=text_file())
        assert Expense.all_objects.get(pk=released.pk).status == Expense.Status.RELEASED
        assert not ExpenseAttachment.all_objects.exists()


class TestDerogation:
    def test_president_releases_despite_blocking_with_reason(self, ctx):
        late = release(ctx, make_expense(ctx), now=days_ago(10))
        urgent = make_expense(ctx, make_category(ctx, name="Décès"), amount="100")

        released = services.release_expense_with_derogation(
            expense=urgent, president=ctx.president.user, reason="Décès d'un joueur"
        )

        assert released.status == Expense.Status.RELEASED
        derogation = ExpenseDerogation.all_objects.get(expense=released)
        assert derogation.reason == "Décès d'un joueur"
        assert derogation.granted_by_id == ctx.president.user_id
        assert list(derogation.blocking_expenses.values_list("pk", flat=True)) == [late.pk]
        entry = logs("treasury.expense.derogation_granted").get()
        assert entry.actor_id == ctx.president.user_id  # auteur journalisé, sans PIN
        assert entry.after["blocking_expense_ids"] == [late.pk]
        assert entry.after["reason"] == "Décès d'un joueur"
        assert Transaction.all_objects.get(expense=released).amount == Decimal("-100.00")
        # La dérogation ne lève pas le blocage pour les suivantes.
        assert services.can_release_expense(ctx.club).allowed is False

        with pytest.raises(LedgerImmutableError):
            derogation.save()
        with pytest.raises(LedgerImmutableError):
            derogation.delete()

    def test_derogation_rules(self, ctx):
        expense = make_expense(ctx)
        with pytest.raises(services.TreasuryValidationError, match="sans dérogation"):
            services.release_expense_with_derogation(
                expense=expense, president=ctx.president.user, reason="Urgence"
            )
        release(ctx, make_expense(ctx, make_category(ctx, name="Autre")), now=days_ago(10))
        with pytest.raises(services.TreasuryPermissionError):
            services.release_expense_with_derogation(
                expense=expense, president=ctx.vice_president.user, reason="Urgence"
            )
        with pytest.raises(services.TreasuryValidationError, match="motif de la dérogation"):
            services.release_expense_with_derogation(
                expense=expense, president=ctx.president.user, reason="  "
            )
        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.PENDING
        assert not ExpenseDerogation.all_objects.exists()

    def test_derogation_never_bypasses_good_standing(self, ctx):
        category = make_category(ctx, name="Soins", good_standing_only=True)
        expense = make_expense(ctx, category, beneficiary_membership=ctx.player)
        put_in_debt(ctx, ctx.player)
        release(ctx, make_expense(ctx, make_category(ctx, name="Autre")), now=days_ago(10))
        with pytest.raises(services.TreasuryValidationError, match="en dette"):
            services.release_expense_with_derogation(
                expense=expense, president=ctx.president.user, reason="Urgence"
            )


# ---------------------------------------------------------------------------
# Caisse disponible (CDC 4.4.6) -- calculée, jamais stockée
# ---------------------------------------------------------------------------


class TestAvailableCash:
    def test_cash_is_receipts_minus_released_expenses(self, ctx, fee_type):
        assert services.get_available_cash(ctx.club) == Decimal("0.00")
        payment = services.record_membership_fee_payment(
            membership=ctx.pending_member,
            amount="5",
            method="cash",
            paid_on=club_today(ctx) - datetime.timedelta(days=2),
            validated_by=ctx.treasurer.user,
        )
        ctype = put_in_debt(ctx, ctx.player, amount="40")
        pay_mandatory(ctx, ctx.player, ctype, amount="40")
        assert services.get_available_cash(ctx.club) == Decimal("45.00")

        release(ctx, make_expense(ctx, amount="12.50"))
        make_expense(ctx, make_category(ctx, name="En attente"), amount="999")  # non libérée
        refused = make_expense(ctx, make_category(ctx, name="Refusée"), amount="999")
        services.refuse_expense(expense=refused, refused_by=ctx.president.user, reason="Non")
        assert services.get_available_cash(ctx.club) == Decimal("32.50")

        reversal = services.request_payment_reversal(payment=payment, reason="Erreur", requested_by=ctx.treasurer.user)
        services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)
        assert services.get_available_cash(ctx.club) == Decimal("27.50")
