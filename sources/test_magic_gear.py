"""Tests for magic_gear — den rene magiske-enhancement-overlay-motor.

Hermetisk (ingen DB): base-genstande konstrueres inline. Priser er verificeret mod
kendte SRD-markedspriser (+1 longsword 2.315 gp, +5 longsword 50.315 gp,
+1 full plate 2.650 gp, +2 heavy steel shield 4.170 gp).

Kør: python -m pytest test_magic_gear.py   (fra sources/)
"""
import pytest

import magic_gear as mg

LONGSWORD = {"name": "Longsword", "cost_cp": 1500}          # 15 gp
FULL_PLATE = {"name": "Full Plate", "cost_cp": 150000}      # 1.500 gp
HEAVY_SHIELD = {"name": "Heavy Steel Shield", "type": "shield", "cost_cp": 2000}  # 20 gp


def test_weapon_bonuses_apply_to_attack_and_damage():
    w = mg.enhance_weapon(LONGSWORD, 3)
    assert w["enhancement"] == 3
    assert w["attack_bonus"] == 3 and w["damage_bonus"] == 3
    assert w["masterwork"] is True
    assert w["caster_level"] == 9                 # 3 × bonus


def test_weapon_name_prefixes_bonus():
    assert mg.enhance_weapon(LONGSWORD, 1)["name"] == "+1 Longsword"


def test_weapon_price_matches_srd():
    # +1 longsword = base 15 + masterwork 300 + 2.000 = 2.315 gp
    assert mg.enhance_weapon(LONGSWORD, 1)["total_cost_cp"] == 231500
    # +5 longsword = 15 + 300 + 2.000×25 = 50.315 gp
    assert mg.enhance_weapon(LONGSWORD, 5)["total_cost_cp"] == 5031500


def test_armor_bonus_is_ac_and_reduces_acp():
    a = mg.enhance_armor(FULL_PLATE, 1)
    assert a["ac_bonus"] == 1
    assert a["acp_reduction"] == 1                # masterwork
    assert a["name"] == "+1 Full Plate"
    # +1 full plate = 1.500 + masterwork 150 + 1.000 = 2.650 gp
    assert a["total_cost_cp"] == 265000


def test_shield_uses_shield_pricing():
    s = mg.enhance_armor(HEAVY_SHIELD, 2)
    assert s["ac_bonus"] == 2
    # +2 heavy steel shield = 20 + 150 + 1.000×4 = 4.170 gp
    assert s["total_cost_cp"] == 417000


def test_added_cost_is_item_independent():
    # Prisen magien lægger til afhænger kun af type + bonus, ikke basisgenstanden.
    assert mg.added_cost_cp("weapons", 2) == (300 + 2000 * 4) * 100
    assert mg.added_cost_cp("armor", 2) == (150 + 1000 * 4) * 100


@pytest.mark.parametrize("bonus", [0, 6, -1, 2.5, "1"])
def test_invalid_bonus_raises(bonus):
    with pytest.raises(ValueError):
        mg.enhance_weapon(LONGSWORD, bonus)


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        mg.added_cost_cp("potions", 1)


def test_as_inventory_item_weapon():
    kw = mg.as_inventory_item("weapons/longsword", 1)
    assert kw == {"ref": "weapons/longsword", "enhancement": 1,
                  "state": "backpack", "bonus": 1}


def test_as_inventory_item_armor_has_no_to_hit_bonus():
    kw = mg.as_inventory_item("armor/full-plate", 2)
    assert kw == {"ref": "armor/full-plate", "enhancement": 2, "state": "backpack"}
    assert "bonus" not in kw                     # rustning: enhancement→AC, ingen til-hit


def test_as_inventory_item_rejects_non_gear():
    with pytest.raises(ValueError):
        mg.as_inventory_item("items/torch", 1)


def test_as_inventory_item_rejects_bad_bonus():
    with pytest.raises(ValueError):
        mg.as_inventory_item("weapons/longsword", 0)
