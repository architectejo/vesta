"""API de la grille des cotisations (tâche 2.6 ; CDC 4.4.7 ; fiche d'écran
docs/ecrans/tresorerie-grille-cotisations.md ; matrice 2.4).

Permissions explicites : Pdt, VP (défaut de la fiche d'écran : la matrice
2.4 fait foi), Trés, Adj ; 403 pour tout autre rôle ; 401 sans jeton ;
404 pour un type ou un joueur d'un autre club. Pagination à 50 lignes,
tri, recherche, filtre « avec impayés », détail du mois, export CSV.

Les tests d'API ne figent pas l'horloge : ils portent sur l'année
précédente (tous les mois échus).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.clubs.models import MembershipRole
from apps.clubs.tests.factories import MembershipRoleFactory
from apps.treasury import services
from apps.treasury.tests.conftest import make_member
from apps.treasury.tests.grid_helpers import attach, attached_type, free_monthly_type, make_dues, pay, player

pytestmark = pytest.mark.django_db


def client_for(member) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member.user).access_token}")
    return client


def last_year(ctx) -> int:
    return services.get_club_today(ctx.club).year - 1


def url(name, *args):
    return reverse(f"treasury:{name}", args=args)


def endpoints(ctype_id, year, membership_id):
    return [
        url("grid-types"),
        url("grid", ctype_id, year),
        url("grid-export", ctype_id, year),
        url("grid-month", ctype_id, year, membership_id, 1),
    ]


def pay_now(ctx, member, ctype, amount, day):
    return pay(ctx, member, ctype, amount, day, now=timezone.now())


@pytest.fixture
def grid_data(ctx):
    year = last_year(ctx)
    ctype = attached_type(ctx)
    members = []
    for index in range(55):
        member = player(ctx, f"Prenom{index:02d}", f"Nom{index:02d}", jersey=(index % 99) + 1)
        attach(ctx, member, ctype, starts_on=datetime.date(year, 1, 1))
        make_dues(ctx, member, ctype, range(1, 13), year=year)
        members.append(member)
    pay_now(ctx, members[0], ctype, "120", datetime.date(year, 1, 5))
    pay_now(ctx, members[1], ctype, "45", datetime.date(year, 1, 5))
    return ctype, year, members


class TestPermissions:
    def test_401_sans_authentification(self, ctx):
        ctype = attached_type(ctx)
        for path in endpoints(ctype.pk, 2025, ctx.player.pk):
            assert APIClient().get(path).status_code == 401, path

    @pytest.mark.parametrize(
        "role",
        [
            MembershipRole.Role.SPORTS_DIRECTOR,
            MembershipRole.Role.STEWARD,
            MembershipRole.Role.COACH,
            MembershipRole.Role.CAPTAIN,
            MembershipRole.Role.DOCTOR,
            None,
        ],
    )
    def test_403_pour_les_autres_roles(self, ctx, role):
        ctype = attached_type(ctx)
        member = make_member(ctx.club)
        if role:
            MembershipRoleFactory(
                membership=member,
                club=ctx.club,
                role=role,
                appointed_at=timezone.now(),
                # Médecin : choix explicite exigé à la nomination (10.2 n° 17).
                is_qualified_professional=True if role == MembershipRole.Role.DOCTOR else None,
            )
        client = client_for(member)
        for path in endpoints(ctype.pk, 2025, ctx.player.pk):
            assert client.get(path).status_code == 403, path

    @pytest.mark.parametrize("role", ["president", "vice_president", "treasurer", "assistant_treasurer"])
    def test_200_pour_le_bureau_autorise(self, ctx, role):
        ctype = attached_type(ctx)
        client = client_for(getattr(ctx, role))
        for path in endpoints(ctype.pk, last_year(ctx), ctx.player.pk):
            assert client.get(path).status_code == 200, path

    def test_404_type_ou_joueur_d_un_autre_club(self, ctx, other_ctx):
        mine = attached_type(ctx)
        theirs = attached_type(other_ctx)
        client = client_for(ctx.treasurer)
        year = last_year(ctx)
        for path in (url("grid", theirs.pk, year), url("grid-export", theirs.pk, year)):
            response = client.get(path)
            assert response.status_code == 404 and response.data["detail"] == "Type de cotisation introuvable dans ce club."
        assert client.get(url("grid-month", theirs.pk, year, ctx.player.pk, 1)).status_code == 404
        assert client.get(url("grid-month", mine.pk, year, other_ctx.player.pk, 1)).status_code == 404

    def test_types_d_un_autre_club_invisibles(self, ctx, other_ctx):
        attached_type(ctx, name="Mien")
        attached_type(other_ctx, name="Autre club")
        data = client_for(ctx.president).get(url("grid-types")).data
        assert [item["name"] for item in data["active"]] == ["Mien"]


class TestTypes:
    def test_types_actifs_archives_et_defaut(self, ctx):
        free = free_monthly_type(ctx, name="A vestiaire")
        monthly = attached_type(ctx, name="Mensuelle 20", amount="20")
        archived = attached_type(ctx, name="Ancienne mensuelle")
        services.archive_contribution_type(contribution_type=archived, archived_by=ctx.president.user)
        data = client_for(ctx.treasurer).get(url("grid-types")).data
        assert data["currency"] == "USD"
        assert [item["id"] for item in data["active"]] == [free.pk, monthly.pk]
        assert [item["id"] for item in data["archived"]] == [archived.pk]
        # Premier type mensuel obligatoire (fiche d'écran §3.1).
        assert data["default_type_id"] == monthly.pk
        assert data["active"][0]["is_free"] is True


class TestGrille:
    def test_pagination_50_lignes(self, ctx, grid_data):
        ctype, year, _ = grid_data
        client = client_for(ctx.treasurer)
        first = client.get(url("grid", ctype.pk, year)).data
        assert (first["count"], first["limit"], first["next_offset"], len(first["results"])) == (55, 50, 50, 50)
        assert first["rows_total"] == 55
        second = client.get(url("grid", ctype.pk, year) + "?offset=50").data
        assert len(second["results"]) == 5 and second["next_offset"] is None

    def test_contenu_d_une_ligne(self, ctx, grid_data):
        ctype, year, members = grid_data
        data = client_for(ctx.vice_president).get(url("grid", ctype.pk, year) + "?q=Nom01").data
        assert data["currency"] == "USD" and data["year"] == year
        assert [month["label"] for month in data["months"]][:3] == ["janv.", "févr.", "mars"]
        assert data["states"]["overdue"] == "Impayé échu"
        (row,) = data["results"]
        assert row["membership_id"] == members[1].pk and row["name"] == "Prenom01 Nom01"
        assert [cell["allocated"] for cell in row["cells"][:6]] == ["10.00", "10.00", "10.00", "10.00", "5.00", "0.00"]
        assert [cell["state"] for cell in row["cells"][:6]] == ["paid"] * 4 + ["partial", "overdue"]
        assert row["cells"][4]["state_label"] == "Partiel"
        assert row["total"] == "45.00" and row["overdue_amount"] == "75.00" and row["has_unpaid"] is True
        assert row["player_status"]["amount_due"] == "75.00"
        assert row["player_status"]["is_in_good_standing"] is False

    def test_tri_par_nom_et_par_total(self, ctx, grid_data):
        ctype, year, members = grid_data
        client = client_for(ctx.treasurer)
        names = [row["last_name"] for row in client.get(url("grid", ctype.pk, year)).data["results"]]
        assert names == sorted(names)
        top = client.get(url("grid", ctype.pk, year) + "?ordering=-total").data["results"]
        assert [row["membership_id"] for row in top[:2]] == [members[0].pk, members[1].pk]
        bottom = client.get(url("grid", ctype.pk, year) + "?ordering=total").data["results"]
        assert bottom[0]["total"] == "0.00"
        assert client.get(url("grid", ctype.pk, year) + "?ordering=solde").status_code == 400

    def test_recherche_et_filtre_impayes(self, ctx, grid_data):
        ctype, year, members = grid_data
        client = client_for(ctx.treasurer)
        assert client.get(url("grid", ctype.pk, year) + "?q=inexistant").data["count"] == 0
        unpaid = client.get(url("grid", ctype.pk, year) + "?unpaid=1").data
        assert unpaid["count"] == 54 and members[0].pk not in {row["membership_id"] for row in unpaid["results"]}

    def test_type_libre_jamais_rouge(self, ctx):
        year = last_year(ctx)
        ctype = free_monthly_type(ctx)
        member = player(ctx, "Libre", "Payeur")
        pay_now(ctx, member, ctype, "4", datetime.date(year, 5, 3))
        data = client_for(ctx.treasurer).get(url("grid", ctype.pk, year) + "?q=Payeur").data
        (row,) = data["results"]
        assert {cell["state"] for cell in row["cells"]} == {"free"}
        assert row["cells"][4]["allocated"] == "4.00" and row["has_unpaid"] is False
        assert client_for(ctx.treasurer).get(url("grid", ctype.pk, year) + "?unpaid=1").data["count"] == 0

    def test_annee_invalide(self, ctx):
        ctype = attached_type(ctx)
        response = client_for(ctx.treasurer).get(url("grid", ctype.pk, 1999))
        assert response.status_code == 400 and "Année invalide" in response.data["detail"]

    def test_aucune_ecriture_ni_journal(self, ctx, grid_data):
        from apps.audit.models import AuditLog

        ctype, year, _ = grid_data
        before = AuditLog.objects.count()
        client_for(ctx.treasurer).get(url("grid", ctype.pk, year))
        client_for(ctx.treasurer).get(url("grid-export", ctype.pk, year))
        assert AuditLog.objects.count() == before


class TestDetailDuMois:
    def test_detail_avec_paiement_etale(self, ctx):
        year = last_year(ctx)
        ctype = attached_type(ctx)
        member = player(ctx, "Etale", "Joueur")
        attach(ctx, member, ctype, starts_on=datetime.date(year, 1, 1))
        make_dues(ctx, member, ctype, range(1, 13), year=year)
        payment = pay_now(ctx, member, ctype, "40", datetime.date(year, 3, 5))
        data = client_for(ctx.treasurer).get(url("grid-month", ctype.pk, year, member.pk, 2)).data
        assert data["period_label"] == f"février {year}"
        assert data["cell"]["state"] == "paid" and data["cell"]["amount_due"] == "10.00"
        (item,) = data["payments"]
        assert item["payment_id"] == payment.pk and item["allocated"] == "10.00" and item["amount"] == "40.00"
        assert item["receipt_number"] == payment.receipt_number and item["method_label"] == "Espèces"
        assert item["spread_label"] == (
            f"Paiement de 40.00 USD du 05/03/{year}, réparti de janvier {year} à avril {year}."
        )
        assert data["can_record_payment"] is True

    def test_photo_du_joueur_en_url_absolue(self, ctx):
        """Grille et détail du mois : photo de profil en URL absolue vers l'API
        (interface et API servies sur des hôtes distincts)."""

        year = last_year(ctx)
        ctype = attached_type(ctx)
        member = player(ctx, "Photo", "Grille")
        attach(ctx, member, ctype, starts_on=datetime.date(year, 1, 1))
        member.user.photo.name = "users/photos/grille.jpg"
        member.user.save(update_fields=["photo"])
        expected = "http://testserver/media/users/photos/grille.jpg"
        client = client_for(ctx.treasurer)
        (row,) = client.get(url("grid", ctype.pk, year) + "?q=Grille").data["results"]
        assert row["photo"] == expected
        detail = client.get(url("grid-month", ctype.pk, year, member.pk, 1)).data
        assert detail["player"]["photo"] == expected

    def test_president_ne_peut_pas_enregistrer(self, ctx):
        ctype = attached_type(ctx)
        data = client_for(ctx.president).get(url("grid-month", ctype.pk, last_year(ctx), ctx.player.pk, 1)).data
        assert data["can_record_payment"] is False and data["payments"] == []
        assert data["cell"]["state"] == "not_due"

    def test_mois_invalide(self, ctx):
        ctype = attached_type(ctx)
        response = client_for(ctx.treasurer).get(url("grid-month", ctype.pk, last_year(ctx), ctx.player.pk, 13))
        assert response.status_code == 400


class TestExport:
    def test_export_csv(self, ctx, grid_data):
        ctype, year, _ = grid_data
        response = client_for(ctx.president).get(url("grid-export", ctype.pk, year))
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv; charset=utf-8"
        disposition = response["Content-Disposition"]
        assert disposition == f'attachment; filename="grille-mensuelle-10-{year}.csv"'
        assert ctx.club.name.lower() not in disposition.lower()
        lines = response.content.decode("utf-8").lstrip("﻿").split("\r\n")
        assert lines[0].startswith("Joueur;N°;janv. ")
        assert len([line for line in lines[1:] if line]) == 55
        assert f"Nom01 Prenom01;2;10.00;10.00;10.00;10.00;5.00;0.00;0.00;0.00;0.00;0.00;0.00;0.00;45.00" in lines

    def test_export_filtre_impayes(self, ctx, grid_data):
        ctype, year, _ = grid_data
        response = client_for(ctx.treasurer).get(url("grid-export", ctype.pk, year) + "?unpaid=1")
        lines = [line for line in response.content.decode("utf-8").split("\r\n")[1:] if line]
        assert len(lines) == 54

    def test_montant_total_egal_au_solde(self, ctx, grid_data):
        ctype, year, members = grid_data
        data = client_for(ctx.treasurer).get(url("grid", ctype.pk, year) + "?q=Nom00").data
        (row,) = data["results"]
        assert Decimal(row["total"]) == Decimal("120.00") and row["player_status"]["balance"] == "0.00"
