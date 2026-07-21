"""Tests for magic_items (Del B1: bårne wondrous items → modifiers via effekt-motoren).

Bruger den seedede srd35.db (get_magic_item). Verificerer at et BÅRET item bidrager
sine modifiers, at backpack ikke gør, at stacking følger typereglen, og at ability-
forstærkere kaskaderer.
"""
import db
import effects
import items as items_module
from models import Character, AbilityScores, InventoryItem


def _char(inv):
    return Character(name="T", race="Human", cls="Fighter", level=1,
                     hp_current=10, hp_max=10,
                     ability_scores=AbilityScores(14, 12, 13, 10, 8, 11),
                     inventory=inv)


def test_catalog_row_decodes_modifiers():
    mi = db.get_magic_item("cloak_of_resistance_1")
    assert mi["name"] == "Cloak of Resistance +1"
    assert mi["modifiers"] == [{"target": "save_all", "type": "resistance", "value": 1}]
    assert mi["price_cp"] == 100000


def test_worn_item_contributes_backpack_does_not():
    worn = [InventoryItem(ref="magic_items/cloak_of_resistance_1", state="worn")]
    back = [InventoryItem(ref="magic_items/cloak_of_resistance_1", state="backpack")]
    mods_w, src = effects.magic_item_modifiers(worn, db)
    mods_b, _ = effects.magic_item_modifiers(back, db)
    assert mods_w == [{"target": "save_all", "type": "resistance", "value": 1}]
    assert src[0]["name"] == "Cloak of Resistance +1"
    assert mods_b == []


def test_cloak_raises_all_saves():
    c = _char([InventoryItem(ref="magic_items/cloak_of_resistance_2", state="worn")])
    mods, _ = effects.collect_character_effects(c, db)
    assert all(effects.save_effect_bonus(mods, s) == 2
               for s in ("fortitude", "reflex", "will"))


def test_ring_of_protection_is_deflection_ac():
    c = _char([InventoryItem(ref="magic_items/ring_of_protection_1", state="worn")])
    mods, _ = effects.collect_character_effects(c, db)
    ac = [m for m in mods if m.get("target") == "ac"]
    assert ac == [{"target": "ac", "type": "deflection", "value": 1}]


def test_ability_booster_cascades():
    c = _char([InventoryItem(ref="magic_items/belt_of_giant_strength_4", state="worn")])
    mods, _ = effects.collect_character_effects(c, db)
    eff = effects.effective_ability_scores(c.ability_scores, mods)
    assert eff.str == 18                    # 14 base + 4 enhancement


def test_same_type_does_not_stack():
    c = _char([InventoryItem(ref="magic_items/cloak_of_resistance_2", state="worn"),
               InventoryItem(ref="magic_items/cloak_of_resistance_1", state="worn")])
    mods, _ = effects.collect_character_effects(c, db)
    assert effects.save_effect_bonus(mods, "will") == 2    # kun den højeste resistance


def test_inventory_resolves_name_and_weight_from_catalog():
    it = InventoryItem(ref="magic_items/cloak_of_resistance_2", state="worn")
    r = items_module.resolve_item(it, db)
    assert r["name"] == "Cloak of Resistance +2"
    assert r["source"] == "magic_items"
