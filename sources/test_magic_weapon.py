"""Unit-test: magisk enhancement på et våben → +N til-hit OG +N skade (Fase C trin 3).

Kør: python -m pytest test_magic_weapon.py   (fra sources/)

Et DM-loot-våben bærer item.enhancement (magisk +N). Til-hit-siden kommer via
item.bonus ("masterwork/magi"), skade-siden via enhancement (derive_attacks/make).
Ændringen er additiv: et almindeligt våben (enhancement=0) er uændret.
"""
import db
from character import InventoryItem, derive_attacks, AbilityScores, attack_total

_STR10 = AbilityScores(str=10, dex=10)     # mod 0 → isolerer magi-bidraget


def _wielded(ref, **kw):
    atks = derive_attacks([InventoryItem(ref=ref, state="wielded", **kw)], db, size="medium")
    return atks[0]


def test_plain_weapon_has_no_magic_damage():
    a = _wielded("weapons/longsword")
    r = attack_total(a, _STR10, bab=1, size="medium")
    assert r["to_hit"] == 1            # BAB1, ingen magi
    assert r["damage"] == "1d8"        # ingen Str-mod, ingen enhancement


def test_magic_weapon_adds_to_hit_and_damage():
    # Præcis som DM-loot bygges (magic_gear.as_inventory_item + endpoint):
    # name "+1 …", bonus (til-hit) + enhancement (skade).
    a = _wielded("weapons/longsword", name="+1 Longsword", bonus=1, enhancement=1)
    assert a.name == "+1 Longsword"
    r = attack_total(a, _STR10, bab=1, size="medium")
    assert r["to_hit"] == 2            # BAB1 + magi1
    assert r["damage"] == "1d8+1"      # enhancement +1 til skade


def test_enhancement_damage_scales():
    a = _wielded("weapons/longsword", name="+3 Longsword", bonus=3, enhancement=3)
    r = attack_total(a, _STR10, bab=5, size="medium")
    assert r["to_hit"] == 8            # BAB5 + magi3
    assert r["damage"] == "1d8+3"
