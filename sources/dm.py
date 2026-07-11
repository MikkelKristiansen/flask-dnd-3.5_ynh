"""Blueprint: DM-modul (R1) — kampagne-oversigt + play-visning.

Ruter under /dm:
  GET  /dm/                     oversigt: sessioner + opret-formular
  POST /dm/sessions             opret session (navn, eventyr, party)
  POST /dm/sessions/<slug>/delete
  GET  /dm/play/<slug>          åbn session; ?scene=<id> navigerer + gemmer

Scene-INDHOLDET vises basalt her (read-aloud, prosa, roster, rum). Party-
statblokke + billed-/entity-opslag kommer i R1 commit 4.
"""
import re

from flask import (Blueprint, abort, redirect, render_template, request,
                   send_from_directory, url_for)
from markupsafe import Markup, escape

import bestiary
import db
import dm_board
import dm_media
import dm_party
import dm_scene
import dm_session as ds
import dm_setups
import traps as traps_module

# Entity-typer der slås op som statblok (klikbare → inspector).
# _STAT_TYPES = væsener (→ bestiary.monster_view); _TRAP_TYPE = fælder (→ traps.trap_view).
# Øvrige dokument-lokale typer (kort/brev/gaade) håndteres som handouts (lightbox).
_STAT_TYPES = {"monster", "npc"}
_TRAP_TYPE = "faelde"

dm_bp = Blueprint("dm", __name__, url_prefix="/dm")

_ENTITY_RE = re.compile(r"@([A-Za-zÆØÅæøå]+)\[([^\]]+)\]")


@dm_bp.app_template_filter("entities")
def _entities_filter(text: str, docs: dict | None = None) -> Markup:
    """Vis @type[id] som en diskret markeret reference.

    `docs` er {"type:id": titel} for eventyrets dokument-lokale handouts. En
    reference der findes deri bliver et klikbart link (åbner handout i lightbox,
    med titlen som tekst); alt andet (fx @monster/@npc) forbliver ren tekst —
    deres statblokke kommer i R2.
    """
    docs = docs or {}
    out, last = [], 0
    for m in _ENTITY_RE.finditer(text or ""):
        out.append(escape(text[last:m.start()]))
        typ, ident = m.group(1).lower(), m.group(2)
        key = f"{typ}:{ident}"
        if key in docs:                                   # handout → lightbox
            out.append(Markup(
                '<a class="ent ent-{} ent-link" data-doc="{}">{}</a>').format(
                    typ, key, docs[key]))
        elif typ in _STAT_TYPES or typ == _TRAP_TYPE:     # monster/npc/fælde → statblok-fetch
            out.append(Markup(
                '<a class="ent ent-{} ent-stat" data-stat="{}/{}">{}</a>').format(
                    typ, typ, ident, ident))
        else:
            out.append(Markup('<span class="ent ent-{}">{}</span>').format(
                typ, ident))
        last = m.end()
    out.append(escape((text or "")[last:]))
    return Markup("").join(out)


@dm_bp.route("/")
def index():
    return render_template("dm/index.html",
                           sessions=ds.list_sessions(),
                           adventures=ds.list_adventures(),
                           characters=dm_scene._character_slugs(),
                           adv_error=request.args.get("adv_error"))


@dm_bp.route("/adventures", methods=["POST"])
def new_adventure():
    """Opret et nyt eventyr fra forsiden og hop direkte i tekst-editoren."""
    name = (request.form.get("name") or "").strip()
    try:
        ref = ds.create_adventure(name)
    except ValueError:
        return redirect(url_for("dm.index", adv_error="Skriv et gyldigt navn til eventyret."))
    except FileExistsError:
        return redirect(url_for("dm.index", adv_error="Der findes allerede et eventyr med det navn."))
    return redirect(url_for("dm.edit_adventure", adventure=ref))


