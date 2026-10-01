"""Revue indépendante : assistance sociale et fichiers (CDC 4.5.3, 6.7, 7.6 ; 10.2 n° 33 et 37).

Complète ``test_social_assistance.py`` sans le modifier : bornes d'éligibilité
au jour près, tolérance de dette, paiements partiels, montant figé, double
approbation, catégorie archivée, fichiers refusés (format, taille, contenu),
stockage privé, données personnelles absentes du journal.
"""

from __future__ import annotations

import datetime
import os
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.clubs.models import ClubSettings, Membership
from apps.treasury import services
from apps.treasury.models import (
    Expense,
    ExpenseAttachment,
    SocialAssistanceEvent,
    SocialAssistanceRequest,
    Transaction,
)
from apps.treasury.tests.conftest import PIN, make_member
from apps.treasury.tests.expense_helpers import (
    PDF_CONTENT,
    club_today,
    days_ago,
    make_category,
    make_expense,
    pay_mandatory,
    pdf_file,
    put_in_debt,
    release,
)
from apps.treasury.tests.expense_review_helpers import (  # noqa: F401  (fixtures)
    dump,
    jpeg_bytes,
    png_bytes,
    staff,
    treasury_logs,
    walk_keys,
)

pytestmark = pytest.mark.django_db

DAY = datetime.timedelta(days=1)


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


# ---------------------------------------------------------------------------
# Éligibilité : bornes au jour près, tolérance, paiements partiels
# ---------------------------------------------------------------------------


class TestEligibilityBoundaries:
    def test_a_due_falling_exactly_on_the_event_day_is_not_yet_a_debt(self, ctx):
        today = club_today(ctx)
        event = today - 10 * DAY
        put_in_debt(ctx, ctx.player, amount="10", due_date=event)  # échéance = jour de l'événement
        eligibility = services.get_social_assistance_eligibility(ctx.player, event, at_date=event)
        assert eligibility.was_in_good_standing_at_event is True
        assert eligibility.eligible is True and eligibility.can_be_approved is True

    def test_a_due_one_day_before_the_event_makes_the_player_ineligible(self, ctx):
        today = club_today(ctx)
        event = today - 10 * DAY
        put_in_debt(ctx, ctx.player, amount="10", due_date=event - DAY)
        eligibility = services.get_social_assistance_eligibility(ctx.player, event)
        assert eligibility.eligible is False
        assert eligibility.amount_to_regularize == Decimal("10.00")

    @pytest.mark.parametrize("tolerance,offset_days,in_debt", [(5, 5, False), (5, 6, True), (0, 0, False), (0, 1, True)])
    def test_club_debt_tolerance_shifts_the_boundary(self, ctx, tolerance, offset_days, in_debt):
        ClubSettings.objects.filter(club=ctx.club).update(debt_tolerance_days=tolerance)
        today = club_today(ctx)
        put_in_debt(ctx, ctx.player, amount="10", due_date=today - offset_days * DAY)
        eligibility = services.get_social_assistance_eligibility(ctx.player, today, at_date=today)
        assert eligibility.can_be_approved is (not in_debt)

    def test_partial_payment_reduces_the_amount_to_regularize_but_does_not_make_the_player_eligible(self, ctx):
        today = club_today(ctx)
        ctype = put_in_debt(ctx, ctx.player, amount="10", due_date=today - 30 * DAY)
        pay_mandatory(ctx, ctx.player, ctype, amount="4")
        eligibility = services.get_social_assistance_eligibility(ctx.player, today - 5 * DAY)
        assert eligibility.can_be_approved is False and eligibility.eligible is False
        assert eligibility.amount_to_regularize == Decimal("6.00")

        pay_mandatory(ctx, ctx.player, ctype, amount="6")
        assert services.get_social_assistance_eligibility(ctx.player, today - 5 * DAY).can_be_approved is True

    def test_overpayment_keeps_the_player_in_order(self, ctx):
        today = club_today(ctx)
        ctype = put_in_debt(ctx, ctx.player, amount="10", due_date=today - 30 * DAY)
        pay_mandatory(ctx, ctx.player, ctype, amount="50")
        eligibility = services.get_social_assistance_eligibility(ctx.player, today)
        assert eligibility.can_be_approved and eligibility.amount_to_regularize == Decimal("0.00")

    def test_debt_of_another_player_or_of_another_club_never_counts(self, ctx, other_ctx):
        put_in_debt(ctx, ctx.treasurer, amount="99", due_date=club_today(ctx) - 30 * DAY)
        put_in_debt(other_ctx, other_ctx.player, amount="99", due_date=club_today(other_ctx) - 30 * DAY)
        assert services.get_social_assistance_eligibility(ctx.player, club_today(ctx)).can_be_approved is True

    def test_an_expense_released_for_the_player_does_not_alter_his_eligibility(self, ctx):
        make_scale(ctx)
        request_obj = submit(ctx)
        expense = services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        release(ctx, expense)
        eligibility = services.get_social_assistance_eligibility(ctx.player, club_today(ctx))
        assert eligibility.can_be_approved is True
        assert services.get_balance(ctx.player) == Decimal("0.00")
        txn = Transaction.all_objects.get(expense=expense)
        assert txn.membership_id == ctx.player.pk and txn.contribution_type_id is None


