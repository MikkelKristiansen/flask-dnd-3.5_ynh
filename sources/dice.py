"""Dice roller — no I/O, no external dependencies."""
import re
import random


def roll(expression: str) -> dict:
    """Parse and roll a dice expression like '1d20+4', '3d6', 'd%'.

    Også en ren tal-sum uden terning ('1', '0+150') — nogle healing-formler (Cure
    Minor Wounds: fast 1; Heal: 10/niveau, intet terning-led) er deterministiske,
    ikke tilfældige. Returneres med rolls=[] så UI'en ved der ikke var noget at rulle.

    Returns:
        {"rolls": list[int], "modifier": int, "total": int}
    """
    expr = expression.strip().lower().replace(" ", "")

    # Handle d% as d100
    expr = expr.replace("d%", "d100")

    if "d" not in expr:
        if not re.fullmatch(r"[+-]?\d+([+-]\d+)*", expr):
            raise ValueError(f"Invalid dice expression: {expression!r}")
        total = sum(int(t) for t in re.findall(r"[+-]?\d+", expr))
        return {"rolls": [], "modifier": total, "total": total}

    # Pattern: optional count, 'd', sides, optional modifier
    match = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", expr)
    if not match:
        raise ValueError(f"Invalid dice expression: {expression!r}")

    count_str, sides_str, mod_str = match.groups()
    count = int(count_str) if count_str else 1
    sides = int(sides_str)
    modifier = int(mod_str) if mod_str else 0

    if count < 1:
        raise ValueError("Must roll at least 1 die")
    if sides < 1:
        raise ValueError("Die must have at least 1 side")

    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier

    return {"rolls": rolls, "modifier": modifier, "total": total}
