"""Blueprint: spell-slots, kast-tilstande, ladninger, forberedelse, domæner.

_char_path importeres lazy (inde i hver route) for at undgå cirkulær import —
app.py importerer og registrerer dette blueprint, så det kan ikke selv
importere fra app.py på modul-niveau.
"""
from flask import Blueprint, jsonify, request

import character as char_module
import db
import refdata
import spells_known_active
from route_helpers import _find_summon

spells_bp = Blueprint("spells", __name__)


@spells_bp.route("/api/spells", methods=["POST"])
def api_spells():
    from app import _char_path
    data        = request.get_json()
    slug        = data.get("char")
    level       = int(data.get("level"))
    spell_index = int(data.get("spell_index", 0))
    mark_used   = bool(data.get("used"))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    spells_used = {k: list(v) for k, v in char.spells_used.items()}
    spells_active = {k: list(v) for k, v in char.spells_active.items()}
    spell_charges = dict(char.spell_charges)
    spell_durations = dict(char.spell_durations)

    # Et slot der forlader "I brug" og bærer et væsen (direkte summon-kast ELLER et
    # ofret spell) rydder det. is_summon_spell styrer desuden reload (Kast-knappen).
    prepared = char.spells_prepared.get(level, [])
    is_summon_spell = (0 <= spell_index < len(prepared)
                       and refdata.summon_family(prepared[spell_index]) is not None)
    bound_summon = _find_summon(char.summons, level, spell_index) is not None

    # Tre-tilstands-spells (self_duration) sender "state" = free|active|used.
    # To-tilstands-spells sender som før "used" = true/false.
    state = data.get("state")
    if state is not None:
        for d in (spells_used, spells_active):
            if level in d and spell_index in d[level]:
                d[level].remove(spell_index)
        key = char_module.spell_charge_key(level, spell_index)
        spell_charges.pop(key, None)
        spell_durations.pop(key, None)
        if state == "active":
            spells_active.setdefault(level, []).append(spell_index)
            sid = char.spells_prepared.get(level, [])
            if 0 <= spell_index < len(sid):
                # Init ladninger fra kataloget (fx Magic Stone: 3 sten).
                maxc = char_module.spell_max_charges(sid[spell_index], db)
                if maxc:
                    spell_charges[key] = maxc
                # Snapshot varigheds-nedtælleren for en tidsbestemt utility (kategori F).
                snap = char_module.spell_duration_snapshot(
                    db.get_spell(sid[spell_index]) or {}, char.level)
                if snap:
                    spell_durations[key] = snap
        elif state == "used":
            spells_used.setdefault(level, []).append(spell_index)
        # state == "free": fjernet fra begge ovenfor
        updates = {"spells_used": spells_used, "spells_active": spells_active,
                   "spell_charges": spell_charges, "spell_durations": spell_durations}
        # Slot forlader "I brug" → fjern det bundne væsen (fanen forsvinder).
        if bound_summon and state != "active":
            summons = [s for s in char.summons
                       if not (s.get("spell_level") == level
                               and s.get("spell_index") == spell_index)]
            if len(summons) != len(char.summons):
                updates["summons"] = summons
        char_module.save_character(str(path), updates)
    else:
        if mark_used:
            spells_used.setdefault(level, [])
            if spell_index not in spells_used[level]:
                spells_used[level].append(spell_index)
        else:
            if level in spells_used and spell_index in spells_used[level]:
                spells_used[level].remove(spell_index)
        char_module.save_character(str(path), {"spells_used": spells_used})

    return jsonify({
        "spells_used": {str(k): v for k, v in spells_used.items()},
        "spells_active": {str(k): v for k, v in spells_active.items()},
        "spell_charges": spell_charges,
        # Reload hvis et summon-spell (Kast-knap skifter) eller et væsen var bundet (fane).
        "is_summon": is_summon_spell or bound_summon,
    })

@spells_bp.route("/api/spells_known", methods=["POST"])
def api_spells_known():
    """Lær eller glem et spell på en spontan casters kendte liste (sorcerer/bard)."""
    from app import _char_path
    data     = request.get_json()
    slug     = data.get("char")
    action   = data.get("action")            # "add" | "remove"
    level    = int(data.get("level"))
    spell_id = str(data.get("spell_id", ""))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char  = char_module.load_character(str(path))
    known = {k: list(v) for k, v in char.spells_known.items()}
    lst   = known.setdefault(level, [])
    if action == "add" and spell_id and spell_id not in lst:
        lst.append(spell_id)
    elif action == "remove" and spell_id in lst:
        lst.remove(spell_id)
    char_module.save_character(str(path), {"spells_known": known})
    return jsonify({"ok": True, "spells_known": {str(k): v for k, v in known.items()}})

