"""dm_routes_encounter — encounter-tracker-ruterne (R3) på DM-blueprintet.

Udspaltet fra dm.py (som var vokset til 31 ruter). Ruterne dekorerer SAMME `dm_bp`
som resten af DM-modulet (importeret fra dm), så `url_for("dm.encounter_…")` er
uændret. dm.py importerer dette modul i bunden, så decorators kører og registrerer
ruterne. Delte helpers (`_tracker_html`/`_load_or_404`/`_scene_board_maps`) bliver i
dm.py og importeres herfra.
"""
from flask import render_template, request

import dm_encounter
import dm_scene
import dm_session as ds
import dm_setups
from dm import _load_or_404, _scene_board_maps, _tracker_html, dm_bp


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
