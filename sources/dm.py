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
import character as char_module
import db
import dm_board
import dm_media
import dm_party
import dm_session as ds
import dm_setups
from paths import CHARACTERS_DIR

# Entity-typer der slås op som statblok (klikbare → inspector). Dokument-lokale
# typer (kort/brev/gaade/faelde) håndteres separat som handouts (lightbox).
_STAT_TYPES = {"monster", "npc"}

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
        elif typ in _STAT_TYPES:                          # monster/npc → statblok-fetch
            out.append(Markup(
                '<a class="ent ent-{} ent-stat" data-stat="{}/{}">{}</a>').format(
                    typ, typ, ident, ident))
        else:
            out.append(Markup('<span class="ent ent-{}">{}</span>').format(
                typ, ident))
        last = m.end()
    out.append(escape((text or "")[last:]))
    return Markup("").join(out)


def _doc_titles(adventure) -> dict:
    """{"type:id": titel} for eventyrets dokumenter — fodrer entities-filteret."""
    return {f"{d.type}:{d.id}": d.title for d in adventure.documents.values()}


def _character_slugs() -> list[str]:
    if not CHARACTERS_DIR.exists():
        return []
    return sorted(p.stem for p in CHARACTERS_DIR.glob("*.yaml"))


@dm_bp.route("/")
def index():
    return render_template("dm/index.html",
                           sessions=ds.list_sessions(),
                           adventures=ds.list_adventures(),
                           characters=_character_slugs())


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


def _scene_rosters(scene):
    """Alle roster-poster i en scene (top-niveau + i rum)."""
    entries = []
    for b in getattr(scene, "blocks", []):
        if getattr(b, "kind", None) == "roster":
            entries.extend(b.entries)
        elif getattr(b, "kind", None) == "room":
            for rb in b.blocks:
                if getattr(rb, "kind", None) == "roster":
                    entries.extend(rb.entries)
    return entries


def _monster_source(ref, adv):
    """Resolv et roster-id til combatant-kildedata (navn/init/hp) via adventure-
    lokalt statblok → bestiar → fallback (ukendt = rå id, 0 init, ingen hp)."""
    stats = adv.statblock(ref) or db.get_monster(ref)
    if stats:
        v = bestiary.monster_view(stats)
        return {"name": v["name"], "init_mod": v["init"], "hp_max": v["hp_max"],
                "kind": "monster"}
    return {"name": ref, "init_mod": 0, "hp_max": None, "kind": "monster"}


def _encounter_sources(session, adv):
    """Byg combatant-kilder for den aktive scene: monstre fra rosteret + party-PC'er."""
    scene = next((s for s in adv.scenes if s.id == session.active_scene),
                 adv.scenes[0] if adv.scenes else None)
    sources = []
    if scene:
        for e in _scene_rosters(scene):
            src = _monster_source(e.id, adv)
            sources.append({"ref": e.id, "count": e.count, **src})
    for pc in dm_party.party_view(session.party, db):
        if pc.get("broken"):
            continue
        sources.append({"ref": pc["slug"], "count": 1, "name": pc["name"],
                        "kind": "pc", "init_mod": pc["init"], "hp_max": pc["hp_max"]})
    return sources


def _encounter_statblocks(session, ordered):
    """Statblokke pr. DISTINKT monstertype i kampen (Goblin A/B deler ét kort),
    så DM'en har monster-stats permanent foran sig. Reference-data resolves live
    (adventure-lokalt → bestiar) — ikke gemt i sessionen. PC'er udelades (de står
    i party-panelet). Rækkefølge følger tur-ordenen."""
    try:
        adv = ds.load_adventure(session.adventure)
    except FileNotFoundError:
        adv = None
    out, seen = [], set()
    for c in ordered:
        if c["kind"] == "pc" or c["ref"] in seen:
            continue
        seen.add(c["ref"])
        row = (adv.statblock(c["ref"]) if adv else None) or db.get_monster(c["ref"])
        if row:
            out.append(bestiary.monster_view(row))
    return out


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
        statblocks = _encounter_statblocks(session, ordered)
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
    combs = dm_encounter.build_combatants(_encounter_sources(session, adv))
    # Auto-rul initiativ for monstre; PC'er efterlades blanke (DM taster spillernes rul).
    dm_encounter.roll_initiative([c for c in combs if c["kind"] != "pc"])
    session = ds.begin_encounter(slug, combs)
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


