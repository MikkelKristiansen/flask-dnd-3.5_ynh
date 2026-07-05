"""Blueprint: Summon Nature's Ally / Summon Monster — kast, HP, runde-varighed.

_char_path importeres lazy (se routes_spells.py for hvorfor).
"""
from flask import Blueprint, jsonify, request

import character as char_module
import db
import dice as dice_module
import refdata
import summon as summon_module
from route_helpers import _find_summon

summon_bp = Blueprint("summon", __name__)


@summon_bp.route("/api/summon", methods=["POST"])
def api_summon():
    """Kast et summonet væsen (Summon Nature's Ally ELLER Summon Monster).

    To modes:
    - "cast": slot'et ER et forberedt/kendt summon-spell (SNA eller SM), der sættes
      "I brug". Familien udledes af spell-id'et (refdata.summon_family).
    - "sacrifice": slot'et er et hvilket som helst andet forberedt spell, der ofres
      til SNA af samme niveau (kun klasser med spontaneous_summon — druide). SM har
      ingen spontan-vej. Det ofrede slot sættes også "I brug".

    Begge: summon-niveau N = slot-niveauet. Summon Monster kan bære en celestial/
    fiendish-skabelon (data.template). Augment Summoning snapshottes fra feats. HP
    sættes til fuld (hp_max pr. væsen). En tynd ref bindes til (spell_level=N, index).
    """
    from app import _char_path
    data        = request.get_json()
    slug        = data.get("char")
    mode        = data.get("mode", "cast")
    level       = int(data.get("level"))           # slot-niveau = summon-niveau
    spell_index = int(data.get("spell_index", 0))
    creature    = (data.get("creature") or "").strip()
    template    = (data.get("template") or "").strip() or None
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))

    # Validér slot'et efter mode + udled hvilken familie der castes.
    prepared = char.spells_prepared.get(level, [])
    if not (0 <= spell_index < len(prepared)):
        return jsonify({"error": "ugyldigt slot"}), 400
    sid = prepared[spell_index]
    family = refdata.summon_family(sid)
    if mode == "sacrifice":
        if not refdata.class_data(char.cls).get("spontaneous_summon"):
            return jsonify({"error": "klassen kan ikke spontant summone"}), 400
        if family is not None:
            return jsonify({"error": "brug Kast på selve summon-spellet"}), 400
        cast_family = "sna"          # offer konverteres altid til SNA (druide)
    else:  # cast
        if family is None:
            return jsonify({"error": "ikke et summon-spell"}), 400
        cast_family = family
    if spell_index in char.spells_active.get(level, []) or \
            spell_index in char.spells_used.get(level, []):
        return jsonify({"error": "spell allerede brugt"}), 400

    # Validér + udled antal: væsenet skal ligge i ét af cast-niveauets spor (niveau-N-
    # listen eller en lavere liste for flere svagere væsner). Sporet bestemmer antals-
    # udtrykket (1 / 1d3 / 1d4+1), som rulles server-side — klienten bestemmer det ikke.
    count_expr = refdata.summon_count_expr(cast_family, level, creature, template)
    if count_expr is None:
        return jsonify({"error": "ugyldigt væsen"}), 400
    # "1" (niveau-N-listen) er en konstant; lavere spor ("1d3"/"1d4+1") rulles.
    count = int(count_expr) if count_expr.isdigit() else dice_module.roll(count_expr)["total"]

    # Augment Summoning-snapshot fra karakterens feats (+4 Str/+4 Con på væsenet).
    augment = any(char_module.feat_id(e) == "augment_summoning" for e in char.feats)

    # Byg statblokken én gang for at få hp_max → fuld HP pr. væsen ved kast.
    ref = {"creature": creature, "template": template, "spell_level": level,
           "spell_index": spell_index, "count": count, "augment": augment}
    stat = summon_module.build_summon(ref, db)
    if not stat:
        return jsonify({"error": "ugyldigt væsen"}), 400
    ref["hp_current"] = [stat["hp_max"]] * count
    # Varighed: Summon Monster/SNA varer 1 runde pr. casterniveau (fast ved kast).
    # Summon Swarm er en undtagelse (SRD: "Concentration + 2 rounds", ikke
    # niveau-skaleret) — modelleret som en simpel manuel 2-runders tæller på
    # samme -/+/⟲-mekanik: spilleren holder selv tallet oppe mens vedkommende
    # koncentrerer sig (⟲ nulstiller til 2) og lader det tælle ned når
    # koncentrationen brydes. Mindre SRD-tro end en dedikeret koncentrations-
    # toggle, men genbruger 100% af den eksisterende tracker uden ny UI-tilstand.
    rounds = 2 if cast_family == "swarm" else char.level
    ref["rounds_max"] = rounds
    ref["rounds_left"] = rounds

    # Sæt summon-spellet "I brug" (samme mekanik som cycleSpell → state=active).
    spells_active = {k: list(v) for k, v in char.spells_active.items()}
    spells_used   = {k: list(v) for k, v in char.spells_used.items()}
    spells_active.setdefault(level, []).append(spell_index)

    # Append summon-ref og gem hele summons-listen + spell-tilstanden.
    summons = list(char.summons) + [ref]
    char_module.save_character(str(path), {
        "summons": summons,
        "spells_active": spells_active,
        "spells_used": spells_used,
    })
    return jsonify({"ok": True, "count": count, "count_expr": count_expr})