@dm_bp.route("/sessions", methods=["POST"])
def create():
    name = (request.form.get("name") or "").strip()
    adventure = request.form.get("adventure") or ""
    party = request.form.getlist("party")
    if not adventure:
        abort(400, "Vælg et eventyr.")
    try:
        session = ds.create_session(name, adventure, party)
    except FileNotFoundError:
        abort(404, "Eventyret findes ikke.")
    return redirect(url_for("dm.play", slug=session.slug))


@dm_bp.route("/sessions/<slug>/delete", methods=["POST"])
def delete(slug):
    ds.delete_session(slug)
    return redirect(url_for("dm.index"))


@dm_bp.route("/adventures/<adventure>")
def adventure(adventure):
    """Administrér ét eventyrs kort/handout-billeder: se dem + upload + slet."""
    if adventure not in ds.list_adventures():
        abort(404)
    adv_dir = ds.adventure_dir(adventure)
    return render_template("dm/adventure.html", ref=adventure,
                           media=dm_media.list_media(adv_dir),
                           uploaded=request.args.get("uploaded"),
                           error=request.args.get("error"))


@dm_bp.route("/adventures/<adventure>/edit", methods=["GET", "POST"])
def edit_adventure(adventure):
    """Rediger et eventyrs rå Markdown i browseren (simpel tekstboks) — fjerner
    behovet for scp. Gemmer atomisk; play/bræt re-parser ved næste indlæsning."""
    if adventure not in ds.list_adventures():
        abort(404)
    if request.method == "POST":
        ds.write_adventure_source(adventure, request.form.get("source", ""))
        return redirect(url_for("dm.edit_adventure", adventure=adventure, saved=1))
    adv = ds.load_adventure(adventure)               # parse-resumé som kvittering
    return render_template("dm/edit.html", ref=adventure,
                           source=ds.read_adventure_source(adventure),
                           summary={"scenes": len(adv.scenes), "docs": len(adv.documents)},
                           saved=request.args.get("saved"))


@dm_bp.route("/adventures/<adventure>/media", methods=["POST"])
def upload_media(adventure):
    if adventure not in ds.list_adventures():
        abort(404)
    adv_dir = ds.adventure_dir(adventure)
    names, errors = [], []
    for f in request.files.getlist("images"):
        if not f or not f.filename:
            continue
        try:
            names.append(dm_media.save_media(adv_dir, f))
        except ValueError as e:
            errors.append(f"{f.filename}: {e}")
    q = {}
    if names:
        q["uploaded"] = ", ".join(names)
    if errors:
        q["error"] = " · ".join(errors)
    return redirect(url_for("dm.adventure", adventure=adventure, **q))


@dm_bp.route("/adventures/<adventure>/media/<filename>/delete", methods=["POST"])
def delete_media(adventure, filename):
    if adventure not in ds.list_adventures():
        abort(404)
    dm_media.delete_media(ds.adventure_dir(adventure), filename)
    return redirect(url_for("dm.adventure", adventure=adventure))


# ── Encounter-tracker (R3) ───────────────────────────────────────────────────
import dm_encounter


def _tracker_html(session):
    """Render tracker-fragmentet for sessionens encounter (eller start-knap)."""
    enc = session.encounter
    ordered, current_id, statblocks = [], None, []
    if enc.get("active"):
        by_id = {c["id"]: c for c in enc.get("combatants", [])}
        ordered = [by_id[cid] for cid in enc.get("turn_order", []) if cid in by_id]
        order = enc.get("turn_order", [])
        if order:
            current_id = order[min(enc.get("turn_index", 0), len(order) - 1)]
        statblocks = dm_scene._encounter_statblocks(session, ordered)
    return render_template("dm/_tracker.html", enc=enc, ordered=ordered,
                           current_id=current_id, slug=session.slug,
                           statblocks=statblocks,
                           all_conditions=db.get_all_conditions())


def _load_or_404(slug):
    try:
        return ds.load_session(slug)
    except FileNotFoundError:
        abort(404)


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