# ---------------------------------------------------------------------------
# Dépôt d'une demande
# ---------------------------------------------------------------------------


class TestSubmissionEdgeCases:
    def test_event_on_the_club_local_day_is_accepted_and_tomorrow_refused(self, ctx):
        make_scale(ctx)
        assert submit(ctx, event_date=club_today(ctx)).status == SocialAssistanceRequest.Status.SUBMITTED
        with pytest.raises(services.TreasuryValidationError, match="futur"):
            submit(ctx, event_date=club_today(ctx) + DAY)

    def test_old_event_is_accepted(self, ctx):
        make_scale(ctx)
        assert submit(ctx, event_date=club_today(ctx) - 3000 * DAY)

    @pytest.mark.parametrize("event", ["divorce", "", None, "BIRTH"])
    def test_unknown_event_type_is_refused(self, ctx, event):
        make_scale(ctx)
        with pytest.raises(services.TreasuryValidationError, match="Événement inconnu"):
            submit(ctx, event=event)
        assert not SocialAssistanceRequest.all_objects.exists()

    def test_string_or_datetime_event_date_is_refused(self, ctx):
        make_scale(ctx)
        with pytest.raises(services.TreasuryValidationError, match="date"):
            submit(ctx, event_date="2026-01-01")
        with pytest.raises(services.TreasuryValidationError, match="date"):
            submit(ctx, event_date=timezone.now())

    def test_player_in_debt_submission_keeps_the_exact_amount_to_regularize_at_that_time(self, ctx):
        make_scale(ctx)
        ctype = put_in_debt(ctx, ctx.player, amount="12.50", due_date=club_today(ctx) - 30 * DAY)
        request_obj = submit(ctx)
        pay_mandatory(ctx, ctx.player, ctype, amount="12.50")
        request_obj.refresh_from_db()
        assert request_obj.amount_to_regularize == Decimal("12.50")  # instantané figé
        assert request_obj.eligible_at_submission is False
        assert services.get_social_assistance_eligibility(ctx.player, request_obj.event_date).can_be_approved

    def test_pending_departed_and_other_club_members_cannot_submit(self, ctx, other_ctx, staff):
        make_scale(ctx)
        for member in (ctx.pending_member, staff.departed):
            with pytest.raises(services.TreasuryValidationError, match="inscrit"):
                submit(ctx, member)
        with pytest.raises(services.TreasuryPermissionError):
            submit(ctx, ctx.player, by=other_ctx.player)
        assert not SocialAssistanceRequest.all_objects.exists()

    def test_submission_journal_holds_neither_the_description_nor_the_file(self, ctx):
        make_scale(ctx)
        request_obj = submit(ctx, description="Décès de mon père, cérémonie à Gombe.", attachment=pdf_file("acte-secret.pdf"))
        entry = AuditLog.objects.get(action_type="treasury.social_assistance.submitted")
        text = dump(entry.after) + dump(entry.before)
        assert "Gombe" not in text and "acte-secret" not in text and ".pdf" not in text
        assert "description" not in {k.lower() for k in walk_keys(entry.after)}
        assert entry.actor_id == ctx.player.user_id and entry.club_id == ctx.club.pk
        assert request_obj.pk

    def test_a_rejected_submission_writes_no_row_no_log_and_no_file(self, ctx):
        make_scale(ctx)
        before = treasury_logs().count()
        with pytest.raises(services.TreasuryValidationError):
            submit(ctx, attachment=SimpleUploadedFile("faux.pdf", b"pas un pdf", content_type="application/pdf"))
        assert treasury_logs().count() == before
        assert not SocialAssistanceRequest.all_objects.exists()
        root = Path(django_settings.PRIVATE_MEDIA_ROOT)
        assert not root.exists() or not [p for p in root.rglob("*") if p.is_file()]


