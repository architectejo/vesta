"""Saisie des montants par l'API : virgule décimale partout (décision client
du 15/11/2026).

Un seul champ de sérialiseur (``apps.treasury.fields.MoneyField``) applique
EXACTEMENT les règles de ``services.to_money`` (une seule source de vérité) :
virgule ou point décimal acceptés, plus de 2 décimales, notation
scientifique, séparateur de milliers et flottants refusés, jamais arrondis
en silence. Les montants renvoyés par l'API restent au format « 10.50 ».
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import serializers
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.treasury import services
from apps.treasury.fields import MoneyField
from apps.treasury.models import ContributionType, Expense, ExpenseCategory, SocialAssistanceScale
from apps.treasury.tests.expense_helpers import club_today, make_category

pytestmark = pytest.mark.django_db

ACCEPTED = [
    ("10,50", Decimal("10.50")),
    ("10.50", Decimal("10.50")),
    ("12,5", Decimal("12.50")),
    (" 7 ", Decimal("7.00")),
    ("0,99", Decimal("0.99")),
    ("10,", Decimal("10.00")),  # accepté par ``to_money`` : même règle ici
    (15, Decimal("15.00")),
    (Decimal("3.4"), Decimal("3.40")),
    # Nombre JSON : lu dans son écriture exacte, puis mêmes règles que le texte.
    (12.5, Decimal("12.50")),
    (0.1, Decimal("0.10")),
]
REFUSED = [
    "10,555", "10.555", "1e3", "1 000", "1.000,50", "abc", "", True,
    10.555, float("nan"), float("inf"), 1e22, [], {},
]


def _as_text(raw):
    """Valeur qu'analyse réellement ``to_money`` pour un nombre JSON."""

    return repr(raw) if isinstance(raw, float) else raw