@summon_bp.route("/api/summon_hp", methods=["POST"])
def api_summon_hp():
    """Justér HP for ÉT væsen i et summon (identificeret af SNA-slot + væsen-index).

    Spejler /api/companion_hp, men summons har en HP-liste (ét tal pr. count).
    Gemmer hele summons-listen (Fase 2's summons-nøgle).
    """
    from app import _char_path
    data     = request.get_json()
    slug     = data.get("char")
    level    = int(data.get("spell_level"))
    index    = int(data.get("spell_index"))
    creature = int(data.get("creature_index", 0))
    delta    = int(data.get("delta", 0))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    ref = _find_summon(char.summons, level, index)
    if not ref:
        return jsonify({"error": "no summon"}), 400
    stat = summon_module.build_summon(ref, db)
    if not stat:
        return jsonify({"error": "no summon"}), 400
    hp_max = stat["hp_max"]
    hp_list = list(stat["hp_current"])      # resolveret liste (ét tal pr. væsen)
    if not (0 <= creature < len(hp_list)):
        return jsonify({"error": "bad creature index"}), 400
    hp_list[creature] = max(-9, min(hp_max, hp_list[creature] + delta))
    ref["hp_current"] = hp_list
    char_module.save_character(str(path), {"summons": char.summons})
    return jsonify({"hp_current": hp_list, "hp_max": hp_max, "creature_index": creature})

@summon_bp.route("/api/summon_rounds", methods=["POST"])
def api_summon_rounds():
    """Tæl et summons resterende runder op/ned (varighed = 1 runde/casterniveau).

    delta justerer rounds_left (klampet 0..rounds_max); reset=True sætter tilbage
    til fuld varighed. Ændrer aldrig HP eller afskediger — det styrer brugeren selv.
    """
    from app import _char_path
    data  = request.get_json()
    slug  = data.get("char")
    level = int(data.get("spell_level"))
    index = int(data.get("spell_index"))
    delta = int(data.get("delta", 0))
    reset = bool(data.get("reset", False))
    path = _char_path(slug)
    if not path.exists():
        return jsonify({"error": "not found"}), 404

    char = char_module.load_character(str(path))
    ref = _find_summon(char.summons, level, index)
    if not ref:
        return jsonify({"error": "no summon"}), 400
    rmax = ref.get("rounds_max")
    if rmax is None:
        return jsonify({"error": "no duration"}), 400
    rmax = int(rmax)
    cur = int(ref.get("rounds_left", rmax))
    new = rmax if reset else max(0, min(rmax, cur + delta))
    ref["rounds_left"] = new
    char_module.save_character(str(path), {"summons": char.summons})
    return jsonify({"rounds_left": new, "rounds_max": rmax})

