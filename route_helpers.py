"""Små hjælpefunktioner delt af flere routes_*.py-blueprints.

Ligger adskilt fra app.py for at undgå cirkulær import (blueprint-modulerne
importerer herfra, app.py importerer blueprint-modulerne).
"""


def _find_summon(summons: list, level: int, index: int) -> dict | None:
    """Find summon-ref'en for SNA-slot'et (spell_level, spell_index) — eller None."""
    for s in summons:
        if s.get("spell_level") == level and s.get("spell_index") == index:
            return s
    return None
