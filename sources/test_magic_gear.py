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


# ── Special abilities (Del A: pris + navn; mekanik wires senere) ────────────
FLAMING = {"id": "flaming", "name": "Flaming", "price": {"type": "bonus", "value": 1}}
KEEN    = {"id": "keen",    "name": "Keen",    "price": {"type": "bonus", "value": 1}}
GLAMERED = {"id": "glamered", "name": "Glamered", "price": {"type": "flat", "value": 2700}}


def test_bonus_ability_raises_effective_bonus_for_price():
    # +1 Flaming longsword prissættes som effektiv +2: 15 + 300 + 2.000×2² = 8.315 gp
    w = mg.enhance_weapon(LONGSWORD, 1, [FLAMING])
    assert w["name"] == "+1 Flaming Longsword"
    assert w["enhancement"] == 1                       # kamptal uændret (ikke +2)
    assert w["attack_bonus"] == 1 and w["damage_bonus"] == 1
    assert w["total_cost_cp"] == 831500
    assert w["caster_level"] == 6                       # 3 × effektiv 2


def test_multiple_bonus_abilities_sum_into_effective():
    # +2 Flaming Keen = effektiv +4: 15 + 300 + 2.000×4² = 32.315 gp
    w = mg.enhance_weapon(LONGSWORD, 2, [FLAMING, KEEN])
    assert w["name"] == "+2 Flaming Keen Longsword"
    assert w["total_cost_cp"] == 3231500


def test_flat_ability_adds_fixed_gp_not_bonus():
    # Glamered er +2.700 gp fast; effektiv bonus forbliver +1
    a = mg.enhance_armor(FULL_PLATE, 1, [GLAMERED])
    assert a["name"] == "+1 Glamered Full Plate"
    # 1.500 + 150 + 1.000×1² + 2.700 = 5.350 gp
    assert a["total_cost_cp"] == 535000


def test_effective_bonus_cap_enforced():
    speed = {"id": "speed", "name": "Speed", "price": {"type": "bonus", "value": 3}}
    vorpal = {"id": "vorpal", "name": "Vorpal", "price": {"type": "bonus", "value": 5}}
    with pytest.raises(ValueError):              # 5 + 3 + 5 = +13 > +10
        mg.enhance_weapon(LONGSWORD, 5, [speed, vorpal])


def test_no_abilities_is_backward_compatible():
    # Uden abilities er resultatet identisk med den rene enhancement-pris
    assert mg.enhance_weapon(LONGSWORD, 1, [])["total_cost_cp"] == \
           mg.enhance_weapon(LONGSWORD, 1)["total_cost_cp"]


def test_as_inventory_item_carries_ability_ids():
    kw = mg.as_inventory_item("weapons/longsword", 1, ["flaming", "keen"])
    assert kw["abilities"] == ["flaming", "keen"]
