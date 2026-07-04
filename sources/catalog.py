"""Berig udstyrs-kataloget til udrustningsbutikken.

Ét ansvar: saml weapons + armor + items til én liste og påfør pr. post de tal
UI'et skal bruge (formateret pris, størrelses-justeret vægt, proficient-flag,
anbefalet-flag, detalje-felter).

Den gyldne regel: Python ejer reglerne. Dette modul REGNER ingen 3.5-regler selv
— al regel-afledt udregning (vægt-skalering, proficiency, bæreevne) sker via
`rules.py`. Her samles og formateres kun, så JS bagefter blot kan lægge sammen.
"""

import rules
from attacks import weapon_proficient, armor_proficient
from items import carry_limits, cost_for_size, material_modifiers, weight_for_size, weight_kind


def format_cost(cost_cp) -> str:
    """cp → læsbar pris: 1500→'15 gp', 70→'7 sp', 205→'2 gp 5 cp', 0/None→'—'."""
    cp = int(cost_cp or 0)
    if cp == 0:
        return "—"
    gp, rem = divmod(cp, 100)
    sp, c = divmod(rem, 10)
    parts = []
    if gp:
        parts.append(f"{gp} gp")
    if sp:
        parts.append(f"{sp} sp")
    if c:
        parts.append(f"{c} cp")
    return " ".join(parts)


def _humanize(text: str) -> str:
    """'one-handed' / 'adventuring_gear' → 'One-Handed' / 'Adventuring Gear'."""
    return (text or "").replace("_", " ").replace("-", " ").title()


def _row_weight(record: dict, table: str, size: str) -> float:
    """Størrelses-justeret enhedsvægt for én katalog-række (via rules.py)."""
    base = record.get("weight") or 0.0
    if table == "items":
        bundle = record.get("bundle") or 1
        if bundle > 1:
            base = base / bundle
    return weight_for_size(base, weight_kind(table, record), size)


def _row_cost(record: dict, table: str, size: str) -> int:
    """Størrelses-justeret enhedspris (cp) for én katalog-række (via rules.py).

    Samme skaleringsklasse som vægten (weight_kind): kun våben/rustning ændrer pris
    med størrelse, og kun ved Large (×2). Gear er uændret.
    """
    return cost_for_size(record.get("cost_cp"), weight_kind(table, record), size)


def _weapon_entry(w: dict, *, weapon_prof, allowed_weapons, recommended, size) -> dict:
    dmg = w.get("dmg_s") if (size or "").lower() == "small" else w.get("dmg_m")
    cost = _row_cost(w, "weapons", size)
    return {
        "ref": f"weapons/{w['id']}",
        "name": w["name"],
        "category": "weapons",
        "group": f"{_humanize(w.get('category'))} {_humanize(w.get('weapon_class'))}".strip(),
        "cost_cp": cost,
        "cost_str": format_cost(cost),
        "weight": _row_weight(w, "weapons", size),
        "proficient": weapon_proficient(w, weapon_prof, allowed_weapons),
        "recommended": w["id"] in recommended,
        "description": w.get("description"),
        "modifiers": material_modifiers(w, "weapons", size),
        "detail": {
            "dmg": dmg,
            "crit": w.get("critical"),
            "type": w.get("damage_type"),
            "range_ft": w.get("range_ft"),
        },
    }


def _armor_entry(a: dict, *, armor_prof, allowed_armor, recommended, size) -> dict:
    is_shield = a.get("type") == "shield"
    group = "Shields" if is_shield else f"{_humanize(a.get('type'))} Armor"
    cost = _row_cost(a, "armor", size)
    return {
        "ref": f"armor/{a['id']}",
        "name": a["name"],
        "category": "armor",
        "group": group,
        "cost_cp": cost,
        "cost_str": format_cost(cost),
        "weight": _row_weight(a, "armor", size),
        "proficient": armor_proficient(a, armor_prof, allowed_armor),
        "recommended": a["id"] in recommended,
        "description": a.get("description"),
        "modifiers": material_modifiers(a, "armor", size),
        "detail": {
            "ac": a.get("armor_bonus"),
            "max_dex": a.get("max_dex"),
            "check": a.get("armor_check"),
            "spell_failure": a.get("spell_failure"),
        },
    }


