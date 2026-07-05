"""Blueprint: dyreledsager (companion/familiar/mount), wild shape.

_char_path importeres lazy (se routes_spells.py for hvorfor).
"""
from flask import Blueprint, jsonify, request

import character as char_module
import companion as companion_module
import db
import familiar as familiar_module
import refdata
import wild_shape as wild_shape_module

companion_bp = Blueprint("companion", __name__)


@companion_bp.route("/api/companion_hp", methods=["POST"])
def api_companion_hp():
    from app import _char_path
    data  = request.get_json()
    slug  = data.get("char")
    delta = int(data.get("delta", 0))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    comp = companion_module.build_companion(char, db)
    if not comp:
        return jsonify({"error": "no companion"}), 400
    hp_max = comp["hp_max"]
    hp_cur = comp["hp_current"]
    new_hp = max(-9, min(hp_max, hp_cur + delta))
    char_module.save_character(str(path), {"companion_hp_current": new_hp})
    return jsonify({"hp_current": new_hp, "hp_max": hp_max})

@companion_bp.route("/api/companion_tricks", methods=["POST"])
def api_companion_tricks():
    from app import _char_path
    data = request.get_json()
    slug = data.get("char")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    if not char.companion:
        return jsonify({"error": "no companion"}), 400
    # Normalisér: trim, fjern tomme, bevar rækkefølge, dedupér.
    seen, tricks = set(), []
    for t in (data.get("tricks") or []):
        name = str(t).strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            tricks.append(name)
    char_module.save_character(str(path), {"companion_tricks": tricks})
    return jsonify({"tricks": tricks})

