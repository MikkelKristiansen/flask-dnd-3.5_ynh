"""specific_items — visnings-helpers for navngivne specifics (Del C).

db.get_specific_item leverer den rå række (abilities afkodet). Dette modul beriger
den til inspektør-visning: pris i gp, ability-navne, base-genstandens navn. Selve
give-loot'et (base_ref + enhancement + abilities → InventoryItem) genbruger Del A's
magic_gear.as_inventory_item i dm.py. Ren formatering — kun opslag på den givne række.
"""
from __future__ import annotations

import catalog
import db
import magic_abilities


def specific_item_view(row: dict) -> dict:
    """Katalog-række → visnings-dict: pris-streng + ability-navne + base-navn."""
    v = dict(row)
    v["price_str"] = catalog.format_cost(row.get("price_cp") or 0)
    v["ability_names"] = [a["name"] for a in magic_abilities.resolve(row.get("abilities") or [])]
    table, _, oid = (row.get("base_ref") or "").partition("/")
    base = (db.get_weapon(oid) if table == "weapons"
            else db.get_armor(oid) if table == "armor" else None)
    v["base_name"] = base["name"] if base else oid
    return v
