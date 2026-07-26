"""Blueprint: angreb, tilstande/buffs, kampindstillinger, kastbare våben.

_char_path importeres lazy (se routes_spells.py for hvorfor).
"""
from flask import Blueprint, jsonify, request

import character as char_module
import db
from route_helpers import _find_summon

combat_bp = Blueprint("combat", __name__)


@combat_bp.route("/api/weapon_throw", methods=["POST"])
def api_weapon_throw():
    """Skift et kastbart våbens tilstand mellem nærkamp og kastet.

    Sætter item.thrown eksplicit til det MODSATTE af den nuværende effektive
    tilstand (None = våbnets natur: nærkampsvåben→nærkamp, kastevåben→kastet).
    """
    from app import _char_path
    data      = request.get_json()
    slug      = data.get("char")
    inv_index = int(data.get("inv_index", -1))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    if not (0 <= inv_index < len(char.inventory)):
        return jsonify({"error": "bad index"}), 400
    item = char.inventory[inv_index]
    if not item.ref.startswith("weapons/"):
        return jsonify({"error": "not a weapon"}), 400
    w = db.get_weapon(item.ref.split("/", 1)[1])
    if not (w and w.get("thrown")):
        return jsonify({"error": "not throwable"}), 400

    effective = item.thrown if item.thrown is not None else (w["weapon_class"] == "ranged")
    item.thrown = not effective

    char_module.save_character(str(path), {"inventory": char.inventory})
    return jsonify({"inv_index": inv_index, "thrown": item.thrown})

@combat_bp.route("/api/conditions", methods=["POST"])
def api_conditions():
    from app import _char_path
    data         = request.get_json()
    slug         = data.get("char")
    condition_id = data.get("condition_id")
    action       = data.get("action")   # "add" | "remove"
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    target = data.get("target", "character")
    char = char_module.load_character(str(path))

    # Summon: muter tilstands-listen på den summon-ref der matcher SNA-slot'et.
    if target == "summon":
        ref = _find_summon(char.summons,
                           int(data.get("spell_level")), int(data.get("spell_index")))
        if not ref:
            return jsonify({"error": "no summon"}), 400
        conditions = list(ref.get("conditions") or [])
        if action == "add" and condition_id and condition_id not in conditions:
            conditions.append(condition_id)
        elif action == "remove" and condition_id in conditions:
            conditions.remove(condition_id)
        ref["conditions"] = conditions
        char_module.save_character(str(path), {"summons": char.summons})
        return jsonify({"conditions": conditions})

    if target == "companion":
        comp = char.companion or {}
        if not comp:
            return jsonify({"error": "no companion"}), 400
        conditions = list(comp.get("conditions") or [])
    else:
        conditions = list(char.conditions)

    if action == "add" and condition_id and condition_id not in conditions:
        conditions.append(condition_id)
    elif action == "remove" and condition_id in conditions:
        conditions.remove(condition_id)

    key = "companion_conditions" if target == "companion" else "conditions"
    char_module.save_character(str(path), {key: conditions})
    return jsonify({"conditions": conditions})

@combat_bp.route("/api/buffs", methods=["POST"])
def api_buffs():
    from app import _char_path
    data   = request.get_json()
    slug   = data.get("char")
    action = data.get("action")           # "add" | "remove"
    target = data.get("target", "character")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    ref = None
    if target == "summon":
        ref = _find_summon(char.summons,
                           int(data.get("spell_level")), int(data.get("spell_index")))
        if not ref:
            return jsonify({"error": "no summon"}), 400
        buffs = list(ref.get("buffs") or [])
    elif target == "companion":
        comp = char.companion or {}
        if not comp:
            return jsonify({"error": "no companion"}), 400
        buffs = list(comp.get("buffs") or [])
    else:
        buffs = list(char.buffs)

    if action == "add":
        b = data.get("buff") or {}
        name = str(b.get("name", "")).strip()
        if name:
            entry = {"name": name, "note": str(b.get("note", "")).strip(),
                     "affects": [str(a) for a in (b.get("affects") or [])]}
            if b.get("spell_id"):
                entry["spell_id"] = str(b["spell_id"])
            # value-override (fx valgt ability-skade) — bæres med så modifieren
            # kan slås op med den faktiske mængde. Kun gem hvis den er et tal.
            if b.get("value") is not None:
                try:
                    entry["value"] = int(b["value"])
                except (TypeError, ValueError):
                    pass
            buffs.append(entry)
    elif action == "remove":
        i = int(data.get("index", -1))
        if 0 <= i < len(buffs):
            buffs.pop(i)

    if target == "summon":
        ref["buffs"] = buffs
        char_module.save_character(str(path), {"summons": char.summons})
    else:
        key = "companion_buffs" if target == "companion" else "buffs"
        char_module.save_character(str(path), {key: buffs})
    return jsonify({"ok": True})