@dm_bp.route("/api/statblock/<adventure>/<etype>/<ident>")
def api_statblock(adventure, etype, ident):
    """Slå en klikket entity op og returnér dens statblok som HTML-fragment til
    inspector-panelet. Opslags-rækkefølge: adventure-lokalt statblok (unikke
    NPC'er) → delt bestiar (generiske monstre) → party-PC (via slug) → ingen."""
    if adventure not in ds.list_adventures():
        abort(404)
    adv = ds.load_adventure(adventure)
    if etype == _TRAP_TYPE:                            # fælde → delt fælde-katalog
        row = db.get_trap(ident)
        if row:
            return render_template("dm/_trap.html", t=traps_module.trap_view(row))
        return render_template("dm/_statblock.html", none=True, etype=etype, ident=ident)
    stats = adv.statblock(ident)
    if stats:
        return render_template("dm/_statblock.html",
                               m=bestiary.monster_view(stats), origin="Eventyr")
    row = db.get_monster(ident)
    if row:
        return render_template("dm/_statblock.html",
                               m=bestiary.monster_view(row), origin="Bestiar")
    pcs = dm_party.party_view([ident], db)
    if pcs and not pcs[0].get("broken"):
        return render_template("dm/_statblock.html", pc=pcs[0])
    return render_template("dm/_statblock.html", none=True, etype=etype, ident=ident)


@dm_bp.route("/board/<adventure>/<map_slug>")
def board(adventure, map_slug):
    """Vis et korts startopstilling (grid + tokens) med grid-kalibrering og
    træk-placér-editor. board.tokens er både initial-render OG editorens
    JS-model; palette = kandidater der kan trækkes ind."""
    if adventure not in ds.list_adventures():
        abort(404)
    adv = ds.load_adventure(adventure)
    src, title = dm_scene._map_src(adv, map_slug)
    setup = dm_setups.load_setup(adventure, map_slug)
    # ?from=<session> → tilbage-link til den kamp man kom fra (validér den findes).
    back = request.args.get("from")
    if back and not any(s["slug"] == back for s in ds.list_sessions()):
        back = None
    return render_template(
        "dm/board.html", title=title,
        map_url=url_for("dm.media", adventure=adventure, filename=src) if src else None,
        board=dm_board.board_view(setup, adv, db, audience="dm"),
        palette=dm_scene._board_palette(adv), token_style=dm_board.token_style(),
        traps=[{"id": t["id"], "name": t["name"]} for t in db.get_all_traps()],
        back_session=back)


@dm_bp.route("/bestiary/<adventure>")
def bestiary_view(adventure):
    """Bestiarie-fane: alle monstre/NPC'er i ét eventyr som statblokke, så DM'en
    kan slå væsener op uden for en scene. ?from=<session> giver et tilbage-link
    til kampen. (Navngivet *_view for ikke at skygge for `bestiary`-modulet.)"""
    if adventure not in ds.list_adventures():
        abort(404)
    adv = ds.load_adventure(adventure)
    back = request.args.get("from")
    if back and not any(s["slug"] == back for s in ds.list_sessions()):
        back = None
    return render_template("dm/bestiary.html", title=adv.title,
                           adventure=adventure, entries=dm_scene._bestiary_entries(adv),
                           back_session=back)


@dm_bp.route("/board/<adventure>/<map_slug>/grid", methods=["POST"])
def board_grid(adventure, map_slug):
    """Gem grid-kalibreringen (cellestørrelse + offset) for et kort."""
    if adventure not in ds.list_adventures():
        abort(404)
    setup = dm_setups.load_setup(adventure, map_slug)
    setup["grid"] = {"cell": round(float(request.form.get("cell") or 0), 2),
                     "x": int(float(request.form.get("x") or 0)),
                     "y": int(float(request.form.get("y") or 0))}
    dm_setups.save_setup(adventure, map_slug, setup)
    return ("", 204)


