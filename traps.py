"""traps — visningsmodel for en fælde-statblok (SRD v3.5).

Parallelt med bestiary.monster_view: tag en rå `traps`-række og form den til en
stabil dict til `_trap.html`-inspectoren. En fælde er TRYKT (statisk) — der er
intet at beregne, så view'et er tyndt: det afkobler blot templaten fra db-
kolonnerne og giver ét sted at lægge afledt visning senere, hvis behovet opstår.
"""
from __future__ import annotations

_FIELDS = ("cr", "trap_type", "trigger", "reset", "attack", "save", "effect",
           "search_dc", "disable_dc", "price", "note", "source_note")


def trap_view(row: dict) -> dict:
    """Rå fælde-række → visnings-dict. Navn falder tilbage på id; øvrige felter
    bæres uændret (kan være None → templaten udelader dem)."""
    view = {"id": row.get("id"), "name": row.get("name") or row.get("id")}
    for f in _FIELDS:
        view[f] = row.get(f)
    return view
