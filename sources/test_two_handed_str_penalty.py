"""Unit-tests: en Str-STRAF multipliceres aldrig af tohånds/off-hånds-faktoren.

Kør: python -m pytest test_two_handed_str_penalty.py   (fra sources/)

Bug: tohånds ganger Str ×1.5, men koden ganger også en negativ modifier
(floor(-1 · 1.5) = -2). RAW/Rules Compendium: kun en Str-*bonus* multipliceres —
en straf tæller ×1. Tjørn (gnome, Str 9 = -1) med et Small masterwork-spyd skal
altså slå 1d6-1, ikke 1d6-2. Se _str_damage_bonus i attacks.py.
"""
import db
from character import (AbilityScores, Attack, attack_total,
                       attack_damage_breakdown, derive_attacks, InventoryItem)


# --- Ende-til-ende: Tjørns faktiske tilfælde (Small gnome, Str 9, tohånds-spyd) ---

def test_tjorn_small_spear_str_penalty_not_doubled():
    inv = [InventoryItem(ref="weapons/spear", state="wielded")]
    atk = derive_attacks(inv, db, size="small")[0]
    assert atk.str_damage_mult == 1.5          # tohånds → ×1.5-sti bekræftet
    r = attack_total(atk, AbilityScores(str=9), bab=1, size="small")  # -1
    assert r["damage"] == "1d6-1"              # IKKE 1d6-2


# --- Enheds-niveau: kernen i reglen, uafhængigt af våbendata ---

def test_two_handed_penalty_applied_once():
    atk = Attack(name="Spyd", base_damage="1d8", str_damage_mult=1.5)
    r = attack_total(atk, AbilityScores(str=9), bab=0, size="medium")  # -1
    assert r["damage"] == "1d8-1"


def test_two_handed_bonus_still_scaled():
    # Regression: en positiv Str-bonus SKAL stadig ganges med 1.5.
    atk = Attack(name="Spyd", base_damage="1d8", str_damage_mult=1.5)
    r = attack_total(atk, AbilityScores(str=14), bab=0, size="medium")  # +2 → +3
    assert r["damage"] == "1d8+3"


def test_off_hand_penalty_applied_once():
    atk = Attack(name="Dolk (off)", base_damage="1d4", str_damage_mult=0.5)
    r = attack_total(atk, AbilityScores(str=9), bab=0, size="medium")  # -1
    assert r["damage"] == "1d4-1"


# --- Hover-opdelingen viser samme (rettede) tal ---

def test_breakdown_shows_penalty_once():
    atk = Attack(name="Spyd", base_damage="1d6", str_damage_mult=1.5)
    bd = attack_damage_breakdown(atk, AbilityScores(str=9))  # -1
    assert bd["total"] == "1d6-1"
    str_line = [p for p in bd["parts"] if p["label"].startswith("STR")]
    assert str_line and str_line[0]["value"] == -1