@dm_bp.route("/board/<adventure>/<map_slug>/tokens", methods=["POST"])
def board_tokens(adventure, map_slug):
    """Gem token-placeringerne fra opstillings-editoren. Grid-delen røres ikke;
    listen saniteres server-side før den skrives."""
    if adventure not in ds.list_adventures():
        abort(404)
    setup = dm_setups.load_setup(adventure, map_slug)
    setup["tokens"] = dm_setups.sanitize_tokens(request.get_json(silent=True))
    dm_setups.save_setup(adventure, map_slug, setup)
    return ("", 204)


@dm_bp.route("/media/<adventure>/<path:filename>")
def media(adventure, filename):
    """Servér et eventyrs billeder fra `adventures/<eventyr>/media/…`.
    `adventure` saniteres til ét mappe-segment; send_from_directory afviser
    desuden sti-traversal i `filename`."""
    return send_from_directory(ds.adventure_dir(adventure), filename)


def _scene_board_maps(session, adventure):
    """Bræt-data pr. @kort-embed i sessionens aktive scene, PLUS i hvert af
    scenens rum. Kamp-primær-kortet (det aktive rums kort hvis en rum-kamp er
    i gang, ellers scenens første kort) viser LIVE kamp-positioner; resten
    viser den forfattede opstilling. Returnerer (board_maps, primær-map-slug)."""
    active = next((sc for sc in adventure.scenes if sc.id == session.active_scene),
                  adventure.scenes[0] if adventure.scenes else None)
    enc = session.encounter
    current_id = dm_scene._current_combatant_id(enc)
    room_id = enc.get("room") if enc.get("active") else None
    combat_slug = (dm_scene._active_map_slug(adventure, session, room_id)
                  if enc.get("active") else None)

    # Saml embeds fra scenens top-blokke OG fra hvert rums under-blokke.
    embeds = [b for b in (active.blocks if active else [])
             if getattr(b, "kind", None) == "embed" and b.entity.type == "kort"]
    for b in (active.blocks if active else []):
        if getattr(b, "kind", None) == "room":
            embeds.extend(rb for rb in b.blocks
                          if getattr(rb, "kind", None) == "embed" and rb.entity.type == "kort")

    board_maps, map_slug = {}, None
    for b in embeds:
        mslug = b.entity.id
        if map_slug is None:
            map_slug = mslug
        if mslug in board_maps:
            continue
        src, title = dm_scene._map_src(adventure, mslug)
        setup = dm_setups.load_setup(session.adventure, mslug)
        combat = bool(enc.get("active")) and mslug == combat_slug
        board = (dm_board.combat_board_view(setup, enc, current_id) if combat
                 else dm_board.board_view(setup, adventure, db, audience="dm"))
        board_maps[mslug] = {
            "map_url": url_for("dm.media", adventure=session.adventure,
                               filename=src) if src else None,
            "board": board, "title": title, "combat": combat, "map_slug": mslug}
    if combat_slug and combat_slug in board_maps:
        map_slug = combat_slug
    return board_maps, map_slug


@dm_bp.route("/play/<slug>")
def play(slug):
    try:
        session = ds.load_session(slug)
    except FileNotFoundError:
        abort(404)
    adventure = ds.load_adventure(session.adventure)
    scene_ids = {sc.id for sc in adventure.scenes}
    scene_id = request.args.get("scene")
    if scene_id and scene_id in scene_ids:
        session = ds.goto_scene(slug, scene_id)          # persistér navigation
    active = next((sc for sc in adventure.scenes if sc.id == session.active_scene),
                  adventure.scenes[0] if adventure.scenes else None)
    party = dm_party.party_view(session.party, db)
    board_maps, map_slug = _scene_board_maps(session, adventure)
    return render_template("dm/play.html", session=session,
                           adventure=adventure, active=active, party=party,
                           adv_ref=session.adventure, map_slug=map_slug,
                           board_maps=board_maps,
                           doc_titles=dm_scene._doc_titles(adventure),
                           tracker_html=_tracker_html(session))
