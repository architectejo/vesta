"""API de l'import des cotisations historiques (tâche 2.6 ; CDC 4.4.8,
7.2 ; matrice 2.4).

Trésorier et adjoint uniquement (403 sinon, 401 sans jeton), multipart,
aperçu sans aucune écriture, import définitif confirmé par code PIN, 404
pour un type d'un autre club, rapport détaillé des lignes en échec.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.treasury import services
from apps.treasury.models import Due, Payment
from apps.treasury.tests.conftest import PIN, WRONG_PIN
from apps.treasury.tests.grid_helpers import attach, attached_type, csv_file, csv_line, player

pytestmark = pytest.mark.django_db

PREVIEW = "treasury:contribution-import-preview"
IMPORT = "treasury:contribution-import"


def client_for(member) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member.user).access_token}")
    return client


def last_year(ctx) -> int:
    return services.get_club_today(ctx.club).year - 1


@pytest.fixture
def setup(ctx):
    year = last_year(ctx)
    ctype = attached_type(ctx)
    # Entré l'année d'avant : aucun mois d'arrivée dans l'année importée (Q4).
    member = player(ctx, "Adolphe", "Abedi", joined_on=datetime.date(year - 1, 6, 1))
    attach(ctx, member, ctype, starts_on=datetime.date(year, 1, 1))
    return ctype, member, year


def body(ctype, year, lines, **extra):
    data = {"contribution_type_id": ctype.pk, "year": year, "file": csv_file(lines)}
    data.update(extra)
    return data


class TestPermissions:
    def test_401_sans_authentification(self, ctx, setup):
        ctype, _, year = setup
        for name in (PREVIEW, IMPORT):
            response = APIClient().post(reverse(name), body(ctype, year, []), format="multipart")
            assert response.status_code == 401

    @pytest.mark.parametrize("role", ["president", "vice_president", "player"])
    def test_403_hors_tresorier_et_adjoint(self, ctx, setup, role):
        ctype, _, year = setup
        client = client_for(getattr(ctx, role))
        for name in (PREVIEW, IMPORT):
            data = body(ctype, year, [csv_line("Adolphe Abedi", "10")], pin=PIN)
            assert client.post(reverse(name), data, format="multipart").status_code == 403
        assert Payment.all_objects.count() == 0

    def test_404_type_d_un_autre_club(self, ctx, other_ctx, setup):
        _, _, year = setup
        theirs = attached_type(other_ctx)
        client = client_for(ctx.treasurer)
        for name in (PREVIEW, IMPORT):
            response = client.post(reverse(name), body(theirs, year, [], pin=PIN), format="multipart")
            assert response.status_code == 404
            assert response.data["detail"] == "Type de cotisation introuvable dans ce club."

    def test_json_refuse(self, ctx, setup):
        ctype, _, year = setup
        response = client_for(ctx.treasurer).post(
            reverse(PREVIEW), {"contribution_type_id": ctype.pk, "year": year}, format="json"
        )
        assert response.status_code == 415


class TestApercu:
    def test_apercu_sans_ecriture(self, ctx, setup):
        ctype, member, year = setup
        before = (Payment.all_objects.count(), Due.all_objects.count(), AuditLog.objects.count())
        lines = [csv_line("ABEDI Adolphe", "60", "ok", "ok"), csv_line("Personne Inconnue", "10")]
        response = client_for(ctx.assistant_treasurer).post(reverse(PREVIEW), body(ctype, year, lines), format="multipart")
        assert response.status_code == 200, response.data
        assert (Payment.all_objects.count(), Due.all_objects.count(), AuditLog.objects.count()) == before
        data = response.data
        assert data["is_preview"] is True and data["import_batch_id"] is None
        assert data["summary"] == {
            "rows_total": 2,
            "rows_succeeded": 1,
            "rows_failed": 1,
            "payments_count": 1,
            "payments_total": "60.00",
            "dues_count": 12,
            "already_imported_count": 0,
        }
        ok_row, failed_row = data["rows"]
        assert ok_row["player"]["membership_id"] == member.pk and ok_row["status"] == "ok"
        assert [cell["state"] for cell in ok_row["cells"]] == ["paid"] * 6 + ["overdue"] * 6
        assert ok_row["payments"] == [
            {
                "period": datetime.date(year, 1, 1),
                "paid_on": datetime.date(year, 1, 1),
                "amount": "60.00",
                "origin": "amount",
                "reference": f"Import historique 01/{year}",
            }
        ]
        assert ok_row["balance_after"] == "-60.00"
        assert ok_row["player_status_after"]["is_in_good_standing"] is False
        assert failed_row == {
            "line_number": 3,
            "identity": "Personne Inconnue",
            "status": "failed",
            "player": None,
            "errors": ["Joueur introuvable dans ce club (« Personne Inconnue »)."],
            "warnings": [],
            "payments": [],
            "already_imported": [],
            "dues": [],
            "cells": [],
            "total": None,
            "balance_before": None,
            "balance_after": None,
            "player_status_after": None,
        }

    def test_fichier_illisible_400_avec_code(self, ctx, setup):
        ctype, _, year = setup
        data = {"contribution_type_id": ctype.pk, "year": year, "file": csv_file(["a;b"], header="x;y")}
        response = client_for(ctx.treasurer).post(reverse(PREVIEW), data, format="multipart")
        assert response.status_code == 400 and response.data["code"] == "import_file_invalid"


class TestImport:
    def test_import_definitif_avec_pin(self, ctx, setup):
        ctype, member, year = setup
        lines = [csv_line("Adolphe Abedi", "60", "ok", "ok", "ok", "ok", "ok", "ok")]
        response = client_for(ctx.treasurer).post(reverse(IMPORT), body(ctype, year, lines, pin=PIN), format="multipart")
        assert response.status_code == 201, response.data
        data = response.data
        assert data["is_preview"] is False and data["import_batch_id"] is not None
        assert data["rows"][0]["status"] == "imported"
        assert [p.amount for p in Payment.all_objects.filter(membership=member).order_by("paid_on")] == [
            Decimal("60.00"),
            Decimal("10.00"),
        ]
        assert PIN not in response.content.decode("utf-8")

        grid = client_for(ctx.treasurer).get(reverse("treasury:grid", args=[ctype.pk, year]))
        (row,) = grid.data["results"]
        assert row["total"] == "70.00"
        assert row["player_status"]["balance"] == "-50.00"

    def test_pin_obligatoire(self, ctx, setup):
        ctype, _, year = setup
        response = client_for(ctx.treasurer).post(
            reverse(IMPORT), body(ctype, year, [csv_line("Adolphe Abedi", "10")]), format="multipart"
        )
        assert response.status_code == 400 and "pin" in response.data

    def test_pin_faux_rien_n_est_ecrit(self, ctx, setup):
        ctype, _, year = setup
        response = client_for(ctx.treasurer).post(
            reverse(IMPORT), body(ctype, year, [csv_line("Adolphe Abedi", "10")], pin=WRONG_PIN), format="multipart"
        )
        assert response.status_code == 400 and response.data["attempts_remaining"] == 2
        assert Payment.all_objects.count() == 0 and Due.all_objects.count() == 0

    def test_registre_gele_409(self, ctx, setup):
        ctype, _, year = setup
        services.freeze_ledger(club=ctx.club, reason="test", actor=None)
        response = client_for(ctx.treasurer).post(
            reverse(IMPORT), body(ctype, year, [csv_line("Adolphe Abedi", "10")], pin=PIN), format="multipart"
        )
        assert response.status_code == 409 and response.data["code"] == "ledger_frozen"
