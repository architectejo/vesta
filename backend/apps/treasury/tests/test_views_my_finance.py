"""Données financières du joueur connecté, pour lui seul (page « Mon
profil » ; fiche docs/ecrans/comptes-mon-profil.md §3.2, §4.4 ; CDC 4.4.7
« Chaque joueur voit sa propre ligne dans son profil » ; matrice 2.4,
colonne « P ») et capacité ``can_decide_payment_reversal`` (CDC 4.4.4).

Endpoints en lecture seule :
- ``GET /treasury/my-payments/`` et ``/treasury/my-payments/<id>/`` ;
- ``GET /treasury/my-grid/<année>/`` et
  ``/treasury/my-grid/<type>/<année>/months/<mois>/``.

Étanchéité : entre joueurs du même club (aucun identifiant de joueur
accepté, 404 sur la donnée d'un autre) et entre clubs (404).

Les tests d'API ne figent pas l'horloge : la grille porte sur l'année
précédente (tous les mois échus).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.treasury import services
from apps.treasury.models import Payment
from apps.treasury.tests.cash_helpers import monthly_type
from apps.treasury.tests.conftest import PIN, past_day
from apps.treasury.tests.grid_helpers import attach, attached_type, free_monthly_type, make_dues, pay, player

pytestmark = pytest.mark.django_db

RECEIPT = b"%PDF-1.4\n%recu de test\n%%EOF\n"

PAYMENT_KEYS = {
    "id", "contribution_type", "amount", "currency", "paid_on", "method", "method_label", "source",
    "source_label", "reference", "status", "status_label", "validated_at", "receipt_number",
    "receipt_available", "receipt_url",
}


def client_for(member) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member.user).access_token}")
    return client


def url(name, *args):
    return reverse(f"treasury:{name}", args=args)


def last_year(ctx) -> int:
    return services.get_club_today(ctx.club).year - 1


def record(ctx, member, ctype, amount="10", *, paid_on=None):
    return services.record_payment(
        membership=member,
        contribution_type=ctype,
        amount=amount,
        method=Payment.Method.CASH,
        paid_on=paid_on or past_day(),
        recorded_by=ctx.treasurer.user,
    )


def declare(member, ctype, *, amount="10", reference="LAX-001"):
    return services.declare_payment(
        membership=member, declared_by=member.user, contribution_type=ctype, amount=amount, reference=reference
    )


def cancel(ctx, payment):
    reversal = services.request_payment_reversal(payment=payment, reason="Saisie en double", requested_by=ctx.treasurer.user)
    return services.approve_payment_reversal(reversal=reversal, approved_by=ctx.president.user)


def set_payment_link(ctx):
    club_settings = ctx.club.settings
    club_settings.payment_link_url = "https://paiement.example.test/lien"
    club_settings.save()


def ids(response):
    return [item["id"] for item in response.data["results"]]


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------


def test_401_sans_authentification_partout(ctx):
    ctype = monthly_type(ctx)
    payment = record(ctx, ctx.player, ctype)
    anonymous = APIClient()
    for path in (
        url("my-payments"),
        url("my-payment-detail", payment.pk),
        url("my-grid", last_year(ctx)),
        url("my-grid-month", ctype.pk, last_year(ctx), 1),
    ):
        assert anonymous.get(path).status_code == 401, path


# ---------------------------------------------------------------------------
# « Mes paiements »
# ---------------------------------------------------------------------------


class TestMyPayments:
    def test_paiements_valides_de_toutes_sources_et_seulement_les_siens(self, ctx, other_ctx):
        ctype = monthly_type(ctx)
        set_payment_link(ctx)
        entry = record(ctx, ctx.player, ctype, "10")
        declared = declare(ctx.player, ctype, reference="LAX-OK")
        services.validate_declared_payment(payment=declared, validated_by=ctx.treasurer.user)
        declare(ctx.player, ctype, reference="LAX-ATTENTE")  # à valider : exclue
        refused = declare(ctx.player, ctype, reference="LAX-REFUS")
        services.reject_declared_payment(payment=refused, rejected_by=ctx.treasurer.user, reason="Introuvable.")
        record(ctx, ctx.vice_president, ctype, "30")  # autre joueur du club
        record(other_ctx, other_ctx.player, monthly_type(other_ctx), "50")  # autre club

        response = client_for(ctx.player).get(url("my-payments"))

        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"
        assert sorted(ids(response)) == sorted([entry.pk, declared.pk])
        assert response.data["count"] == 2
        assert response.data["next_offset"] is None
        sources = {item["source"] for item in response.data["results"]}
        assert sources == {Payment.Source.TREASURER_ENTRY, Payment.Source.PLAYER_DECLARATION}
        assert all(item["status"] == "validated" for item in response.data["results"])

    def test_forme_exacte_d_une_ligne(self, ctx):
        ctype = monthly_type(ctx, name="Mensuelle")
        payment = record(ctx, ctx.player, ctype, "12.5")
        item = client_for(ctx.player).get(url("my-payments")).data["results"][0]
        assert set(item) == PAYMENT_KEYS
        assert item["id"] == payment.pk
        assert item["contribution_type"] == {"id": ctype.pk, "name": "Mensuelle"}
        assert item["amount"] == "12.50"
        assert item["currency"] == "USD"
        assert item["method"] == "cash" and item["method_label"] == "Espèces"
        assert item["source"] == "treasurer_entry" and item["source_label"] == "Saisie Trésorier"
        assert item["status"] == "validated" and item["status_label"] == "Validé"
        assert item["receipt_number"] == payment.receipt_number
        # Aucun champ réservé au bureau (auteur, pièce jointe, session de caisse).
        assert not {"submitted_by", "validated_by", "attachment_url", "cash_session_id", "player"} & set(item)

    def test_tri_du_plus_recent_au_plus_ancien(self, ctx):
        ctype = monthly_type(ctx)
        old = record(ctx, ctx.player, ctype, paid_on=past_day(20))
        recent = record(ctx, ctx.player, ctype, paid_on=past_day(3))
        assert ids(client_for(ctx.player).get(url("my-payments"))) == [recent.pk, old.pk]

    def test_annulation_exclue_par_defaut_et_filtrable(self, ctx):
        ctype = monthly_type(ctx)
        kept = record(ctx, ctx.player, ctype, "10")
        cancelled = record(ctx, ctx.player, ctype, "20")
        cancel(ctx, cancelled)
        client = client_for(ctx.player)

        assert ids(client.get(url("my-payments"))) == [kept.pk]
        only_cancelled = client.get(url("my-payments"), {"status": "cancelled"})
        assert ids(only_cancelled) == [cancelled.pk]
        assert only_cancelled.data["results"][0]["status"] == "cancelled"
        assert only_cancelled.data["results"][0]["status_label"] == "Annulé"
        both = client.get(url("my-payments"), {"status": "validated,cancelled"})
        assert sorted(ids(both)) == sorted([kept.pk, cancelled.pk])

    @pytest.mark.parametrize("value", ["to_validate", "refused", "inconnu"])
    def test_statut_inconnu_400(self, ctx, value):
        response = client_for(ctx.player).get(url("my-payments"), {"status": value})
        assert response.status_code == 400
        assert response.data["detail"] == "État de paiement inconnu."

    def test_pagination_voir_plus(self, ctx):
        ctype = monthly_type(ctx)
        for day in range(3, 8):
            record(ctx, ctx.player, ctype, paid_on=past_day(day))
        client = client_for(ctx.player)
        first = client.get(url("my-payments"), {"limit": 2})
        assert first.data["count"] == 5 and len(first.data["results"]) == 2 and first.data["next_offset"] == 2
        last = client.get(url("my-payments"), {"limit": 2, "offset": 4})
        assert len(last.data["results"]) == 1 and last.data["next_offset"] is None
        assert client.get(url("my-payments"), {"limit": "abc"}).status_code == 400

    def test_le_bureau_ne_voit_ici_que_ses_propres_paiements(self, ctx):
        ctype = monthly_type(ctx)
        own = record(ctx, ctx.treasurer, ctype)
        record(ctx, ctx.player, ctype)
        for member in (ctx.treasurer, ctx.president):
            expected = [own.pk] if member is ctx.treasurer else []
            assert ids(client_for(member).get(url("my-payments"))) == expected

    def test_aucun_paiement(self, ctx):
        response = client_for(ctx.player).get(url("my-payments"))
        assert response.data == {"count": 0, "next_offset": None, "results": []}


class TestMyPaymentDetail:
    def test_detail_avec_repartition_par_mois(self, ctx):
        ctype = monthly_type(ctx)
        payment = record(ctx, ctx.player, ctype, "20")
        response = client_for(ctx.player).get(url("my-payment-detail", payment.pk))
        assert response.status_code == 200
        assert set(response.data) == PAYMENT_KEYS | {"allocations"}
        allocations = response.data["allocations"]
        assert sum(Decimal(line["amount"]) for line in allocations) == Decimal("20.00")
        assert set(allocations[0]) == {"period", "period_label", "amount"}
        periods = [line["period"] for line in allocations]
        assert periods == sorted(periods)

    def test_paiement_annule_consultable(self, ctx):
        ctype = monthly_type(ctx)
        payment = record(ctx, ctx.player, ctype, "20")
        cancel(ctx, payment)
        response = client_for(ctx.player).get(url("my-payment-detail", payment.pk))
        assert response.status_code == 200
        assert response.data["status"] == "cancelled"
        assert response.data["allocations"] == []

    def test_404_paiement_d_un_autre_joueur_du_club(self, ctx):
        ctype = monthly_type(ctx)
        theirs = record(ctx, ctx.vice_president, ctype)
        response = client_for(ctx.player).get(url("my-payment-detail", theirs.pk))
        assert response.status_code == 404
        assert response.data["detail"] == "Ce paiement n'existe pas dans ce club."

    def test_404_meme_pour_le_president(self, ctx):
        """Endpoint personnel : le bureau consulte les paiements des autres
        par le tableau de bord, jamais par « mes paiements »."""

        ctype = monthly_type(ctx)
        theirs = record(ctx, ctx.player, ctype)
        assert client_for(ctx.president).get(url("my-payment-detail", theirs.pk)).status_code == 404

    def test_404_paiement_d_un_autre_club(self, ctx, other_ctx):
        theirs = record(other_ctx, other_ctx.player, monthly_type(other_ctx))
        assert client_for(ctx.player).get(url("my-payment-detail", theirs.pk)).status_code == 404
        assert client_for(other_ctx.player).get(url("my-payment-detail", theirs.pk)).status_code == 200

    def test_404_declaration_non_validee(self, ctx):
        ctype = monthly_type(ctx)
        set_payment_link(ctx)
        pending = declare(ctx.player, ctype)
        assert client_for(ctx.player).get(url("my-payment-detail", pending.pk)).status_code == 404


class TestReceipt:
    def test_recu_indisponible_tant_que_le_fichier_n_existe_pas(self, ctx):
        payment = record(ctx, ctx.player, monthly_type(ctx))
        item = client_for(ctx.player).get(url("my-payments")).data["results"][0]
        assert item["receipt_available"] is False
        assert item["receipt_url"] is None
        assert payment.receipt_number is not None

    def test_recu_disponible_telechargeable_par_le_seul_joueur(self, ctx):
        payment = record(ctx, ctx.player, monthly_type(ctx))
        payment.receipt_file.save("recu.pdf", ContentFile(RECEIPT), save=True)
        item = client_for(ctx.player).get(url("my-payment-detail", payment.pk)).data
        assert item["receipt_available"] is True
        assert item["receipt_url"] == url("payment-receipt-download", payment.pk)
        download = client_for(ctx.player).get(item["receipt_url"])
        assert download.status_code == 200
        assert b"".join(download.streaming_content) == RECEIPT
        assert client_for(ctx.vice_president).get(item["receipt_url"]).status_code == 200  # lecteur bureau (2.4)
        other = player(ctx, "Autre", "Joueur")
        assert client_for(other).get(item["receipt_url"]).status_code == 404


# ---------------------------------------------------------------------------
# « Mes cotisations {année} » (ligne de grille)
# ---------------------------------------------------------------------------


@pytest.fixture
def grid_case(ctx):
    """Année précédente : le joueur A est rattaché à la mensuelle (12 mois
    dus, 45 payés) ; le joueur B, rattaché aussi, a tout payé ; un type
    rattaché ne concerne personne ; un type libre concerne tout le monde."""

    year = last_year(ctx)
    jan = datetime.date(year, 1, 1)
    ctype = attached_type(ctx, name="Mensuelle")
    unrelated = attached_type(ctx, name="Transport")
    free = free_monthly_type(ctx, name="Vestiaire")
    member_a = player(ctx, "Alice", "Ayo", joined_on=jan)
    member_b = player(ctx, "Bob", "Bula", joined_on=jan)
    for member in (member_a, member_b):
        attach(ctx, member, ctype, starts_on=jan)
        make_dues(ctx, member, ctype, range(1, 13), year=year)
    pay(ctx, member_a, ctype, "45", datetime.date(year, 1, 5), now=timezone.now())
    pay(ctx, member_b, ctype, "120", datetime.date(year, 1, 5), now=timezone.now())
    return {"year": year, "ctype": ctype, "unrelated": unrelated, "free": free, "a": member_a, "b": member_b}


class TestMyGrid:
    def test_forme_exacte_et_cellules_identiques_a_la_grille_du_bureau(self, ctx, grid_case):
        year, ctype, member = grid_case["year"], grid_case["ctype"], grid_case["a"]
        response = client_for(member).get(url("my-grid", year))
        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"
        data = response.data
        assert set(data) == {"year", "currency", "today", "months", "states", "player_status", "lines"}
        assert data["year"] == year and data["currency"] == "USD"
        assert len(data["months"]) == 12 and data["months"][0]["label"] == "janv."
        assert data["states"] == services.GRID_STATE_LABELS

        lines = {line["contribution_type"]["id"]: line for line in data["lines"]}
        assert set(lines) == {ctype.pk, grid_case["free"].pk}  # type « Transport » absent
        line = lines[ctype.pk]
        assert set(line) == {"contribution_type", "cells", "total", "overdue_amount", "has_unpaid"}

        bureau = services.build_contribution_grid(
            contribution_type=ctype, year=year, requested_by=ctx.treasurer.user, membership=member
        ).rows[0]
        assert [cell["state"] for cell in line["cells"]] == [cell.state for cell in bureau.cells]
        assert [cell["allocated"] for cell in line["cells"]] == [f"{cell.allocated:.2f}" for cell in bureau.cells]
        assert line["total"] == "45.00" == f"{bureau.total:.2f}"
        assert line["overdue_amount"] == "75.00" and line["has_unpaid"] is True
        assert [cell["state"] for cell in line["cells"][:5]] == ["paid", "paid", "paid", "paid", "partial"]
        assert line["cells"][4]["allocated"] == "5.00"

    def test_type_libre_jamais_en_dette(self, ctx, grid_case):
        data = client_for(grid_case["a"]).get(url("my-grid", grid_case["year"])).data
        free_line = next(line for line in data["lines"] if line["contribution_type"]["id"] == grid_case["free"].pk)
        assert {cell["state"] for cell in free_line["cells"]} == {"free"}
        assert free_line["overdue_amount"] == "0.00" and free_line["has_unpaid"] is False

    def test_situation_calculee_par_le_service(self, ctx, grid_case):
        member = grid_case["a"]
        data = client_for(member).get(url("my-grid", grid_case["year"])).data
        summary = services.get_balance_summary(member)
        assert data["player_status"]["balance"] == f"{summary.balance:.2f}"
        assert data["player_status"]["is_in_good_standing"] is False
        assert data["player_status"]["amount_due"] == f"{summary.amount_due:.2f}"

    def test_etancheite_entre_joueurs(self, ctx, grid_case):
        """B a tout payé : rien de ses données n'apparaît chez A, et inversement."""

        year, ctype = grid_case["year"], grid_case["ctype"]
        line_a = next(
            line for line in client_for(grid_case["a"]).get(url("my-grid", year)).data["lines"]
            if line["contribution_type"]["id"] == ctype.pk
        )
        line_b = next(
            line for line in client_for(grid_case["b"]).get(url("my-grid", year)).data["lines"]
            if line["contribution_type"]["id"] == ctype.pk
        )
        assert line_a["total"] == "45.00" and line_b["total"] == "120.00"
        assert line_b["has_unpaid"] is False

    def test_joueur_rattache_a_aucun_type(self, ctx, grid_case):
        loner = player(ctx, "Seul", "Sans", joined_on=datetime.date(grid_case["year"] + 1, 1, 1))
        data = client_for(loner).get(url("my-grid", grid_case["year"])).data
        assert data["lines"] == []

    def test_etancheite_entre_clubs(self, ctx, other_ctx, grid_case):
        other_type = attached_type(other_ctx, name="Mensuelle")
        response = client_for(other_ctx.player).get(url("my-grid", grid_case["year"]))
        assert response.status_code == 200
        assert response.data["currency"] == "CDF"
        type_ids = {line["contribution_type"]["id"] for line in response.data["lines"]}
        assert not type_ids & {grid_case["ctype"].pk, grid_case["free"].pk, grid_case["unrelated"].pk}
        assert other_type.pk not in type_ids  # rattaché à personne

    @pytest.mark.parametrize("year", [1999, 2999])
    def test_annee_invalide(self, ctx, year):
        response = client_for(ctx.player).get(url("my-grid", year))
        assert response.status_code == 400
        assert "Année invalide" in response.data["detail"]


