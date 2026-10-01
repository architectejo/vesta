"""Tableau de bord Trésorerie : indicateurs, derniers paiements, détail d'un
paiement et circuit d'annulation par l'API (CDC 4.4.4, 4.4.6, 7.2 ; fiche
docs/ecrans/tresorerie-tableau-de-bord.md §3 et §4.4).

Couvre : formules des indicateurs (encaissé, taux de recouvrement, dettes,
caisse), rôles (matrice 2.4), étanchéité entre clubs (404), pagination
« Voir plus », contenu du détail, PIN et motif du circuit d'annulation.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditLog
from apps.clubs.models import Membership
from apps.treasury import services
from apps.treasury.models import Payment, PaymentReversal, Transaction
from apps.treasury.tests.cash_helpers import club_today, free_type, monthly_type, named_member, put_in_debt
from apps.treasury.tests.conftest import PIN, WRONG_PIN

pytestmark = pytest.mark.django_db

READERS = ["president", "vice_president", "treasurer", "assistant_treasurer"]
SUMMARY_URL = reverse("treasury:dashboard-summary")
LIST_URL = reverse("treasury:payment-create")


def client_for(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def month_ago(ctx, months: int) -> datetime.date:
    period = club_today(ctx).replace(day=1)
    for _ in range(months):
        period = (period - datetime.timedelta(days=1)).replace(day=1)
    return period


def pay(ctx, membership, ctype, *, amount="10", paid_on, method="cash", reference=""):
    return services.record_payment(
        membership=membership,
        contribution_type=ctype,
        amount=amount,
        method=method,
        reference=reference,
        paid_on=paid_on,
        recorded_by=ctx.treasurer.user,
        pin=PIN,
    )


def reverse_payment(ctx, payment):
    reversal = services.request_payment_reversal(
        payment=payment, reason="Saisie en double", requested_by=ctx.treasurer.user
    )
    return services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user, pin=PIN)


def detail_url(payment) -> str:
    return reverse("treasury:payment-detail", args=[payment.pk])


def action_url(payment, action: str) -> str:
    name = {"request": "payment-reversal-request", "approve": "payment-reversal-approve", "reject": "payment-reversal-reject"}
    return reverse(f"treasury:{name[action]}", args=[payment.pk])


@pytest.fixture
def scenario(ctx):
    """Mois M (il y a deux mois) : trois joueurs doivent 10 $ chacun.
    A paie 10, B paie 4, C ne paie rien ; A verse aussi 3 $ sur un type
    libre ; D paie 10 puis le paiement est annulé."""

    ctype = monthly_type(ctx)
    free = free_type(ctx)
    month = month_ago(ctx, 2)
    paid_on = month.replace(day=15)
    a = named_member(ctx, first_name="Alain", last_name="Aa")
    b = named_member(ctx, first_name="Bruno", last_name="Bb")
    c = named_member(ctx, first_name="Cedric", last_name="Cc")
    d = named_member(ctx, first_name="Denis", last_name="Dd")
    for member in (a, b, c):
        put_in_debt(ctx, member, ctype, amount="10", months_ago=2)
    pay_a = pay(ctx, a, ctype, amount="10", paid_on=paid_on)
    pay_b = pay(ctx, b, ctype, amount="4", paid_on=paid_on, method="mobile_money", reference="MM-42")
    pay_free = pay(ctx, a, free, amount="3", paid_on=paid_on)
    pay_d = pay(ctx, d, ctype, amount="10", paid_on=paid_on)
    reverse_payment(ctx, pay_d)
    return {
        "ctype": ctype, "month": month, "a": a, "b": b, "c": c, "d": d,
        "pay_a": pay_a, "pay_b": pay_b, "pay_free": pay_free, "pay_d": pay_d,
    }


# ---------------------------------------------------------------------------
# Indicateurs
# ---------------------------------------------------------------------------


class TestDashboardSummary:
    def test_formules_des_indicateurs(self, ctx, scenario):
        month = scenario["month"]
        response = client_for(ctx.treasurer.user).get(SUMMARY_URL, {"month": month.strftime("%Y-%m")})

        assert response.status_code == 200
        data = response.json()
        assert data["period"] == month.strftime("%Y-%m")
        assert data["currency"] == "USD"
        # 10 (A) + 4 (B) + 3 (A, type libre) ; le paiement annulé de D ne compte plus.
        assert data["collected"] == "17.00"
        # Dus échus du mois : 30 ; couverts : 10 (A) + 4 (B) -> 46,67 %.
        assert data["matured_due_total"] == "30.00"
        assert data["matured_due_covered"] == "14.00"
        assert data["collection_rate"] == "46.67"
        # Soldes négatifs : B -6, C -10.
        assert data["total_debts"] == "16.00"
        assert data["members_in_debt"] == 2
        assert data["available_cash"] == f"{services.get_available_cash(ctx.club):.2f}" == "17.00"

    def test_mois_par_defaut_mois_en_cours_sans_du_echu(self, ctx, scenario):
        data = client_for(ctx.president.user).get(SUMMARY_URL).json()
        assert data["period"] == club_today(ctx).strftime("%Y-%m")
        assert data["collected"] == "0.00"
        assert data["collection_rate"] is None
        assert data["matured_due_total"] == "0.00"
        # Dettes et caisse : toujours celles du jour.
        assert data["total_debts"] == "16.00"
        assert data["available_cash"] == "17.00"

    def test_club_vide_valeurs_a_zero(self, ctx):
        data = client_for(ctx.treasurer.user).get(SUMMARY_URL).json()
        assert data["collected"] == "0.00"
        assert data["total_debts"] == "0.00"
        assert data["members_in_debt"] == 0
        assert data["available_cash"] == "0.00"
        assert data["collection_rate"] is None

    def test_joueur_parti_exclu_du_total_des_dettes(self, ctx):
        ctype = monthly_type(ctx)
        gone = named_member(ctx, first_name="Parti", last_name="Pp", status=Membership.Status.DEPARTED)
        stays = named_member(ctx, first_name="Reste", last_name="Rr")
        put_in_debt(ctx, gone, ctype, amount="10")
        put_in_debt(ctx, stays, ctype, amount="7")

        data = client_for(ctx.treasurer.user).get(SUMMARY_URL).json()
        assert data["total_debts"] == "7.00"
        assert data["members_in_debt"] == 1

    def test_mois_invalide(self, ctx):
        response = client_for(ctx.treasurer.user).get(SUMMARY_URL, {"month": "2026-13"})
        assert response.status_code == 400
        response = client_for(ctx.treasurer.user).get(SUMMARY_URL, {"month": "abc"})
        assert response.status_code == 400

    @pytest.mark.parametrize("role", READERS)
    def test_lecteurs_autorises(self, ctx, role):
        assert client_for(getattr(ctx, role).user).get(SUMMARY_URL).status_code == 200

    def test_joueur_et_anonyme_refuses(self, ctx):
        assert client_for(ctx.player.user).get(SUMMARY_URL).status_code == 403
        assert APIClient().get(SUMMARY_URL).status_code == 401

    def test_etancheite_indicateurs_de_son_club_uniquement(self, ctx, other_ctx, scenario):
        data = client_for(other_ctx.treasurer.user).get(
            SUMMARY_URL, {"month": scenario["month"].strftime("%Y-%m")}
        ).json()
        assert data["currency"] == "CDF"
        assert data["collected"] == "0.00"
        assert data["total_debts"] == "0.00"
        assert data["available_cash"] == "0.00"


# ---------------------------------------------------------------------------
# Derniers paiements
# ---------------------------------------------------------------------------


class TestPaymentList:
    def test_contenu_et_tri(self, ctx, scenario):
        response = client_for(ctx.vice_president.user).get(LIST_URL)
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 4
        assert data["next_offset"] is None
        # Même date de valeur : le plus récemment saisi d'abord.
        ids = [item["id"] for item in data["results"]]
        assert ids == [scenario[k].pk for k in ("pay_d", "pay_free", "pay_b", "pay_a")]
        by_id = {item["id"]: item for item in data["results"]}
        b = by_id[scenario["pay_b"].pk]
        assert b["player"]["name"] == "Bruno Bb"
        assert b["contribution_type"]["name"] == "Mensuelle 10"
        assert b["amount"] == "4.00"
        assert b["currency"] == "USD"
        assert b["method"] == "mobile_money"
        assert b["method_label"] == "Mobile money"
        assert b["status"] == "validated"
        assert b["status_label"] == "Validé"
        assert by_id[scenario["pay_d"].pk]["status"] == "cancelled"
        assert by_id[scenario["pay_d"].pk]["status_label"] == "Annulé"

    def test_pagination_voir_plus(self, ctx):
        ctype = monthly_type(ctx)
        member = named_member(ctx, first_name="Page", last_name="Pg")
        for day in range(1, 26):
            pay(ctx, member, ctype, amount="1", paid_on=datetime.date(2026, 1, day))
        client = client_for(ctx.treasurer.user)

        first = client.get(LIST_URL).json()
        assert first["count"] == 25
        assert len(first["results"]) == 20
        assert first["next_offset"] == 20
        second = client.get(LIST_URL, {"offset": 20}).json()
        assert len(second["results"]) == 5
        assert second["next_offset"] is None
        seen = [item["id"] for item in first["results"] + second["results"]]
        assert len(set(seen)) == 25
        assert client.get(LIST_URL, {"limit": "x"}).status_code == 400

    def test_filtres_statut_et_annulation_en_attente(self, ctx, scenario):
        client = client_for(ctx.treasurer.user)
        cancelled = client.get(LIST_URL, {"status": "cancelled"}).json()
        assert [item["id"] for item in cancelled["results"]] == [scenario["pay_d"].pk]
        assert client.get(LIST_URL, {"status": "inconnu"}).status_code == 400

        services.request_payment_reversal(payment=scenario["pay_a"], reason="Erreur", requested_by=ctx.treasurer.user)
        pending = client.get(LIST_URL, {"reversal": "pending_approval"}).json()
        assert [item["id"] for item in pending["results"]] == [scenario["pay_a"].pk]
        assert pending["results"][0]["reversal_pending"] is True

    def test_photo_du_joueur_en_url_absolue(self, ctx, scenario):
        """Interface et API sont servies sur des hôtes distincts : la photo de
        profil doit être une URL absolue vers l'API, liste comme détail."""

        user = scenario["b"].user
        user.photo.name = "users/photos/bruno.jpg"
        user.save(update_fields=["photo"])
        client = client_for(ctx.treasurer.user)
        expected = "http://testserver/media/users/photos/bruno.jpg"

        by_id = {item["id"]: item for item in client.get(LIST_URL).json()["results"]}
        assert by_id[scenario["pay_b"].pk]["player"]["photo"] == expected
        assert by_id[scenario["pay_a"].pk]["player"]["photo"] is None
        assert client.get(detail_url(scenario["pay_b"])).json()["player"]["photo"] == expected

    def test_joueur_refuse(self, ctx, scenario):
        assert client_for(ctx.player.user).get(LIST_URL).status_code == 403

    def test_etancheite_liste(self, ctx, other_ctx, scenario):
        data = client_for(other_ctx.treasurer.user).get(LIST_URL).json()
        assert data["count"] == 0
        assert data["results"] == []


