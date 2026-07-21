"""dm_board — byg bræt-visningsmodellen fra en startopstilling.

Resolver hver token til visnings-props (PC → portræt-slug + initial; monster/npc
→ navn + label + stabil farve pr. type; markør → emoji) og filtrerer efter
PUBLIKUM: audience="player" udelader hidden-tokens (fundament for et senere
player-view — vi maler os ikke i et hjørne). Ren udledning, ingen I/O.
"""
from __future__ import annotations

_MARKER_ICON = {"trap": "🪤", "door": "🚪", "treasure": "💰", "note": "📌"}
# Distinkte farver pr. monster/npc-type (skive-tokens uden art).
_COLORS = ["#b5432c", "#4a7a4a", "#3d6b8a", "#8a6d3d", "#6b4a8a", "#3d8a86", "#8a3d5f"]
# Ledsagere (companion/familiar/mount) får én fast grøn — samme som trackerens
# ledsager-markering (.cbt-comp) — så allierede væsener er ens at scanne på brættet.
_COMPANION_KINDS = ("companion", "familiar", "mount")
_COMPANION_COLOR = "#6fae7a"


def token_style() -> dict:
    """Farve-paletten + markør-ikonerne, så browser-editoren kan farve/ikone nye
    tokens EFTER samme tabeller som server-renderet (én sandhedskilde)."""
    return {"colors": list(_COLORS), "icons": dict(_MARKER_ICON)}


# Størrelse → antal grid-tern pr. side (matcher pawn-basernes fysiske footprint).
# Alt medium og mindre står på ét tern; store væsener skalerer op.
_SIZE_CELLS = {"fine": 1, "diminutive": 1, "tiny": 1, "small": 1, "medium": 1,
               "large": 2, "huge": 3, "gargantuan": 4, "colossal": 6}


def _size_cells(size) -> int:
    """Antal tern (pr. side) et væsen af denne størrelse optager. Ukendt → 1."""
    return _SIZE_CELLS.get(str(size or "medium").strip().lower(), 1)


def _creature_name(ref, adv, db):
    row = (adv.statblock(ref) if adv else None) or (db.get_monster(ref) if db else None)
    return row["name"] if row else ref


def _creature_size(ref, adv, db):
    """Størrelses-strengen for et ref (adventure-lokalt statblok → bestiar), til at
    skalere store væseners tokens i opstillingen (kamp-brættet bruger combatantens
    egen medbragte size i stedet)."""
    row = (adv.statblock(ref) if adv else None) or (db.get_monster(ref) if db else None)
    return row.get("size") if row else None


def board_view(setup: dict, adv=None, db=None, audience: str = "dm",
               token_lookup=None) -> dict:
    """Bræt-model: {grid, tokens:[…]}. audience='player' skjuler hidden-tokens.

    token_lookup(ref)->slug|None injiceres af kalderen (monster_tokens.token_lookup)
    og afgør om et monster tegnes som billed-standee eller bogstav-skive — så
    view-modellen selv forbliver I/O-fri."""
    color_of, palette_i = {}, 0
    tokens = []
    for t in setup.get("tokens", []):
        hidden = bool(t.get("hidden"))
        if audience == "player" and hidden:
            continue
        kind = t.get("kind", "note")
        ref = t.get("ref", "")
        # ref/note bæres med ud (ud over de rene visnings-props) så editoren kan
        # redigere og gemme dem igen uden et separat opslag.
        tv = {"kind": kind, "col": int(t.get("col", 0)), "row": int(t.get("row", 0)),
              "hidden": hidden, "ref": ref, "note": t.get("note", "")}
        if kind == "pc":
            tv["portrait"] = ref                       # /portrait/<slug>, m/ fallback
            tv["label"] = (t.get("label") or ref[:2]).upper()
            tv["name"] = t.get("label") or ref
        elif kind in ("monster", "npc"):
            name = _creature_name(ref, adv, db)
            lbl = t.get("label", "")
            tv["cells"] = _size_cells(_creature_size(ref, adv, db))
            slug = token_lookup(ref) if token_lookup else None
            if slug:
                tv["token"] = slug                     # → billed-standee
            else:
                if ref not in color_of:
                    color_of[ref] = _COLORS[palette_i % len(_COLORS)]
                    palette_i += 1
                tv["color"] = color_of[ref]            # → bogstav-skive (som hidtil)
            tv["label"] = (lbl or name[:1]).upper()
            tv["name"] = f"{name} {lbl}".strip()
        else:                                          # markør
            tv["icon"] = _MARKER_ICON.get(kind, "📌")
            tv["name"] = t.get("note") or t.get("label") or kind
        tokens.append(tv)
    return {"grid": dict(setup.get("grid") or {}), "tokens": tokens}