class TestMyGridMonth:
    def test_detail_du_mois_lecture_seule(self, ctx, grid_case):
        year, ctype = grid_case["year"], grid_case["ctype"]
        response = client_for(grid_case["a"]).get(url("my-grid-month", ctype.pk, year, 5))
        assert response.status_code == 200
        data = response.data
        assert data["cell"]["state"] == "partial" and data["cell"]["allocated"] == "5.00"
        assert data["player"]["membership_id"] == grid_case["a"].pk
        assert data["can_record_payment"] is False
        assert len(data["payments"]) == 1
        assert data["payments"][0]["allocated"] == "5.00"
        assert data["payments"][0]["spread_label"] is not None

    def test_jamais_d_action_d_enregistrement_meme_pour_le_tresorier(self, ctx):
        year = last_year(ctx)
        ctype = attached_type(ctx)
        attach(ctx, ctx.treasurer, ctype, starts_on=datetime.date(year, 1, 1))
        response = client_for(ctx.treasurer).get(url("my-grid-month", ctype.pk, year, 1))
        assert response.status_code == 200
        assert response.data["can_record_payment"] is False

    def test_404_type_qui_ne_le_concerne_pas(self, ctx, grid_case):
        response = client_for(grid_case["a"]).get(url("my-grid-month", grid_case["unrelated"].pk, grid_case["year"], 1))
        assert response.status_code == 404

    def test_404_type_d_un_autre_club(self, ctx, other_ctx, grid_case):
        theirs = attached_type(other_ctx)
        response = client_for(grid_case["a"]).get(url("my-grid-month", theirs.pk, grid_case["year"], 1))
        assert response.status_code == 404

    def test_aucun_identifiant_de_joueur_accepte(self, ctx, grid_case):
        """Le joueur lu est toujours l'utilisateur connecté : B obtient sa
        propre cellule, jamais celle de A."""

        year, ctype = grid_case["year"], grid_case["ctype"]
        data = client_for(grid_case["b"]).get(url("my-grid-month", ctype.pk, year, 5)).data
        assert data["player"]["membership_id"] == grid_case["b"].pk
        assert data["cell"]["state"] == "paid"

    @pytest.mark.parametrize("month", [0, 13])
    def test_mois_invalide(self, ctx, grid_case, month):
        response = client_for(grid_case["a"]).get(url("my-grid-month", grid_case["ctype"].pk, grid_case["year"], month))
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Services : jamais les données d'un autre utilisateur
# ---------------------------------------------------------------------------


