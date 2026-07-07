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


def token_style() -> dict:
    """Farve-paletten + markør-ikonerne, så browser-editoren kan farve/ikone nye
    tokens EFTER samme tabeller som server-renderet (én sandhedskilde)."""
    return {"colors": list(_COLORS), "icons": dict(_MARKER_ICON)}


def _creature_name(ref, adv, db):
    row = (adv.statblock(ref) if adv else None) or (db.get_monster(ref) if db else None)
    return row["name"] if row else ref


def board_view(setup: dict, adv=None, db=None, audience: str = "dm") -> dict:
    """Bræt-model: {grid, tokens:[…]}. audience='player' skjuler hidden-tokens."""
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
            if ref not in color_of:
                color_of[ref] = _COLORS[palette_i % len(_COLORS)]
                palette_i += 1
            tv["color"] = color_of[ref]
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
            "name": t.get("note") or t.get("label") or kind}


def _instance_letter(c: dict) -> str:
    """Bogstav-etiket for en combatant-skive: 'A' fra id 'kriger-a', ellers navnets
    forbogstav (enlig instans)."""
    ref, cid = c.get("ref", ""), c.get("id", "")
    if ref and cid.startswith(ref + "-"):
        return cid[len(ref) + 1:].upper()
    return (c.get("name") or ref)[:1].upper()


def combat_board_view(setup: dict, encounter: dict, current_id: str | None = None) -> dict:
    """Kamp-bræt: markører fra den forfattede opstilling + væsener fra encounterens
    combatants på deres LIVE positioner (col/row sat ved seed/flyt), beriget med
    HP, død-flag og aktiv-tur-markering. Combatants uden position udelades (de
    står 'uden for brættet' men er stadig i trackeren). Grid arves fra opstillingen
    (samme kalibrering editoren brugte). Genbruger _board.html via samme token-form
    som board_view — bare med ekstra kamp-felter (cid/hp/active/dead)."""
    tokens = [_marker_token(t) for t in setup.get("tokens", [])
              if t.get("kind") not in ("pc", "monster", "npc")]
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
            if ref not in color_of:
                color_of[ref] = _COLORS[palette_i % len(_COLORS)]
                palette_i += 1
            tv["color"] = color_of[ref]
            tv["label"] = _instance_letter(c)
        tokens.append(tv)
    return {"grid": dict(setup.get("grid") or {}), "tokens": tokens}