@dm_bp.route("/api/statblock/<adventure>/<etype>/<ident>")
def api_statblock(adventure, etype, ident):
    """Slå en klikket entity op og returnér dens statblok som HTML-fragment til
    inspector-panelet. Opslags-rækkefølge: adventure-lokalt statblok (unikke
    NPC'er) → delt bestiar (generiske monstre) → party-PC (via slug) → ingen."""
    if adventure not in ds.list_adventures():
        abort(404)
    adv = ds.load_adventure(adventure)
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


def _board_palette(adv):
    """Kandidater DM'en kan trække ind på brættet: eventyrets egne monstre/NPC'er
    (unikke refs fra alle scene-rosters, navn resolvet) + alle PC'er + de faste
    markør-typer. Ren udledning til opstillings-editoren."""
    creatures, seen = [], set()
    for scene in adv.scenes:
        for e in _scene_rosters(scene):
            # Kun væsener som træk-tokens; roster-fælder (@faelde) placeres via
            # den faste markør-palette (ref-binding er en senere fase).
            if e.type not in ("monster", "npc"):
                continue
            key = (e.type, e.id)
            if key in seen:
                continue
            seen.add(key)
            row = adv.statblock(e.id) or db.get_monster(e.id)
            name = bestiary.monster_view(row)["name"] if row else e.id
            creatures.append({"kind": e.type, "ref": e.id, "name": name})
    pcs = []
    for slug in _character_slugs():
        try:
            name = char_module.load_character(str(CHARACTERS_DIR / f"{slug}.yaml")).name
        except Exception:
            name = slug
        pcs.append({"kind": "pc", "ref": slug, "name": name or slug})
    markers = [{"kind": "trap", "name": "Fælde"}, {"kind": "door", "name": "Dør"},
               {"kind": "treasure", "name": "Skat"}, {"kind": "note", "name": "Note"}]
    return {"creatures": creatures, "pcs": pcs, "markers": markers}


def _map_src(adv, map_slug):
    """Billed-src for et kort (fra dets '## Kort:'-def i eventyret)."""
    doc = adv.documents.get(("kort", map_slug))
    if not doc:
        return None, map_slug
    img = next((b for b in doc.blocks if getattr(b, "kind", None) == "image"), None)
    return (img.src if img else None), doc.title


@dm_bp.route("/board/<adventure>/<map_slug>")
def board(adventure, map_slug):
    """Vis et korts startopstilling (grid + tokens) med grid-kalibrering og
    træk-placér-editor. board.tokens er både initial-render OG editorens
    JS-model; palette = kandidater der kan trækkes ind."""
    if adventure not in ds.list_adventures():
        abort(404)
    adv = ds.load_adventure(adventure)
    src, title = _map_src(adv, map_slug)
    setup = dm_setups.load_setup(adventure, map_slug)
    # ?from=<session> → tilbage-link til den kamp man kom fra (validér den findes).
    back = request.args.get("from")
    if back and not any(s["slug"] == back for s in ds.list_sessions()):
        back = None
    return render_template(
        "dm/board.html", title=title,
        map_url=url_for("dm.media", adventure=adventure, filename=src) if src else None,
        board=dm_board.board_view(setup, adv, db, audience="dm"),
        palette=_board_palette(adv), token_style=dm_board.token_style(),
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
    # Bræt-data pr. @kort-embed i aktiv scene, så play-viewet kan vise selve
    # brættet (kort + grid + opstillingens tokens), ikke bare kort-billedet.
    # map_slug = første kort (til "Åbn bræt"-linket).
    board_maps, map_slug = {}, None
    for b in (active.blocks if active else []):
        if getattr(b, "kind", None) == "embed" and b.entity.type == "kort":
            mslug = b.entity.id
            if map_slug is None:
                map_slug = mslug
            if mslug not in board_maps:
                src, _ = _map_src(adventure, mslug)
                setup = dm_setups.load_setup(session.adventure, mslug)
                board_maps[mslug] = {
                    "map_url": url_for("dm.media", adventure=session.adventure,
                                       filename=src) if src else None,
                    "board": dm_board.board_view(setup, adventure, db, audience="dm")}
    return render_template("dm/play.html", session=session,
                           adventure=adventure, active=active, party=party,
                           adv_ref=session.adventure, map_slug=map_slug,
                           board_maps=board_maps,
                           doc_titles=_doc_titles(adventure),
                           tracker_html=_tracker_html(session))
