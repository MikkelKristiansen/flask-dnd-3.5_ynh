"""magic_items — visnings-helpers for magiske genstande (Del B).

db.get_magic_item leverer den rå katalog-række (modifiers afkodet). Dette modul
formaterer den til inspector-/opslags-visning: pris i gp, og en kort dansk
effekt-opsummering pr. modifier (så DM'en kan se hvad genstanden gør uden at læse
JSON). Ren formatering — ingen DB/IO ud over den række der gives ind.
"""
from __future__ import annotations

import catalog

# Kort dansk etiket pr. modifier-target (bruges i effekt-opsummeringen).
_TARGET_LABEL = {
    "str": "Styrke", "dex": "Behændighed", "con": "Kropsbygning",
    "int": "Intelligens", "wis": "Visdom", "cha": "Karisma",
    "ac": "AC", "save_all": "alle saves", "save_fort": "Fysik-save",
    "save_ref": "Refleks-save", "save_will": "Vilje-save",
    "attack": "angreb", "damage": "skade", "skill_all": "alle skills",
    "hp_temp": "midlertidig HP",
}


def _describe_modifier(m: dict) -> str:
    """'{ac, deflection, 1}' → '+1 deflection til AC'. Generisk fallback for
    ukendte targets, så nye items altid får en læsbar linje."""
    target = _TARGET_LABEL.get(m.get("target"), m.get("target") or "?")
    typ = m.get("type") or ""
    val = int(m.get("value", 0))
    sign = f"+{val}" if val >= 0 else str(val)
    typ_part = f" {typ}" if typ else ""
    return f"{sign}{typ_part} til {target}" if m.get("target") == "ac" \
        else f"{sign}{typ_part} — {target}"


def magic_item_view(row: dict) -> dict:
    """Katalog-række → visnings-dict: pris-streng + effekt-opsummering."""
    v = dict(row)
    v["price_str"] = catalog.format_cost(row.get("price_cp") or 0)
    v["effects"] = [_describe_modifier(m) for m in (row.get("modifiers") or [])]
    return v
