"""DM-modul: ren udledning af view-modeller for DM-play — adventure+session →
data, ingen Flask/HTML."""
import bestiary
import db
import dm_party
import dm_rolls
import dm_session as ds
import dm_setups
import traps as traps_module
import character as char_module
from paths import CHARACTERS_DIR

# Entity-typer der slås op som statblok (bruges af _bestiary_entries til at
# filtrere roster-poster ned til væsener — samme sæt som dm.py's filter).
_STAT_TYPES = {"monster", "npc"}
_TRAP_TYPE = "faelde"


def _character_slugs() -> list[str]:
    if not CHARACTERS_DIR.exists():
        return []
    return sorted(p.stem for p in CHARACTERS_DIR.glob("*.yaml"))


def _doc_titles(adventure) -> dict:
    """{"type:id": titel} for eventyrets dokumenter — fodrer entities-filteret."""
    return {f"{d.type}:{d.id}": d.title for d in adventure.documents.values()}


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


def _room_rosters(room):
    """Alle roster-poster i ét rum (kun rummets eget, ikke søskende-rum)."""
    return [e for b in getattr(room, "blocks", [])
            if getattr(b, "kind", None) == "roster" for e in b.entries]


def _find_room(scene, room_id):
    """Find rummet med `room_id` i scenen (None hvis det ikke findes)."""
    for b in getattr(scene, "blocks", []):
        if getattr(b, "kind", None) == "room" and b.id == room_id:
            return b
    return None


def _monster_source(ref, adv):
    """Resolv et roster-id til combatant-kildedata (navn/init/hp) via adventure-
    lokalt statblok → bestiar → fallback (ukendt = rå id, 0 init, ingen hp)."""
    stats = adv.statblock(ref) or db.get_monster(ref)
    if stats:
        v = bestiary.monster_view(stats)
        return {"name": v["name"], "init_mod": v["init"], "hp_max": v["hp_max"],
                "kind": "monster"}
    return {"name": ref, "init_mod": 0, "hp_max": None, "kind": "monster"}


def _encounter_sources(session, adv, room_id=None):
    """Byg combatant-kilder for den aktive scene: monstre fra rosteret + party-PC'er
    + PC'ernes ledsagere (animal companion / familiar / mount). `room_id` sat →
    kun DET rums monstre (rum-scopet kamp); party/ledsagere er altid med."""
    scene = next((s for s in adv.scenes if s.id == session.active_scene),
                 adv.scenes[0] if adv.scenes else None)
    sources = []
    if scene:
        monster_entries = (_room_rosters(_find_room(scene, room_id))
                           if room_id else _scene_rosters(scene))
        for e in monster_entries:
            src = _monster_source(e.id, adv)
            sources.append({"ref": e.id, "count": e.count, **src})
    for pc in dm_party.party_view(session.party, db):
        if pc.get("broken"):
            continue
        sources.append({"ref": pc["slug"], "count": 1, "name": pc["name"],
                        "kind": "pc", "init_mod": pc["init"], "hp_max": pc["hp_max"]})
    # Ledsagere er egne combatants (egen initiativ/HP) — auto-rulles som monstre.
    # `owner` bæres med, så brættet kan stille ledsageren op ved siden af sin PC.
    for comp in dm_party.party_companions(session.party, db):
        sources.append({"ref": comp["ref"], "count": 1, "name": comp["name"],
                        "kind": comp["kind"], "init_mod": comp["init_mod"],
                        "hp_max": comp["hp_max"], "owner": comp["owner"]})
    return sources


def _encounter_statblocks(session, ordered):
    """To ting i ét gennemløb (deler statblok-opslaget, så eventyret kun loades én gang):

    1. Returnér statblokke pr. DISTINKT monstertype (Goblin A/B deler ét reference-
       kort) i tur-rækkefølge, så DM'en har monster-stats permanent foran sig.
    2. Hæft `rolls` PR. INSTANS på hver monster-combatant (in-place) — de klikbare
       til-hit/skade/save-udtryk med combatantens aktive conditions foldet ind
       (dm_rolls). Så Goblin A (shaken) ruller lavere end Goblin B.

    Reference-data resolves live (adventure-lokalt → bestiar), ikke gemt i sessionen.
    PC'er udelades (de står i party-panelet og ruller på egne ark)."""
    try:
        adv = ds.load_adventure(session.adventure)
    except FileNotFoundError:
        adv = None
    views: dict[str, dict] = {}                 # ref → monster_view (delt opslag)
    out, seen = [], set()
    for c in ordered:
        if c["kind"] == "pc":
            continue
        ref = c["ref"]
        if ref not in views:
            row = (adv.statblock(ref) if adv else None) or db.get_monster(ref)
            views[ref] = bestiary.monster_view(row) if row else None
        m = views[ref]
        if not m:
            continue
        c["rolls"] = dm_rolls.combatant_rolls(m, c.get("conditions") or [], db)
        if ref not in seen:                     # ét reference-kort pr. type
            seen.add(ref)
            out.append(m)
    return out


