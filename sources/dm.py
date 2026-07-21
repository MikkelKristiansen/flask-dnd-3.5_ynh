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

from flask import Blueprint, abort, redirect, render_template, request, url_for
from markupsafe import Markup, escape

import bestiary
import character as char_module
import db
import dm_board
import dm_media
import monster_tokens
import dm_party
import dm_scene
import dm_session as ds
import dm_setups
import catalog
import doors as doors_module
import magic_abilities
import magic_gear
import magic_items as magic_items_module
import traps as traps_module

# Entity-typer der slås op som statblok (klikbare → inspector).
# _STAT_TYPES = væsener (→ bestiary.monster_view); _TRAP_TYPE = fælder (→ traps.trap_view).
# _DOOR_TYPES = dør-stavevarianter (dansk/ascii) → kanonisk "door" (db.get_door).
# Øvrige dokument-lokale typer (kort/brev/gaade) håndteres som handouts (lightbox).
_STAT_TYPES = {"monster", "npc"}
_TRAP_TYPE = "faelde"
_DOOR_TYPES = {"dør", "door"}
_MAGIC_TYPE = "magisk"                                # @magisk[base+bonus] → magic_gear-overlay
_ITEM_TYPE = "genstand"                               # @genstand[id] → magic_items-katalog

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
        elif typ in _STAT_TYPES or typ in (_TRAP_TYPE, _MAGIC_TYPE, _ITEM_TYPE):  # monster/npc/fælde/magisk/genstand → statblok-fetch
            out.append(Markup(
                '<a class="ent ent-{} ent-stat" data-stat="{}/{}">{}</a>').format(
                    typ, typ, ident, ident))
        elif typ in _DOOR_TYPES:                          # dør/door → statblok-fetch (kanonisk "door")
            out.append(Markup(
                '<a class="ent ent-{} ent-stat" data-stat="door/{}">{}</a>').format(
                    typ, ident, ident))
        else:
            out.append(Markup('<span class="ent ent-{}">{}</span>').format(
                typ, ident))
        last = m.end()
    out.append(escape((text or "")[last:]))
    return Markup("").join(out)


@dm_bp.app_template_filter("has_combatants")
def _has_combatants_filter(room) -> bool:
    """Template-filter: har rummet et væsen (monster/npc) at kæmpe mod? Gater
    'Start kamp fra dette rum'-knappen, så fælde-kun-rum ikke får den."""
    return dm_scene.room_has_combatants(room)


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
                           media=dm_media.list_media(ds.adventure_dir(adventure)),
                           entity_api=url_for("dm.entity_ids"),
                           saved=request.args.get("saved"))


# ── Encounter-tracker (R3): delte helpers her; ruterne i dm_routes_encounter.py ─
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
    # Gate 'Start kamp fra denne scene': kun hvis den aktive scene har væsener/
    # fælder/kort (ikke en ren fortælle-scene). Springes over under aktiv kamp
    # (så vi ikke re-parser eventyret ved hver tracker-swap).
    scene_relevant = False
    if not enc.get("active"):
        adv = ds.load_adventure(session.adventure)
        scene = next((s for s in adv.scenes if s.id == session.active_scene),
                     adv.scenes[0] if adv.scenes else None)
        scene_relevant = dm_scene.scene_is_combat_relevant(scene)
    return render_template("dm/_tracker.html", enc=enc, ordered=ordered,
                           current_id=current_id, slug=session.slug,
                           statblocks=statblocks, scene_relevant=scene_relevant,
                           all_conditions=db.get_all_conditions())


def _load_or_404(slug):
    try:
        return ds.load_session(slug)
    except FileNotFoundError:
        abort(404)


@dm_bp.route("/api/party/<slug>", methods=["POST"])
def edit_party(slug):
    """Rediger en kørende sessions party (Lag 2): tilføj/fjern en spiller. Det er
    HER 'hvem er med' bor — ændringen slår igennem i party-panelet og i næste
    'Start kamp' (opstillings-brættet placerer kun positioner)."""
    session = _load_or_404(slug)
    action = request.form.get("action")
    pc = (request.form.get("pc") or "").strip()
    party = list(session.party)
    if action == "add" and pc in dm_scene._character_slugs() and pc not in party:
        party.append(pc)
    elif action == "remove" and pc in party:
        party.remove(pc)
    session.party = party
    ds.save_session(session)
    return redirect(url_for("dm.play", slug=slug))