@spells_bp.route("/api/cast_known", methods=["POST"])
def api_cast_known():
    """Spontan caster: forbrug (+1) eller frigiv (−1) en slot af et niveau.

    Slot-loftet beregnes server-side ud fra klasse-level + caster-evne (klienten
    bestemmer ikke grænsen), så forbruget altid holder sig i [0, total]."""
    from app import _char_path
    data  = request.get_json()
    slug  = data.get("char")
    level = int(data.get("level"))
    delta = int(data.get("delta", 1))        # +1 = kast, −1 = fortryd
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char    = char_module.load_character(str(path))
    cld     = db.get_class_level(char.cls.lower(), char.level)
    cast_ab = refdata.class_data(char.cls).get("cast_ability", "wis")
    total   = (char_module.spell_slots_total(
        cld, getattr(char.ability_scores, cast_ab)).get(level, 0) if cld else 0)
    used = dict(char.spells_known_used)
    used[level] = max(0, min(total, used.get(level, 0) + delta))
    char_module.save_character(str(path), {"spells_known_used": used})
    return jsonify({"ok": True, "level": level, "used": used[level], "total": total})

@spells_bp.route("/api/known_active", methods=["POST"])
def api_known_active():
    """Spontane castere: opret/fjern en aktiv spell-INSTANS (varigheds-/vedvarende
    spell). Pulje-slotten forbruges separat via /api/cast_known — dette endpoint
    styrer kun instans-listen, nøglet på uid i stedet for level-index.

    action="activate" (level, spell_id) → tilføj instans m/ varigheds-snapshot.
    action="deactivate" (uid)          → fjern instansen (slotten refunderes ikke).
    action="tick" (uid, delta, reset)  → justér instansens varigheds-nedtæller
        (delta klampet 0..max; reset=True → fuld varighed). Har instansen intet
        snapshot endnu (aktiveret før feature'en), synthesizes det ved første klik.
    """
    from app import _char_path
    data     = request.get_json()
    slug     = data.get("char")
    action   = data.get("action")
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    instances = [dict(i) for i in char.spells_known_active]

    if action == "activate":
        level    = int(data.get("level"))
        spell_id = str(data.get("spell_id", ""))
        if not spell_id:
            return jsonify({"error": "no spell"}), 400
        instances.append(
            spells_known_active.make_instance(char, spell_id, level, db))
    elif action == "deactivate":
        uid = str(data.get("uid", ""))
        instances = [i for i in instances if str(i.get("uid")) != uid]
    elif action == "tick":
        uid   = str(data.get("uid", ""))
        delta = int(data.get("delta", 0))
        reset = bool(data.get("reset", False))
        inst = next((i for i in instances if str(i.get("uid")) == uid), None)
        if inst is None:
            return jsonify({"error": "no instance"}), 400
        snap = inst.get("duration")
        if snap is None:
            snap = char_module.spell_duration_snapshot(
                db.get_spell(inst["spell_id"]) or {}, char.level)
            if snap is None:
                return jsonify({"error": "no duration"}), 400
        rmax = int(snap["max"])
        cur = int(snap["left"])
        new = rmax if reset else max(0, min(rmax, cur + delta))
        inst["duration"] = {"left": new, "max": rmax, "unit": snap["unit"]}
        char.spells_known_active = instances
        char_module.save_character(str(path), {"spells_known_active": instances})
        return jsonify({"ok": True, "left": new, "max": rmax,
                        "unit_label": char_module.dur_unit_label(snap["unit"])})
    else:
        return jsonify({"error": "bad action"}), 400

    char.spells_known_active = instances
    char_module.save_character(str(path), {"spells_known_active": instances})
    return jsonify({"ok": True,
                    "known_active": spells_known_active.derive_known_active(char, db)})

@spells_bp.route("/api/spell_duration", methods=["POST"])
def api_spell_duration():
    """Tæl en aktiv utility-spells (kategori F) resterende varighed op/ned.

    delta justerer left (klampet 0..max); reset=True sætter tilbage til fuld varighed.
    Findes der intet snapshot endnu (spell aktiveret før feature'en), synthesizes det
    fra spellets parsede varighed ved første klik. Ændrer intet andet end nedtælleren.
    """
    from app import _char_path
    data  = request.get_json()
    slug  = data.get("char")
    level = int(data.get("level"))
    index = int(data.get("spell_index"))
    delta = int(data.get("delta", 0))
    reset = bool(data.get("reset", False))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    key = char_module.spell_charge_key(level, index)
    spell_durations = dict(char.spell_durations)
    snap = spell_durations.get(key)
    if snap is None:
        prepared = char.spells_prepared.get(level, [])
        if not (0 <= index < len(prepared)):
            return jsonify({"error": "no spell"}), 400
        snap = char_module.spell_duration_snapshot(
            db.get_spell(prepared[index]) or {}, char.level)
        if snap is None:
            return jsonify({"error": "no duration"}), 400

    rmax = int(snap["max"])
    cur = int(snap["left"])
    new = rmax if reset else max(0, min(rmax, cur + delta))
    spell_durations[key] = {"left": new, "max": rmax, "unit": snap["unit"]}
    char_module.save_character(str(path), {"spell_durations": spell_durations})
    return jsonify({"left": new, "max": rmax,
                    "unit_label": char_module.dur_unit_label(snap["unit"])})

