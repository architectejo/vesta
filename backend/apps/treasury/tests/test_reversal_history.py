"""Historique des demandes d'annulation dans le détail d'un paiement
(décision client du 15/11/2026 ; CDC 4.4.4).

``reversal`` reste la demande courante ; ``reversal_history`` liste toutes
les demandes, de la plus récente à la plus ancienne (demandée, refusée,
approuvée), visible par les mêmes rôles que le détail du paiement. Aucune
migration : les demandes refusées sont déjà conservées (append-only).
"""

from __future__ import annotations

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.treasury import services
from apps.treasury.tests.cash_helpers import club_today, monthly_type

pytestmark = pytest.mark.django_db

READERS = ["president", "vice_president", "treasurer", "assistant_treasurer"]
ENTRY_KEYS = {
    "id", "status", "status_label", "reason", "reason_kind", "requested_by", "requested_at",
    "decided_by", "decided_at", "rejection_reason",
}


def client_for(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def detail_url(payment) -> str:
    return reverse("treasury:payment-detail", args=[payment.pk])


@pytest.fixture
def payment(ctx):
    ctype = monthly_type(ctx)
    return services.record_payment(
        membership=ctx.player,
        contribution_type=ctype,
        amount="10",
        method="cash",
        reference="",
        paid_on=club_today(ctx) - datetime.timedelta(days=1),
        recorded_by=ctx.treasurer.user,
    )


def _request(ctx, payment, reason, user=None):
    return services.request_payment_reversal(
        payment=payment, reason=reason, requested_by=(user or ctx.treasurer.user)
    )


def _reject(ctx, reversal, why):
    return services.reject_payment_reversal(
        reversal=reversal, rejected_by=ctx.president.user, rejection_reason=why
    )


def _full_story(ctx, payment):
    """Refusée, refusée à nouveau, puis approuvée."""

    first = _reject(ctx, _request(ctx, payment, "Saisie en double"), "Paiement correct")
    second = _reject(ctx, _request(ctx, payment, "Mauvais joueur", ctx.assistant_treasurer.user), "Vérifié")
    third = services.approve_payment_reversal(
        reversal=_request(ctx, payment, "Erreur de montant"), approved_by=ctx.president.user
    )
    return first, second, third


def _name(user):
    return f"{user.first_name} {user.last_name}".strip()


class TestReversalHistory:
    def test_sans_demande_liste_vide(self, ctx, payment):
        data = client_for(ctx.president.user).get(detail_url(payment)).json()
        assert data["reversal"] is None
        assert data["reversal_history"] == []

    def test_demande_en_attente(self, ctx, payment):
        pending = _request(ctx, payment, "Saisie en double")
        data = client_for(ctx.treasurer.user).get(detail_url(payment)).json()
        assert len(data["reversal_history"]) == 1
        entry = data["reversal_history"][0]
        assert set(entry) == ENTRY_KEYS
        assert entry["id"] == pending.pk
        assert entry["status"] == "pending_approval"
        assert entry["status_label"] == "En attente d'approbation"
        assert entry["reason"] == "Saisie en double"
        assert entry["reason_kind"] == "error"
        assert entry["requested_by"] == {"id": ctx.treasurer.user.pk, "name": _name(ctx.treasurer.user)}
        assert entry["requested_at"] is not None
        assert entry["decided_by"] is None
        assert entry["decided_at"] is None
        assert entry["rejection_reason"] == ""

    def test_ordre_du_plus_recent_au_plus_ancien(self, ctx, payment):
        first, second, third = _full_story(ctx, payment)
        data = client_for(ctx.president.user).get(detail_url(payment)).json()

        history = data["reversal_history"]
        assert [item["id"] for item in history] == [third.pk, second.pk, first.pk]
        assert [item["status"] for item in history] == ["approved", "rejected", "rejected"]
        # La demande courante reste exposée telle quelle et correspond à la plus récente.
        assert data["reversal"]["id"] == third.pk
        assert data["status"] == "cancelled"

        approved, rejected_again, rejected = history
        assert approved["status_label"] == "Approuvée"
        assert approved["reason"] == "Erreur de montant"
        assert approved["decided_by"]["id"] == ctx.president.user.pk
        assert approved["decided_at"] is not None
        assert approved["rejection_reason"] == ""

        assert rejected_again["requested_by"]["id"] == ctx.assistant_treasurer.user.pk
        assert rejected_again["reason"] == "Mauvais joueur"
        assert rejected_again["rejection_reason"] == "Vérifié"

        assert rejected["status_label"] == "Rejetée"
        assert rejected["reason"] == "Saisie en double"
        assert rejected["decided_by"] == {"id": ctx.president.user.pk, "name": _name(ctx.president.user)}
        assert rejected["decided_at"] is not None
        assert rejected["rejection_reason"] == "Paiement correct"
        for item in history:
            assert set(item) == ENTRY_KEYS

    def test_historique_apres_une_action_api(self, ctx, payment):
        _reject(ctx, _request(ctx, payment, "Saisie en double"), "Paiement correct")
        response = client_for(ctx.treasurer.user).post(
            reverse("treasury:payment-reversal-request", args=[payment.pk]), {"reason": "Nouveau motif"}, format="json"
        )
        assert response.status_code == 201
        history = response.json()["reversal_history"]
        assert [item["status"] for item in history] == ["pending_approval", "rejected"]
        assert history[0]["reason"] == "Nouveau motif"

    @pytest.mark.parametrize("role", READERS)
    def test_visible_par_les_lecteurs_du_detail(self, ctx, payment, role):
        _reject(ctx, _request(ctx, payment, "Saisie en double"), "Paiement correct")
        response = client_for(getattr(ctx, role).user).get(detail_url(payment))
        assert response.status_code == 200
        assert len(response.json()["reversal_history"]) == 1

    def test_joueur_refuse(self, ctx, payment):
        _request(ctx, payment, "Saisie en double")
        assert client_for(ctx.player.user).get(detail_url(payment)).status_code == 403

    def test_etancheite_entre_clubs(self, ctx, other_ctx, payment):
        _request(ctx, payment, "Saisie en double")
        assert client_for(other_ctx.president.user).get(detail_url(payment)).status_code == 404

    def test_nombre_de_requetes_independant_de_la_longueur(self, ctx, payment):
        """L'historique est lu depuis le prefetch existant : 3 demandes ne
        coûtent pas plus de requêtes qu'une seule."""

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        _full_story(ctx, payment)
        other = services.record_payment(
            membership=ctx.player,
            contribution_type=payment.contribution_type,
            amount="10",
            method="cash",
            reference="",
            paid_on=club_today(ctx) - datetime.timedelta(days=1),
            recorded_by=ctx.treasurer.user,
        )
        _reject(ctx, _request(ctx, other, "x"), "y")
        client = client_for(ctx.president.user)
        client.get(detail_url(other))  # échauffement
        with CaptureQueriesContext(connection) as single:
            assert client.get(detail_url(other)).status_code == 200
        with CaptureQueriesContext(connection) as triple:
            assert client.get(detail_url(payment)).status_code == 200
        assert len(triple) == len(single)