def _marker_token(t: dict) -> dict:
    kind = t.get("kind", "note")
    return {"kind": kind, "col": int(t.get("col", 0)), "row": int(t.get("row", 0)),
            "hidden": bool(t.get("hidden")), "icon": _MARKER_ICON.get(kind, "📌"),
            "ref": t.get("ref", ""), "note": t.get("note", ""),
            "name": t.get("note") or t.get("label") or kind}


def _instance_letter(c: dict) -> str:
    """Bogstav-etiket for en combatant-skive: 'A' fra id 'kriger-a', ellers navnets
    forbogstav (enlig instans)."""
    ref, cid = c.get("ref", ""), c.get("id", "")
    if ref and cid.startswith(ref + "-"):
        return cid[len(ref) + 1:].upper()
    return (c.get("name") or ref)[:1].upper()


def combat_board_view(setup: dict, encounter: dict, current_id: str | None = None,
                      token_lookup=None) -> dict:
    """Kamp-bræt: markører fra den forfattede opstilling + væsener fra encounterens
    combatants på deres LIVE positioner (col/row sat ved seed/flyt), beriget med
    HP, død-flag og aktiv-tur-markering. Combatants uden position udelades (de
    står 'uden for brættet' men er stadig i trackeren). Grid arves fra opstillingen
    (samme kalibrering editoren brugte). Genbruger _board.html via samme token-form
    som board_view — bare med ekstra kamp-felter (cid/hp/active/dead)."""
    tokens = [_marker_token(t) for t in setup.get("tokens", [])
              if t.get("kind") not in ("pc", "monster", "npc")]
    # Dør-markører der spores (object_hp) får en HP-badge på brættet (genbruger
    # .tok-hp-badgen). Nøglen SKAL matche dm_routes_encounter._door_hp_key
    # (ref:col:row). Kun døre DM'en har interageret med har en entry → badge dér.
    object_hp = encounter.get("object_hp") or {}
    for t in tokens:
        if t["kind"] == "door":
            entry = object_hp.get(f"{t['ref']}:{t['col']}:{t['row']}")
            if entry:
                cur, mx = entry.get("current"), entry.get("max")
                t["hp"] = f"{cur}/{mx}" if mx is not None else str(cur)
                t["dead"] = cur is not None and cur <= 0     # 0 HP → smadret-markering
    color_of, palette_i = {}, 0
    for c in encounter.get("combatants", []):
        if c.get("col") is None or c.get("row") is None:
            continue
        kind, ref = c.get("kind", "monster"), c.get("ref", "")
        cur, hp_max = c.get("current_hp"), c.get("hp_max")
        tv = {"kind": kind, "col": int(c["col"]), "row": int(c["row"]),
              "cid": c["id"], "name": c.get("name") or ref,
              "hp": ("" if cur is None else
                     f"{cur}/{hp_max}" if hp_max is not None else str(cur)),
              "dead": cur is not None and cur <= 0,
              "active": c["id"] == current_id}
        if kind == "pc":
            tv["portrait"] = ref
            tv["label"] = (c.get("name") or ref)[:2].upper()
        else:
            # Væsen-token (monster/npc/ledsager): billed-standee hvis der findes et
            # billede, ellers bogstav-skive. Størrelse skalerer store væsener.
            tv["cells"] = _size_cells(c.get("size"))
            tv["label"] = _instance_letter(c)
            is_comp = kind in _COMPANION_KINDS
            slug = token_lookup(ref) if token_lookup else None
            if slug:
                tv["token"] = slug
                if is_comp:
                    tv["base"] = _COMPANION_COLOR      # grøn fod = allieret standee
            elif is_comp:
                tv["color"] = _COMPANION_COLOR         # grøn skive (som hidtil)
            else:
                if ref not in color_of:
                    color_of[ref] = _COLORS[palette_i % len(_COLORS)]
                    palette_i += 1
                tv["color"] = color_of[ref]
        tokens.append(tv)
    return {"grid": dict(setup.get("grid") or {}), "tokens": tokens}