@spells_bp.route("/api/spell_charge", methods=["POST"])
def api_spell_charge():
    """Tæl en spells ladninger op/ned (Magic Stone: brug en sten).

    Rammer ladningerne 0, er spellen opbrugt → flyt fra "I brug" til "Brugt".
    """
    from app import _char_path
    data        = request.get_json()
    slug        = data.get("char")
    level       = int(data.get("level"))
    spell_index = int(data.get("spell_index", 0))
    delta       = int(data.get("delta", -1))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    spells_used = {k: list(v) for k, v in char.spells_used.items()}
    spells_active = {k: list(v) for k, v in char.spells_active.items()}
    spell_charges = dict(char.spell_charges)
    key = char_module.spell_charge_key(level, spell_index)

    new = max(0, spell_charges.get(key, 0) + delta)
    if new <= 0:
        # Opbrugt → ladning væk, spell fra "I brug" til "Brugt".
        spell_charges.pop(key, None)
        if level in spells_active and spell_index in spells_active[level]:
            spells_active[level].remove(spell_index)
        spells_used.setdefault(level, [])
        if spell_index not in spells_used[level]:
            spells_used[level].append(spell_index)
    else:
        spell_charges[key] = new

    char_module.save_character(
        str(path), {"spells_used": spells_used, "spells_active": spells_active,
                    "spell_charges": spell_charges})
    return jsonify({
        "spells_used": {str(k): v for k, v in spells_used.items()},
        "spells_active": {str(k): v for k, v in spells_active.items()},
        "spell_charges": spell_charges,
    })

@spells_bp.route("/api/spell_mode", methods=["POST"])
def api_spell_mode():
    """Skift en aktiv spells angrebs-tilstand (Produce Flame: nærkamp ⇄ kastet).

    Rykker det gemte tilstands-indeks én frem (modulo antal tilstande i spellens
    mode_group) og gemmer det. Antallet slås op i kataloget ud fra den forberedte
    spell på (level, spell_index).
    """
    from app import _char_path
    data        = request.get_json()
    slug        = data.get("char")
    level       = int(data.get("level"))
    spell_index = int(data.get("spell_index", 0))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    prepared = char.spells_prepared.get(level, [])
    if not (0 <= spell_index < len(prepared)):
        return jsonify({"error": "bad index"}), 400
    sid = prepared[spell_index]
    count = sum(1 for r in db.get_spell_attacks(sid) if r.get("mode_group"))
    if count < 2:
        return jsonify({"error": "no modes"}), 400

    spell_modes = dict(char.spell_modes)
    key = char_module.spell_charge_key(level, spell_index)
    spell_modes[key] = (spell_modes.get(key, 0) + 1) % count

    char_module.save_character(str(path), {"spell_modes": spell_modes})
    return jsonify({"spell_modes": spell_modes})

@spells_bp.route("/api/prepare", methods=["POST"])
def api_prepare():
    from app import _char_path
    data = request.get_json()
    slug     = data.get("char")
    prepared = data.get("prepared_spells", {})   # {level_str: [spell_ids]}
    domain   = data.get("domain_prepared", {})   # {level_str: spell_id}
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    prepared_int = {int(k): list(v) for k, v in prepared.items()}
    domain_int = {int(k): str(v) for k, v in domain.items() if v}
    char_module.save_character(str(path), {
        "spells_prepared": prepared_int,
        "spells_used": {},          # ny forberedelse nulstiller brug
        "domain_spells_prepared": domain_int,
        "domain_spells_used": {},   # ny forberedelse nulstiller domæne-brug
    })
    return jsonify({
        "ok": True,
        "prepared_spells": {str(k): v for k, v in prepared_int.items()},
        "domain_prepared": {str(k): v for k, v in domain_int.items()},
    })

@spells_bp.route("/api/domain_used", methods=["POST"])
def api_domain_used():
    from app import _char_path
    data  = request.get_json()
    slug  = data.get("char")
    level = int(data.get("level", 0))
    used  = bool(data.get("used", False))
    path  = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    char = char_module.load_character(str(path))
    domain_used = dict(char.domain_spells_used)
    domain_used[level] = used
    char_module.save_character(str(path), {"domain_spells_used": domain_used})
    return jsonify({"ok": True, "domain_spells_used": {str(k): v for k, v in domain_used.items()}})

