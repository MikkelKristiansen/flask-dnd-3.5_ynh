"""magic_abilities — data-adgang for special-ability-kataloget (data/magic_abilities.yaml).

Ét ansvar: indlæse ability-kataloget og slå entries op. Holder I/O adskilt fra den
RENE prissætnings-/navne-motor i magic_gear (som får allerede-opslåede ability-dicts
som argument — præcis som den får en våben-dict). Samme adskillelse som catalog.py
(I/O) vs. magic_gear.py (ren logik).

En ability-entry: {id, name, slots:[weapon|armor|shield], price:{type:bonus|flat,
value}, note, source}.
"""
from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

_DATA = Path(__file__).parent / "data" / "magic_abilities.yaml"


def _load() -> list[dict]:
    yaml = YAML(typ="safe")
    return list(yaml.load(_DATA) or [])


# Indlæses én gang ved import (kilden til sandheden); nøglet på id for hurtigt opslag.
_ALL: list[dict] = _load()
_BY_ID: dict[str, dict] = {a["id"]: a for a in _ALL}


def get(ability_id: str) -> dict | None:
    """Ability-entry for id'et, eller None hvis ukendt."""
    return _BY_ID.get(ability_id)


def resolve(ids) -> list[dict]:
    """Slå en liste af ability-id'er op → liste af entries (ukendte id'er droppes,
    rækkefølge bevaret)."""
    return [_BY_ID[i] for i in (ids or []) if i in _BY_ID]


def for_slot(slot: str) -> list[dict]:
    """Alle abilities der kan sidde på en given slot (weapon|armor|shield)."""
    return [a for a in _ALL if slot in (a.get("slots") or [])]
