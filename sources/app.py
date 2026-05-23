"""D&D 3.5 Flask-app — tablet-first karakterark."""
import os
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

import character as char_module
import db
import dice as dice_module

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
CHARACTERS_DIR = Path(os.environ.get("DND_CHARACTERS_DIR",
                                     str(Path(__file__).parent / "characters")))


def _char_path(slug: str) -> Path:
    return CHARACTERS_DIR / f"{slug}.yaml"


# ── Pages ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    files = sorted(CHARACTERS_DIR.glob("*.yaml"))
    chars = []
    for f in files:
        try:
            c   = char_module.load_character(str(f))
            ab  = c.ability_scores
            hp_pct = max(0, min(100, c.hp_current * 100 // c.hp_max)) if c.hp_max else 0
            xp_info = char_module.xp_progress(c.experience_points, c.level)
            enc = char_module.encumbrance_level(
                ab.str, char_module.total_weight(c.inventory), c.size)
            chars.append({
                "slug":       f.stem,
                "name":       c.name,
                "race":       c.race,
                "cls":        c.cls,
                "level":      c.level,
                "hp_current": c.hp_current,
                "hp_max":     c.hp_max,
                "hp_pct":     hp_pct,
                "dead":       c.hp_current <= 0,
                "conditions": c.conditions,
                "xp_ready":   xp_info["ready"],
                "enc":        enc,
            })
        except Exception:
            chars.append({"slug": f.stem, "name": f.stem,
                          "race": "", "cls": "", "level": "?",
                          "hp_current": 0, "hp_max": 0, "hp_pct": 0,
                          "dead": False, "conditions": [], "xp_ready": False, "enc": ""})
    return render_template("index.html", chars=chars)


@app.route("/karakter/<name>")
def karakter(name):
    path = _char_path(name)
    if not path.exists():
        abort(404)

    char = char_module.load_character(str(path))
    ab = char.ability_scores

    saves = {
        "Fortitude": char_module.save_total(char.saves.get("fortitude", 0), ab.con),
        "Reflex":    char_module.save_total(char.saves.get("reflex",    0), ab.dex),
        "Will":      char_module.save_total(char.saves.get("will",      0), ab.wis),
    }

    skill_data = [
        {"skill": s, "defn": db.get_skill(s.id),
         "total": char_module.skill_total(s, ab, db)}
        for s in char.skills
    ]
    feat_data  = [(fid, db.get_feat(fid)) for fid in char.feats]

    spell_data: dict[int, list] = {}
    for lvl, spell_ids in char.spells_prepared.items():
        used = char.spells_used.get(lvl, [])
        spell_data[lvl] = [
            {"id": sid, "spell": db.get_spell(sid), "used": sid in used}
            for sid in spell_ids
        ]

    condition_data  = [(cid, db.get_condition(cid)) for cid in char.conditions]
    all_conditions  = db.get_all_conditions()

    class_level_data = db.get_class_level(char.cls.lower(), char.level)
    slots: dict[int, int] = {}
    if class_level_data:
        slots = char_module.spell_slots_total(class_level_data, ab.wis)

    xp_info    = char_module.xp_progress(char.experience_points, char.level)
    weight     = char_module.total_weight(char.inventory)
    enc_limits = char_module.carry_limits(ab.str, char.size)
    enc        = char_module.encumbrance_level(ab.str, weight, char.size)
    base_speed = char.combat.get("speed", 30)
    inventory_json = [
        {"name": i.name, "weight": i.weight, "qty": i.qty, "notes": i.notes}
        for i in char.inventory
    ]

    abilities = [
        ("STR", ab.str, ab.modifier("str")),
        ("DEX", ab.dex, ab.modifier("dex")),
        ("CON", ab.con, ab.modifier("con")),
        ("INT", ab.int, ab.modifier("int")),
        ("WIS", ab.wis, ab.modifier("wis")),
        ("CHA", ab.cha, ab.modifier("cha")),
    ]

    # Level-up info
    new_level = char.level + 1
    new_level_data = db.get_class_level(char.cls.lower(), new_level)
    new_features: list[str] = []
    if new_level_data:
        raw = new_level_data.get("features", [])
        new_features = raw if isinstance(raw, list) else [f"{k}: {v}" for k, v in raw.items()]
    levelup_info = {
        "current_level": char.level,
        "new_level":     new_level,
        "hit_die":       char_module.hit_die(char.cls),
        "con_modifier":  ab.modifier("con"),
        "skill_points":  char_module.skill_points_per_level(char.cls, ab.modifier("int")),
        "feat_level":    char_module.is_feat_level(new_level),
        "ability_level": char_module.is_ability_level(new_level),
        "new_features":  new_features,
        "xp_ready":      xp_info["ready"],
    }
    all_feats_json = [
        {"id": f["id"], "name": f["name"],
         "type": f.get("type") or "",
         "prerequisites": f.get("prerequisites") or "",
         "benefit": f.get("benefit") or ""}
        for f in db.get_all_feats()
    ]
    all_skills_json = [
        {"id": s["id"], "name": s["name"], "ability": s.get("ability", "")}
        for s in db.get_all_skills()
    ]
    cls_skills_json = sorted(char_module.class_skills(char.cls))

    # Druid spells grouped by level — for preparation modal
    cls_lower = char.cls.lower()
    all_cls_spells = db.search_spells(class_filter=cls_lower)
    available_spells: dict[int, list] = {}
    for spell in all_cls_spells:
        lvl = spell.get(f"level_{cls_lower}")
        if lvl is not None:
            available_spells.setdefault(lvl, []).append(spell)

    return render_template(
        "character.html",
        name=name,
        char=char,
        abilities=abilities,
        saves=saves,
        skill_data=skill_data,
        feat_data=feat_data,
        spell_data=spell_data,
        slots=slots,
        condition_data=condition_data,
        all_conditions=all_conditions,
        xp_info=xp_info,
        weight=weight,
        enc_limits=enc_limits,
        enc=enc,
        base_speed=base_speed,
        inventory_json=inventory_json,
        available_spells=available_spells,
        levelup_info=levelup_info,
        all_feats_json=all_feats_json,
        all_skills_json=all_skills_json,
        cls_skills_json=cls_skills_json,
    )


# ── API ────────────────────────────────────────────────────────────────────

@app.route("/api/hp", methods=["POST"])
def api_hp():
    data = request.get_json()
    slug  = data.get("char")
    delta = int(data.get("delta", 0))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    new_hp = max(-9, min(char.hp_max, char.hp_current + delta))
    char_module.save_character(str(path), {"hp_current": new_hp})
    return jsonify({"hp_current": new_hp, "hp_max": char.hp_max})


@app.route("/api/spells", methods=["POST"])
def api_spells():
    data     = request.get_json()
    slug     = data.get("char")
    level    = int(data.get("level"))
    spell_id = data.get("spell_id")
    mark_used = bool(data.get("used"))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    spells_used = {k: list(v) for k, v in char.spells_used.items()}

    if mark_used:
        spells_used.setdefault(level, [])
        if spell_id not in spells_used[level]:
            spells_used[level].append(spell_id)
    else:
        if level in spells_used and spell_id in spells_used[level]:
            spells_used[level].remove(spell_id)

    char_module.save_character(str(path), {"spells_used": spells_used})
    return jsonify({"spells_used": {str(k): v for k, v in spells_used.items()}})


@app.route("/api/conditions", methods=["POST"])
def api_conditions():
    data         = request.get_json()
    slug         = data.get("char")
    condition_id = data.get("condition_id")
    action       = data.get("action")   # "add" | "remove"
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    conditions = list(char.conditions)

    if action == "add" and condition_id not in conditions:
        conditions.append(condition_id)
    elif action == "remove" and condition_id in conditions:
        conditions.remove(condition_id)

    char_module.save_character(str(path), {"conditions": conditions})
    return jsonify({"conditions": conditions})


@app.route("/api/roll/<path:expression>")
def api_roll(expression):
    try:
        result = dice_module.roll(expression)
        result["expression"] = expression
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/xp", methods=["POST"])
def api_xp():
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


@app.route("/api/levelup", methods=["POST"])
def api_levelup():
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
    ability_boost = data.get("ability_boost") or None
    new_level     = char.level + 1

    char_module.save_character(str(path), {
        "level":         new_level,
        "hp_max":        char.hp_max + hp_gained,
        "hp_current":    char.hp_current + hp_gained,
        "skill_deltas":  skill_deltas,
        "new_feat":      new_feat,
        "ability_boost": ability_boost,
    })
    return jsonify({"ok": True, "new_level": new_level, "hp_gained": hp_gained})


@app.route("/api/inventory", methods=["POST"])
def api_inventory():
    data   = request.get_json()
    slug   = data.get("char")
    action = data.get("action")   # "add" | "remove"
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char      = char_module.load_character(str(path))
    inventory = list(char.inventory)

    if action == "add":
        name = str(data.get("name", "")).strip()
        if not name:
            return jsonify({"error": "name required"}), 400
        inventory.append(char_module.InventoryItem(
            name=name,
            weight=float(data.get("weight", 0)),
            qty=int(data.get("qty", 1)),
            notes=str(data.get("notes", "")),
        ))
    elif action == "remove":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(inventory):
            inventory.pop(idx)
    elif action == "update":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(inventory):
            old = inventory[idx]
            inventory[idx] = char_module.InventoryItem(
                name=str(data.get("name", old.name)),
                weight=float(data.get("weight", old.weight)),
                qty=max(1, int(data.get("qty", old.qty))),
                notes=str(data.get("notes", old.notes)),
            )

    char_module.save_character(str(path), {"inventory": inventory})
    ab     = char.ability_scores
    weight = char_module.total_weight(inventory)
    enc    = char_module.encumbrance_level(ab.str, weight, char.size)
    return jsonify({
        "inventory": [{"name": i.name, "weight": i.weight, "qty": i.qty, "notes": i.notes}
                      for i in inventory],
        "weight":     weight,
        "enc":        enc,
        "enc_limits": char_module.carry_limits(ab.str, char.size),
    })


@app.route("/api/prepare", methods=["POST"])
def api_prepare():
    data = request.get_json()
    slug     = data.get("char")
    prepared = data.get("prepared_spells", {})   # {level_str: [spell_ids]}
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    prepared_int = {int(k): list(v) for k, v in prepared.items()}
    char_module.save_character(str(path), {
        "spells_prepared": prepared_int,
        "spells_used": {},          # ny forberedelse nulstiller brug
    })
    return jsonify({"ok": True, "prepared_spells": {str(k): v for k, v in prepared_int.items()}})


@app.route("/api/newday", methods=["POST"])
def api_newday():
    data = request.get_json()
    slug = data.get("char")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char_module.save_character(str(path), {"spells_used": {}})
    return jsonify({"ok": True})


@app.route("/api/companion_hp", methods=["POST"])
def api_companion_hp():
    data  = request.get_json()
    slug  = data.get("char")
    delta = int(data.get("delta", 0))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    comp = char.companion
    if not comp:
        return jsonify({"error": "no companion"}), 400
    hp_max = (comp.get("hp") or {}).get("max", 0)
    hp_cur = (comp.get("hp") or {}).get("current", 0)
    new_hp = max(-9, min(hp_max, hp_cur + delta))
    char_module.save_character(str(path), {"companion_hp_current": new_hp})
    return jsonify({"hp_current": new_hp, "hp_max": hp_max})


@app.route("/api/gold", methods=["POST"])
def api_gold():
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


@app.route("/api/notes", methods=["POST"])
def api_notes():
    data  = request.get_json()
    slug  = data.get("char")
    notes = str(data.get("notes", ""))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char_module.save_character(str(path), {"notes": notes})
    return jsonify({"ok": True})


@app.route("/api/detail/<dtype>/<did>")
def api_detail(dtype, did):
    lookup = {"spell": db.get_spell, "skill": db.get_skill,
              "feat": db.get_feat, "condition": db.get_condition}
    fn = lookup.get(dtype)
    if not fn:
        return jsonify({"error": "unknown type"}), 400
    row = fn(did)
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(row)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