# ---------------------------------------------------------------------------
# Détail d'un paiement
# ---------------------------------------------------------------------------


class TestPaymentDetail:
    def test_champs_de_la_modale(self, ctx, scenario):
        payment = scenario["pay_b"]
        data = client_for(ctx.president.user).get(detail_url(payment)).json()

        assert data["id"] == payment.pk
        assert data["player"]["membership_id"] == scenario["b"].pk
        assert data["player"]["name"] == "Bruno Bb"
        assert data["contribution_type"]["name"] == "Mensuelle 10"
        assert data["amount"] == "4.00"
        assert data["method_label"] == "Mobile money"
        assert data["reference"] == "MM-42"
        assert data["paid_on"] == scenario["month"].replace(day=15).isoformat()
        assert data["attachment_url"] is None
        assert data["submitted_by"]["name"] == f"{ctx.treasurer.user.first_name} {ctx.treasurer.user.last_name}".strip()
        assert data["validated_by"]["id"] == ctx.treasurer.user.pk
        assert data["validated_at"] is not None
        assert data["receipt_number"] == payment.receipt_number
        assert data["receipt_url"] == reverse("treasury:payment-receipt-download", args=[payment.pk])
        assert data["allocations"] == [{"period": scenario["month"].isoformat(), "amount": "4.00"}]
        assert data["status"] == "validated"
        assert data["reversal"] is None

    def test_superuser_affiche_systeme_vesta(self, ctx):
        # Un paiement scellé est immuable : le masquage est vérifié sur
        # l'outil de sérialisation partagé par tous les champs « auteur ».
        from apps.treasury.serializers import _actor

        ghost = UserFactory(is_superuser=True)
        assert _actor(ghost, ctx.treasurer.user) == {"id": None, "name": "Systeme Vesta"}
        assert _actor(ghost, ghost)["id"] == ghost.pk
        assert _actor(ctx.treasurer.user, ctx.president.user)["id"] == ctx.treasurer.user.pk

    def test_404_inter_club(self, ctx, other_ctx, scenario):
        response = client_for(other_ctx.president.user).get(detail_url(scenario["pay_a"]))
        assert response.status_code == 404

    def test_joueur_refuse(self, ctx, scenario):
        assert client_for(ctx.player.user).get(detail_url(scenario["pay_a"])).status_code == 403


