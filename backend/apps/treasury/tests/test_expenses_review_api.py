"""Revue indépendante : API dépenses et assistance sociale.

Couvre ce que ``test_views_expenses.py`` ne couvrait pas : matrice 2.4 complète
(fonctions sans droit, joueur « En attente », joueur parti, cumul, rôle révoqué,
Superuser), étanchéité entre clubs sur CHAQUE endpoint (lecture, action,
fichier, listes, résumé), PIN par l'API (absent, mal formé, verrouillé, jamais
renvoyé), jour d'échéance J+7 et fuseau vus par l'API, affectation de masse,
fichiers refusés et en-têtes de téléchargement.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import pytest
from django.contrib.auth.hashers import make_password
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.clubs.models import Membership, MembershipRole
from apps.clubs.tests.factories import MembershipFactory
from apps.notifications.models import Notification
from apps.treasury import services
from apps.treasury.models import (
    Expense,
    ExpenseAttachment,
    ExpenseCategory,
    ExpenseDerogation,
    SocialAssistanceEvent,
    SocialAssistanceRequest,
    SocialAssistanceScale,
    Transaction,
)
from apps.treasury.tests.conftest import PIN, WRONG_PIN
from apps.treasury.tests.expense_helpers import (
    PDF_CONTENT,
    club_today,
    days_ago,
    make_category,
    make_expense,
    pdf_file,
    release,
)
from apps.treasury.tests.expense_review_helpers import (  # noqa: F401  (fixtures)
    dump,
    jpeg_bytes,
    revoke_role,
    set_now,
    staff,
    treasury_logs,
    utc,
    walk_keys,
)

pytestmark = pytest.mark.django_db

READERS = {"president", "vice_president", "treasurer", "assistant_treasurer"}
MANAGERS = {"president", "treasurer"}
RECORDERS = {"treasurer", "assistant_treasurer"}
VALIDATORS = {"president", "vice_president"}
DEROGATORS = {"president"}
NON_MEMBERS = {"pending_member", "departed"}


def client_for(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def url(name, *args):
    return reverse(f"treasury:{name}", args=args)


def upload(name, content, content_type="application/octet-stream"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content, content_type=content_type)


# ---------------------------------------------------------------------------
# Monde de test : un club « A » (ctx) et son voisin « B » (other_ctx), chacun avec
# ses catégories, barèmes, dépenses, pièces jointes, demandes.
# ---------------------------------------------------------------------------


@dataclass
class World:
    ctx: object
    category: ExpenseCategory
    spare_category: ExpenseCategory
    scale: SocialAssistanceScale
    pending: Expense
    released: Expense
    overdue: Expense
    pending_attachment: ExpenseAttachment
    request: SocialAssistanceRequest


def build_world(ctx, *, overdue=False) -> World:
    category = make_category(ctx, name="Transport")
    spare = make_category(ctx, name="Disponible")
    assistance = make_category(ctx, name="Assistance sociale", good_standing_only=True)
    scale = services.create_social_assistance_scale(
        club=ctx.club,
        created_by=ctx.president.user,
        event_type=SocialAssistanceEvent.DEATH,
        amount="50",
        processing_days=7,
        expense_category=assistance,
    )
    pending = make_expense(ctx, category, attachment=pdf_file("piece.pdf"))
    released = release(ctx, make_expense(ctx, category, amount="12"))
    overdue_expense = None
    if overdue:
        overdue_expense = release(ctx, make_expense(ctx, category, amount="9"), now=days_ago(10))
    request_obj = services.submit_social_assistance_request(
        membership=ctx.player,
        submitted_by=ctx.player.user,
        event_type=SocialAssistanceEvent.DEATH,
        event_date=club_today(ctx) - datetime.timedelta(days=3),
        description="Décès de mon père, confidentiel.",
        attachment=pdf_file("acte.pdf"),
    )
    return World(
        ctx=ctx,
        category=category,
        spare_category=spare,
        scale=scale,
        pending=pending,
        released=released,
        overdue=overdue_expense,
        pending_attachment=pending.attachments.get(),
        request=request_obj,
    )


@pytest.fixture
def world(ctx) -> World:
    return build_world(ctx)


@pytest.fixture
def foreign(other_ctx) -> World:
    return build_world(other_ctx, overdue=True)


def members_by_role(ctx, staff_) -> dict:
    roles = {
        "president": ctx.president,
        "vice_president": ctx.vice_president,
        "treasurer": ctx.treasurer,
        "assistant_treasurer": ctx.assistant_treasurer,
        "player": ctx.player,
        "pending_member": ctx.pending_member,
    }
    roles.update(staff_.all())
    return roles


def snapshot(club) -> dict:
    """État complet observable d'un club (pour prouver qu'un refus ne change RIEN)."""

    return {
        "expenses": sorted(
            Expense.all_objects.filter(club=club).values_list(
                "pk", "status", "amount", "justification_deadline", "refusal_reason"
            )
        ),
        "categories": sorted(
            ExpenseCategory.all_objects.filter(club=club).values_list("pk", "name", "status", "ceiling")
        ),
        "scales": sorted(
            SocialAssistanceScale.all_objects.filter(club=club).values_list("pk", "status", "amount", "processing_days")
        ),
        "requests": sorted(
            SocialAssistanceRequest.all_objects.filter(club=club).values_list("pk", "status", "planned_amount")
        ),
        "attachments": sorted(ExpenseAttachment.all_objects.filter(club=club).values_list("pk", "kind")),
        "transactions": sorted(Transaction.all_objects.filter(club=club).values_list("pk", "amount", "hash")),
        "derogations": sorted(ExpenseDerogation.all_objects.filter(club=club).values_list("pk", "reason")),
        "journal": AuditLog.objects.filter(club=club).count(),
        "notifications": Notification.objects.filter(club=club).count(),
    }


# ---------------------------------------------------------------------------
# Table des endpoints : méthode, URL, corps, rôles autorisés (matrice 2.4)
# ---------------------------------------------------------------------------


@dataclass
class Endpoint:
    label: str
    method: str
    path: str
    allowed: set
    data: dict | None = None
    format: str = "json"
    mutating: bool = True


def endpoints(w: World) -> list[Endpoint]:
    every_member = {
        "president", "vice_president", "treasurer", "assistant_treasurer", "player", "coach", "captain",
        "doctor", "recruiter", "sports_director_and_steward",
    }
    today = club_today(w.ctx).isoformat()
    return [
        Endpoint("category list GET", "get", url("expense-category-list"), READERS, mutating=False),
        Endpoint("category list POST", "post", url("expense-category-list"), MANAGERS, {"name": "Nouvelle"}),
        Endpoint("category detail GET", "get", url("expense-category-detail", w.category.pk), READERS, mutating=False),
        Endpoint("category detail PATCH", "patch", url("expense-category-detail", w.category.pk), MANAGERS, {"ceiling": "500"}),
        Endpoint(
            "category archive POST", "post", url("expense-category-detail", w.spare_category.pk), MANAGERS,
            {"action": "archive"},
        ),
        Endpoint("expense list GET", "get", url("expense-list"), READERS, mutating=False),
        Endpoint(
            "expense list POST", "post", url("expense-list"), RECORDERS,
            {"category_id": w.category.pk, "amount": "5.00", "beneficiary_name": "X", "reason": "Y", "expense_date": today},
        ),
        Endpoint("expense summary GET", "get", url("expense-summary"), READERS, mutating=False),
        Endpoint("expense detail GET", "get", url("expense-detail", w.pending.pk), READERS, mutating=False),
        Endpoint("expense refuse POST", "post", url("expense-refuse", w.pending.pk), VALIDATORS, {"reason": "Non"}),
        Endpoint("expense release POST", "post", url("expense-release", w.pending.pk), VALIDATORS, {"pin": PIN}),
        Endpoint(
            "expense derogation POST", "post", url("expense-derogation", w.pending.pk), DEROGATORS,
            {"pin": PIN, "reason": "Urgence"},
        ),
        Endpoint(
            "expense receipt POST", "post", url("expense-receipt", w.released.pk), RECORDERS,
            {"file": pdf_file("facture.pdf")}, format="multipart",
        ),
        Endpoint(
            "expense attachment GET", "get", url("expense-attachment-download", w.pending_attachment.pk), READERS,
            mutating=False,
        ),
        Endpoint("scale list GET", "get", url("social-assistance-scale-list"), every_member, mutating=False),
        Endpoint(
            "scale list POST", "post", url("social-assistance-scale-list"), MANAGERS,
            {"event_type": "birth", "amount": "20", "processing_days": 4, "expense_category_id": w.scale.expense_category_id},
        ),
        Endpoint("scale PATCH", "patch", url("social-assistance-scale-detail", w.scale.pk), MANAGERS, {"processing_days": 9}),
        Endpoint("scale archive POST", "post", url("social-assistance-scale-detail", w.scale.pk), MANAGERS, {"action": "archive"}),
        Endpoint(
            "preview GET", "get", url("social-assistance-preview") + f"?event_type=death&event_date={today}", every_member,
            mutating=False,
        ),
        Endpoint("capabilities GET", "get", url("capabilities"), every_member, mutating=False),
        Endpoint("request list GET", "get", url("social-assistance-request-list"), every_member, mutating=False),
        Endpoint("request approve POST", "post", url("social-assistance-approve", w.request.pk), VALIDATORS, {}),
        Endpoint("request reject POST", "post", url("social-assistance-reject", w.request.pk), VALIDATORS, {"reason": "Non"}),
    ]


def call(client, endpoint: Endpoint):
    method = getattr(client, endpoint.method)
    if endpoint.method == "get":
        return method(endpoint.path)
    payload = endpoint.data
    if endpoint.format == "multipart":
        payload = {"file": pdf_file("facture.pdf")}
    return method(endpoint.path, payload, format=endpoint.format)


def endpoint_labels() -> list[str]:
    # Étiquettes statiques (évite de construire un monde à la collecte).
    return [
        "category list GET", "category list POST", "category detail GET", "category detail PATCH",
        "category archive POST", "expense list GET", "expense list POST", "expense summary GET",
        "expense detail GET", "expense refuse POST", "expense release POST", "expense derogation POST",
        "expense receipt POST", "expense attachment GET", "scale list GET", "scale list POST", "scale PATCH",
        "scale archive POST", "preview GET", "capabilities GET", "request list GET", "request approve POST",
        "request reject POST",
    ]


def pick(w: World, label: str) -> Endpoint:
    return next(e for e in endpoints(w) if e.label == label)


# ---------------------------------------------------------------------------
# Matrice des rôles (CDC 2.4)
# ---------------------------------------------------------------------------


class TestRoleMatrix:
    @pytest.mark.parametrize("label", endpoint_labels())
    def test_every_role_without_the_right_gets_403_and_changes_nothing(self, ctx, staff, world, label):
        endpoint = pick(world, label)
        roles = members_by_role(ctx, staff)
        before = snapshot(ctx.club)
        denied = sorted(set(roles) - endpoint.allowed)
        assert denied, "chaque endpoint doit avoir au moins un rôle refusé"
        for role in denied:
            response = call(client_for(roles[role].user), endpoint)
            assert response.status_code == 403, f"{label} : {role} obtient {response.status_code}"
        assert snapshot(ctx.club) == before

    @pytest.mark.parametrize("label", [l for l in endpoint_labels() if l.endswith("GET")])
    def test_every_authorised_role_can_read(self, ctx, staff, world, label):
        endpoint = pick(world, label)
        roles = members_by_role(ctx, staff)
        for role in sorted(endpoint.allowed):
            response = call(client_for(roles[role].user), endpoint)
            assert response.status_code == 200, f"{label} : {role} obtient {response.status_code} {response.data}"

    @pytest.mark.parametrize(
        "label,role",
        [
            (label, role)
            for label, roles in [
                ("category list POST", sorted(MANAGERS)),
                ("category detail PATCH", sorted(MANAGERS)),
                ("category archive POST", sorted(MANAGERS)),
                ("expense list POST", sorted(RECORDERS)),
                ("expense refuse POST", sorted(VALIDATORS)),
                ("expense release POST", sorted(VALIDATORS)),
                ("expense derogation POST", ["president"]),
                ("expense receipt POST", sorted(RECORDERS)),
                ("scale list POST", sorted(MANAGERS)),
                ("scale PATCH", sorted(MANAGERS)),
                ("scale archive POST", sorted(MANAGERS)),
                ("request approve POST", sorted(VALIDATORS)),
                ("request reject POST", sorted(VALIDATORS)),
            ]
            for role in roles
        ],
    )
    def test_every_authorised_role_can_perform_the_write(self, ctx, world, label, role):
        endpoint = pick(world, label)
        if label == "expense derogation POST":
            release(ctx, make_expense(ctx, world.category, amount="3"), now=days_ago(10))  # blocage actif
        response = call(client_for(getattr(ctx, role).user), endpoint)
        assert response.status_code in (200, 201), f"{label} : {role} obtient {response.status_code} {response.data}"

    def test_player_cumulating_two_functions_without_expense_rights_still_gets_nothing(self, ctx, staff, world):
        member = staff.sports_director_and_steward
        assert len(MembershipRole.all_objects.filter(membership=member, revoked_at__isnull=True)) == 2
        for label in ("expense list GET", "expense release POST", "category list POST", "scale list POST"):
            assert call(client_for(member.user), pick(world, label)).status_code == 403

    def test_cumulated_treasurer_and_vice_president_get_the_union_of_both_columns(self, ctx, world):
        from apps.clubs.models import ClubSettings
        from apps.clubs.tests.factories import MembershipRoleFactory
        from django.utils import timezone

        club_settings = ClubSettings.objects.get(club=ctx.club)
        club_settings.board_seats_per_role = 2
        club_settings.save()
        ctx.club.refresh_from_db()
        ctx.treasurer.refresh_from_db()
        MembershipRoleFactory(
            membership=ctx.treasurer, club=ctx.club, role=MembershipRole.Role.VICE_PRESIDENT, appointed_at=timezone.now()
        )
        client = client_for(ctx.treasurer.user)
        assert call(client, pick(world, "expense list POST")).status_code == 201  # colonne Trésorier
        assert call(client, pick(world, "expense release POST")).status_code == 200  # colonne VP
        assert call(client, pick(world, "expense derogation POST")).status_code == 403  # jamais Président

    def test_revoked_function_loses_access_on_the_very_next_request(self, ctx, world):
        client = client_for(ctx.treasurer.user)
        assert call(client, pick(world, "expense list GET")).status_code == 200
        revoke_role(ctx.treasurer, MembershipRole.Role.TREASURER)
        assert call(client, pick(world, "expense list GET")).status_code == 403
        assert call(client, pick(world, "expense list POST")).status_code == 403
        assert client.get(url("capabilities")).data["capabilities"]["can_read_expenses"] is False

    def test_a_president_demoted_to_plain_player_loses_validation_and_derogation(self, ctx, world):
        client = client_for(ctx.president.user)
        revoke_role(ctx.president, MembershipRole.Role.PRESIDENT)
        for label in ("expense release POST", "expense derogation POST", "expense refuse POST", "request approve POST"):
            assert call(client, pick(world, label)).status_code == 403
        assert client.get(url("capabilities")).data["capabilities"]["can_request_assistance"] is True

    def test_superuser_without_a_membership_has_no_access_to_club_expenses(self, ctx, world):
        superuser = User.objects.create_superuser(email="root@example.org", password="x" * 12)
        client = client_for(superuser)
        for label in ("expense list GET", "expense summary GET", "expense release POST", "scale list GET", "request list GET"):
            assert call(client, pick(world, label)).status_code == 403

    def test_departed_player_is_locked_out_of_every_endpoint(self, ctx, staff, world):
        client = client_for(staff.departed.user)
        for endpoint in endpoints(world):
            assert call(client, endpoint).status_code == 403, endpoint.label

    def test_pending_membership_cannot_ask_for_assistance_nor_preview_it(self, ctx, world):
        client = client_for(ctx.pending_member.user)
        response = client.post(
            url("social-assistance-request-list"),
            {
                "event_type": "death",
                "event_date": club_today(ctx).isoformat(),
                "description": "Décès",
                "attachment": pdf_file("acte.pdf"),
            },
            format="multipart",
        )
        assert response.status_code == 403
        assert not SocialAssistanceRequest.all_objects.filter(membership=ctx.pending_member).exists()

    @pytest.mark.parametrize("role", ["coach", "captain", "doctor", "recruiter", "sports_director_and_steward"])
    def test_functions_outside_the_matrix_column_can_still_ask_for_assistance_as_players(self, ctx, staff, world, role):
        member = staff.all()[role]
        response = client_for(member.user).post(
            url("social-assistance-request-list"),
            {
                "event_type": "death",
                "event_date": club_today(ctx).isoformat(),
                "description": "Décès",
                "attachment": pdf_file("acte.pdf"),
            },
            format="multipart",
        )
        assert response.status_code == 201, response.data
        assert response.data["membership_id"] == member.pk

    def test_only_the_requester_president_and_vice_president_see_a_request(self, ctx, staff, world):
        for role, expected in [
            ("player", 200), ("president", 200), ("vice_president", 200),
            ("treasurer", 404), ("assistant_treasurer", 404), ("coach", 404), ("doctor", 404),
        ]:
            member = members_by_role(ctx, staff)[role]
            detail = client_for(member.user).get(url("social-assistance-request-detail", world.request.pk))
            assert detail.status_code == expected, f"détail : {role}"
            attachment = client_for(member.user).get(url("social-assistance-attachment-download", world.request.pk))
            assert attachment.status_code == expected, f"pièce : {role}"
            listing = client_for(member.user).get(url("social-assistance-request-list")).data
            assert (world.request.pk in [r["id"] for r in listing["results"]]) is (expected == 200), f"liste : {role}"

    def test_unauthenticated_requests_are_refused_everywhere(self, ctx, world):
        anonymous = APIClient()
        for endpoint in endpoints(world):
            assert call(anonymous, endpoint).status_code == 401, endpoint.label
        assert anonymous.get(url("social-assistance-attachment-download", world.request.pk)).status_code == 401
        assert anonymous.get(url("social-assistance-request-detail", world.request.pk)).status_code == 401

    def test_capabilities_are_all_false_except_assistance_for_functions_without_treasury_rights(self, ctx, staff):
        for member in (staff.coach, staff.captain, staff.doctor, staff.recruiter, staff.sports_director_and_steward):
            data = client_for(member.user).get(url("capabilities")).data
            granted = {key for key, value in data["capabilities"].items() if value}
            assert granted == {"can_request_assistance"}


# ---------------------------------------------------------------------------
# Étanchéité entre clubs : chaque endpoint, chaque verbe
# ---------------------------------------------------------------------------


class TestCrossClubIsolation:
    def _foreign_targets(self, f: World) -> list[tuple[str, str, str, dict | None, str]]:
        """(libellé, méthode, chemin, corps, rôle du club A qui aurait le droit dans son propre club)."""

        return [
            ("category detail GET", "get", url("expense-category-detail", f.category.pk), None, "president"),
            ("category PATCH", "patch", url("expense-category-detail", f.category.pk), {"name": "Piraté"}, "president"),
            ("category archive", "post", url("expense-category-detail", f.spare_category.pk), {"action": "archive"}, "president"),
            ("expense detail", "get", url("expense-detail", f.pending.pk), None, "president"),
            ("expense refuse", "post", url("expense-refuse", f.pending.pk), {"reason": "Piraté"}, "president"),
            ("expense release", "post", url("expense-release", f.pending.pk), {"pin": PIN}, "president"),
            ("expense derogation", "post", url("expense-derogation", f.pending.pk), {"pin": PIN, "reason": "Piraté"}, "president"),
            ("expense receipt", "post", url("expense-receipt", (f.overdue or f.released).pk), "file", "treasurer"),
            ("expense receipt (released)", "post", url("expense-receipt", f.released.pk), "file", "assistant_treasurer"),
            ("expense attachment", "get", url("expense-attachment-download", f.pending_attachment.pk), None, "president"),
            ("scale PATCH", "patch", url("social-assistance-scale-detail", f.scale.pk), {"amount": "1"}, "president"),
            ("scale archive", "post", url("social-assistance-scale-detail", f.scale.pk), {"action": "archive"}, "treasurer"),
            ("request detail", "get", url("social-assistance-request-detail", f.request.pk), None, "president"),
            ("request approve", "post", url("social-assistance-approve", f.request.pk), {}, "president"),
            ("request reject", "post", url("social-assistance-reject", f.request.pk), {"reason": "Piraté"}, "vice_president"),
            ("request attachment", "get", url("social-assistance-attachment-download", f.request.pk), None, "president"),
        ]

    def test_every_pk_endpoint_answers_404_for_the_other_club_and_changes_nothing(self, ctx, other_ctx, world, foreign):
        before_foreign = snapshot(other_ctx.club)
        before_own = snapshot(ctx.club)
        for label, method, path, data, role in self._foreign_targets(foreign):
            client = client_for(getattr(ctx, role).user)
            if data == "file":
                response = client.post(path, {"file": pdf_file("piraté.pdf")}, format="multipart")
            elif method == "get":
                response = client.get(path)
            else:
                response = getattr(client, method)(path, data, format="json")
            assert response.status_code == 404, f"{label} : {response.status_code} {getattr(response, 'data', '')}"
        assert snapshot(other_ctx.club) == before_foreign
        assert snapshot(ctx.club) == before_own

    def test_the_same_holds_in_the_other_direction(self, ctx, other_ctx, world, foreign):
        before = snapshot(ctx.club)
        for label, method, path, data, role in self._foreign_targets(world):
            client = client_for(getattr(other_ctx, role).user)
            if data == "file":
                response = client.post(path, {"file": pdf_file("x.pdf")}, format="multipart")
            elif method == "get":
                response = client.get(path)
            else:
                response = getattr(client, method)(path, data, format="json")
            assert response.status_code == 404, f"{label} : {response.status_code}"
        assert snapshot(ctx.club) == before

    def test_a_foreign_object_is_indistinguishable_from_a_missing_one(self, ctx, other_ctx, world, foreign):
        client = client_for(ctx.president.user)
        missing = client.get(url("expense-detail", 999999))
        alien = client.get(url("expense-detail", foreign.pending.pk))
        assert (missing.status_code, missing.data) == (alien.status_code, alien.data)
        missing = client.get(url("expense-attachment-download", 999999))
        alien = client.get(url("expense-attachment-download", foreign.pending_attachment.pk))
        assert (missing.status_code, missing.data) == (alien.status_code, alien.data)

    def test_lists_and_summary_never_contain_a_single_foreign_row(self, ctx, other_ctx, world, foreign):
        president = client_for(ctx.president.user)
        own_ids = set(Expense.all_objects.filter(club=ctx.club).values_list("pk", flat=True))
        foreign_ids = set(Expense.all_objects.filter(club=other_ctx.club).values_list("pk", flat=True))
        assert foreign_ids and not (own_ids & foreign_ids)

        listing = president.get(url("expense-list"), {"limit": 100}).data
        assert {row["id"] for row in listing["results"]} == own_ids and listing["count"] == len(own_ids)
        for status_filter in ("pending", "released", "unjustified", "released,justified,unjustified"):
            rows = president.get(url("expense-list"), {"status": status_filter, "limit": 100}).data["results"]
            assert not ({row["id"] for row in rows} & foreign_ids)
        by_category = president.get(url("expense-list"), {"category": foreign.category.pk}).data
        assert by_category["count"] == 0

        categories = president.get(url("expense-category-list"), {"status": "active"}).data
        assert {c["id"] for c in categories} == set(
            ExpenseCategory.all_objects.filter(club=ctx.club, status="active").values_list("pk", flat=True)
        )
        archived = president.get(url("expense-category-list"), {"status": "archived"}).data
        assert archived == []

        scales = client_for(ctx.player.user).get(url("social-assistance-scale-list")).data
        assert {s["id"] for s in scales} == {world.scale.pk}
        requests_ = president.get(url("social-assistance-request-list"), {"limit": 100}).data
        assert {r["id"] for r in requests_["results"]} == {world.request.pk}

        summary = president.get(url("expense-summary")).data
        assert summary["can_release"] is True and summary["blocking_expense_ids"] == []
        assert foreign.overdue.pk not in summary["blocking_expense_ids"]
        assert summary["currency"] == "USD"
        # Le voisin, lui, est bloqué et en CDF, avec sa propre caisse.
        foreign_summary = client_for(other_ctx.president.user).get(url("expense-summary")).data
        assert foreign_summary["can_release"] is False and foreign_summary["blocking_expense_ids"] == [foreign.overdue.pk]
        assert foreign_summary["currency"] == "CDF"
        assert foreign_summary["available_cash"] != summary["available_cash"]

    def test_the_text_of_a_foreign_row_never_appears_in_any_list_response(self, ctx, other_ctx, world):
        make_expense(other_ctx, make_category(other_ctx, name="SECRET-B"), beneficiary_name="BENEFICIAIRE-SECRET-B", reason="MOTIF-SECRET-B")
        client = client_for(ctx.president.user)
        for path in (
            url("expense-list"), url("expense-category-list"), url("expense-summary"),
            url("social-assistance-request-list"), url("social-assistance-scale-list"), url("capabilities"),
        ):
            content = client.get(path).content.decode()
            assert "SECRET-B" not in content, path

    def test_creation_with_foreign_references_is_refused_and_writes_nothing(self, ctx, other_ctx, world, foreign):
        # 404 (et non 400) : un identifiant d'un autre club est traité comme
        # inexistant, cohérent avec le reste du projet (audit sécurité A5).
        before_a, before_b = snapshot(ctx.club), snapshot(other_ctx.club)
        treasurer = client_for(ctx.treasurer.user)
        today = club_today(ctx).isoformat()
        base = {"amount": "5.00", "beneficiary_name": "X", "reason": "Y", "expense_date": today}
        assert treasurer.post(url("expense-list"), {**base, "category_id": foreign.category.pk}, format="json").status_code == 404
        assert treasurer.post(
            url("expense-list"),
            {**base, "category_id": world.category.pk, "beneficiary_membership_id": other_ctx.player.pk},
            format="json",
        ).status_code == 404
        president = client_for(ctx.president.user)
        assert president.post(
            url("social-assistance-scale-list"),
            {"event_type": "birth", "amount": "5", "processing_days": 3, "expense_category_id": foreign.scale.expense_category_id},
            format="json",
        ).status_code == 404
        assert president.patch(
            url("social-assistance-scale-detail", world.scale.pk), {"expense_category_id": foreign.scale.expense_category_id}, format="json"
        ).status_code == 404
        assert snapshot(ctx.club) == before_a and snapshot(other_ctx.club) == before_b

    def test_a_player_of_club_a_cannot_file_a_request_on_behalf_of_a_player_of_club_b(self, ctx, other_ctx, world, foreign):
        response = client_for(ctx.player.user).post(
            url("social-assistance-request-list"),
            {
                "event_type": "death",
                "event_date": club_today(ctx).isoformat(),
                "description": "Usurpation",
                "attachment": pdf_file("acte.pdf"),
                "membership_id": other_ctx.player.pk,
                "club": other_ctx.club.pk,
            },
            format="multipart",
        )
        assert response.status_code == 201
        created = SocialAssistanceRequest.all_objects.get(pk=response.data["id"])
        assert created.club_id == ctx.club.pk and created.membership_id == ctx.player.pk

    @pytest.mark.parametrize("header", [{"HTTP_X_CLUB_ID": "OTHER"}, {"HTTP_X_TENANT_ID": "OTHER"}, {"HTTP_X_CLUB": "OTHER"}])
    def test_a_club_id_header_or_query_parameter_never_switches_the_club(self, ctx, other_ctx, world, foreign, header):
        headers = {key: str(other_ctx.club.pk) for key in header}
        client = client_for(ctx.president.user)
        response = client.get(url("expense-list"), **headers)
        assert {row["id"] for row in response.data["results"]} == set(
            Expense.all_objects.filter(club=ctx.club).values_list("pk", flat=True)
        )
        response = client.get(url("expense-list"), {"club": other_ctx.club.pk, "club_id": other_ctx.club.pk, "tenant_id": other_ctx.club.pk})
        assert {row["id"] for row in response.data["results"]} == set(
            Expense.all_objects.filter(club=ctx.club).values_list("pk", flat=True)
        )

    def test_user_with_active_memberships_in_two_clubs_gets_no_data_from_either(self, ctx, other_ctx, world, foreign):
        MembershipFactory(club=other_ctx.club, user=ctx.president.user, status=Membership.Status.ACTIVE)
        client = client_for(ctx.president.user)
        for path in (url("expense-list"), url("expense-summary"), url("expense-category-list"), url("social-assistance-request-list")):
            response = client.get(path)
            assert response.status_code in (400, 403, 404), path
            assert "results" not in getattr(response, "data", {}) or response.data["results"] == []

    def test_foreign_president_cannot_release_even_with_a_correct_pin_and_pin_counter_is_untouched(self, ctx, other_ctx, world, foreign):
        response = client_for(ctx.president.user).post(url("expense-release", foreign.pending.pk), {"pin": PIN}, format="json")
        assert response.status_code == 404
        assert not Transaction.all_objects.filter(expense=foreign.pending).exists()
        # Wrong PIN on a foreign object must not burn an attempt either (404 avant tout contrôle de PIN).
        client_for(ctx.president.user).post(url("expense-release", foreign.pending.pk), {"pin": WRONG_PIN}, format="json")
        ctx.president.user.refresh_from_db()
        assert ctx.president.user.pin_failed_attempts == 0

    def test_cron_style_marking_only_touches_the_requested_club(self, ctx, other_ctx, world, foreign):
        assert foreign.overdue.status == Expense.Status.RELEASED
        services.mark_overdue_expenses_unjustified(ctx.club, actor=ctx.president.user)
        assert Expense.all_objects.get(pk=foreign.overdue.pk).status == Expense.Status.RELEASED
        services.mark_overdue_expenses_unjustified(other_ctx.club, actor=other_ctx.president.user)
        assert Expense.all_objects.get(pk=foreign.overdue.pk).status == Expense.Status.UNJUSTIFIED
        assert not Notification.objects.filter(
            recipient_id__in=[ctx.president.user_id, ctx.treasurer.user_id, ctx.assistant_treasurer.user_id]
        ).filter(event_type=Notification.EventType.EXPENSE_BLOCKING).exists()


# ---------------------------------------------------------------------------
# PIN par l'API (CDC 7.2)
# ---------------------------------------------------------------------------


class TestPinThroughTheApi:
    def _release(self, client, expense, **body):
        return client.post(url("expense-release", expense.pk), body, format="json")

    def test_missing_empty_and_oversized_pin_are_rejected_before_any_attempt_is_counted(self, ctx, world):
        client = client_for(ctx.vice_president.user)
        for body in ({}, {"pin": ""}, {"pin": "1" * 13}, {"pin": None}, {"pin": ["2468"]}):
            response = self._release(client, world.pending, **body)
            assert response.status_code == 400, body
        ctx.vice_president.user.refresh_from_db()
        assert ctx.vice_president.user.pin_failed_attempts == 0
        assert Expense.all_objects.get(pk=world.pending.pk).status == Expense.Status.PENDING

    @pytest.mark.parametrize("bad", ["abcd", "24", "24681", "246 8", "٢٤٦٨", "0000"])
    def test_malformed_or_wrong_pins_never_release(self, ctx, world, bad):
        response = self._release(client_for(ctx.president.user), world.pending, pin=bad)
        assert response.status_code == 400
        assert Expense.all_objects.get(pk=world.pending.pk).status == Expense.Status.PENDING
        assert not Transaction.all_objects.filter(expense=world.pending).exists()

    def test_attempts_remaining_then_423_lock_then_even_the_right_pin_is_refused(self, ctx, world):
        client = client_for(ctx.president.user)
        first = self._release(client, world.pending, pin=WRONG_PIN)
        second = self._release(client, world.pending, pin=WRONG_PIN)
        third = self._release(client, world.pending, pin=WRONG_PIN)
        fourth = self._release(client, world.pending, pin=PIN)
        assert (first.status_code, first.data["attempts_remaining"]) == (400, 2)
        assert (second.status_code, second.data["attempts_remaining"]) == (400, 1)
        assert third.status_code == 423 and third.data["locked_until"]
        assert fourth.status_code == 423
        assert Expense.all_objects.get(pk=world.pending.pk).status == Expense.Status.PENDING

    def test_the_lock_also_blocks_the_derogation_endpoint(self, ctx, world):
        release(ctx, make_expense(ctx, world.category, amount="3"), now=days_ago(10))
        client = client_for(ctx.president.user)
        for _ in range(3):
            client.post(url("expense-derogation", world.pending.pk), {"pin": WRONG_PIN, "reason": "U"}, format="json")
        response = client.post(url("expense-derogation", world.pending.pk), {"pin": PIN, "reason": "U"}, format="json")
        assert response.status_code == 423
        assert not ExpenseDerogation.all_objects.exists()

    def test_user_without_a_pin_gets_a_clear_french_error(self, ctx, world):
        User.objects.filter(pk=ctx.vice_president.user_id).update(pin_hash="")
        response = self._release(client_for(ctx.vice_president.user), world.pending, pin=PIN)
        assert response.status_code == 400 and "PIN" in response.data["detail"]
        assert Expense.all_objects.get(pk=world.pending.pk).status == Expense.Status.PENDING

    def test_blocked_release_answers_409_before_the_pin_is_examined(self, ctx, world):
        release(ctx, make_expense(ctx, world.category, amount="3"), now=days_ago(10))
        client = client_for(ctx.vice_president.user)
        assert self._release(client, world.pending, pin=WRONG_PIN).status_code == 409
        ctx.vice_president.user.refresh_from_db()
        assert ctx.vice_president.user.pin_failed_attempts == 0

    def test_derogation_requires_reason_and_pin_and_only_when_blocked(self, ctx, world):
        client = client_for(ctx.president.user)
        path = url("expense-derogation", world.pending.pk)
        assert client.post(path, {"pin": PIN, "reason": "Urgence"}, format="json").status_code == 400  # pas bloqué
        release(ctx, make_expense(ctx, world.category, amount="3"), now=days_ago(10))
        assert client.post(path, {"pin": PIN}, format="json").status_code == 400
        assert client.post(path, {"pin": PIN, "reason": "   "}, format="json").status_code == 400
        assert client.post(path, {"reason": "Urgence"}, format="json").status_code == 400
        assert not ExpenseDerogation.all_objects.exists()
        ok = client.post(path, {"pin": PIN, "reason": "Blessé à soigner"}, format="json")
        assert ok.status_code == 200 and ok.data["derogation"]["reason"] == "Blessé à soigner"

    def test_neither_responses_nor_journal_ever_contain_the_pin(self, ctx, world):
        client = client_for(ctx.president.user)
        bodies = []
        for pin in (WRONG_PIN, PIN):
            response = self._release(client, world.pending, pin=pin)
            bodies.append(response.content.decode())
        release(ctx, make_expense(ctx, world.category, amount="3"), now=days_ago(10))
        urgent = make_expense(ctx, make_category(ctx, name="Urgence"))
        response = client.post(url("expense-derogation", urgent.pk), {"pin": PIN, "reason": "Décès"}, format="json")
        bodies.append(response.content.decode())
        for body in bodies:
            assert f'"{PIN}"' not in body and f'"{WRONG_PIN}"' not in body and '"pin"' not in body
        pin_hash = User.objects.get(pk=ctx.president.user_id).pin_hash
        for entry in AuditLog.objects.all():
            text = dump(entry.before) + dump(entry.after)
            assert f'"{PIN}"' not in text and f'"{WRONG_PIN}"' not in text and pin_hash not in text
            assert "pin" not in {key.lower() for key in walk_keys(entry.after)}


# ---------------------------------------------------------------------------
# Échéance J+7 et fuseau du club vus par l'API
# ---------------------------------------------------------------------------


class TestDeadlineThroughTheApi:
    def test_seven_day_window_closes_at_the_club_local_midnight(self, ctx, set_now):
        category = make_category(ctx, name="Transport")
        first = make_expense(ctx, category)
        second = make_expense(ctx, make_category(ctx, name="Autre"))

        set_now(utc(2026, 9, 20, 12))  # 13h locale, échéance = 2026-09-27
        response = client_for(ctx.president.user).post(url("expense-release", first.pk), {"pin": PIN}, format="json")
        assert response.status_code == 200 and response.data["justification_deadline"] == datetime.date(2026, 9, 27)

        set_now(utc(2026, 9, 27, 22, 59))  # 23h59 locale : dernier instant valide
        client = client_for(ctx.vice_president.user)
        assert client.get(url("expense-detail", first.pk)).data["is_overdue"] is False
        assert client.get(url("expense-summary")).data["can_release"] is True

        set_now(utc(2026, 9, 27, 23, 0))  # 00h00 locale du 28 : en retard
        assert client.get(url("expense-detail", first.pk)).data["is_overdue"] is True
        summary = client.get(url("expense-summary")).data
        assert summary["can_release"] is False and summary["blocking_expense_ids"] == [first.pk]
        blocked = client.post(url("expense-release", second.pk), {"pin": PIN}, format="json")
        assert blocked.status_code == 409 and blocked.data["code"] == "expense_release_blocked"

    def test_blocking_lifts_through_the_receipt_endpoint_and_the_next_release_passes(self, ctx, world):
        late = release(ctx, make_expense(ctx, world.category, amount="4"), now=days_ago(10))
        target = make_expense(ctx, make_category(ctx, name="Autre"))
        vp = client_for(ctx.vice_president.user)
        assert vp.post(url("expense-release", target.pk), {"pin": PIN}, format="json").status_code == 409
        upload_response = client_for(ctx.assistant_treasurer.user).post(
            url("expense-receipt", late.pk), {"file": pdf_file("facture.pdf")}, format="multipart"
        )
        assert upload_response.status_code == 200 and upload_response.data["status"] == "justified"
        assert vp.post(url("expense-release", target.pk), {"pin": PIN}, format="json").status_code == 200

    def test_actions_on_a_final_expense_answer_400_and_do_not_change_it(self, ctx, world):
        client = client_for(ctx.president.user)
        client.post(url("expense-refuse", world.pending.pk), {"reason": "Non"}, format="json")
        for path, body in [
            (url("expense-release", world.pending.pk), {"pin": PIN}),
            (url("expense-refuse", world.pending.pk), {"reason": "Encore"}),
        ]:
            assert client.post(path, body, format="json").status_code == 400
        receipt = client_for(ctx.treasurer.user).post(
            url("expense-receipt", world.pending.pk), {"file": pdf_file("f.pdf")}, format="multipart"
        )
        assert receipt.status_code == 400
        assert Expense.all_objects.get(pk=world.pending.pk).status == Expense.Status.REFUSED


# ---------------------------------------------------------------------------
# Montants et affectation de masse
# ---------------------------------------------------------------------------


class TestAmountsAndMassAssignment:
    def _post(self, ctx, category, **override):
        body = {
            "category_id": category.pk,
            "amount": "10.00",
            "beneficiary_name": "Fournisseur",
            "reason": "Achat",
            "expense_date": club_today(ctx).isoformat(),
            **override,
        }
        return client_for(ctx.treasurer.user).post(url("expense-list"), body, format="json")

    @pytest.mark.parametrize(
        "amount", ["-5", "-0.01", "0", "0.00", "abc", "", None, "25.005", "99999999999.99", "NaN", "Infinity", "1e3x", [], {}]
    )
    def test_invalid_amounts_answer_400_and_write_nothing(self, ctx, world, amount):
        before = snapshot(ctx.club)
        assert self._post(ctx, world.category, amount=amount).status_code == 400
        assert snapshot(ctx.club) == before

    @pytest.mark.parametrize(
        "amount,expected",
        [("0.01", "0.01"), (12.5, "12.50"), (5, "5.00"), ("9999999999.99", "9999999999.99"), ("100", "100.00")],
    )
    def test_valid_amounts_are_returned_with_two_decimals(self, ctx, world, amount, expected):
        response = self._post(ctx, world.category, amount=amount)
        assert response.status_code == 201, response.data
        assert response.data["amount"] == expected

    def test_client_cannot_set_status_club_author_or_release_fields_on_creation(self, ctx, other_ctx, world, foreign):
        response = self._post(
            ctx,
            world.category,
            status="released",
            club=other_ctx.club.pk,
            club_id=other_ctx.club.pk,
            created_by=ctx.president.user_id,
            released_by=ctx.president.user_id,
            released_at="2026-01-01T00:00:00Z",
            justification_deadline="2099-01-01",
            currency="EUR",
            refusal_reason="x",
        )
        assert response.status_code == 201
        stored = Expense.all_objects.get(pk=response.data["id"])
        assert stored.status == Expense.Status.PENDING and stored.club_id == ctx.club.pk
        assert stored.created_by_id == ctx.treasurer.user_id and stored.released_by_id is None
        assert stored.currency == "USD" and stored.justification_deadline is None
        assert not Transaction.all_objects.filter(expense=stored).exists()

    def test_client_cannot_set_the_amount_status_or_membership_of_a_request(self, ctx, world):
        other = ctx.treasurer
        response = client_for(ctx.player.user).post(
            url("social-assistance-request-list"),
            {
                "event_type": "death",
                "event_date": club_today(ctx).isoformat(),
                "description": "Décès",
                "attachment": pdf_file("acte.pdf"),
                "status": "approved",
                "planned_amount": "999999",
                "membership_id": other.pk,
                "eligible_at_submission": "true",
                "decided_by": ctx.president.user_id,
            },
            format="multipart",
        )
        assert response.status_code == 201
        stored = SocialAssistanceRequest.all_objects.get(pk=response.data["id"])
        assert stored.status == SocialAssistanceRequest.Status.SUBMITTED
        assert stored.planned_amount == world.scale.amount and stored.membership_id == ctx.player.pk
        assert stored.decided_by_id is None

    def test_category_update_ignores_unknown_and_protected_fields(self, ctx, world):
        response = client_for(ctx.president.user).patch(
            url("expense-category-detail", world.category.pk),
            {"status": "archived", "club": 999, "name": "Renommée", "created_by": 1},
            format="json",
        )
        assert response.status_code == 200
        stored = ExpenseCategory.all_objects.get(pk=world.category.pk)
        assert stored.status == "active" and stored.name == "Renommée" and stored.club_id == ctx.club.pk

    def test_category_ceiling_and_scale_amount_validation(self, ctx, world):
        client = client_for(ctx.president.user)
        for bad in ("0", "-1", "abc"):
            assert client.patch(url("expense-category-detail", world.category.pk), {"ceiling": bad}, format="json").status_code == 400
            assert client.patch(url("social-assistance-scale-detail", world.scale.pk), {"amount": bad}, format="json").status_code == 400
        for bad_days in (0, -3, 366, "x"):
            assert client.patch(
                url("social-assistance-scale-detail", world.scale.pk), {"processing_days": bad_days}, format="json"
            ).status_code == 400
        assert ExpenseCategory.all_objects.get(pk=world.category.pk).ceiling is None
        assert SocialAssistanceScale.all_objects.get(pk=world.scale.pk).processing_days == 7


# ---------------------------------------------------------------------------
# Fichiers
# ---------------------------------------------------------------------------


class TestFilesThroughTheApi:
    def _entry(self, ctx, category, file):
        return client_for(ctx.treasurer.user).post(
            url("expense-list"),
            {
                "category_id": category.pk,
                "amount": "5.00",
                "beneficiary_name": "X",
                "reason": "Y",
                "expense_date": club_today(ctx).isoformat(),
                "attachment": file,
            },
            format="multipart",
        )

    @pytest.mark.parametrize(
        "name,content",
        [
            ("faux.pdf", b"ceci n'est pas un PDF"),
            ("page.html", b"<html><script>1</script></html>"),
            ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>"),
            ("virus.pdf", b"MZ\x90\x00\x03"),
            ("vide.pdf", b""),
        ],
    )
    def test_forbidden_files_are_refused_on_entry_receipt_and_assistance(self, ctx, world, name, content):
        before = snapshot(ctx.club)
        entry = self._entry(ctx, world.category, upload(name, content, "application/pdf"))
        assert entry.status_code in (400,)
        receipt = client_for(ctx.treasurer.user).post(
            url("expense-receipt", world.released.pk), {"file": upload(name, content, "application/pdf")}, format="multipart"
        )
        assert receipt.status_code == 400
        assistance = client_for(ctx.treasurer.user).post(
            url("social-assistance-request-list"),
            {
                "event_type": "death",
                "event_date": club_today(ctx).isoformat(),
                "description": "Décès",
                "attachment": upload(name, content, "application/pdf"),
            },
            format="multipart",
        )
        assert assistance.status_code == 400
        assert snapshot(ctx.club) == before

    def test_oversize_upload_is_refused_with_a_french_message(self, ctx, world):
        big = upload("gros.pdf", b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024), "application/pdf")
        response = self._entry(ctx, world.category, big)
        assert response.status_code == 400 and "10 Mo" in response.data["detail"]

    def test_receipt_without_a_file_is_refused(self, ctx, world):
        response = client_for(ctx.treasurer.user).post(url("expense-receipt", world.released.pk), {}, format="multipart")
        assert response.status_code == 400
        assert Expense.all_objects.get(pk=world.released.pk).status == Expense.Status.RELEASED

    def test_photo_receipt_is_accepted(self, ctx, world):
        response = client_for(ctx.treasurer.user).post(
            url("expense-receipt", world.released.pk), {"file": upload("recu.jpg", jpeg_bytes(), "image/jpeg")}, format="multipart"
        )
        assert response.status_code == 200 and response.data["status"] == "justified"

    def test_downloads_are_attachments_named_by_the_server_never_by_the_uploader(self, ctx, world):
        expense = make_expense(ctx, world.category, attachment=upload("../../Facture-secrète.pdf", PDF_CONTENT, "application/pdf"))
        attachment = expense.attachments.get()
        response = client_for(ctx.president.user).get(url("expense-attachment-download", attachment.pk))
        assert response.status_code == 200
        disposition = response["Content-Disposition"]
        assert disposition.startswith("attachment") and "secrète" not in disposition and ".." not in disposition
        assert f"depense-{expense.pk}-piece.pdf" in disposition
        assert response.get("X-Content-Type-Options") == "nosniff"

    def test_assistance_proof_download_headers(self, ctx, world):
        response = client_for(ctx.player.user).get(url("social-assistance-attachment-download", world.request.pk))
        assert response.status_code == 200
        assert response["Content-Disposition"].startswith("attachment")
        assert "acte" not in response["Content-Disposition"]
        assert response.get("X-Content-Type-Options") == "nosniff"

    def test_receipts_of_other_clubs_and_kinds_are_not_downloadable(self, ctx, other_ctx, world, foreign):
        late = foreign.overdue
        receipt = services.justify_expense(expense=late, uploaded_by=other_ctx.treasurer.user, file=pdf_file())
        attachment_id = receipt.attachments.get(kind="receipt").pk
        assert client_for(ctx.president.user).get(url("expense-attachment-download", attachment_id)).status_code == 404
        assert client_for(other_ctx.president.user).get(url("expense-attachment-download", attachment_id)).status_code == 200
        assert client_for(other_ctx.player.user).get(url("expense-attachment-download", attachment_id)).status_code == 403

    def test_serialised_expense_exposes_only_authenticated_download_urls(self, ctx, world):
        data = client_for(ctx.president.user).get(url("expense-detail", world.pending.pk)).data
        for item in data["attachments"]:
            assert item["download_url"].startswith("/api/") or item["download_url"].startswith("/")
            assert "/media/" not in item["download_url"] and "private" not in item["download_url"]
        request_data = client_for(ctx.player.user).get(url("social-assistance-request-detail", world.request.pk)).data
        assert "/media/" not in request_data["attachment_url"]
