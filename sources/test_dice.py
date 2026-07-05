"""Unit-tests for dice.py — ren terninglogik.

Kør: python -m pytest test_dice.py   (fra sources/)
"""
import pytest

import dice


def test_simple_die():
    r = dice.roll("1d6")
    assert 1 <= r["rolls"][0] <= 6
    assert r["total"] == r["rolls"][0]


def test_die_with_modifier():
    r = dice.roll("1d8+3")
    assert r["modifier"] == 3
    assert r["total"] == r["rolls"][0] + 3


def test_flat_number_no_die_rolled():
    # Cure Minor Wounds: fast 1 punkt, ingen tilfældighed.
    assert dice.roll("1") == {"rolls": [], "modifier": 1, "total": 1}


def test_flat_expression_with_leading_zero_and_bonus():
    # Heal-formlen bygges som "0+150" (base 0 + skaleret bonus).
    assert dice.roll("0+150") == {"rolls": [], "modifier": 150, "total": 150}


def test_invalid_expression_still_raises():
    with pytest.raises(ValueError):
        dice.roll("abc")


def test_empty_expression_raises():
    with pytest.raises(ValueError):
        dice.roll("")