def client_for(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def url(name, *args):
    return reverse(f"treasury:{name}", args=args)


def _expected_message(raw) -> str:
    with pytest.raises(services.InvalidAmountError) as exc:
        services.to_money(raw)
    return str(exc.value)


# ---------------------------------------------------------------------------
# Le champ lui-même : mêmes règles que ``to_money``
# ---------------------------------------------------------------------------


class _Form(serializers.Serializer):
    amount = MoneyField()
    optional = MoneyField(required=False, allow_null=True)


class TestMoneyField:
    @pytest.mark.parametrize("raw,expected", ACCEPTED)
    def test_accepte_virgule_et_point(self, raw, expected):
        form = _Form(data={"amount": raw})
        assert form.is_valid(), form.errors
        value = form.validated_data["amount"]
        assert isinstance(value, Decimal)
        assert value == expected
        assert value == services.to_money(_as_text(raw))  # une seule source de vérité
        assert value.as_tuple().exponent == -2

    @pytest.mark.parametrize("raw", [r for r in REFUSED if not isinstance(r, (list, dict))])
    def test_refuse_avec_le_message_de_to_money(self, raw):
        form = _Form(data={"amount": raw})
        assert not form.is_valid()
        assert [str(m) for m in form.errors["amount"]] == [_expected_message(_as_text(raw))]

    @pytest.mark.parametrize("raw", [[], {}])
    def test_refuse_les_structures(self, raw):
        form = _Form(data={"amount": raw})
        assert not form.is_valid()
        assert "Montant invalide" in str(form.errors["amount"][0])

    def test_montant_trop_eleve(self):
        form = _Form(data={"amount": "99999999999"})
        assert not form.is_valid()
        assert str(form.errors["amount"][0]) == "Montant trop élevé."

    def test_obligatoire_et_null(self):
        form = _Form(data={})
        assert not form.is_valid() and "amount" in form.errors
        form = _Form(data={"amount": "5", "optional": None})
        assert form.is_valid(), form.errors
        assert form.validated_data["optional"] is None

    def test_representation_au_point_decimal(self):
        assert MoneyField().to_representation(Decimal("10.5")) == "10.50"


# ---------------------------------------------------------------------------
# Endpoints de saisie
# ---------------------------------------------------------------------------


def _type_payload(**overrides):
    data = {
        "name": "Mensuelle",
        "nature": ContributionType.Nature.MANDATORY,
        "amount": "20,50",
        "periodicity": ContributionType.Periodicity.MONTHLY,
        "scope": ContributionType.Scope.ALL,
    }
    data.update(overrides)
    return data


class TestContributionTypeAmount:
    def test_creation_et_modification_a_la_virgule(self, ctx):
        client = client_for(ctx.president.user)
        created = client.post(url("contribution-type-list"), _type_payload(), format="json")
        assert created.status_code == 201, created.data
        assert created.data["amount"] == "20.50"
        ctype = ContributionType.all_objects.get(pk=created.data["id"])
        assert ctype.amount == Decimal("20.50")

        updated = client.patch(url("contribution-type-detail", ctype.pk), {"amount": "25,5"}, format="json")
        assert updated.status_code == 200, updated.data
        assert updated.data["amount"] == "25.50"

    def test_multipart_a_la_virgule(self, ctx):
        response = client_for(ctx.president.user).post(
            url("contribution-type-list"), _type_payload(amount="9,90"), format="multipart"
        )
        assert response.status_code == 201, response.data
        assert response.data["amount"] == "9.90"

    @pytest.mark.parametrize("raw", ["20,555", "1e3", "1 000", 20.555])
    def test_saisie_refusee_sans_ecriture(self, ctx, raw):
        response = client_for(ctx.president.user).post(
            url("contribution-type-list"), _type_payload(amount=raw), format="json"
        )
        assert response.status_code == 400
        assert str(response.data["amount"][0]).startswith("Montant invalide")
        assert not ContributionType.all_objects.filter(club=ctx.club).exists()

    def test_type_libre_sans_montant(self, ctx):
        response = client_for(ctx.president.user).post(
            url("contribution-type-list"),
            _type_payload(nature=ContributionType.Nature.FREE, amount=None),
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["amount"] is None


class TestExpenseAmounts:
    def test_plafond_de_categorie_a_la_virgule(self, ctx):
        client = client_for(ctx.treasurer.user)
        created = client.post(
            url("expense-category-list"), {"name": "Soins", "ceiling": "150,75"}, format="json"
        )
        assert created.status_code == 201, created.data
        assert created.data["ceiling"] == "150.75"
        category = ExpenseCategory.all_objects.get(pk=created.data["id"])
        updated = client.patch(url("expense-category-detail", category.pk), {"ceiling": "80,5"}, format="json")
        assert updated.status_code == 200, updated.data
        assert updated.data["ceiling"] == "80.50"
        refused = client.patch(url("expense-category-detail", category.pk), {"ceiling": "80,555"}, format="json")
        assert refused.status_code == 400
        assert "ceiling" in refused.data

    def test_depense_a_la_virgule(self, ctx):
        category = make_category(ctx)
        response = client_for(ctx.treasurer.user).post(
            url("expense-list"),
            {
                "category_id": category.pk,
                "amount": "25,40",
                "beneficiary_name": "Pharmacie",
                "reason": "Soins",
                "expense_date": club_today(ctx).isoformat(),
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["amount"] == "25.40"
        assert Expense.all_objects.get(pk=response.data["id"]).amount == Decimal("25.40")

    @pytest.mark.parametrize("raw", ["25,404", "2e1", "1 000"])
    def test_depense_refusee(self, ctx, raw):
        category = make_category(ctx)
        response = client_for(ctx.treasurer.user).post(
            url("expense-list"),
            {
                "category_id": category.pk,
                "amount": raw,
                "beneficiary_name": "Pharmacie",
                "reason": "Soins",
                "expense_date": club_today(ctx).isoformat(),
            },
            format="json",
        )
        assert response.status_code == 400
        assert str(response.data["amount"][0]).startswith("Montant invalide")
        assert not Expense.all_objects.filter(club=ctx.club).exists()


class TestSocialAssistanceScaleAmount:
    def test_bareme_a_la_virgule(self, ctx):
        category = make_category(ctx, name="Assistance", good_standing_only=True)
        client = client_for(ctx.treasurer.user)
        created = client.post(
            url("social-assistance-scale-list"),
            {"event_type": "birth", "amount": "30,25", "processing_days": 5, "expense_category_id": category.pk},
            format="json",
        )
        assert created.status_code == 201, created.data
        assert created.data["amount"] == "30.25"
        updated = client.patch(
            url("social-assistance-scale-detail", created.data["id"]), {"amount": "45,5"}, format="json"
        )
        assert updated.status_code == 200, updated.data
        assert updated.data["amount"] == "45.50"
        assert SocialAssistanceScale.all_objects.get(pk=created.data["id"]).amount == Decimal("45.50")
        refused = client.patch(
            url("social-assistance-scale-detail", created.data["id"]), {"amount": "1e2"}, format="json"
        )
        assert refused.status_code == 400
        assert "amount" in refused.data


class TestPaymentEntriesAlreadyAcceptComma:
    """Saisie de paiement et « J'ai payé » : déjà conformes (``to_money``),
    verrouillés ici pour ne pas régresser."""

    def test_aperçu_de_paiement_a_la_virgule(self, ctx):
        from apps.treasury.tests.cash_helpers import monthly_type

        ctype = monthly_type(ctx)
        response = client_for(ctx.treasurer.user).post(
            url("payment-preview"),
            {
                "membership_id": ctx.player.pk,
                "contribution_type_id": ctype.pk,
                "amount": "12,50",
                "paid_on": (club_today(ctx) - datetime.timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        assert response.status_code == 200, response.data
        assert response.data["amount"] == "12.50"