# ---------------------------------------------------------------------------
# Décision : montant figé, double approbation, catégorie archivée
# ---------------------------------------------------------------------------


class TestDecisionEdgeCases:
    def test_approved_expense_uses_the_amount_frozen_at_submission_not_the_current_scale(self, ctx):
        scale = make_scale(ctx, amount="50")
        request_obj = submit(ctx)
        services.update_social_assistance_scale(scale=scale, updated_by=ctx.president.user, amount="500")
        expense = services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        assert expense.amount == Decimal("50.00")
        assert release(ctx, expense).amount == Decimal("50.00")
        assert services.get_available_cash(ctx.club) == Decimal("-50.00")

    def test_two_approvals_with_a_stale_copy_create_a_single_expense(self, ctx):
        make_scale(ctx)
        request_obj = submit(ctx)
        stale = SocialAssistanceRequest.all_objects.get(pk=request_obj.pk)
        services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        with pytest.raises(services.TreasuryValidationError, match="déjà été traitée"):
            services.approve_social_assistance_request(request_obj=stale, approved_by=ctx.vice_president.user)
        assert Expense.all_objects.filter(social_assistance_request=request_obj).count() == 1
        assert AuditLog.objects.filter(action_type="treasury.social_assistance.approved").count() == 1

    def test_approval_and_rejection_racing_leave_a_single_decision(self, ctx):
        make_scale(ctx)
        request_obj = submit(ctx)
        stale = SocialAssistanceRequest.all_objects.get(pk=request_obj.pk)
        services.reject_social_assistance_request(request_obj=request_obj, rejected_by=ctx.vice_president.user, reason="Non")
        with pytest.raises(services.TreasuryValidationError, match="déjà été traitée"):
            services.approve_social_assistance_request(request_obj=stale, approved_by=ctx.president.user)
        assert not Expense.all_objects.exists()

    def test_approval_refused_when_the_scale_category_was_archived_meanwhile(self, ctx):
        category = assistance_category(ctx)
        scale = make_scale(ctx, category=category)
        request_obj = submit(ctx)
        services.archive_social_assistance_scale(scale=scale, archived_by=ctx.president.user)
        services.archive_expense_category(category=category, archived_by=ctx.president.user)
        with pytest.raises(services.TreasuryValidationError, match="archivée"):
            services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        assert not Expense.all_objects.exists()
        assert SocialAssistanceRequest.all_objects.get(pk=request_obj.pk).status == "submitted"

    def test_partial_repayment_is_not_enough_for_approval_and_full_repayment_is(self, ctx):
        make_scale(ctx)
        ctype = put_in_debt(ctx, ctx.player, amount="10", due_date=club_today(ctx) - 30 * DAY)
        request_obj = submit(ctx)
        pay_mandatory(ctx, ctx.player, ctype, amount="9.99")
        with pytest.raises(services.TreasuryValidationError, match="0.01"):
            services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)
        pay_mandatory(ctx, ctx.player, ctype, amount="0.01")
        assert services.approve_social_assistance_request(request_obj=request_obj, approved_by=ctx.president.user)

    def test_debt_appearing_after_approval_blocks_release_until_repaid(self, ctx):
        make_scale(ctx)
        expense = services.approve_social_assistance_request(request_obj=submit(ctx), approved_by=ctx.president.user)
        ctype = put_in_debt(ctx, ctx.player, amount="10", due_date=club_today(ctx) - DAY)
        with pytest.raises(services.TreasuryValidationError, match="non libérable"):
            release(ctx, expense)
        assert not Transaction.all_objects.filter(expense=expense).exists()
        pay_mandatory(ctx, ctx.player, ctype, amount="10")
        assert release(ctx, expense).status == Expense.Status.RELEASED

    def test_assistance_release_needs_the_pin_and_a_wrong_pin_changes_nothing(self, ctx):
        from apps.accounts.services import InvalidPinError

        make_scale(ctx)
        expense = services.approve_social_assistance_request(request_obj=submit(ctx), approved_by=ctx.president.user)
        with pytest.raises(InvalidPinError):
            services.release_expense(expense=expense, released_by=ctx.vice_president.user, pin="0000")
        assert Expense.all_objects.get(pk=expense.pk).status == Expense.Status.PENDING
        assert not Transaction.all_objects.exists()

    def test_assistance_expense_is_blocked_by_an_unjustified_expense_like_any_other(self, ctx):
        make_scale(ctx)
        expense = services.approve_social_assistance_request(request_obj=submit(ctx), approved_by=ctx.president.user)
        release(ctx, make_expense(ctx, make_category(ctx, name="Autre")), now=days_ago(10))
        with pytest.raises(services.ExpenseReleaseBlockedError):
            release(ctx, expense)
        released = services.release_expense_with_derogation(
            expense=expense, president=ctx.president.user, reason="Décès du père du joueur", pin=PIN
        )
        assert released.status == Expense.Status.RELEASED

    def test_rejection_reason_whitespace_only_is_refused_and_the_request_stays_open(self, ctx):
        make_scale(ctx)
        request_obj = submit(ctx)
        with pytest.raises(services.TreasuryValidationError, match="motif du refus"):
            services.reject_social_assistance_request(request_obj=request_obj, rejected_by=ctx.president.user, reason="  \n ")
        assert SocialAssistanceRequest.all_objects.get(pk=request_obj.pk).status == "submitted"

    def test_functions_without_the_right_cannot_decide(self, ctx, staff):
        make_scale(ctx)
        request_obj = submit(ctx)
        for name, member in staff.all().items():
            with pytest.raises(services.TreasuryPermissionError):
                services.approve_social_assistance_request(request_obj=request_obj, approved_by=member.user)
            with pytest.raises(services.TreasuryPermissionError):
                services.reject_social_assistance_request(request_obj=request_obj, rejected_by=member.user, reason="Non")
        assert not treasury_logs().filter(action_type__contains="social_assistance.approved").exists()

    def test_scale_management_is_denied_to_functions_without_the_right(self, ctx, staff):
        category = assistance_category(ctx)
        for member in staff.all().values():
            with pytest.raises(services.TreasuryPermissionError):
                services.create_social_assistance_scale(
                    club=ctx.club,
                    created_by=member.user,
                    event_type=SocialAssistanceEvent.DEATH,
                    amount="10",
                    processing_days=3,
                    expense_category=category,
                )
        assert not services.SocialAssistanceScale.all_objects.exists()

    @pytest.mark.parametrize("bad", [0, -1, 366, True, "7", 7.5, None])
    def test_scale_processing_days_bounds(self, ctx, bad):
        with pytest.raises(services.TreasuryValidationError, match="délai"):
            make_scale(ctx, days=bad)

    @pytest.mark.parametrize("amount", ["-1", "0", "0.004", "abc", None, 10.5, "10000000000.00"])
    def test_scale_amount_bounds(self, ctx, amount):
        with pytest.raises(services.InvalidAmountError):
            make_scale(ctx, amount=amount)

    def test_scale_amount_is_rounded_half_up(self, ctx):
        assert make_scale(ctx, amount="12.345").amount == Decimal("12.35")