def _parse_magic_ident(ident: str) -> tuple[str | None, int | None, list[str]]:
    """'longsword+1' → ('longsword', 1, []). Med abilities (komma-separeret efter
    base+bonus): 'longsword+1,flaming,keen' → ('longsword', 1, ['flaming','keen']).
    Uden '+N'-suffiks eller ikke-tal → (None, None, []). Base-id'er kan selv have
    bindestreger (heavy-steel-shield) men aldrig '+' eller ',', så vi splitter først
    abilities fra på komma, dernæst base fra bonus på det sidste '+'."""
    head, _, tail = ident.partition(",")
    base, sep, raw = head.rpartition("+")
    if not sep or not raw.isdigit():
        return None, None, []
    abilities = [a for a in (s.strip() for s in tail.split(",")) if a] if tail else []
    return base, int(raw), abilities


def _magic_gear_view(base_id: str, bonus: int, ability_ids: list | None = None) -> dict | None:
    """Slå base-våben/-rustning op i kataloget og påfør enhancement- + ability-overlay
    (magic_gear, ren motor). Returnér visnings-dict til _magic.html, eller None hvis
    basen ikke findes / bonussen er ugyldig (magic_gear rejser ValueError). `slot`
    (weapon|armor|shield) + `pickable` giver give-loot-byggeren dens afkrydsningsliste."""
    ability_ids = ability_ids or []
    try:
        w = db.get_weapon(base_id)
        if w:
            abilities = magic_abilities.resolve(ability_ids)
            ov = magic_gear.enhance_weapon(w, bonus, abilities)
            ov["kind_label"] = "Magisk våben"
            ov["base_ref"] = f"weapons/{base_id}"
            ov["ability_ids"] = ability_ids
            ov["slot"] = "weapon"
            ov["pickable"] = magic_abilities.for_slot("weapon")
            ov["detail"] = {"dmg": w.get("dmg_m"), "crit": w.get("critical"),
                            "type": w.get("damage_type")}
            ov["price_str"] = catalog.format_cost(ov["total_cost_cp"])
            return ov
        a = db.get_armor(base_id)
        if a:
            slot = "shield" if a.get("type") == "shield" else "armor"
            abilities = magic_abilities.resolve(ability_ids)
            ov = magic_gear.enhance_armor(a, bonus, abilities)
            ov["kind_label"] = "Magisk skjold" if slot == "shield" else "Magisk rustning"
            ov["base_ref"] = f"armor/{base_id}"
            ov["ability_ids"] = ability_ids
            ov["slot"] = slot
            ov["pickable"] = magic_abilities.for_slot(slot)
            ov["price_str"] = catalog.format_cost(ov["total_cost_cp"])
            return ov
    except ValueError:
        return None
    return None


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
    if etype == "door":                                 # dør → delt dør-katalog
        row = db.get_door(ident)
        if row:
            return render_template("dm/_door.html", d=doors_module.door_view(row))
        return render_template("dm/_statblock.html", none=True, etype=etype, ident=ident)
    if etype == _MAGIC_TYPE:                            # magisk[base+bonus,abilities] → overlay
        base_id, bonus, ability_ids = _parse_magic_ident(ident)
        view = _magic_gear_view(base_id, bonus, ability_ids) if base_id else None
        if view:
            chars = [{"slug": p["slug"], "name": p["name"]}
                     for p in dm_party.party_view(dm_scene._character_slugs(), db)]
            return render_template("dm/_magic.html", it=view, bonus=bonus, chars=chars)
        return render_template("dm/_statblock.html", none=True, etype=etype, ident=ident)
    if etype == _ITEM_TYPE:                            # genstand[id] → magic_items-katalog
        row = db.get_magic_item(ident)
        if row:
            chars = [{"slug": p["slug"], "name": p["name"]}
                     for p in dm_party.party_view(dm_scene._character_slugs(), db)]
            return render_template("dm/_magic_item.html",
                                   it=magic_items_module.magic_item_view(row), chars=chars)
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


