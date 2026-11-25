"""API des dépenses, de l'assistance sociale et des capacités (tâche 2.2).

Couvre la matrice 2.4 (chaque endpoint déclare ses rôles), l'absence de PIN
(décision client du 11/10/2026 : auteur journalisé, ``pin`` envoyé ignoré),
le blocage (409), la dérogation, les fichiers privés servis par des vues
authentifiées (CLAUDE.md règle n° 10), l'étanchéité entre clubs (404,
jamais 403) et l'exposition de la devise du club.
"""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.treasury import services
from apps.treasury.models import Expense, SocialAssistanceEvent, SocialAssistanceRequest
from apps.treasury.tests.conftest import PIN, WRONG_PIN, assert_logged_by
from apps.treasury.tests.expense_helpers import (
    PDF_CONTENT,
    club_today,
    days_ago,
    make_category,
    make_expense,
    pdf_file,
    put_in_debt,
    release,
)

pytestmark = pytest.mark.django_db

READERS = ["president", "vice_president", "treasurer", "assistant_treasurer"]


def client_for(member) -> APIClient:
    client = APIClient()
    token = RefreshToken.for_user(member.user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def url(name, *args):
    return reverse(f"treasury:{name}", args=args)


def body(response) -> bytes:
    return b"".join(response.streaming_content)


# ---------------------------------------------------------------------------
# Capacités et devise
# ---------------------------------------------------------------------------


class TestCapabilities:
    EXPECTED = {
        "president": {
            "can_read", "can_write", "can_read_expenses", "can_manage_expense_categories",
            "can_validate_expenses", "can_derogate", "can_manage_assistance_scales",
            "can_process_assistance_requests", "can_request_assistance", "can_decide_payment_reversal",
        },
        "vice_president": {
            "can_read", "can_read_expenses", "can_validate_expenses", "can_process_assistance_requests",
            "can_request_assistance",
        },
        "treasurer": {
            "can_read", "can_write", "can_record_payments", "can_read_expenses",
            "can_manage_expense_categories", "can_submit_expenses", "can_upload_expense_receipts",
            "can_manage_assistance_scales", "can_request_assistance",
        },
        "assistant_treasurer": {
            "can_read", "can_record_payments", "can_read_expenses", "can_submit_expenses",
            "can_upload_expense_receipts", "can_request_assistance",
        },
        "player": {"can_request_assistance"},
    }

    @pytest.mark.parametrize("role", list(EXPECTED))
    def test_capabilities_are_computed_from_roles(self, ctx, role):
        response = client_for(getattr(ctx, role)).get(url("capabilities"))
        assert response.status_code == 200
        assert response.data["currency"] == "USD"
        granted = {key for key, value in response.data["capabilities"].items() if value}
        assert granted == self.EXPECTED[role]

    def test_currency_is_the_active_club_one(self, other_ctx):
        response = client_for(other_ctx.treasurer).get(url("capabilities"))
        assert response.data["currency"] == "CDF"

    def test_cumulated_roles_are_united(self, ctx):
        from django.utils import timezone

        from apps.clubs.models import ClubSettings, MembershipRole
        from apps.clubs.tests.factories import MembershipRoleFactory

        club_settings = ClubSettings.objects.get(club=ctx.club)
        club_settings.board_seats_per_role = 2
        club_settings.save()
        ctx.club.refresh_from_db()
        ctx.assistant_treasurer.refresh_from_db()
        MembershipRoleFactory(
            membership=ctx.assistant_treasurer, club=ctx.club, role=MembershipRole.Role.VICE_PRESIDENT,
            appointed_at=timezone.now(),
        )
        caps = client_for(ctx.assistant_treasurer).get(url("capabilities")).data["capabilities"]
        assert caps["can_submit_expenses"] and caps["can_validate_expenses"]

    def test_unauthenticated_refused(self, ctx):
        assert APIClient().get(url("capabilities")).status_code == 401


# ---------------------------------------------------------------------------
# Catégories
# ---------------------------------------------------------------------------


class TestCategoryApi:
    @pytest.mark.parametrize("role", READERS)
    def test_readers_list_categories(self, ctx, role):
        make_category(ctx, ceiling="100")
        response = client_for(getattr(ctx, role)).get(url("expense-category-list"))
        assert response.status_code == 200
        assert response.data[0]["ceiling"] == "100.00"
        assert response.data[0]["receipt_required"] is True

    def test_player_cannot_read(self, ctx):
        assert client_for(ctx.player).get(url("expense-category-list")).status_code == 403

    @pytest.mark.parametrize("role,expected", [("president", 201), ("treasurer", 201), ("vice_president", 403), ("assistant_treasurer", 403)])
    def test_only_president_and_treasurer_write(self, ctx, role, expected):
        response = client_for(getattr(ctx, role)).post(
            url("expense-category-list"), {"name": "Soins", "good_standing_only": True}, format="json"
        )
        assert response.status_code == expected

    def test_update_archive_and_cross_club(self, ctx, other_ctx):
        category = make_category(ctx)
        client = client_for(ctx.treasurer)
        response = client.patch(url("expense-category-detail", category.pk), {"ceiling": "80"}, format="json")
        assert response.status_code == 200 and response.data["ceiling"] == "80.00"
        response = client.post(url("expense-category-detail", category.pk), {"action": "archive"}, format="json")
        assert response.status_code == 200 and response.data["status"] == "archived"

        foreign = make_category(other_ctx)
        assert client.get(url("expense-category-detail", foreign.pk)).status_code == 404
        assert client.patch(url("expense-category-detail", foreign.pk), {"name": "x"}, format="json").status_code == 404


# ---------------------------------------------------------------------------
# Dépenses
# ---------------------------------------------------------------------------


class TestExpenseApi:
    def payload(self, category, **extra):
        return {
            "category_id": category.pk,
            "amount": "25.00",
            "beneficiary_name": "Pharmacie du Centre",
            "reason": "Soins d'un joueur blessé",
            "expense_date": club_today_str(),
            **extra,
        }

    @pytest.mark.parametrize("role", ["treasurer", "assistant_treasurer"])
    def test_entry_with_optional_document(self, ctx, role):
        category = make_category(ctx)
        response = client_for(getattr(ctx, role)).post(
            url("expense-list"), {**self.payload(category), "attachment": pdf_file()}, format="multipart"
        )
        assert response.status_code == 201, response.data
        assert response.data["status"] == "pending"
        assert response.data["status_label"] == "En attente"
        assert response.data["currency"] == "USD"
        assert response.data["attachments"][0]["kind"] == "supporting"
        assert "/media/" not in response.data["attachments"][0]["download_url"]

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    def test_entry_refused_to_other_roles(self, ctx, role):
        category = make_category(ctx)
        response = client_for(getattr(ctx, role)).post(url("expense-list"), self.payload(category), format="json")
        assert response.status_code == 403
        assert not Expense.all_objects.exists()

    def test_entry_errors_are_in_french(self, ctx, other_ctx):
        category = make_category(ctx, ceiling="10")
        client = client_for(ctx.treasurer)
        response = client.post(url("expense-list"), self.payload(category), format="json")
        assert response.status_code == 400 and "plafond" in response.data["detail"]
        # Référence d'un autre club : 404, comme un objet inexistant (audit sécurité A5).
        response = client.post(url("expense-list"), self.payload(make_category(other_ctx)), format="json")
        assert response.status_code == 404 and "introuvable" in response.data["detail"]
        response = client.post(
            url("expense-list"),
            self.payload(make_category(ctx, name="B"), beneficiary_membership_id=other_ctx.player.pk),
            format="json",
        )
        assert response.status_code == 404 and "introuvable" in response.data["detail"]

    def test_list_filters_and_pagination(self, ctx):
        category = make_category(ctx)
        for _ in range(3):
            make_expense(ctx, category)
        released = release(ctx, make_expense(ctx, category))
        client = client_for(ctx.vice_president)

        response = client.get(url("expense-list"), {"status": "pending", "limit": 2})
        assert response.status_code == 200
        assert response.data["count"] == 3 and len(response.data["results"]) == 2
        assert response.data["next_offset"] == 2
        response = client.get(url("expense-list"), {"status": "released,justified"})
        assert [row["id"] for row in response.data["results"]] == [released.pk]
        assert response.data["results"][0]["justification_deadline"] is not None
        assert response.data["results"][0]["is_overdue"] is False
        assert client.get(url("expense-list"), {"status": "inconnu"}).status_code == 400
        assert client_for(ctx.player).get(url("expense-list")).status_code == 403

    def test_detail_cross_club_is_404(self, ctx, other_ctx):
        foreign = make_expense(other_ctx)
        client = client_for(ctx.president)
        assert client.get(url("expense-detail", foreign.pk)).status_code == 404
        assert client.post(url("expense-release", foreign.pk), {}, format="json").status_code == 404
        assert client.post(url("expense-refuse", foreign.pk), {"reason": "x"}, format="json").status_code == 404
        assert Expense.all_objects.get(pk=foreign.pk).status == Expense.Status.PENDING

    def test_release_without_pin_logs_the_author(self, ctx):
        expense = make_expense(ctx)
        client = client_for(ctx.vice_president)
        response = client.post(url("expense-release", expense.pk), {}, format="json")
        assert response.status_code == 200
        assert response.data["status"] == "released"
        assert response.data["released_by"]["id"] == ctx.vice_president.user_id
        assert_logged_by("treasury.expense.released", ctx.vice_president.user, club=ctx.club)

    def test_release_ignores_a_pin_sent_by_an_old_client(self, ctx):
        expense = make_expense(ctx)
        response = client_for(ctx.vice_president).post(
            url("expense-release", expense.pk), {"pin": WRONG_PIN}, format="json"
        )
        assert response.status_code == 200 and "attempts_remaining" not in response.data
        assert response.data["status"] == "released"

    @pytest.mark.parametrize("role", ["treasurer", "assistant_treasurer", "player"])
    def test_release_refused_to_other_roles(self, ctx, role):
        expense = make_expense(ctx)
        response = client_for(getattr(ctx, role)).post(url("expense-release", expense.pk), {}, format="json")
        assert response.status_code == 403

    def test_refuse_requires_reason(self, ctx):
        expense = make_expense(ctx)
        client = client_for(ctx.president)
        response = client.post(url("expense-refuse", expense.pk), {"reason": ""}, format="json")
        assert response.status_code == 400 and response.data["detail"] == "Indiquez le motif du refus."
        response = client.post(url("expense-refuse", expense.pk), {"reason": "Hors budget"}, format="json")
        assert response.status_code == 200 and response.data["status"] == "refused"

    def test_blocking_derogation_and_receipt_flow(self, ctx):
        late = release(ctx, make_expense(ctx), now=days_ago(10))
        urgent = make_expense(ctx, make_category(ctx, name="Urgence"))

        summary = client_for(ctx.treasurer).get(url("expense-summary")).data
        assert summary["can_release"] is False and summary["blocking_expense_ids"] == [late.pk]
        assert summary["currency"] == "USD"

        response = client_for(ctx.vice_president).post(url("expense-release", urgent.pk), {}, format="json")
        assert response.status_code == 409 and response.data["code"] == "expense_release_blocked"

        response = client_for(ctx.vice_president).post(
            url("expense-derogation", urgent.pk), {"reason": "Blessé"}, format="json"
        )
        assert response.status_code == 403
        response = client_for(ctx.president).post(
            url("expense-derogation", urgent.pk), {"reason": "Blessé à soigner"}, format="json"
        )
        assert response.status_code == 200
        assert response.data["derogation"]["reason"] == "Blessé à soigner"

        detail = client_for(ctx.president).get(url("expense-detail", late.pk)).data
        assert detail["is_overdue"] is True

        response = client_for(ctx.vice_president).post(
            url("expense-receipt", late.pk), {"file": pdf_file()}, format="multipart"
        )
        assert response.status_code == 403
        response = client_for(ctx.assistant_treasurer).post(
            url("expense-receipt", late.pk), {"file": pdf_file("facture.pdf")}, format="multipart"
        )
        assert response.status_code == 200 and response.data["status"] == "justified"
        assert client_for(ctx.treasurer).get(url("expense-summary")).data["can_release"] is True

    def test_available_cash_in_summary(self, ctx):
        release(ctx, make_expense(ctx, amount="7.5"))
        summary = client_for(ctx.president).get(url("expense-summary")).data
        assert summary["available_cash"] == "-7.50"
        assert client_for(ctx.player).get(url("expense-summary")).status_code == 403


class TestExpenseFiles:
    @pytest.mark.parametrize("role", READERS)
    def test_readers_download_documents(self, ctx, role):
        expense = make_expense(ctx, attachment=pdf_file())
        attachment = expense.attachments.get()
        response = client_for(getattr(ctx, role)).get(url("expense-attachment-download", attachment.pk))
        assert response.status_code == 200
        assert response["Content-Disposition"].startswith("attachment")
        assert body(response) == PDF_CONTENT

    def test_player_and_other_club_cannot_download(self, ctx, other_ctx):
        attachment = make_expense(ctx, attachment=pdf_file()).attachments.get()
        assert client_for(ctx.player).get(url("expense-attachment-download", attachment.pk)).status_code == 403
        assert client_for(other_ctx.president).get(url("expense-attachment-download", attachment.pk)).status_code == 404
        assert APIClient().get(url("expense-attachment-download", attachment.pk)).status_code == 401


# ---------------------------------------------------------------------------
# Assistance sociale
# ---------------------------------------------------------------------------


def club_today_str():
    from django.utils import timezone
    from zoneinfo import ZoneInfo

    return timezone.now().astimezone(ZoneInfo("Africa/Kinshasa")).date().isoformat()


def setup_scale(ctx):
    return services.create_social_assistance_scale(
        club=ctx.club,
        created_by=ctx.president.user,
        event_type=SocialAssistanceEvent.DEATH,
        amount="50",
        processing_days=7,
        expense_category=make_category(ctx, name="Assistance sociale", good_standing_only=True),
    )


def submit_via_api(ctx, member):
    return client_for(member).post(
        url("social-assistance-request-list"),
        {
            "event_type": "death",
            "event_date": (club_today(ctx) - datetime.timedelta(days=2)).isoformat(),
            "description": "Décès de ma mère.",
            "attachment": pdf_file("acte.pdf"),
        },
        format="multipart",
    )


class TestAssistanceApi:
    def test_scales_are_readable_by_every_member_and_written_by_president_or_treasurer(self, ctx):
        category = make_category(ctx, name="Assistance", good_standing_only=True)
        payload = {"event_type": "birth", "amount": "30", "processing_days": 5, "expense_category_id": category.pk}
        assert client_for(ctx.vice_president).post(url("social-assistance-scale-list"), payload, format="json").status_code == 403
        response = client_for(ctx.treasurer).post(url("social-assistance-scale-list"), payload, format="json")
        assert response.status_code == 201
        listing = client_for(ctx.player).get(url("social-assistance-scale-list"))
        assert listing.status_code == 200 and listing.data[0]["amount"] == "30.00"
        scale_id = response.data["id"]
        assert client_for(ctx.player).patch(
            url("social-assistance-scale-detail", scale_id), {"amount": "1"}, format="json"
        ).status_code == 403
        response = client_for(ctx.president).patch(
            url("social-assistance-scale-detail", scale_id), {"processing_days": 3}, format="json"
        )
        assert response.status_code == 200 and response.data["processing_days"] == 3

    def test_preview_before_sending(self, ctx):
        response = client_for(ctx.player).get(
            url("social-assistance-preview"), {"event_type": "death", "event_date": club_today(ctx).isoformat()}
        )
        assert response.status_code == 200
        assert response.data["scale_configured"] is False
        setup_scale(ctx)
        put_in_debt(ctx, ctx.player, amount="10")
        data = client_for(ctx.player).get(
            url("social-assistance-preview"), {"event_type": "death", "event_date": club_today(ctx).isoformat()}
        ).data
        assert data["planned_amount"] == "50.00" and data["processing_days"] == 7
        assert data["eligibility"]["amount_to_regularize"] == "10.00"
        assert data["eligibility"]["currency"] == "USD"

    def test_player_submits_and_follows_only_his_own_requests(self, ctx):
        setup_scale(ctx)
        put_in_debt(ctx, ctx.player, amount="10", due_date=club_today(ctx) - datetime.timedelta(days=30))
        response = submit_via_api(ctx, ctx.player)
        assert response.status_code == 201, response.data
        assert response.data["eligible_at_submission"] is False
        assert response.data["amount_to_regularize_at_submission"] == "10.00"
        mine = response.data["id"]
        other = submit_via_api(ctx, ctx.treasurer).data["id"]

        listing = client_for(ctx.player).get(url("social-assistance-request-list")).data
        assert [row["id"] for row in listing["results"]] == [mine]
        assert listing["results"][0]["current_eligibility"] is None
        assert client_for(ctx.player).get(url("social-assistance-request-detail", other)).status_code == 404
        assert client_for(ctx.player).get(url("social-assistance-attachment-download", other)).status_code == 404
        own_file = client_for(ctx.player).get(url("social-assistance-attachment-download", mine))
        assert own_file.status_code == 200 and body(own_file) == PDF_CONTENT

        # Le Trésorier ne voit que ses propres demandes (matrice 2.4 « P »).
        listing = client_for(ctx.treasurer).get(url("social-assistance-request-list")).data
        assert [row["id"] for row in listing["results"]] == [other]

    @pytest.mark.parametrize("role", ["president", "vice_president"])
    def test_president_and_vp_see_all_with_current_eligibility(self, ctx, role):
        setup_scale(ctx)
        put_in_debt(ctx, ctx.player, amount="10")
        request_id = submit_via_api(ctx, ctx.player).data["id"]
        client = client_for(getattr(ctx, role))
        listing = client.get(url("social-assistance-request-list")).data
        assert listing["count"] == 1
        eligibility = listing["results"][0]["current_eligibility"]
        assert eligibility["can_be_approved"] is False and eligibility["amount_to_regularize"] == "10.00"
        mine = client.get(url("social-assistance-request-list"), {"mine": "1"}).data
        assert mine["count"] == 0
        assert client.get(url("social-assistance-attachment-download", request_id)).status_code == 200

    def test_approve_and_reject(self, ctx):
        setup_scale(ctx)
        first = submit_via_api(ctx, ctx.player).data["id"]
        second = submit_via_api(ctx, ctx.assistant_treasurer).data["id"]

        assert client_for(ctx.treasurer).post(url("social-assistance-approve", first), {}, format="json").status_code == 403
        response = client_for(ctx.vice_president).post(url("social-assistance-approve", first), {}, format="json")
        assert response.status_code == 200
        assert response.data["status"] == "approved"
        assert response.data["expense"]["status"] == "pending"

        response = client_for(ctx.president).post(url("social-assistance-reject", second), {"reason": ""}, format="json")
        assert response.status_code == 400
        response = client_for(ctx.president).post(
            url("social-assistance-reject", second), {"reason": "Hors délai"}, format="json"
        )
        assert response.status_code == 200 and response.data["status"] == "rejected"

    def test_approval_refused_while_in_debt(self, ctx):
        setup_scale(ctx)
        put_in_debt(ctx, ctx.player, amount="10", due_date=club_today(ctx) - datetime.timedelta(days=30))
        request_id = submit_via_api(ctx, ctx.player).data["id"]
        response = client_for(ctx.president).post(url("social-assistance-approve", request_id), {}, format="json")
        assert response.status_code == 400
        assert "à régulariser" in response.data["detail"]
        assert "10.2 n° 37" not in response.data["detail"]  # aucune référence interne (D-A10)
        assert SocialAssistanceRequest.all_objects.get(pk=request_id).status == "submitted"

    def test_cross_club_requests_are_404(self, ctx, other_ctx):
        setup_scale(other_ctx)
        foreign = submit_via_api(other_ctx, other_ctx.player).data["id"]
        client = client_for(ctx.president)
        assert client.get(url("social-assistance-request-detail", foreign)).status_code == 404
        assert client.post(url("social-assistance-approve", foreign), {}, format="json").status_code == 404
        assert client.get(url("social-assistance-attachment-download", foreign)).status_code == 404
        assert client.get(url("social-assistance-request-list")).data["count"] == 0

    def test_missing_attachment_is_refused(self, ctx):
        setup_scale(ctx)
        response = client_for(ctx.player).post(
            url("social-assistance-request-list"),
            {"event_type": "death", "event_date": club_today(ctx).isoformat(), "description": "x"},
            format="multipart",
        )
        assert response.status_code == 400