def _item_entry(it: dict, *, recommended, size) -> dict:
    cost = _row_cost(it, "items", size)
    return {
        "ref": f"items/{it['id']}",
        "name": it["name"],
        "category": "items",
        "group": _humanize(it.get("category")),
        "cost_cp": cost,
        "cost_str": format_cost(cost),
        "weight": _row_weight(it, "items", size),
        "proficient": True,           # almindeligt gear har ingen proficiency
        "recommended": it["id"] in recommended,
        "description": it.get("description"),
        "modifiers": [],              # gear har ingen materiale-modifikatorer
        "detail": {},
    }


def build_catalog(db, *, weapon_prof=None, armor_prof=None,
                  allowed_weapons=frozenset(), allowed_armor=frozenset(),
                  recommended_ids=frozenset(), str_score: int = 10,
                  size: str = "medium") -> dict:
    """Byg det berigede katalog som UI'et tegnes ud fra.

    Parametre (ikke en karakter — også brugt under generering hvor den ikke findes):
      weapon_prof / armor_prof   klassens proficiency-blokke (None = ingen straf)
      allowed_weapons / _armor   ekstra tilladte id'er (fx race-våben)
      recommended_ids            id'er der markeres 'anbefalet' (fra starting_kits)
      str_score / size           til bæreevne-grænserne (enc_limits)

    Returnerer {"items": [...], "enc_limits": {light, medium, heavy}}.
    """
    items = []
    for w in db.get_all_weapons():
        items.append(_weapon_entry(
            w, weapon_prof=weapon_prof, allowed_weapons=allowed_weapons,
            recommended=recommended_ids, size=size))
    for a in db.get_all_armor():
        items.append(_armor_entry(
            a, armor_prof=armor_prof, allowed_armor=allowed_armor,
            recommended=recommended_ids, size=size))
    for it in db.get_all_items():
        items.append(_item_entry(it, recommended=recommended_ids, size=size))

    return {"items": items, "enc_limits": carry_limits(str_score, size)}


def apply_material_overlay(record: dict, table: str, mods) -> dict:
    """Oversæt valgte materiale-mods → ekstra inventar-felter (Fase A-semantik).

    Kun masterwork har en rigtig regel-effekt: rustning får ACP-forbedring via
    masterwork-flaget; et våben får +1 til-hit (masterwork-flaget er armor-semantik
    i denne kodebase, så til-hit lægges i `bonus`). Cold iron / sølv har ingen
    model-felter → de gemmes som materiale-mærkat i navnet + en note (prisen tæller
    i butikken; DR-bypass og sølvets −1 skade noteres til spilleren/DM).

    Returnerer et overlay af InventoryItem-felter (masterwork/bonus/name/notes).
    Ukendte eller for varen ugyldige mod-nøgler ignoreres (valideres mod
    material_modifiers).
    """
    valid = {m["key"] for m in material_modifiers(record, table)}
    chosen = [m for m in (mods or []) if m in valid]
    if not chosen:
        return {}
    overlay: dict = {}
    prefix, notes = [], []
    if "masterwork" in chosen:
        overlay["masterwork"] = True
        if table == "weapons":
            overlay["bonus"] = 1
        prefix.append("Masterwork")
    if "cold_iron" in chosen:
        prefix.append("Cold Iron")
        notes.append("Cold iron: omgår DR/cold iron.")
    if "silvered" in chosen:
        prefix.append("Alch. Silver")
        notes.append("Alkymisk sølv: −1 skade, omgår DR/silver.")
    if prefix:
        overlay["name"] = " ".join(prefix + [record["name"]])
    if notes:
        overlay["notes"] = " ".join(notes)
    return overlay
