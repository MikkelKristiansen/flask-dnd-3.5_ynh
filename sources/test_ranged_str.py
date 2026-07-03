"""Unit-tests for ranged Str-til-skade (composite bue, regular bue, kaster-våben).

Kør: python -m pytest test_ranged_str.py   (fra sources/)

Bug: _DEFAULT_STR_MULT["ranged"] gav ALLE ranged-våben 0 Str til skade. Korrekt
kun for armbrøster. Denne fil dækker de øvrige tilfælde (data-drevet via
weapons.ranged_str — se briefs/BRIEF-composite-bow-str-damage.md, Model A:
composite = fuld Str-bonus, rating-cap på ære).
"""
import db
from character import (AbilityScores, Attack, attack_total,
                       attack_damage_breakdown, derive_attacks, InventoryItem)


def test_composite_shortbow_adds_str_bonus():
    inv = [InventoryItem(ref="weapons/shortbow_composite", state="wielded")]
    atk = derive_attacks(inv, db)[0]
    assert atk.str_penalty_only is False
    assert atk.str_damage_mult == 1.0
    r = attack_total(atk, AbilityScores(str=12), bab=1, size="medium")  # +1
    assert r["damage"] == "1d6+1"


def test_composite_shortbow_str_penalty_applies():
    inv = [InventoryItem(ref="weapons/shortbow_composite", state="wielded")]
    atk = derive_attacks(inv, db)[0]
    r = attack_total(atk, AbilityScores(str=8), bab=1, size="medium")  # -1
    assert r["damage"] == "1d6-1"


def test_regular_shortbow_ignores_str_bonus():
    inv = [InventoryItem(ref="weapons/shortbow", state="wielded")]
    atk = derive_attacks(inv, db)[0]
    assert atk.str_penalty_only is True
    r = attack_total(atk, AbilityScores(str=14), bab=1, size="medium")  # +2, men ignoreres
    assert r["damage"] == "1d6"


def test_regular_shortbow_keeps_str_penalty():
    inv = [InventoryItem(ref="weapons/shortbow", state="wielded")]
    atk = derive_attacks(inv, db)[0]
    r = attack_total(atk, AbilityScores(str=8), bab=1, size="medium")  # -1, tæller
    assert r["damage"] == "1d6-1"


def test_sling_gets_full_str():
    inv = [InventoryItem(ref="weapons/sling", state="wielded")]
    atk = derive_attacks(inv, db)[0]
    r = attack_total(atk, AbilityScores(str=12), bab=1, size="medium")  # +1
    assert r["damage"] == "1d4+1"


def test_crossbow_unaffected_by_str():
    inv = [InventoryItem(ref="weapons/crossbow_light", state="wielded")]
    atk = derive_attacks(inv, db)[0]
    assert atk.str_penalty_only is False
    r = attack_total(atk, AbilityScores(str=12), bab=1, size="medium")  # +1, ignoreres
    assert r["damage"] == "1d8"


def test_breakdown_regular_bow_shows_no_str_line():
    w = Attack(name="Shortbow", base_damage="1d6", str_damage_mult=1.0,
              str_penalty_only=True)
    bd = attack_damage_breakdown(w, AbilityScores(str=14))  # +2, klampet til 0
    labels = [p["label"] for p in bd["parts"]]
    assert "STR" not in labels
    assert bd["total"] == "1d6"


def test_breakdown_composite_bow_shows_str_bonus():
    w = Attack(name="Composite shortbow", base_damage="1d6", str_damage_mult=1.0)
    bd = attack_damage_breakdown(w, AbilityScores(str=12))  # +1
    labels = {p["label"]: p for p in bd["parts"]}
    assert labels["STR"]["value"] == 1
    assert bd["total"] == "1d6+1"
