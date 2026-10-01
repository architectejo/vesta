"""Montants (invariant 12 ; CLAUDE.md 7 ; decision D7 de schema-treasury.md)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.treasury.services import InvalidAmountError, to_money


@pytest.mark.parametrize(
    "raw, expected",
    [
        (Decimal("5"), Decimal("5.00")),
        ("5", Decimal("5.00")),
        (5, Decimal("5.00")),
        ("5.005", Decimal("5.01")),  # D7 : ROUND_HALF_UP
        ("5.004", Decimal("5.00")),
        (Decimal("0.125"), Decimal("0.13")),
    ],
)
def test_to_money_arrondit_a_deux_decimales_half_up(raw, expected):
    value = to_money(raw)
    assert value == expected
    assert isinstance(value, Decimal)
    assert value.as_tuple().exponent == -2


@pytest.mark.parametrize("raw", [5.0, 0.1, True, None, "abc", "", "NaN", "Infinity"])
def test_to_money_refuse_float_booleen_et_valeurs_illisibles(raw):
    with pytest.raises(InvalidAmountError) as exc:
        to_money(raw)
    assert "montant" in str(exc.value).lower()
