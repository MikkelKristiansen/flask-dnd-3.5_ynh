"""bestiary — visnings-model for et monster/NPC-statblok.

Ét ansvar: form en (trykt) monster-række til den dict DM-inspector-panelet viser.
Tallene er allerede færdige (trykt hybrid — se data/monsters.yaml); her udledes
KUN ability-modifiers ved visning (aldrig gemt), og felterne pakkes pænt.

Samme funktion bruges til både bestiar-monstre (db.get_monster) og adventure-
lokale statblokke (dm_parser: ## Statblok:) — begge har samme skema, og attacks/
skills/feats er allerede afkodet til lister før de når hertil.

Ingen Flask, ingen DB, ingen I/O.
"""
from __future__ import annotations

_ABILITIES = (("str", "STR"), ("dex", "DEX"), ("con", "CON"),
              ("int", "INT"), ("wis", "WIS"), ("cha", "CHA"))


def _mod_str(score) -> str:
    """Ability-modifier som fortegnstekst; '—' hvis væsenet ingen score har (fx
    udøde uden Con)."""
    if score is None:
        return "—"
    return f"{(int(score) - 10) // 2:+d}"


def monster_view(row: dict) -> dict:
    """Byg inspector-visningen for ét monster. `row` = en monsters-række (JSON-
    lister allerede afkodet) eller et adventure-lokalt statblok med samme felter."""
    return {
        "id": row.get("id"),
        "name": row.get("name") or row.get("id"),
        "size": row.get("size"),
        "type": row.get("type"),
        "cr": row.get("cr"),
        "alignment": row.get("alignment"),
        "hd": row.get("hd"),
        "hp_max": row.get("hp_max"),
        "ac": {"ac": row.get("ac"), "touch": row.get("ac_touch"),
               "flat_footed": row.get("ac_flat"), "note": row.get("ac_note")},
        "init": row.get("init") or 0,
        "speed": row.get("speed"),
        "bab": row.get("bab") or 0,
        "grapple": row.get("grapple"),
        "abilities": [{"key": k, "label": lbl, "score": row.get(k),
                       "mod": _mod_str(row.get(k))} for k, lbl in _ABILITIES],
        "saves": {"fort": row.get("save_fort") or 0,
                  "ref": row.get("save_ref") or 0,
                  "will": row.get("save_will") or 0},
        "attacks": row.get("attacks") or [],
        "full_attack": row.get("full_attack"),
        "special_attacks": row.get("special_attacks"),
        "special_qualities": row.get("special_qualities"),
        "skills": row.get("skills") or [],
        "feats": row.get("feats") or [],
        "source_note": row.get("source_note"),
    }