@combat_bp.route("/api/combat_options", methods=["POST"])
def api_combat_options():
    """Slå én kampindstilling til/fra (Point Blank/Dodge/Charge/Fighting
    Defensively — simple bools) ELLER sæt en talværdi (Power Attack/Combat
    Expertise — "editable" options, Lag B).

    Body sender enten "on" (bool, simpel toggle — også brugt til namespacede
    under-toggle-nøgler som "power_attack.two_handed") eller "value" (heltal,
    editable option). Slukkes en editable option (value < 1), ryddes dens
    under-toggle-nøgler også, så fx en slukket Power Attack ikke efterlader
    en forældreløs "power_attack.two_handed"-flag.
    """
    from app import _char_path
    data      = request.get_json()
    slug      = data.get("char")
    option_id = data.get("option_id")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    opts = dict(char.combat_options)
    if "value" in data:
        try:
            value = int(data.get("value"))
        except (TypeError, ValueError):
            value = 0
        if value >= 1:
            opts[option_id] = value
        else:
            opts.pop(option_id, None)
            for key in [k for k in opts if k.startswith(f"{option_id}.")]:
                opts.pop(key, None)
    else:
        on = bool(data.get("on"))
        if on:
            opts[option_id] = True
        else:
            opts.pop(option_id, None)
    char_module.save_character(str(path), {"combat_options": opts})
    return jsonify({"ok": True})

_ATTACK_KINDS = {"melee", "ranged", "melee_touch", "ranged_touch"}


def _build_attack(a: dict) -> char_module.Attack:
    """Byg et Attack-objekt fra rå modal-data. Kilde styrer skade-modellen:
    spell → fast skade (Str tælles ikke med); våben → terning + Str×mult.
    """
    name = str(a.get("name", "")).strip()
    if not name:
        raise ValueError("name required")
    source = str(a.get("source", "weapon")).lower()
    if source != "spell":
        source = "weapon"
    kind = str(a.get("kind", "melee")).lower()
    if kind not in _ATTACK_KINDS:
        kind = "melee"
    damage = str(a.get("damage", "")).strip()
    common = dict(
        name=name, kind=kind, bonus=int(a.get("bonus") or 0),
        crit=(str(a.get("crit", "")).strip() or "x2"),
        type=str(a.get("type", "")).strip(),
        range=str(a.get("range", "")).strip(),
    )
    if source == "spell":
        return char_module.Attack(
            base_damage="1d4", str_damage_mult=0.0, fixed_damage=damage,
            source="spell", requires=str(a.get("requires", "")).strip(), **common)
    sm = a.get("str_mult")
    sm = 1.0 if sm in (None, "") else float(sm)
    return char_module.Attack(
        base_damage=(damage or "1d4"), str_damage_mult=sm, fixed_damage="",
        source="weapon", requires="", **common)

@combat_bp.route("/api/attacks", methods=["POST"])
def api_attacks():
    from app import _char_path
    data   = request.get_json()
    slug   = data.get("char")
    action = data.get("action")        # "add" | "update" | "remove"
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char    = char_module.load_character(str(path))
    attacks = list(char.attacks)

    if action in ("add", "update"):
        try:
            atk = _build_attack(data.get("attack") or {})
        except (ValueError, TypeError):
            return jsonify({"error": "ugyldigt angreb"}), 400
        if action == "add":
            attacks.append(atk)
        else:
            idx = int(data.get("index", -1))
            if 0 <= idx < len(attacks):
                attacks[idx] = atk
    elif action == "remove":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(attacks):
            attacks.pop(idx)

    char_module.save_character(str(path), {"attacks": attacks})
    return jsonify({"ok": True})