class TestOwnServices:
    def test_un_tiers_ne_peut_pas_lire_les_donnees_d_un_joueur(self, ctx):
        ctype = monthly_type(ctx)
        with pytest.raises(services.TreasuryPermissionError):
            services.own_payments_queryset(membership=ctx.player, requested_by=ctx.president.user)
        with pytest.raises(services.TreasuryPermissionError):
            services.build_own_contribution_lines(membership=ctx.player, year=last_year(ctx), requested_by=ctx.treasurer.user)
        with pytest.raises(services.TreasuryPermissionError):
            services.get_own_grid_month_detail(
                membership=ctx.player, contribution_type=ctype, year=last_year(ctx), month=1,
                requested_by=ctx.vice_president.user,
            )

    def test_type_d_un_autre_club_refuse(self, ctx, other_ctx):
        with pytest.raises(services.OwnContributionTypeNotFoundError):
            services.get_own_grid_month_detail(
                membership=ctx.player, contribution_type=monthly_type(other_ctx), year=last_year(ctx), month=1,
                requested_by=ctx.player.user,
            )


# ---------------------------------------------------------------------------
# Capacité « can_decide_payment_reversal » (CDC 4.4.4)
# ---------------------------------------------------------------------------


class TestDecideReversalCapability:
    ROLES = ["president", "vice_president", "treasurer", "assistant_treasurer", "player"]

    @pytest.mark.parametrize("role", ROLES)
    def test_president_seul(self, ctx, role):
        caps = client_for(getattr(ctx, role)).get(url("capabilities")).data["capabilities"]
        assert caps["can_decide_payment_reversal"] is (role == "president")

    @pytest.mark.parametrize("role", ROLES)
    def test_identique_a_l_approbation_reelle(self, ctx, role):
        payment = record(ctx, ctx.player, monthly_type(ctx))
        services.request_payment_reversal(payment=payment, reason="Erreur", requested_by=ctx.treasurer.user)
        client = client_for(getattr(ctx, role))
        allowed = client.get(url("capabilities")).data["capabilities"]["can_decide_payment_reversal"]
        # Seul le contrôle de rôle (403 ou non) est observé. Plus de PIN depuis
        # le 11/10/2026 : pour le Président, l'approbation aboutit réellement.
        response = client.post(url("payment-reversal-approve", payment.pk), {}, format="json")
        assert (response.status_code != 403) is allowed
        reject = client.post(url("payment-reversal-reject", payment.pk), {"rejection_reason": ""}, format="json")
        assert (reject.status_code != 403) is allowed

    def test_capacites_existantes_inchangees(self, ctx):
        caps = client_for(ctx.player).get(url("capabilities")).data["capabilities"]
        assert {key for key, value in caps.items() if value} == {"can_request_assistance"}
        assert "can_decide_payment_reversal" in caps