@companion_bp.route("/api/companion", methods=["POST"])
def api_companion():
    """Tilkald en ny animal companion (summon) eller sig farvel til den (dismiss).

    summon: bygger en tynd ref {name, animal, hp_current=max, tricks:[]} ved
    karakterens effektive companion-niveau (samme mekanik som generatoren).
    dismiss: rydder char.companion helt (data går tabt — bekræftes i UI'en).
    """
    from app import _char_path
    data   = request.get_json()
    slug   = data.get("char")
    action = str(data.get("action", "")).lower()
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    is_mount = companion_module.mount_eligible(char.cls, char.level)
    is_familiar = familiar_module.familiar_eligible(char.cls, char.level)
    eff_level = companion_module.companion_effective_level(char.cls, char.level)
    if not is_mount and not is_familiar and eff_level <= 0:
        return jsonify({"error": "Klassen kan ikke have en ledsager."}), 400

    if action == "dismiss":
        char_module.save_character(str(path), {"companion": {}})
        return jsonify({"ok": True})

    if action == "summon":
        animal_id = str(data.get("animal", "")).strip()
        animal = db.get_animal(animal_id)
        name = str(data.get("name", "")).strip() or (animal["name"] if animal else "")
        if is_familiar:
            # Familiar: skal være et gyldigt familiar-dyr; HP = ½ mesterens (SRD).
            if not animal or animal_id not in refdata.familiar_ids():
                return jsonify({"error": "Ukendt eller uegnet familiar."}), 400
            # Er en tidligere familiar død, skal ventetiden være udløbet først.
            cooldown = int((char.familiar_lost or {}).get("cooldown", 0))
            if char.familiar_lost and cooldown > 0:
                return jsonify({"error": f"Ventetid: {cooldown} dag(e) tilbage før ny familiar."}), 400
            comp = {"name": name, "animal": animal_id, "kind": "familiar",
                    "hp_current": max(1, char.hp_max // 2)}
            # Ny familiar rydder tabs-straffen.
            char_module.save_character(str(path), {"companion": comp, "familiar_lost": {}})
            return jsonify({"ok": True})
        if is_mount:
            # Paladin-mount: kun de to standard-mounts, og statblok via mount-tabellen.
            if not animal or animal_id not in ("heavy_warhorse", "warpony"):
                return jsonify({"error": "Ukendt eller uegnet mount."}), 400
            deltas = companion_module.mount_deltas(char.level)
            kind = "mount"
        else:
            if not animal or animal.get("companion_ok") == 0:
                return jsonify({"error": "Ukendt eller uegnet dyr."}), 400
            deltas = companion_module.companion_deltas(max(1, eff_level))
            kind = "companion"
        hp_max = companion_module.advance_companion(animal, deltas, db)["hp_max"]
        comp = {"name": name, "animal": animal_id, "hp_current": hp_max, "tricks": []}
        if kind == "mount":
            comp["kind"] = "mount"
        char_module.save_character(str(path), {"companion": comp})
        return jsonify({"ok": True})

    return jsonify({"error": "ukendt action"}), 400

@companion_bp.route("/api/familiar", methods=["POST"])
def api_familiar():
    """Familiar-tab-tracker: familiaren dør (died) eller tæl ventetiden ned (cooldown).

    died: rydder familiaren og starter en ventetid (dage) + midlertidig straf på
    mesteren (−1 angreb/saves), indtil en ny tilkaldes. cooldown: justér dage tilbage
    (klampet ≥ 0). Gen-tilkald sker via /api/companion (summon) når ventetiden er 0.
    """
    from app import _char_path
    data   = request.get_json()
    slug   = data.get("char")
    action = str(data.get("action", "")).lower()
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    if not familiar_module.familiar_eligible(char.cls, char.level):
        return jsonify({"error": "Klassen kan ikke have en familiar."}), 400

    if action == "died":
        # Familiaren fjernes; ventetid + straf starter.
        char_module.save_character(str(path), {
            "companion": {},
            "familiar_lost": {"cooldown": familiar_module.DEFAULT_FAMILIAR_COOLDOWN}})
        return jsonify({"ok": True, "cooldown": familiar_module.DEFAULT_FAMILIAR_COOLDOWN})

    if action == "cooldown":
        delta = int(data.get("delta", 0))
        cur = int((char.familiar_lost or {}).get("cooldown", 0))
        new = max(0, cur + delta)
        char_module.save_character(str(path), {"familiar_lost": {"cooldown": new}})
        return jsonify({"ok": True, "cooldown": new})

    return jsonify({"error": "ukendt action"}), 400

@companion_bp.route("/api/wild_shape", methods=["POST"])
def api_wild_shape():
    """Skift til en wild shape-form (shape) eller tilbage til egen form (revert).

    shape: validér at klassen har wild shape ved niveauet, at formen er lovlig
    (type/størrelse/HD≤niveau) og at der er en use tilbage (animal eller elemental).
    Bruger en use, sætter current_form, og heler HP = niveau (en nats hvile, RAW).
    revert: rydder current_form (forbrugte uses bevares — de er brugt for dagen).
    """
    from app import _char_path
    data   = request.get_json()
    slug   = data.get("char")
    action = str(data.get("action", "")).lower()
    path   = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    ws_data = char_module.class_wild_shape(char.cls)
    info = wild_shape_module.wild_shape_info(ws_data, char.level, char.feats)
    if not info:
        return jsonify({"error": "Klassen har ikke wild shape endnu."}), 400

    state = dict(char.wild_shape or {})

    if action == "revert":
        state["current_form"] = ""
        state["active_abilities"] = []   # form forlades → aktive evner (Rage) ender
        char_module.save_character(str(path), {"wild_shape": state})
        return jsonify({"ok": True})

    if action == "toggle_ability":
        if not state.get("current_form"):
            return jsonify({"error": "Ikke i en form."}), 400
        ability = str(data.get("ability", "")).strip()
        form = wild_shape_module.build_wild_shape_form(char, ws_data, db)
        activatable = {a["slug"] for a in form["natural_abilities"]["gained"]
                       if a.get("activatable")}
        if ability not in activatable:
            return jsonify({"error": "Evnen kan ikke aktiveres i denne form."}), 400
        active = list(state.get("active_abilities") or [])
        if ability in active:
            active.remove(ability)
        else:
            active.append(ability)
        state["active_abilities"] = active
        char_module.save_character(str(path), {"wild_shape": state})
        return jsonify({"ok": True, "active": ability in active})

    if action == "shape":
        form_id = str(data.get("form", "")).strip()
        eligible = {f["id"] for f in wild_shape_module.eligible_forms(info, char.level, db)}
        if form_id not in eligible:
            return jsonify({"error": "Ulovlig form (type/størrelse/HD)."}), 400
        animal = db.get_animal(form_id)
        is_elemental = (animal.get("type") == "elemental")
        used_key = "elemental_used" if is_elemental else "animal_used"
        cap = info["elemental_uses"] if is_elemental else info["animal_uses"]
        if int(state.get(used_key, 0)) >= cap:
            kind = "elemental" if is_elemental else "animal"
            return jsonify({"error": f"Ingen {kind}-uses tilbage i dag."}), 400
        state[used_key] = int(state.get(used_key, 0)) + 1
        state["current_form"] = form_id
        state["active_abilities"] = []   # ny form starter uden aktive evner
        # Heal HP = niveau (en nats hvile) ved hvert wild shape, RAW.
        new_hp = min(char.hp_max, char.hp_current + char.level)
        char_module.save_character(str(path), {"wild_shape": state, "hp_current": new_hp})
        return jsonify({"ok": True})

    return jsonify({"error": "ukendt action"}), 400