@dm_bp.route("/api/give-loot", methods=["POST"])
def api_give_loot():
    """DM lægger et magisk item i en spillers rygsæk. To slags loot deler samme vej:
    en enhancement-bygget våben/rustning (magic_gear: base+bonus+abilities) ELLER en
    færdig katalog-genstand (magic_items/<id>). Begge → append InventoryItem →
    save_character (den eksisterende inventar-save-vej)."""
    from app import _char_path
    slug = (request.form.get("char") or "").strip()
    base_ref = (request.form.get("base_ref") or "").strip()
    table = base_ref.partition("/")[0]

    if table == "magic_items":
        oid = base_ref.partition("/")[2]
        mi = db.get_magic_item(oid)
        if not mi:
            return "Ukendt magisk genstand", 404
        kwargs = {"ref": base_ref, "name": mi["name"], "state": "backpack"}
        if mi.get("spell_id") and mi.get("charges_max"):     # forbrugsvare → fulde ladninger
            kwargs["charges"] = int(mi["charges_max"])
    else:
        try:
            bonus = int(request.form.get("bonus") or "")
        except ValueError:
            return "Ugyldig bonus", 400
        oid = base_ref.partition("/")[2]
        base = (db.get_weapon(oid) if table == "weapons"
                else db.get_armor(oid) if table == "armor" else None)
        if not base:
            return "Ukendt base-genstand", 404
        # Abilities: kun dem der er gyldige for genstandens slot (våben/rustning/skjold).
        slot = "weapon" if table == "weapons" else ("shield" if base.get("type") == "shield" else "armor")
        valid = {a["id"] for a in magic_abilities.for_slot(slot)}
        ability_ids = [a for a in request.form.getlist("abilities") if a in valid]
        try:
            kwargs = magic_gear.as_inventory_item(base_ref, bonus, ability_ids)
        except ValueError:
            return "Ugyldigt magisk item", 400
        kwargs["name"] = magic_gear.magic_name(bonus, base["name"], magic_abilities.resolve(ability_ids))

    if slug not in dm_scene._character_slugs():
        return "Ukendt karakter", 404
    path = _char_path(slug)
    char = char_module.load_character(str(path))
    inventory = list(char.inventory)
    inventory.append(char_module.InventoryItem(**kwargs))
    char_module.save_character(str(path), {"inventory": inventory})
    return f"✓ {kwargs['name']} lagt i {char.name or slug}s rygsæk"


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
    # ?from=<session> → tilbage-link + session-kontekst: paletten viser da KUN
    # sessionens party (ikke alle karakterer), så man kun placerer party-medlemmer.
    back = request.args.get("from")
    session = None
    if back:
        try:
            session = ds.load_session(back)
        except FileNotFoundError:
            back = None
    return render_template(
        "dm/board.html", title=title,
        map_url=url_for("dm.media", adventure=adventure, filename=src) if src else None,
        board=dm_board.board_view(setup, adv, db, audience="dm",
                                  token_lookup=monster_tokens.token_lookup),
        palette=dm_scene._board_palette(adv, party=session.party if session else None),
        token_style=dm_board.token_style(),
        traps=[{"id": t["id"], "name": t["name"]} for t in db.get_all_traps()],
        doors=[{"id": d["id"], "name": d["name"]} for d in db.get_all_doors()],
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
        board = (dm_board.combat_board_view(setup, enc, current_id,
                                            token_lookup=monster_tokens.token_lookup) if combat
                 else dm_board.board_view(setup, adventure, db, audience="dm",
                                          token_lookup=monster_tokens.token_lookup))
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
    available_pcs = [s for s in dm_scene._character_slugs() if s not in session.party]
    board_maps, map_slug = _scene_board_maps(session, adventure)
    return render_template("dm/play.html", session=session,
                           available_pcs=available_pcs,
                           adventure=adventure, active=active, party=party,
                           adv_ref=session.adventure, map_slug=map_slug,
                           board_maps=board_maps,
                           doc_titles=dm_scene._doc_titles(adventure),
                           tracker_html=_tracker_html(session))


# Registrér udspaltede rute-grupper på dm_bp (importeres i BUNDEN, så alle delte
# helpers ovenfor er defineret når submodulet gør `from dm import …`).
import dm_routes_encounter  # noqa: E402,F401  (side-effekt: registrerer encounter-ruter)
import dm_routes_content    # noqa: E402,F401  (side-effekt: registrerer katalog/opslags-ruter)
import dm_routes_media      # noqa: E402,F401  (side-effekt: registrerer media/token-ruter)
