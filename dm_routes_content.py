"""dm_routes_content — DM-modulets katalog/opslags-ruter på dm_bp.

Udspaltet fra dm.py: de rene katalog-ruter (entity-ids til autocomplete/opslagsværk,
adventure-fri catalog-statblok, den selvstændige opslagsværk-side) + bestiarie-fanen.
Dekorerer SAMME dm_bp (fra dm) → url_for uændret; dm.py importerer modulet i bunden.

(api_statblock BLIVER i dm.py — den er adventure-scopet og filtret sammen med
entities-filteret + magic-gear-helperne dér.)
"""
from flask import abort, jsonify, render_template, request, url_for

import bestiary
import db
import dm_party
import dm_scene
import dm_session as ds
import doors as doors_module
import magic_items as magic_items_module
import specific_items as specific_items_module
import traps as traps_module
from dm import _TRAP_TYPE, dm_bp


def _loot_chars(from_session: str | None):
    """Spiller-liste til give-loot i opslagsværket, MEN kun når det er åbnet fra en
    gyldig session (?from=<slug>) — ellers er der ingen kamp-/party-kontekst og
    give-loot vises ikke. Samme liste (alle karakterer) som play-inspektøren."""
    if not from_session or not any(s["slug"] == from_session for s in ds.list_sessions()):
        return None
    return [{"slug": p["slug"], "name": p["name"]}
            for p in dm_party.party_view(dm_scene._character_slugs(), db)]


@dm_bp.route("/api/entity-ids")
def entity_ids():
    """Id+navn til editor-autocomplete (@monster/@faelde/@dør). type-param mapper
    til det delte katalog; ukendt type → tom liste. Dokument-lokale typer
    (npc/brev/kort) hentes IKKE her — de completes fra selve teksten i klienten."""
    getters = {"monster": db.get_all_monsters,
               "faelde": db.get_all_traps,
               "door": db.get_all_doors,
               "genstand": db.get_all_magic_items,
               "specifik": db.get_all_specific_items}
    g = getters.get(request.args.get("type", ""))
    if not g:
        return jsonify([])
    # cr tages med når den findes (monstre/fælder) — bruges af opslagsværkets filter/
    # visning; autocomplete ignorerer den. Døre har ingen cr → None.
    return jsonify([{"id": r["id"], "name": r.get("name") or r["id"], "cr": r.get("cr")}
                    for r in g()])


@dm_bp.route("/api/catalog-statblock/<etype>/<ident>")
def api_catalog_statblock(etype, ident):
    """Statblok for en katalog-post UDEN eventyr-kontekst (opslagsværket, begge lag).
    Rammer kun det delte katalog (db) — ingen adventure-lokale opslag."""
    if etype == _TRAP_TYPE:
        row = db.get_trap(ident)
        if row:
            return render_template("dm/_trap.html", t=traps_module.trap_view(row))
    elif etype == "door":
        row = db.get_door(ident)
        if row:
            return render_template("dm/_door.html", d=doors_module.door_view(row))
    elif etype == "genstand":
        row = db.get_magic_item(ident)
        if row:
            # Åbnet fra en session (?from=<slug>) → give-loot vises; ellers party-løst.
            return render_template("dm/_magic_item.html",
                                   it=magic_items_module.magic_item_view(row),
                                   chars=_loot_chars(request.args.get("from")))
    elif etype == "specifik":
        row = db.get_specific_item(ident)
        if row:
            return render_template("dm/_specific.html",
                                   it=specific_items_module.specific_item_view(row),
                                   chars=_loot_chars(request.args.get("from")))
    else:
        row = db.get_monster(ident)
        if row:
            return render_template("dm/_statblock.html",
                                   m=bestiary.monster_view(row), origin="Bestiar")
    return render_template("dm/_statblock.html", none=True, etype=etype, ident=ident)


@dm_bp.route("/opslag")
def opslag():
    """Selvstændigt opslagsværk: browse hele kataloget (monstre/fælder/døre/genstande).
    ?from=<session-slug> giver kamp-kontekst, så magiske genstande kan uddeles direkte
    (give-loot). Genbruger opslagsværk-panelet + JS'en fra editoren (uden indsæt)."""
    from_session = request.args.get("from") or ""
    if from_session and not any(s["slug"] == from_session for s in ds.list_sessions()):
        from_session = ""
    return render_template("dm/opslag.html", entity_api=url_for("dm.entity_ids"),
                           from_session=from_session)


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
                           traps=dm_scene._trap_entries(adv, adventure),
                           doors=dm_scene._door_entries(adv, adventure),
                           back_session=back)
