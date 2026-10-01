"""Revue indépendante : règles des dépenses (CDC 4.5.1, 4.5.2, 2.4, 7.2).

Complète ``test_expenses.py`` sans le modifier : montants (arrondis, bornes),
délai de justification et fuseau du club, blocage au jour près, dérogation,
PIN (verrouillage, absence, jamais au journal), interleavings de concurrence,
immuabilité en masse, exhaustivité du journal.

Aucune horloge externe : ``now=`` des services ou la fixture ``set_now``.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import InvalidPinError, PinError, PinLockedError, PinNotSetError
from apps.audit.models import AuditLog, AuditLogImmutableError
from apps.clubs.models import ClubSettings, MembershipRole
from apps.core.tenant import active_club
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import (
    Expense,
    ExpenseAttachment,
    ExpenseCategory,
    ExpenseDerogation,
    LedgerImmutableError,
    SocialAssistanceRequest,
    SocialAssistanceScale,
    Transaction,
)
from apps.treasury.tests.conftest import PIN, WRONG_PIN
from apps.treasury.tests.expense_helpers import (
    club_today,
    days_ago,
    make_category,
    make_expense,
    pdf_file,
    release,
)
from apps.treasury.tests.expense_review_helpers import (  # noqa: F401  (fixtures)
    dump,
    revoke_role,
    set_now,
    staff,
    treasury_logs,
    utc,
    walk_keys,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Montants (Decimal) : arrondis, bornes, valeurs invalides
# ---------------------------------------------------------------------------


class TestAmounts:
    @pytest.mark.parametrize(
        "bad",
        [
            "-5", "-0.01", "0", "0.00", "0.004", "abc", "", "  ", None, "NaN", "Infinity", "-Infinity",
            True, 12.5, "10000000000.00", "1,5", "1 000",
        ],
    )
    def test_invalid_amount_is_refused_and_nothing_is_written(self, ctx, bad):
        category = make_category(ctx)
        with pytest.raises(services.InvalidAmountError):
            make_expense(ctx, category, amount=bad)
        assert not Expense.all_objects.exists()
        assert not treasury_logs().filter(action_type="treasury.expense.created").exists()

    @pytest.mark.parametrize("huge", ["1e30", Decimal("1E+40")])
    def test_astronomical_amount_is_refused_with_a_french_error_not_a_crash(self, ctx, huge):
        with pytest.raises(services.InvalidAmountError):
            make_expense(ctx, make_category(ctx), amount=huge)

    @pytest.mark.parametrize(
        "given,stored",
        [
            ("2.675", "2.68"),  # ROUND_HALF_UP exact (un float donnerait 2.67)
            ("1.005", "1.01"),
            ("0.005", "0.01"),
            ("0.014", "0.01"),
            ("7.125", "7.13"),
            (Decimal("7.125"), "7.13"),
            (5, "5.00"),
            ("  12.5  ", "12.50"),
            ("9999999999.99", "9999999999.99"),
        ],
    )
    def test_amount_is_rounded_half_up_to_two_decimals(self, ctx, given, stored):
        expense = make_expense(ctx, make_category(ctx), amount=given)
        assert Expense.all_objects.get(pk=expense.pk).amount == Decimal(stored)

    def test_ceiling_is_compared_after_rounding(self, ctx):
        category = make_category(ctx, ceiling="100")
        assert make_expense(ctx, category, amount="100.004").amount == Decimal("100.00")
        with pytest.raises(services.TreasuryValidationError, match="plafond"):
            make_expense(ctx, category, amount="100.005")

    def test_ten_releases_of_ten_cents_sum_exactly_without_float_drift(self, ctx):
        category = make_category(ctx, receipt_required=False)
        for _ in range(10):
            release(ctx, make_expense(ctx, category, amount="0.10"))
        assert services.get_available_cash(ctx.club) == Decimal("-1.00")
        amounts = set(Transaction.all_objects.filter(club=ctx.club).values_list("amount", flat=True))
        assert amounts == {Decimal("-0.10")}
        assert services.verify_chain(ctx.club).ok

    def test_largest_storable_amount_is_released_and_summed_exactly(self, ctx):
        category = make_category(ctx, receipt_required=False)
        release(ctx, make_expense(ctx, category, amount="9999999999.99"))
        txn = Transaction.all_objects.get(club=ctx.club)
        assert txn.amount == Decimal("-9999999999.99")
        assert services.get_available_cash(ctx.club) == Decimal("-9999999999.99")

    def test_overlong_text_fields_are_refused(self, ctx):
        category = make_category(ctx)
        with pytest.raises(services.TreasuryValidationError, match="160"):
            make_expense(ctx, category, beneficiary_name="B" * 161)
        with pytest.raises(services.TreasuryValidationError, match="120"):
            make_category(ctx, name="N" * 121)
        assert make_expense(ctx, category, beneficiary_name="B" * 160)


# ---------------------------------------------------------------------------
# Délai de justification : jour exact et fuseau du club (CDC 4.5.2, 7.x)
# ---------------------------------------------------------------------------


class TestJustificationDeadline:
    @pytest.mark.parametrize(
        "tz,now_utc,local_day",
        [
            ("Africa/Kinshasa", utc(2026, 9, 20, 23, 30), datetime.date(2026, 9, 21)),  # UTC+1 : lendemain local
            ("Africa/Kinshasa", utc(2026, 9, 20, 22, 59), datetime.date(2026, 9, 20)),
            ("Africa/Kinshasa", utc(2026, 9, 20, 23, 0), datetime.date(2026, 9, 21)),
            ("America/Los_Angeles", utc(2026, 9, 21, 3, 0), datetime.date(2026, 9, 20)),  # UTC-7 : veille locale
        ],
    )
    def test_deadline_is_computed_on_the_club_local_day_not_on_the_utc_day(self, ctx, tz, now_utc, local_day):
        ClubSettings.objects.filter(club=ctx.club).update(timezone=tz)
        released = release(ctx, make_expense(ctx), now=now_utc)
        assert released.justification_deadline == local_day + datetime.timedelta(days=7)

    @pytest.mark.parametrize("days", [1, 3, 7, 30])
    def test_deadline_is_release_day_plus_the_club_delay(self, ctx, days):
        ClubSettings.objects.filter(club=ctx.club).update(expense_justification_days=days)
        released = release(ctx, make_expense(ctx), now=utc(2026, 9, 1, 10))
        assert released.justification_deadline == datetime.date(2026, 9, 1) + datetime.timedelta(days=days)

    def test_default_delay_is_seven_days(self, ctx):
        assert ClubSettings.objects.get(club=ctx.club).expense_justification_days == 7
        released = release(ctx, make_expense(ctx), now=utc(2026, 9, 1, 10))
        assert released.justification_deadline == datetime.date(2026, 9, 8)

    def test_release_is_still_possible_on_the_last_local_minute_and_blocked_the_next_local_minute(self, ctx):
        """J+7 exact, fuseau Africa/Kinshasa (UTC+1) : échéance le 27, dernier instant 23:59 locale."""

        release(ctx, make_expense(ctx), now=utc(2026, 9, 20, 12))  # échéance locale 2026-09-27
        other = make_expense(ctx, make_category(ctx, name="Autre"))

        last_minute = utc(2026, 9, 27, 22, 59)  # 23:59 locale, le 27
        first_minute_after = utc(2026, 9, 27, 23, 0)  # 00:00 locale, le 28

        with pytest.raises(services.ExpenseReleaseBlockedError):
            release(ctx, other, now=first_minute_after)
        assert Expense.all_objects.get(pk=other.pk).status == Expense.Status.PENDING
        assert release(ctx, other, now=last_minute).status == Expense.Status.RELEASED

    def test_cron_marks_unjustified_only_from_the_local_day_after_the_deadline(self, ctx):
        late = release(ctx, make_expense(ctx), now=utc(2026, 9, 20, 12))  # échéance locale 2026-09-27
        assert services.mark_overdue_expenses_unjustified(ctx.club, now=utc(2026, 9, 27, 22, 59)) == []
        marked = services.mark_overdue_expenses_unjustified(ctx.club, now=utc(2026, 9, 27, 23, 0))
        assert [e.pk for e in marked] == [late.pk]

    def test_pending_and_refused_expenses_never_block_however_old(self, ctx):
        old_pending = make_expense(ctx, make_category(ctx, name="A"), now=days_ago(90))
        refused = make_expense(ctx, make_category(ctx, name="B"), now=days_ago(90))
        services.refuse_expense(expense=refused, refused_by=ctx.president.user, reason="Non", now=days_ago(80))
        check = services.can_release_expense(ctx.club)
        assert check.allowed and check.blocking_expense_ids == ()
        assert release(ctx, old_pending).status == Expense.Status.RELEASED

    def test_expense_justified_after_its_deadline_no_longer_blocks(self, ctx):
        late = release(ctx, make_expense(ctx), now=days_ago(10))
        assert services.can_release_expense(ctx.club).allowed is False
        services.justify_expense(expense=late, uploaded_by=ctx.treasurer.user, file=pdf_file())
        assert services.can_release_expense(ctx.club).allowed is True

    def test_two_unjustified_expenses_both_must_be_justified_to_unblock(self, ctx):
        first = release(ctx, make_expense(ctx), now=days_ago(12))
        second = release(ctx, make_expense(ctx, make_category(ctx, name="Autre")), now=days_ago(11))
        # 2e libération refusée alors que la 1re est en retard ? Non : la 2e a été libérée à J-11 avec
        # blocage évalué à J-11 (la 1re n'était pas encore en retard).
        services.mark_overdue_expenses_unjustified(ctx.club)
        assert services.can_release_expense(ctx.club).blocking_expense_ids == (first.pk, second.pk)
        services.justify_expense(expense=first, uploaded_by=ctx.treasurer.user, file=pdf_file())
        assert services.can_release_expense(ctx.club).blocking_expense_ids == (second.pk,)
        services.justify_expense(expense=second, uploaded_by=ctx.assistant_treasurer.user, file=pdf_file())
        assert services.can_release_expense(ctx.club).allowed is True

    def test_justification_refused_for_refused_or_already_justified_expense(self, ctx):
        refused = make_expense(ctx)
        services.refuse_expense(expense=refused, refused_by=ctx.president.user, reason="Non")
        with pytest.raises(services.TreasuryValidationError, match="libérée ou non justifiée"):
            services.justify_expense(expense=refused, uploaded_by=ctx.treasurer.user, file=pdf_file())

        done = release(ctx, make_expense(ctx, make_category(ctx, name="Autre")))
        services.justify_expense(expense=done, uploaded_by=ctx.treasurer.user, file=pdf_file())
        with pytest.raises(services.TreasuryValidationError, match="libérée ou non justifiée"):
            services.justify_expense(expense=done, uploaded_by=ctx.treasurer.user, file=pdf_file())
        assert ExpenseAttachment.all_objects.filter(kind="receipt").count() == 1

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "ÉCART SUSPECTÉ services.py:2835 (mark_overdue_expenses_unjustified) : sans `actor`, le passage "
            "« Non justifiée » n'écrit AUCUNE entrée de journal (CLAUDE.md règle n° 6, CDC 5.1) ; choix documenté "
            "comme « point ouvert » dans le code, non tranché par le client."
        ),
    )
    def test_automatic_unjustified_transition_is_journalised_even_without_actor(self, ctx):
        release(ctx, make_expense(ctx), now=days_ago(10))
        services.mark_overdue_expenses_unjustified(ctx.club)
        assert AuditLog.objects.filter(action_type="treasury.expense.unjustified").count() == 1


# ---------------------------------------------------------------------------
# Dérogation : cas limites (CDC 4.5.2)
# ---------------------------------------------------------------------------


class TestDerogationEdgeCases:
    def _blocked_club_with_urgent(self, ctx, overdue=1):
        blockers = [
            release(ctx, make_expense(ctx, make_category(ctx, name=f"Ancienne {i}")), now=days_ago(30 - i))
            for i in range(overdue)
        ]
        urgent = make_expense(ctx, make_category(ctx, name="Urgence"), amount="80")
        return blockers, urgent

    def test_derogation_records_every_blocking_expense(self, ctx):
        first = release(ctx, make_expense(ctx, make_category(ctx, name="A1")), now=days_ago(30))
        # 2e libération possible : 1re non encore en retard à J-20 ? Elle l'est (échéance J-23) ->
        # on la débloque par dérogation pour disposer de deux dépenses en retard.
        urgent_a = make_expense(ctx, make_category(ctx, name="U1"))
        services.release_expense_with_derogation(
            expense=urgent_a, president=ctx.president.user, reason="Décès", pin=PIN, now=days_ago(20)
        )
        urgent_b = make_expense(ctx, make_category(ctx, name="U2"))
        released = services.release_expense_with_derogation(
            expense=urgent_b, president=ctx.president.user, reason="Blessé", pin=PIN
        )
        derogation = ExpenseDerogation.all_objects.get(expense=released)
        assert sorted(derogation.blocking_expenses.values_list("pk", flat=True)) == sorted([first.pk, urgent_a.pk])
        assert ExpenseDerogation.all_objects.count() == 2

    def test_second_derogation_needs_its_own_reason_and_normal_release_stays_blocked(self, ctx):
        self._blocked_club_with_urgent(ctx)
        again = make_expense(ctx, make_category(ctx, name="Encore"))
        with pytest.raises(services.ExpenseReleaseBlockedError):
            release(ctx, again, by=ctx.president)
        with pytest.raises(services.TreasuryValidationError, match="motif de la dérogation"):
            services.release_expense_with_derogation(expense=again, president=ctx.president.user, reason="", pin=PIN)

    def test_blank_reason_is_refused_before_the_pin_is_consumed(self, ctx):
        _blockers, urgent = self._blocked_club_with_urgent(ctx)
        with pytest.raises(services.TreasuryValidationError):
            services.release_expense_with_derogation(
                expense=urgent, president=ctx.president.user, reason="   ", pin=WRONG_PIN
            )
        ctx.president.user.refresh_from_db()
        assert ctx.president.user.pin_failed_attempts == 0

    @pytest.mark.parametrize("role", ["vice_president", "treasurer", "assistant_treasurer", "player"])
    def test_derogation_by_a_non_president_is_refused_without_consuming_the_pin(self, ctx, role):
        _blockers, urgent = self._blocked_club_with_urgent(ctx)
        user = getattr(ctx, role).user
        with pytest.raises(services.TreasuryPermissionError):
            services.release_expense_with_derogation(expense=urgent, president=user, reason="Urgence", pin=WRONG_PIN)
        user.refresh_from_db()
        assert user.pin_failed_attempts == 0
        assert not ExpenseDerogation.all_objects.exists()
        assert Expense.all_objects.get(pk=urgent.pk).status == Expense.Status.PENDING

    def test_functions_without_any_expense_right_cannot_derogate(self, ctx, staff):
        _blockers, urgent = self._blocked_club_with_urgent(ctx)
        for name, member in staff.all().items():
            with pytest.raises(services.TreasuryPermissionError):
                services.release_expense_with_derogation(
                    expense=urgent, president=member.user, reason="Urgence", pin=PIN
                )
        assert not ExpenseDerogation.all_objects.exists()

    def test_president_whose_role_was_revoked_loses_the_derogation_right_immediately(self, ctx):
        _blockers, urgent = self._blocked_club_with_urgent(ctx)
        revoke_role(ctx.president, MembershipRole.Role.PRESIDENT)
        with pytest.raises(services.TreasuryPermissionError):
            services.release_expense_with_derogation(
                expense=urgent, president=ctx.president.user, reason="Urgence", pin=PIN
            )

    @pytest.mark.parametrize("final", ["refused", "released"])
    def test_derogation_on_an_expense_that_is_no_longer_pending_is_refused(self, ctx, final):
        self._blocked_club_with_urgent(ctx)
        expense = make_expense(ctx, make_category(ctx, name="Cible"))
        if final == "refused":
            services.refuse_expense(expense=expense, refused_by=ctx.vice_president.user, reason="Non")
        else:
            services.release_expense_with_derogation(
                expense=expense, president=ctx.president.user, reason="Urgence", pin=PIN
            )
        with pytest.raises(services.TreasuryValidationError, match="plus en attente"):
            services.release_expense_with_derogation(
                expense=expense, president=ctx.president.user, reason="Deux fois", pin=PIN
            )
        assert Transaction.all_objects.filter(expense=expense).count() == (1 if final == "released" else 0)

    def test_derogation_journal_entry_carries_actor_club_reason_and_blocking_ids_but_no_pin(self, ctx):
        blockers, urgent = self._blocked_club_with_urgent(ctx)
        services.release_expense_with_derogation(
            expense=urgent, president=ctx.president.user, reason="Décès d'un joueur", pin=PIN
        )
        entry = AuditLog.objects.get(action_type="treasury.expense.derogation_granted")
        assert entry.actor_id == ctx.president.user_id
        assert entry.club_id == ctx.club.pk
        assert entry.after["reason"] == "Décès d'un joueur"
        assert entry.after["blocking_expense_ids"] == [b.pk for b in blockers]
        assert "pin" not in {key.lower() for key in walk_keys(entry.after)}
        # Les deux écritures (dérogation + libération) sont journalisées.
        assert AuditLog.objects.filter(action_type="treasury.expense.released", object_id=str(urgent.pk)).count() == 1


# ---------------------------------------------------------------------------
# PIN (CDC 7.2, CLAUDE.md règle n° 7)
# ---------------------------------------------------------------------------


class TestPin:
    def test_three_wrong_pins_lock_the_president_and_even_the_right_pin_is_then_refused(self, ctx):
        expense = make_expense(ctx)
        user = ctx.president.user
        with pytest.raises(InvalidPinError) as first:
            services.release_expense(expense=expense, released_by=user, pin=WRONG_PIN)
        assert first.value.attempts_remaining == 2
        with pytest.raises(InvalidPinError) as second:
            services.release_expense(expense=expense, released_by=user, pin=WRONG_PIN)
        assert second.value.attempts_remaining == 1
        with pytest.raises(PinLockedError):
            services.release_expense(expense=expense, released_by=user, pin=WRONG_PIN)
        with pytest.raises(PinLockedError):
            services.release_expense(expense=expense, released_by=user, pin=PIN)

        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.PENDING
        assert not Transaction.all_objects.exists()
        assert not AuditLog.objects.filter(action_type="treasury.expense.released").exists()

    def test_release_works_again_once_the_lock_has_expired(self, ctx):
        expense = make_expense(ctx)
        user = ctx.president.user
        for _ in range(3):
            with pytest.raises(PinError):
                services.release_expense(expense=expense, released_by=user, pin=WRONG_PIN)
        User.objects.filter(pk=user.pk).update(pin_locked_until=timezone.now() - datetime.timedelta(seconds=1))
        user.refresh_from_db()
        assert services.release_expense(expense=expense, released_by=user, pin=PIN).status == Expense.Status.RELEASED

    def test_the_pin_lock_is_shared_between_release_and_derogation(self, ctx):
        release(ctx, make_expense(ctx), now=days_ago(10))  # blocage actif
        urgent = make_expense(ctx, make_category(ctx, name="Urgence"))
        user = ctx.president.user
        with pytest.raises(services.ExpenseReleaseBlockedError):
            services.release_expense(expense=urgent, released_by=user, pin=WRONG_PIN)  # bloqué AVANT le PIN
        for _ in range(2):
            with pytest.raises(InvalidPinError):
                services.release_expense_with_derogation(expense=urgent, president=user, reason="U", pin=WRONG_PIN)
        with pytest.raises(PinLockedError):
            services.release_expense_with_derogation(expense=urgent, president=user, reason="U", pin=WRONG_PIN)
        with pytest.raises(PinLockedError):
            services.release_expense_with_derogation(expense=urgent, president=user, reason="U", pin=PIN)
        assert not ExpenseDerogation.all_objects.exists()

    def test_a_validator_who_never_defined_a_pin_cannot_release(self, ctx):
        expense = make_expense(ctx)
        User.objects.filter(pk=ctx.vice_president.user_id).update(pin_hash="")
        ctx.vice_president.user.refresh_from_db()
        with pytest.raises(PinNotSetError):
            services.release_expense(expense=expense, released_by=ctx.vice_president.user, pin=PIN)
        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.PENDING

    @pytest.mark.parametrize("bad_pin", ["", "abcd", "0000", "24680", None, " 2468", "2468 "])
    def test_empty_malformed_or_padded_pin_never_releases(self, ctx, bad_pin):
        expense = make_expense(ctx)
        with pytest.raises(PinError):
            services.release_expense(expense=expense, released_by=ctx.president.user, pin=bad_pin)
        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.PENDING
        assert not Transaction.all_objects.exists()

    def test_pin_is_never_written_to_the_journal_nor_to_the_ledger(self, ctx):
        expense = make_expense(ctx)
        with pytest.raises(InvalidPinError):
            services.release_expense(expense=expense, released_by=ctx.president.user, pin=WRONG_PIN)
        release(ctx, expense)
        late = release(ctx, make_expense(ctx, make_category(ctx, name="Autre")), now=days_ago(10))
        urgent = make_expense(ctx, make_category(ctx, name="Urgence"))
        services.release_expense_with_derogation(expense=urgent, president=ctx.president.user, reason="U", pin=PIN)
        assert late.pk

        pin_hash = User.objects.get(pk=ctx.president.user_id).pin_hash
        for entry in AuditLog.objects.all():
            for content in (entry.before, entry.after):
                assert "pin" not in {key.lower().replace("_hash", "") for key in walk_keys(content)}, entry.action_type
                text = dump(content)
                assert f'"{PIN}"' not in text and f'"{WRONG_PIN}"' not in text
                assert pin_hash not in text
        for txn in Transaction.all_objects.all():
            payload = services.transaction_canonical_payload(txn)
            assert PIN not in payload and WRONG_PIN not in payload

    def test_a_refusal_neither_asks_for_nor_consumes_a_pin_attempt(self, ctx):
        """CDC 4.5.2 : la validation exige le PIN, le refus motivé non (aucun essai consommé)."""

        refused = make_expense(ctx)
        services.refuse_expense(expense=refused, refused_by=ctx.vice_president.user, reason="Doublon")
        ctx.vice_president.user.refresh_from_db()
        assert ctx.vice_president.user.pin_failed_attempts == 0


# ---------------------------------------------------------------------------
# Concurrence : interleavings déterministes (SQLite ne verrouille pas les lignes ;
# un vrai test multi-threads relève de la campagne MariaDB de fin de lot).
# ---------------------------------------------------------------------------


class TestConcurrencyInterleavings:
    def _interleave(self, monkeypatch, action):
        """Exécute ``action`` une seule fois pendant la vérification du PIN du premier appel."""

        real = services.require_valid_pin
        state = {"done": False}

        def wrapper(*, user, pin):
            real(user=user, pin=pin)
            if not state["done"]:
                state["done"] = True
                action()

        monkeypatch.setattr(services, "require_valid_pin", wrapper)

    def test_two_releases_of_a_stale_copy_debit_the_cash_once(self, ctx):
        expense = make_expense(ctx, amount="30")
        stale = Expense.all_objects.get(pk=expense.pk)
        release(ctx, expense, by=ctx.vice_president)
        with pytest.raises(services.TreasuryValidationError, match="plus en attente"):
            services.release_expense(expense=stale, released_by=ctx.president.user, pin=PIN)
        assert Transaction.all_objects.filter(expense=expense).count() == 1
        assert services.get_available_cash(ctx.club) == Decimal("-30.00")
        assert AuditLog.objects.filter(action_type="treasury.expense.released").count() == 1

    def test_release_loses_the_race_when_a_competitor_releases_the_same_expense_during_the_pin_check(
        self, ctx, monkeypatch
    ):
        expense = make_expense(ctx, amount="30")
        self._interleave(monkeypatch, lambda: release(ctx, expense, by=ctx.vice_president))
        with pytest.raises(services.TreasuryValidationError, match="plus en attente"):
            services.release_expense(expense=expense, released_by=ctx.president.user, pin=PIN)
        assert Transaction.all_objects.filter(expense=expense).count() == 1
        assert Expense.all_objects.get(pk=expense.pk).released_by_id == ctx.vice_president.user_id
        assert services.get_available_cash(ctx.club) == Decimal("-30.00")

    def test_blocking_is_reevaluated_under_the_lock_when_another_expense_became_overdue_meanwhile(
        self, ctx, monkeypatch
    ):
        target = make_expense(ctx, make_category(ctx, name="Cible"))
        rival = make_expense(ctx, make_category(ctx, name="Rivale"))
        # La rivale est libérée pendant la vérification du PIN, avec une échéance déjà dépassée.
        self._interleave(monkeypatch, lambda: release(ctx, rival, by=ctx.vice_president, now=days_ago(10)))
        with pytest.raises(services.ExpenseReleaseBlockedError):
            services.release_expense(expense=target, released_by=ctx.president.user, pin=PIN)
        assert Expense.all_objects.get(pk=target.pk).status == Expense.Status.PENDING
        assert Transaction.all_objects.filter(club=ctx.club).count() == 1  # seulement la rivale

    def test_derogation_is_refused_if_the_blocking_expense_was_justified_during_the_pin_check(
        self, ctx, monkeypatch
    ):
        late = release(ctx, make_expense(ctx), now=days_ago(10))
        urgent = make_expense(ctx, make_category(ctx, name="Urgence"))
        self._interleave(
            monkeypatch,
            lambda: services.justify_expense(expense=late, uploaded_by=ctx.treasurer.user, file=pdf_file()),
        )
        with pytest.raises(services.TreasuryValidationError, match="sans dérogation"):
            services.release_expense_with_derogation(
                expense=urgent, president=ctx.president.user, reason="Urgence", pin=PIN
            )
        assert not ExpenseDerogation.all_objects.exists()
        assert Expense.all_objects.get(pk=urgent.pk).status == Expense.Status.PENDING

    def test_refusal_and_release_racing_on_one_expense_leave_a_single_final_state(self, ctx, monkeypatch):
        expense = make_expense(ctx)
        self._interleave(
            monkeypatch,
            lambda: services.refuse_expense(expense=expense, refused_by=ctx.vice_president.user, reason="Non"),
        )
        with pytest.raises(services.TreasuryValidationError, match="plus en attente"):
            services.release_expense(expense=expense, released_by=ctx.president.user, pin=PIN)
        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.REFUSED
        assert not Transaction.all_objects.exists()


# ---------------------------------------------------------------------------
# Immuabilité (mise à jour / suppression en masse et en instance)
# ---------------------------------------------------------------------------


class TestImmutability:
    def _one_of_each(self, ctx):
        category = make_category(ctx)
        pending = make_expense(ctx, category, attachment=pdf_file())
        released = release(ctx, make_expense(ctx, category))
        return category, pending, released

    @pytest.mark.parametrize("model", [Expense, ExpenseAttachment, ExpenseDerogation, SocialAssistanceRequest])
    def test_bulk_update_and_bulk_delete_are_blocked_through_both_managers(self, ctx, model):
        self._one_of_each(ctx)
        with active_club(ctx.club):
            for manager in (model.objects, model.all_objects):
                with pytest.raises(LedgerImmutableError):
                    manager.all().update(club=ctx.club)
                with pytest.raises(LedgerImmutableError):
                    manager.all().delete()

    def test_bulk_update_of_a_pending_expense_is_blocked_too(self, ctx):
        _category, pending, _released = self._one_of_each(ctx)
        with pytest.raises(LedgerImmutableError):
            Expense.all_objects.filter(pk=pending.pk).update(amount=Decimal("1.00"))
        with pytest.raises(LedgerImmutableError):
            Expense.all_objects.filter(pk=pending.pk).update(status=Expense.Status.RELEASED)
        with pytest.raises(LedgerImmutableError):
            Expense.all_objects.bulk_update([pending], ["amount"])

    def test_expense_release_transaction_cannot_be_altered_or_removed_in_bulk(self, ctx):
        _category, _pending, released = self._one_of_each(ctx)
        with pytest.raises(LedgerImmutableError):
            Transaction.all_objects.filter(expense=released).update(amount=Decimal("-0.01"))
        with pytest.raises(LedgerImmutableError):
            Transaction.all_objects.filter(expense=released).delete()
        txn = Transaction.all_objects.get(expense=released)
        txn.amount = Decimal("-0.01")
        with pytest.raises(LedgerImmutableError):
            txn.save()
        with pytest.raises(LedgerImmutableError):
            txn.delete()
        assert services.verify_chain(ctx.club).ok

    def test_released_expense_frozen_fields_cannot_be_rewritten_on_the_instance(self, ctx):
        _category, _pending, released = self._one_of_each(ctx)
        other_category = make_category(ctx, name="Autre")
        for field, value in [
            ("amount", Decimal("1.00")),
            ("category", other_category),
            ("beneficiary_name", "Complice"),
            ("reason", "Autre motif"),
            ("justification_deadline", datetime.date(2099, 1, 1)),
            ("released_by", ctx.treasurer.user),
            ("expense_date", datetime.date(2001, 1, 1)),
        ]:
            stored = Expense.all_objects.get(pk=released.pk)
            setattr(stored, field, value)
            with pytest.raises(LedgerImmutableError):
                stored.save()

    def test_released_expense_cannot_be_moved_back_to_pending_at_the_model_level(self, ctx):
        _category, _pending, released = self._one_of_each(ctx)
        stored = Expense.all_objects.get(pk=released.pk)
        stored.status = Expense.Status.PENDING
        with pytest.raises(LedgerImmutableError):
            stored.save()

    def test_final_states_are_frozen_at_the_model_level(self, ctx):
        refused = make_expense(ctx)
        services.refuse_expense(expense=refused, refused_by=ctx.president.user, reason="Non")
        stored = Expense.all_objects.get(pk=refused.pk)
        stored.status = Expense.Status.PENDING
        with pytest.raises(LedgerImmutableError):
            stored.save()

        justified = release(ctx, make_expense(ctx, make_category(ctx, name="Autre")))
        services.justify_expense(expense=justified, uploaded_by=ctx.treasurer.user, file=pdf_file())
        stored = Expense.all_objects.get(pk=justified.pk)
        stored.status = Expense.Status.RELEASED
        with pytest.raises(LedgerImmutableError):
            stored.save()

    def test_attachment_and_derogation_cannot_be_rewritten(self, ctx):
        _category, pending, _released = self._one_of_each(ctx)
        attachment = pending.attachments.get()
        attachment.kind = ExpenseAttachment.Kind.RECEIPT
        with pytest.raises(LedgerImmutableError):
            attachment.save()
        with pytest.raises(LedgerImmutableError):
            attachment.delete()

    @pytest.mark.parametrize("model", [ExpenseCategory, SocialAssistanceScale])
    def test_categories_and_scales_cannot_be_bulk_deleted(self, ctx, model):
        category = make_category(ctx, good_standing_only=True)
        services.create_social_assistance_scale(
            club=ctx.club,
            created_by=ctx.president.user,
            event_type="birth",
            amount="10",
            processing_days=3,
            expense_category=category,
        )
        target = model.all_objects.filter(club=ctx.club)
        if model is ExpenseCategory:
            # Catégorie vierge (sans dépense ni barème) : seule PROTECT ne la protège pas.
            target = model.all_objects.filter(pk=make_category(ctx, name="Vierge").pk)
        with pytest.raises(LedgerImmutableError):
            target.delete()

    def test_audit_log_of_treasury_actions_is_append_only(self, ctx):
        make_expense(ctx)
        entry = treasury_logs().first()
        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(pk=entry.pk).update(action_type="x")
        with pytest.raises(AuditLogImmutableError):
            AuditLog.objects.filter(action_type__startswith="treasury.").delete()
        entry.action_type = "treasury.forged"
        with pytest.raises(AuditLogImmutableError):
            entry.save()
        with pytest.raises(AuditLogImmutableError):
            entry.delete()


# ---------------------------------------------------------------------------
# Journal : chaque écriture produit une entrée, un échec n'en produit aucune
# ---------------------------------------------------------------------------


class TestJournal:
    def test_full_lifecycle_writes_exactly_the_expected_entries_in_order(self, ctx):
        category = make_category(ctx)
        expense = make_expense(ctx, category, attachment=pdf_file())
        released = release(ctx, expense)
        services.justify_expense(expense=released, uploaded_by=ctx.treasurer.user, file=pdf_file())
        assert [e.action_type for e in treasury_logs(ctx.club)] == [
            "treasury.expense_category.created",
            "treasury.expense.created",
            "treasury.expense_attachment.created",
            "treasury.expense.released",
            "treasury.expense_attachment.created",
            "treasury.expense.justified",
        ]

    def test_every_entry_carries_the_club_and_the_real_actor(self, ctx):
        category = make_category(ctx)
        expense = make_expense(ctx, category, by=ctx.assistant_treasurer)
        release(ctx, expense, by=ctx.vice_president)
        by_type = {e.action_type: e for e in treasury_logs(ctx.club)}
        assert by_type["treasury.expense_category.created"].actor_id == ctx.treasurer.user_id
        assert by_type["treasury.expense.created"].actor_id == ctx.assistant_treasurer.user_id
        assert by_type["treasury.expense.released"].actor_id == ctx.vice_president.user_id
        assert {e.club_id for e in treasury_logs()} == {ctx.club.pk}

    def test_rows_and_journal_entries_match_one_to_one_after_a_mixed_scenario(self, ctx):
        c1 = make_category(ctx, name="C1")
        make_category(ctx, name="C2")
        e1 = make_expense(ctx, c1, attachment=pdf_file())
        e2 = make_expense(ctx, c1)
        services.refuse_expense(expense=e2, refused_by=ctx.president.user, reason="Non")
        late = release(ctx, e1, now=days_ago(10))
        urgent = make_expense(ctx, c1)
        services.release_expense_with_derogation(expense=urgent, president=ctx.president.user, reason="U", pin=PIN)
        services.justify_expense(expense=late, uploaded_by=ctx.treasurer.user, file=pdf_file())

        def count(action):
            return AuditLog.objects.filter(action_type=action).count()

        assert count("treasury.expense_category.created") == ExpenseCategory.all_objects.count() == 2
        assert count("treasury.expense.created") == Expense.all_objects.count() == 3
        assert count("treasury.expense_attachment.created") == ExpenseAttachment.all_objects.count() == 2
        assert count("treasury.expense.refused") == 1
        assert count("treasury.expense.released") == Expense.all_objects.filter(released_by__isnull=False).count() == 2
        assert count("treasury.expense.derogation_granted") == ExpenseDerogation.all_objects.count() == 1
        assert count("treasury.expense.justified") == 1

    def test_refused_actions_leave_no_journal_entry_and_no_state_change(self, ctx, staff):
        expense = make_expense(ctx)
        before = treasury_logs().count()
        attempts = [
            lambda: services.release_expense(expense=expense, released_by=ctx.treasurer.user, pin=PIN),
            lambda: services.release_expense(expense=expense, released_by=staff.coach.user, pin=PIN),
            lambda: services.refuse_expense(expense=expense, refused_by=ctx.treasurer.user, reason="x"),
            lambda: services.refuse_expense(expense=expense, refused_by=ctx.president.user, reason=""),
            lambda: services.create_expense_category(club=ctx.club, created_by=ctx.vice_president.user, name="X"),
            lambda: services.justify_expense(expense=expense, uploaded_by=ctx.treasurer.user, file=pdf_file()),
            lambda: make_expense(ctx, by=ctx.president),
        ]
        for attempt in attempts:
            with pytest.raises(services.TreasuryError):
                attempt()
        assert treasury_logs().count() == before
        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.PENDING

    def test_notifications_and_journal_of_a_club_never_reach_the_other_club(self, ctx, other_ctx):
        release(ctx, make_expense(ctx), now=days_ago(10))
        services.mark_overdue_expenses_unjustified(ctx.club, actor=ctx.president.user)
        foreign_users = {other_ctx.president.user_id, other_ctx.treasurer.user_id, other_ctx.vice_president.user_id}
        assert not Notification.objects.filter(recipient_id__in=foreign_users).exists()
        assert not treasury_logs(other_ctx.club).exists()
