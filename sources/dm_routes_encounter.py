"""dm_routes_encounter — encounter-tracker-ruterne (R3) på DM-blueprintet.

Udspaltet fra dm.py (som var vokset til 31 ruter). Ruterne dekorerer SAMME `dm_bp`
som resten af DM-modulet (importeret fra dm), så `url_for("dm.encounter_…")` er
uændret. dm.py importerer dette modul i bunden, så decorators kører og registrerer
ruterne. Delte helpers (`_tracker_html`/`_load_or_404`/`_scene_board_maps`) bliver i
dm.py og importeres herfra.
"""
from flask import jsonify, render_template, request

import db
import dm_encounter
import dm_scene
import dm_session as ds
import dm_setups
import doors as doors_module
from dm import _load_or_404, _scene_board_maps, _tracker_html, dm_bp


def _door_hp_key(ref: str, col, row) -> str:
    """Stabil nøgle pr. dør-INSTANS i encounterens object_hp-store. col/row gør to
    døre af samme type unikke; de er låst under kamp, så nøglen er stabil."""
    return f"{ref}:{col}:{row}"


@dm_bp.route("/api/encounter/<slug>/start", methods=["POST"])
def encounter_start(slug):
    session = _load_or_404(slug)
    adv = ds.load_adventure(session.adventure)
    # Rum-scopet kamp: ?room=<id> → kun dét rums monstre. Valider mod den
    # aktive scene, ellers falder vi tilbage til den gamle scene-brede kamp.
    room_id = request.form.get("room") or None
    if room_id:
        active_scene = next((s for s in adv.scenes if s.id == session.active_scene),
                            adv.scenes[0] if adv.scenes else None)
        if not dm_scene._find_room(active_scene, room_id):
            room_id = None
    combs = dm_encounter.build_combatants(
        dm_scene._encounter_sources(session, adv, room_id))
    # Auto-rul initiativ for monstre; PC'er efterlades blanke (DM taster spillernes rul).
    dm_encounter.roll_initiative([c for c in combs if c["kind"] != "pc"])
    # Seed startpositioner fra kortets opstilling (hvis scenen/rummet har et kort).
    map_slug = dm_scene._active_map_slug(adv, session, room_id)
    tokens = dm_setups.load_setup(session.adventure, map_slug)["tokens"] if map_slug else []
    session = ds.begin_encounter(slug, combs, tokens, room=room_id)
    return _tracker_html(session)


@dm_bp.route("/api/encounter/<slug>/initiative", methods=["POST"])
def encounter_initiative(slug):
    _load_or_404(slug)
    session = ds.set_initiative(slug, request.form.get("cid", ""),
                               int(request.form.get("value") or 0))
    return _tracker_html(session)


@dm_bp.route("/api/encounter/<slug>/next", methods=["POST"])
def encounter_next(slug):
    _load_or_404(slug)
    return _tracker_html(ds.next_turn(slug))


@dm_bp.route("/api/encounter/<slug>/hp", methods=["POST"])
def encounter_hp(slug):
    session = _load_or_404(slug)
    cid = request.form.get("cid", "")
    c = next((x for x in session.encounter.get("combatants", []) if x["id"] == cid), None)
    if c is not None:
        delta = int(request.form.get("delta") or 0)
        new_hp = (c.get("current_hp") or 0) + delta if delta \
            else int(request.form.get("value") or 0)
        session = ds.set_combatant_hp(slug, cid, new_hp)
    return _tracker_html(session)


@dm_bp.route("/api/encounter/<slug>/door/<ref>")
def encounter_door(slug, ref):
    """Dør-statblok til inspektøren, beriget med kamp-HP når en kamp kører. Åbnes af
    dør-markøren i play-viewet (col/row identificerer instansen). Uden aktiv kamp er
    det bare den statiske dør-visning (som opslags-statblokken)."""
    session = _load_or_404(slug)
    row = db.get_door(ref)
    if not row:
        return render_template("dm/_statblock.html", none=True, etype="door", ident=ref)
    live = None
    if session.encounter.get("active"):
        col, rrow = request.args.get("col", "0"), request.args.get("row", "0")
        key = _door_hp_key(ref, col, rrow)
        stored = (session.encounter.get("object_hp") or {}).get(key)
        hp_max = row.get("hp")
        if hp_max is not None:                       # kun døre med HP kan trackes
            live = {"ref": ref, "col": col, "row": rrow,
                    "current": stored["current"] if stored else int(hp_max),
                    "max": int(hp_max), "hardness": row.get("hardness")}
    return render_template("dm/_door.html", d=doors_module.door_view(row), live=live)


@dm_bp.route("/api/encounter/<slug>/door_hp", methods=["POST"])
def encounter_door_hp(slug):
    """Justér en dørs kamp-HP (rå +/-, reset til fuld). Lazy-init fra dør-kataloget;
    kun under aktiv kamp. Returnerer den nye HP så popuppen kan opdatere tallet live."""
    session = _load_or_404(slug)
    if not session.encounter.get("active"):
        return jsonify({"error": "ingen kamp"}), 400
    ref = request.form.get("ref", "")
    col, row = request.form.get("col", "0"), request.form.get("row", "0")
    door = db.get_door(ref)
    if not door or door.get("hp") is None:
        return jsonify({"error": "ukendt dør"}), 400
    hp_max = int(door["hp"])
    key = _door_hp_key(ref, col, row)
    stored = (session.encounter.get("object_hp") or {}).get(key)
    cur = stored["current"] if stored else hp_max
    if request.form.get("reset"):
        new = hp_max
    else:
        new = max(0, min(hp_max, cur + int(request.form.get("delta") or 0)))
    ds.set_object_hp(slug, key, new, hp_max, door.get("hardness"))
    return jsonify({"current": new, "max": hp_max})


@dm_bp.route("/api/encounter/<slug>/condition", methods=["POST"])
def encounter_condition(slug):
    _load_or_404(slug)
    session = ds.toggle_condition(slug, request.form.get("cid", ""),
                                 request.form.get("condition", ""))
    return _tracker_html(session)


@dm_bp.route("/api/encounter/<slug>/end", methods=["POST"])
def encounter_end(slug):
    _load_or_404(slug)
    return _tracker_html(ds.end_encounter(slug))


@dm_bp.route("/api/encounter/<slug>/board")
def encounter_board(slug):
    """Bræt-fragmentet for aktiv scenes primær-kort (kamp- eller opstillings-
    tilstand). Play-viewet refetcher det efter tracker-handlinger, så positioner,
    HP og aktiv-tur-markør holdes synkrone med kampen."""
    session = _load_or_404(slug)
    adv = ds.load_adventure(session.adventure)
    board_maps, map_slug = _scene_board_maps(session, adv)
    if not map_slug:
        return ("", 204)
    return render_template("dm/_map_figure.html", m=board_maps[map_slug],
                           adv_ref=session.adventure, session=session)


@dm_bp.route("/api/encounter/<slug>/move", methods=["POST"])
def encounter_move(slug):
    """Flyt en combatant til en ny grid-celle under kamp (live-position). Brættet
    genhentes af klienten bagefter, så tur/HP-overlay følger med."""
    _load_or_404(slug)
    ds.set_combatant_position(slug, request.form.get("cid", ""),
                              int(float(request.form.get("col") or 0)),
                              int(float(request.form.get("row") or 0)))
    return ("", 204)
