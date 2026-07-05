"""Blueprint: XP, level-up, ny dag, paladin-ressourcer, guld.

_char_path importeres lazy (se routes_spells.py for hvorfor).
"""
from flask import Blueprint, jsonify, request

import character as char_module
import db
import effects
import refdata
from character_view import _paladin_caps

progression_bp = Blueprint("progression", __name__)


@progression_bp.route("/api/xp", methods=["POST"])
def api_xp():
    from app import _char_path
    data  = request.get_json()
    slug  = data.get("char")
    delta = int(data.get("delta", 0))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char   = char_module.load_character(str(path))
    new_xp = max(0, char.experience_points + delta)
    char_module.save_character(str(path), {"experience_points": new_xp})
    return jsonify({
        "experience_points": new_xp,
        "xp_info": char_module.xp_progress(new_xp, char.level),
    })

@progression_bp.route("/api/levelup", methods=["POST"])
def api_levelup():
    from app import _char_path
    data = request.get_json()
    slug = data.get("char")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    if not char_module.xp_progress(char.experience_points, char.level)["ready"]:
        return jsonify({"error": "not ready"}), 400

    con_mod   = char.ability_scores.modifier("con")
    hp_roll   = max(1, int(data.get("hp_roll", 1)))
    hp_gained = max(1, hp_roll + con_mod)
    skill_deltas  = {k: float(v) for k, v in (data.get("skill_deltas") or {}).items()}
    new_feat      = data.get("new_feat") or None
    new_feats     = list(data.get("new_feats") or [])   # op til to: generel + fighter-bonus
    if new_feat:
        new_feats.append(new_feat)
    ability_boost = data.get("ability_boost") or None
    new_level     = char.level + 1

    # Håndhæv feat-prerequisites server-side (klienten filtrerer også, men reglerne
    # bestemmes her). Genbruger samme motor som oprettelse; kæder skal opfyldes af
    # allerede ejede feats + de øvrige feats valgt på SAMME level-up.
    if new_feats:
        all_feats = db.get_all_feats()
        name_by_id = {f["id"]: f["name"] for f in all_feats}
        name_to_id = {f["name"].lower(): f["id"] for f in all_feats}
        prereq_by_id = {f["id"]: f.get("prerequisites") for f in all_feats}
        owned = char_module.owned_feat_tokens(char.feats, name_by_id)
        scores = {a: getattr(char.ability_scores, a)
                  for a in ("str", "dex", "con", "int", "wis", "cha")}
        new_bab = int((db.get_class_level(char.cls.lower(), new_level) or {}).get("bab", 0))
        for nf in new_feats:
            fid = char_module.feat_id(nf)
            missing = char_module.feat_prereq_unmet(
                prereq_by_id.get(fid) or "", owned, scores,
                char.cls, new_level, new_bab, name_to_id)
            if missing:
                return jsonify({"error":
                    f"{name_by_id.get(fid, fid)} kræver: {', '.join(missing)}."}), 400

    char_module.save_character(str(path), {
        "level":         new_level,
        "hp_max":        char.hp_max + hp_gained,
        "hp_current":    char.hp_current + hp_gained,
        "skill_deltas":  skill_deltas,
        "new_feats":     new_feats,
        "ability_boost": ability_boost,
    })
    return jsonify({"ok": True, "new_level": new_level, "hp_gained": hp_gained})

@progression_bp.route("/api/newday", methods=["POST"])
def api_newday():
    from app import _char_path
    data = request.get_json()
    slug = data.get("char")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char_module.save_character(
        str(path),
        {"spells_used": {}, "spells_active": {}, "spell_charges": {},
         "spells_known_used": {}, "domain_spells_used": {}, "wild_shape": {},
         "lay_on_hands_used": 0, "smite_used": 0})
    return jsonify({"ok": True})

@progression_bp.route("/api/paladin", methods=["POST"])
def api_paladin():
    """Paladin-ressourcer: brug en Smite Evil eller helbred dig selv med Lay on Hands.

    Caps genberegnes server-side ud fra effektiv Cha + level (klienten bestemmer ikke
    grænserne). Lay on Hands helbreder paladinen selv (den eneste karakter arket kender)
    og trækker fra dagens pulje. Nulstilles ved "Ny dag".
    """
    from app import _char_path
    data = request.get_json()
    slug = data.get("char")
    action = data.get("action")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    if char.cls != "Paladin":
        return jsonify({"error": "ikke en paladin"}), 400

    active_modifiers, _ = effects.collect_character_effects(char, db)
    eff = char_module.effective_ability_scores(char.ability_scores, active_modifiers)
    lay_pool, smite_per_day = _paladin_caps(char, eff.modifier("cha"))

    if action == "smite":
        new_used = min(smite_per_day, char.smite_used + 1)
        char_module.save_character(str(path), {"smite_used": new_used})
        return jsonify({"ok": True, "smite_remaining": max(0, smite_per_day - new_used)})

    if action == "lay_on_hands":
        remaining = max(0, lay_pool - char.lay_on_hands_used)
        amount = max(0, min(int(data.get("amount", 0)), remaining))
        if amount <= 0:
            return jsonify({"error": "ingen pulje tilbage"}), 400
        new_used = char.lay_on_hands_used + amount
        ceiling = char.hp_max + effects.temp_hp(char, db)
        new_hp = min(ceiling, char.hp_current + amount)
        char_module.save_character(
            str(path), {"lay_on_hands_used": new_used, "hp_current": new_hp})
        return jsonify({"ok": True, "lay_remaining": max(0, lay_pool - new_used),
                        "hp_current": new_hp, "hp_max": char.hp_max})

    return jsonify({"error": "ukendt handling"}), 400

@progression_bp.route("/api/gold", methods=["POST"])
def api_gold():
    from app import _char_path
    data = request.get_json()
    slug = data.get("char")
    coin = data.get("coin")
    val  = int(data.get("value", 0))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    gold = dict(char.gold)
    gold[coin] = max(0, val)
    char_module.save_character(str(path), {"gold": gold})
    return jsonify({"gold": gold})