# ---------------------------------------------------------------------------
# Circuit d'annulation
# ---------------------------------------------------------------------------


class TestReversalApi:
    @pytest.mark.parametrize("role", ["treasurer", "assistant_treasurer"])
    def test_demande_par_tresorier_ou_adjoint(self, ctx, scenario, role):
        payment = scenario["pay_a"]
        response = client_for(getattr(ctx, role).user).post(
            action_url(payment, "request"), {"reason": "Saisie en double"}, format="json"
        )
        assert response.status_code == 201
        data = response.json()
        assert data["reversal"]["status"] == "pending_approval"
        assert data["reversal"]["reason"] == "Saisie en double"
        assert data["reversal_pending"] is True
        # Aucune écriture financière avant la validation du Président.
        assert data["status"] == "validated"
        assert not Transaction.all_objects.filter(reversal__payment=payment).exists()

    def test_motif_obligatoire(self, ctx, scenario):
        response = client_for(ctx.treasurer.user).post(action_url(scenario["pay_a"], "request"), {}, format="json")
        assert response.status_code == 400
        assert response.json()["detail"] == "Le motif de l'annulation est obligatoire."
        assert not PaymentReversal.all_objects.filter(payment=scenario["pay_a"]).exists()

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    def test_demande_refusee_aux_autres_roles(self, ctx, scenario, role):
        response = client_for(getattr(ctx, role).user).post(
            action_url(scenario["pay_a"], "request"), {"reason": "x"}, format="json"
        )
        assert response.status_code == 403

    def test_validation_par_le_president_avec_pin(self, ctx, scenario):
        payment = scenario["pay_a"]
        services.request_payment_reversal(payment=payment, reason="Erreur", requested_by=ctx.treasurer.user)
        client = client_for(ctx.president.user)

        wrong = client.post(action_url(payment, "approve"), {"pin": WRONG_PIN}, format="json")
        assert wrong.status_code == 400
        assert "attempts_remaining" in wrong.json()
        assert PaymentReversal.all_objects.get(payment=payment).status == PaymentReversal.Status.PENDING_APPROVAL
        assert client.post(action_url(payment, "approve"), {}, format="json").status_code == 400

        response = client.post(action_url(payment, "approve"), {"pin": PIN}, format="json")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["reversal"]["status"] == "approved"
        assert data["reversal"]["approved_by"]["id"] == ctx.president.user.pk
        # Paiement conservé, annulation chaînée, solde recalculé (A redevient débiteur).
        assert Payment.all_objects.filter(pk=payment.pk).exists()
        assert Transaction.all_objects.filter(club=ctx.club, kind=Transaction.Kind.PAYMENT_REVERSAL).count() == 2
        assert services.get_balance(scenario["a"]) == Decimal("-10.00")
        assert AuditLog.objects.filter(action_type="treasury.payment_reversal.approved").count() == 2

    @pytest.mark.parametrize("role", ["treasurer", "assistant_treasurer", "vice_president"])
    def test_validation_et_refus_reserves_au_president(self, ctx, scenario, role):
        payment = scenario["pay_a"]
        services.request_payment_reversal(payment=payment, reason="Erreur", requested_by=ctx.treasurer.user)
        client = client_for(getattr(ctx, role).user)
        assert client.post(action_url(payment, "approve"), {"pin": PIN}, format="json").status_code == 403
        assert client.post(action_url(payment, "reject"), {"rejection_reason": "Non"}, format="json").status_code == 403

    def test_refus_par_le_president_motif_obligatoire(self, ctx, scenario):
        payment = scenario["pay_a"]
        services.request_payment_reversal(payment=payment, reason="Erreur", requested_by=ctx.treasurer.user)
        client = client_for(ctx.president.user)

        assert client.post(action_url(payment, "reject"), {}, format="json").status_code == 400
        response = client.post(action_url(payment, "reject"), {"rejection_reason": "Paiement correct"}, format="json")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "validated"
        assert data["reversal"]["status"] == "rejected"
        assert data["reversal"]["rejection_reason"] == "Paiement correct"
        assert services.get_balance(scenario["a"]) == Decimal("0.00")

    def test_pas_de_demande_404(self, ctx, scenario):
        response = client_for(ctx.president.user).post(
            action_url(scenario["pay_a"], "approve"), {"pin": PIN}, format="json"
        )
        assert response.status_code == 404

    def test_deja_annule(self, ctx, scenario):
        response = client_for(ctx.treasurer.user).post(
            action_url(scenario["pay_d"], "request"), {"reason": "Encore"}, format="json"
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("action,body", [
        ("request", {"reason": "x"}),
        ("approve", {"pin": PIN}),
        ("reject", {"rejection_reason": "x"}),
    ])
    def test_404_inter_club(self, ctx, other_ctx, scenario, action, body):
        services.request_payment_reversal(payment=scenario["pay_a"], reason="Erreur", requested_by=ctx.treasurer.user)
        role = "treasurer" if action == "request" else "president"
        response = client_for(getattr(other_ctx, role).user).post(
            action_url(scenario["pay_a"], action), body, format="json"
        )
        assert response.status_code == 404
        assert PaymentReversal.all_objects.get(payment=scenario["pay_a"]).status == PaymentReversal.Status.PENDING_APPROVAL