# ---------------------------------------------------------------------------
# Fichiers (CDC 6.7, 7.6, CLAUDE.md règle n° 10)
# ---------------------------------------------------------------------------


def upload(name, content, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)


BAD_FILES = {
    "text_named_pdf": upload("faux.pdf", b"ceci n'est pas un PDF", "application/pdf"),
    "html": upload("page.html", b"<html><script>alert(1)</script></html>", "text/html"),
    "svg": upload("logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>', "image/svg+xml"),
    "gif": upload("anim.gif", b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!", "image/gif"),
    "exe": upload("virus.pdf", b"MZ\x90\x00\x03\x00\x00\x00", "application/pdf"),
    "zip": upload("archive.pdf", b"PK\x03\x04\x14\x00\x00\x00", "application/pdf"),
    "empty": upload("vide.pdf", b"", "application/pdf"),
    "truncated_png": upload("cassee.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", "image/png"),
    "png_magic_with_junk": upload("junk.png", b"\x89PNG\r\n\x1a\n" + b"A" * 200, "image/png"),
}


def _oversize_pdf():
    return upload("gros.pdf", b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024), "application/pdf")


class TestFiles:
    @pytest.mark.parametrize("kind", list(BAD_FILES))
    def test_forbidden_content_is_refused_on_entry_receipt_and_assistance(self, ctx, kind):
        bad = BAD_FILES[kind]
        category = make_category(ctx)

        def fresh():
            bad.seek(0)
            return SimpleUploadedFile(bad.name, bad.read(), content_type=bad.content_type)

        with pytest.raises(services.TreasuryValidationError):
            make_expense(ctx, category, attachment=fresh())
        released = release(ctx, make_expense(ctx, category))
        if kind != "empty":
            with pytest.raises(services.TreasuryValidationError):
                services.justify_expense(expense=released, uploaded_by=ctx.treasurer.user, file=fresh())
        else:
            # `if not file` du service : un fichier nommé mais vide est traité par le validateur.
            with pytest.raises(services.TreasuryValidationError):
                services.justify_expense(expense=released, uploaded_by=ctx.treasurer.user, file=fresh())
        make_scale(ctx)
        with pytest.raises(services.TreasuryValidationError):
            submit(ctx, attachment=fresh())
        assert not ExpenseAttachment.all_objects.exists()
        assert not SocialAssistanceRequest.all_objects.exists()
        assert Expense.all_objects.get(pk=released.pk).status == Expense.Status.RELEASED

    def test_file_larger_than_ten_mebibytes_is_refused_and_exactly_ten_is_accepted(self, ctx):
        category = make_category(ctx)
        with pytest.raises(services.TreasuryValidationError, match="10 Mo"):
            make_expense(ctx, category, attachment=_oversize_pdf())
        exact = upload("dix.pdf", b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 - 9), "application/pdf")
        assert exact.size == 10 * 1024 * 1024
        assert make_expense(ctx, category, attachment=exact).attachments.count() == 1

    def test_oversize_receipt_and_assistance_proof_are_refused(self, ctx):
        released = release(ctx, make_expense(ctx))
        with pytest.raises(services.TreasuryValidationError, match="10 Mo"):
            services.justify_expense(expense=released, uploaded_by=ctx.treasurer.user, file=_oversize_pdf())
        make_scale(ctx)
        with pytest.raises(services.TreasuryValidationError, match="10 Mo"):
            submit(ctx, attachment=_oversize_pdf())

    @pytest.mark.parametrize(
        "name,content",
        [("photo.png", png_bytes()), ("photo.jpg", jpeg_bytes()), ("sans-extension", PDF_CONTENT), ("MAJ.PDF", PDF_CONTENT)],
    )
    def test_real_png_jpeg_and_pdf_are_accepted_whatever_the_name(self, ctx, name, content):
        expense = make_expense(ctx, make_category(ctx), attachment=upload(name, content))
        assert expense.attachments.count() == 1

    def test_renamed_executable_is_refused_even_with_a_pdf_content_type_and_extension(self, ctx):
        with pytest.raises(services.TreasuryValidationError):
            make_expense(ctx, make_category(ctx), attachment=upload("facture.pdf", b"MZ" + b"\x00" * 64, "application/pdf"))

    @pytest.mark.parametrize("name", ["../../evil.pdf", "..\\..\\evil.pdf", "/etc/passwd.pdf", "a" * 300 + ".pdf"])
    def test_hostile_file_names_never_escape_the_private_storage(self, ctx, name):
        expense = make_expense(ctx, make_category(ctx), attachment=upload(name, PDF_CONTENT, "application/pdf"))
        stored = Path(expense.attachments.get().file.path).resolve()
        assert Path(django_settings.PRIVATE_MEDIA_ROOT).resolve() in stored.parents
        assert stored.is_file() and stored.read_bytes() == PDF_CONTENT

    def test_the_configured_private_root_is_never_inside_the_public_media_root(self):
        """Configuration réelle (base.py), pas la redirection de tests du conftest racine."""

        from config.settings import base

        private_root = Path(base.PRIVATE_MEDIA_ROOT).resolve()
        public_root = Path(base.MEDIA_ROOT).resolve()
        assert public_root not in private_root.parents and private_root != public_root
        assert private_root not in public_root.parents

    def test_assistance_proof_is_stored_privately(self, ctx):
        make_scale(ctx)
        request_obj = submit(ctx)
        stored = Path(request_obj.attachment.path).resolve()
        assert Path(django_settings.PRIVATE_MEDIA_ROOT).resolve() in stored.parents
        with pytest.raises(ValueError):
            request_obj.attachment.url  # noqa: B018

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "ÉCART SUSPECTÉ CDC 4.5.2 « Les photos sont compressées à l'envoi » (et 6.7 « 10 Mo avant compression ») : "
            "aucune compression n'existe dans le flux dépenses (apps/treasury/services.py _add_expense_attachment, "
            "models.py ExpenseAttachment) ; l'image est stockée telle quelle."
        ),
    )
    def test_photo_receipt_is_compressed_on_upload(self, ctx):
        from PIL import Image
        import io

        buffer = io.BytesIO()
        Image.frombytes("RGB", (900, 900), os.urandom(900 * 900 * 3)).save(buffer, format="PNG")
        original = buffer.getvalue()
        expense = make_expense(ctx, make_category(ctx), attachment=upload("gros.png", original, "image/png"))
        stored_size = expense.attachments.get().file.size
        assert stored_size < len(original)
