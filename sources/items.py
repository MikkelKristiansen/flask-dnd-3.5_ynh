"""Vægt, pris, encumbrance og materiale-modifikatorer for udstyr.

Udspaltet fra rules.py (ren leaf: kalder intet i rules; intet i rules kalder den).
Ren beregning — I/O kun via det db-objekt der gives som argument.
"""
import re

from models import InventoryItem

# tabel-præfiks → db-getter (resolve_item)
_REF_LOOKUP = {"weapons": "get_weapon", "armor": "get_armor", "items": "get_item"}
# Alkymisk sølv koster efter våbenklasse (SRD: let 20 gp, enhånds 90, tohånds 180).
_SILVER_DELTA_CP = {"light": 2000, "one-handed": 9000, "two-handed": 18000}
CARRIED_STATES = {"wielded", "worn", "backpack"}   # tæller med i båret vægt
# Light load limits (lbs) for Medium creatures, indexed by STR score 1-20
_LIGHT_LOAD_MEDIUM = {
    1: 3,   2: 6,   3: 10,  4: 13,  5: 16,
    6: 20,  7: 23,  8: 26,  9: 30,  10: 33,
    11: 38, 12: 43, 13: 50, 14: 58, 15: 66,
    16: 76, 17: 86, 18: 100, 19: 116, 20: 133,
}
_SIZE_CARRY_MULTIPLIER = {
    "fine": 0.125, "diminutive": 0.25, "tiny": 0.5,
    "small": 0.75, "medium": 1.0,
    "large_tall": 2.0, "large_long": 1.5,
    "huge_tall": 4.0, "huge_long": 3.0,
    "gargantuan": 8.0, "colossal": 16.0,
}


def carry_limits(str_score: int, size: str = "medium") -> dict:
    """Returns light/medium/heavy load limits in lbs for a creature."""
    clamped_str = max(1, min(str_score, 20))
    base_light = _LIGHT_LOAD_MEDIUM[clamped_str]
    multiplier = _SIZE_CARRY_MULTIPLIER.get(size, 1.0)
    light = base_light * multiplier
    medium = light * 2
    heavy = light * 3
    return {"light": light, "medium": medium, "heavy": heavy}


def encumbrance_level(str_score: int, total_weight: float, size: str = "medium") -> str:
    """Returns 'Light', 'Medium', 'Heavy', or 'Overloaded'."""
    limits = carry_limits(str_score, size)
    if total_weight <= limits["light"]:
        return "Light"
    if total_weight <= limits["medium"]:
        return "Medium"
    if total_weight <= limits["heavy"]:
        return "Heavy"
    return "Overloaded"


def total_weight(inventory: list[InventoryItem]) -> float:
    return sum(item.weight * item.qty for item in inventory)


def weight_for_size(base_weight: float, kind: str, size: str = "medium") -> float:
    """Udregn faktisk vægt for en skabnings størrelse fra Medium-basisvægt.

    kind: 'half'    -> våben/rustning (Small ×½, Large ×2)
          'quarter' -> gear m. SRD-fodnote 1 (Small ×¼)
          'none'    -> uændret med størrelse (fakkel, reb, custom genstande)
    """
    size = (size or "medium").lower()
    if size == "small":
        factor = {"half": 0.5, "quarter": 0.25}.get(kind, 1.0)
    elif size == "large":
        factor = {"half": 2.0}.get(kind, 1.0)
    else:  # medium (og uhåndterede størrelser) — ingen skalering
        factor = 1.0
    return round(base_weight * factor, 3)


def cost_for_size(base_cost_cp, kind: str, size: str = "medium") -> int:
    """Størrelses-justeret pris (i cp) fra Medium-basisprisen.

    Modstykke til weight_for_size. SRD: prisen er ens for en Small og en Medium
    udgave; en Large udgave koster det dobbelte (equipment.md: våben linje 81,
    rustning/skjold tabellen for 'unusual creatures'). Gear (items) ændrer aldrig
    pris med størrelse.

    kind: 'half' -> våben/rustning (Large ×2, ellers ×1)
          alt andet -> uændret med størrelse
    """
    base = int(base_cost_cp or 0)
    if kind == "half" and (size or "medium").lower() == "large":
        return base * 2
    return base


def weight_kind(table: str, record: dict) -> str:
    """Skaleringsklasse for en katalog-række ud fra dens tabel (til weight_for_size).

    Ét sted for reglen 'hvordan skalerer vægten med størrelse': våben/rustning
    halveres/fordobles, gear med SRD-fodnote 1 firdeles for Small, resten uændret.
    """
    if table in ("weapons", "armor"):
        return "half"
    if table == "items":
        return "quarter" if record.get("small_quarter") else "none"
    return "none"


def resolve_item(item: InventoryItem, db, size: str = "medium") -> dict:
    """Slå en inventory-post op mod kataloget og udregn dens faktiske vægt.

    Returnerer navn, enheds- og totalvægt (størrelses-justeret), om den tæller
    som båret, samt katalog-posten (record) hvis ref peger på noget gyldigt.
    """
    name = item.name
    base_weight = item.weight
    kind = "none"
    source = None
    record = None
    if item.ref:
        table, _, oid = item.ref.partition("/")
        getter = getattr(db, _REF_LOOKUP[table], None) if table in _REF_LOOKUP else None
        record = getter(oid) if getter else None
        if record:
            source = table
            name = item.name or record["name"]
            base_weight = record.get("weight") or 0.0
            kind = weight_kind(table, record)
            if table == "items":
                # Bundter (ammo) opgives per bundt i kataloget; qty = enkelte
                # enheder, så vægten regnes per styk.
                bundle = record.get("bundle") or 1
                if bundle > 1:
                    base_weight = base_weight / bundle
    unit = weight_for_size(base_weight, kind, size)
    return {
        "name": name,
        "unit_weight": unit,
        "weight": round(unit * item.qty, 3),
        "kind": kind,
        "carried": item.state in CARRIED_STATES,
        "state": item.state,
        "source": source,
        "record": record,
    }