def _active_map_slug(adv, session, room_id=None):
    """Kort-slug for sessionens aktive scene (første @kort-embed), ellers None.
    `room_id` sat → rummets EGET @kort-embed i stedet (INGEN fallback til
    scenens kort — scenekortet er hele dungeonen; et rum uden eget kort får
    bare intet bræt)."""
    scene = next((s for s in adv.scenes if s.id == session.active_scene),
                 adv.scenes[0] if adv.scenes else None)
    if room_id:
        room = _find_room(scene, room_id) if scene else None
        for b in (room.blocks if room else []):
            if getattr(b, "kind", None) == "embed" and b.entity.type == "kort":
                return b.entity.id
        return None
    for b in (scene.blocks if scene else []):
        if getattr(b, "kind", None) == "embed" and b.entity.type == "kort":
            return b.entity.id
    return None


def _map_src(adv, map_slug):
    """Billed-src for et kort (fra dets '## Kort:'-def i eventyret)."""
    doc = adv.documents.get(("kort", map_slug))
    if not doc:
        return None, map_slug
    img = next((b for b in doc.blocks if getattr(b, "kind", None) == "image"), None)
    return (img.src if img else None), doc.title


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


def _bestiary_entries(adv):
    """Statblokke for alle unikke monstre/NPC'er i eventyrets scene-rosters.

    Samme opslag som _board_palette (adventure-lokalt statblok → delt bestiar),
    men resolvet til det fulde monster_view + antal forekomster på tværs af
    scener. En uopslåelig ref markeres `missing`, så DM'en ser hullet frem for
    en tavs udeladelse. Sorteret efter navn."""
    order, agg = [], {}
    for scene in adv.scenes:
        for e in _scene_rosters(scene):
            if e.type not in _STAT_TYPES:
                continue
            key = (e.type, e.id)
            if key not in agg:
                order.append(key)
                agg[key] = {"type": e.type, "id": e.id, "count": 0}
            agg[key]["count"] += int(getattr(e, "count", 1) or 1)
    entries = []
    for key in order:
        info = agg[key]
        local = adv.statblock(info["id"])
        row = local or db.get_monster(info["id"])
        if row:
            entries.append({"m": bestiary.monster_view(row),
                            "origin": "Eventyr" if local else "Bestiar",
                            "count": info["count"]})
        else:
            entries.append({"missing": True, "etype": info["type"],
                            "ident": info["id"], "count": info["count"]})
    entries.sort(key=lambda x: (x.get("m", {}).get("name") or x.get("ident") or "").lower())
    return entries


def _walk_blocks(blocks):
    """Alle blokke i en blok-liste, inkl. dem inde i rum (ét niveau ned)."""
    for b in blocks or []:
        yield b
        if getattr(b, "kind", None) == "room":
            yield from getattr(b, "blocks", [])


def _trap_entries(adv, adv_ref):
    """Fælde-statblokke for alle fælder eventyret bruger, så DM'en kan browse dem
    i bestiarie-fanen ligesom monstre. @faelde[id] kan optræde to steder i teksten
    — som roster-post i et rums '**Fælder:**'-linje, eller inline i prosa/oplæsning
    — og begge samles her, udvidet med ref-bundne trap-markører (kind=trap) på
    eventyrets kort-opstillinger. En uopslåelig ref markeres `missing`, så DM'en
    ser hullet frem for en tavs udeladelse. Tallet er antal forekomster.
    Sorteret efter navn."""
    order, count = [], {}

    def bump(ident, n=1):
        ident = (ident or "").strip()
        if not ident:
            return
        if ident not in count:
            order.append(ident)
            count[ident] = 0
        count[ident] += n

    for scene in adv.scenes:
        for b in _walk_blocks(scene.blocks):
            kind = getattr(b, "kind", None)
            if kind == "roster":
                for e in b.entries:
                    if e.type == _TRAP_TYPE:
                        bump(e.id, int(getattr(e, "count", 1) or 1))
            elif kind in ("prose", "readaloud"):
                for e in getattr(b, "entities", []):
                    if e.type == _TRAP_TYPE:
                        bump(e.id)
            elif kind == "embed" and b.entity.type == _TRAP_TYPE:
                bump(b.entity.id)

    for t in dm_setups.all_tokens(adv_ref):
        if t.get("kind") == "trap" and t.get("ref"):
            bump(t["ref"])

    entries = []
    for ident in order:
        row = db.get_trap(ident)
        if row:
            entries.append({"t": traps_module.trap_view(row), "count": count[ident]})
        else:
            entries.append({"missing": True, "ident": ident, "count": count[ident]})
    entries.sort(key=lambda x: (x.get("t", {}).get("name") or x.get("ident") or "").lower())
    return entries


def _current_combatant_id(enc):
    """Id på combatanten hvis tur det er (eller None hvis ingen aktiv kamp)."""
    order = enc.get("turn_order", [])
    if enc.get("active") and order:
        return order[min(int(enc.get("turn_index", 0)), len(order) - 1)]
    return None
