"""doors — visningsmodel for en dør-statblok (SRD v3.5).

Parallelt med traps.trap_view: tag en rå `doors`-række og form den til en
stabil dict til `_door.html`-inspectoren. En dør er TRYKT (statisk) — der er
intet at beregne, så view'et er tyndt: det afkobler blot templaten fra db-
kolonnerne og giver ét sted at lægge afledt visning senere, hvis behovet opstår.
"""
from __future__ import annotations

_FIELDS = ("material", "thickness", "hardness", "hp", "break_dc",
           "open_lock_dc", "search_dc", "note", "source_note")


def door_view(row: dict) -> dict:
    """Rå dør-række → visnings-dict. Navn falder tilbage på id; øvrige felter
    bæres uændret (kan være None → templaten udelader dem)."""
    view = {"id": row.get("id"), "name": row.get("name") or row.get("id")}
    for f in _FIELDS:
        view[f] = row.get(f)
    return view