def carried_weight(inventory: list[InventoryItem], db, size: str = "medium") -> float:
    """Samlet båret vægt — kun poster i wielded/worn/backpack, størrelses-justeret."""
    return round(
        sum(r["weight"] for r in (resolve_item(i, db, size) for i in inventory) if r["carried"]),
        3,
    )


def material_modifiers(record: dict, table: str, size: str = "medium") -> list[dict]:
    """Tilgængelige materiale-/kvalitets-modifikatorer for en katalog-række.

    Returnerer [{key, label, delta_cp}] med prisdeltaer pr. SRD:
      masterwork  våben +300 gp / rustning+skjold +150 gp (fast — skalerer IKKE)
      cold_iron   ×2 basispris (delta = basisprisen, størrelses-justeret) — kun metal-nærkampsvåben
      silvered    efter våbenklasse (fast beløb) — kun metal-nærkampsvåben der selv gør skade
    Cold iron / sølv tilbydes kun på let/enhånds/tohånds METAL-våben (ikke buer,
    slynger, ubevæbnet eller træ-/læder-våben som markeret med metal=0 i data).

    SRD: masterwork-kvaliteten og magisk enhancement koster det samme uanset størrelse,
    så kun cold irons ×2-delta følger den størrelses-justerede basispris.
    """
    if table == "weapons":
        mods = [{"key": "masterwork", "label": "Masterwork", "delta_cp": 30000}]
        wclass = record.get("weapon_class")
        if wclass in ("light", "one-handed", "two-handed") and record.get("metal") != 0:
            base = cost_for_size(record.get("cost_cp"), "half", size)
            if base:
                mods.append({"key": "cold_iron", "label": "Cold Iron", "delta_cp": int(base)})
            silver = _SILVER_DELTA_CP.get(wclass)
            if silver:
                mods.append({"key": "silvered", "label": "Alch. Silver", "delta_cp": silver})
        return mods
    if table == "armor":
        return [{"key": "masterwork", "label": "Masterwork", "delta_cp": 15000}]
    return []


def _effective_armor_row(rec: dict, item: InventoryItem) -> dict:
    """Påfør masterwork/magi på en katalog-række → en effektiv kopi.

    Reglerne (3.5 SRD): mesterværk forbedrer rustnings-tjekstraffen (ACP) med +1
    mod 0 (aldrig positiv); en enhancement-bonus lægges til AC og medfører altid
    mesterværk (magisk rustning er pr. definition mesterværk). Resten af rækken
    (max_dex, spell_failure, druid_ok …) er uændret. Vi kopierer rækken, så
    db'ens cache aldrig muteres.
    """
    masterwork = item.masterwork or item.enhancement >= 1
    if not masterwork and item.enhancement == 0:
        return rec
    eff = dict(rec)
    if masterwork:
        eff["armor_check"] = min(0, int(rec.get("armor_check", 0)) + 1)
    if item.enhancement:
        eff["armor_bonus"] = int(rec.get("armor_bonus", 0)) + item.enhancement
    # Vis-navn afspejler tilpasningen (fx "Studded Leather +1 (mesterværk)").
    label = rec.get("name", "")
    if item.enhancement:
        label = f"{label} +{item.enhancement}"
    if item.masterwork and not item.enhancement:
        label = f"{label} (mesterværk)"
    eff["name"] = label
    return eff


def equipped_armor(inventory: list[InventoryItem], db):
    """Find båret rustning + skjold i inventaret (state=worn, ref til armor).

    Returnerer (armor_row, shield_row) som katalog-dicts eller None. Tager den
    første af hver slags: armor = type light/medium/heavy, shield = type shield.
    Masterwork/magi fra inventory-posten er påført rækken (se _effective_armor_row).
    """
    armor_row = shield_row = None
    for item in inventory:
        if item.state != "worn" or not item.ref.startswith("armor/"):
            continue
        rec = db.get_armor(item.ref.split("/", 1)[1])
        if not rec:
            continue
        # Frisk kopi med house_rule-flaget (DM tillader trods druide-metal-forbud),
        # så druid_armor_violations kan dæmpe advarslen uden at mutere db-cachen.
        rec = {**_effective_armor_row(rec, item), "house_rule": bool(item.house_rule)}
        if rec["type"] == "shield":
            shield_row = shield_row or rec
        elif rec["type"] in ("light", "medium", "heavy"):
            armor_row = armor_row or rec
    return armor_row, shield_row


def encumbrance_consequences(enc_level: str, base_speed: int) -> dict:
    """Returns encumbrance penalties per D&D 3.5 PHB p.162."""
    if enc_level == "Light":
        return {"max_dex": None, "check_penalty": 0, "speed": base_speed, "run": 4}
    sq = base_speed // 5
    enc_speed = max(5, (sq - sq // 3) * 5)
    if enc_level == "Medium":
        return {"max_dex": 3, "check_penalty": -3, "speed": enc_speed, "run": 4}
    if enc_level == "Heavy":
        return {"max_dex": 1, "check_penalty": -6, "speed": enc_speed, "run": 3}
    return {"max_dex": 0, "check_penalty": -6, "speed": 5, "run": 3}
