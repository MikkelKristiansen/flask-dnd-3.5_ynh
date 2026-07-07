"""dm_encounter — ren kamp-logik for DM-modulets encounter-tracker (R3).

Ingen Flask, ingen DB, ingen I/O, ingen tilfældighed indbygget (terningkast
injiceres, så logikken er fuldt testbar). Tilstanden (round/turn/combatants)
gemmes af dm_session; her udføres kun de rene transformationer på den.

Kerneansvar:
  • Fold en scene-roster ud til individuelle combatants MED per-instans-labels:
    flere ens monstre (2x kriger) → "Kriger A", "Kriger B" — så tracker (og
    senere grid/tokens) kan holde styr på hvem der er hvem.
  • Rul initiativ (injiceret roller) og byg tur-rækkefølgen.
  • Ryk turen frem (og runden når rækken er gennemløbet).
"""
from __future__ import annotations

import dice


def _excel_col(i: int) -> str:
    """0→A, 25→Z, 26→AA, 27→AB … (bijektiv base-26). Robust for enhver mængde
    ens monstre, ikke kun de første 26."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def build_combatants(sources: list[dict]) -> list[dict]:
    """Fold kilder ud til individuelle combatants.

    `sources`: liste af {name, count, kind, ref, init_mod, hp_max}. Én kilde =
    én type (fx {name:"Kriger", count:2, kind:"monster", ref:"kriger", …}).
    Er der MERE END ÉN af samme ref i alt (på tværs af kilder), får hver instans
    et bogstav-suffiks (Kriger A/B); er der kun én, beholder den sit rene navn.
    id er unikt inden for encounteren (ref eller ref-a/ref-b).
    """
    totals: dict[str, int] = {}
    for s in sources:
        totals[s["ref"]] = totals.get(s["ref"], 0) + int(s.get("count", 1))

    seen: dict[str, int] = {}
    out = []
    for s in sources:
        ref = s["ref"]
        for _ in range(int(s.get("count", 1))):
            idx = seen.get(ref, 0)
            seen[ref] = idx + 1
            lettered = totals[ref] > 1
            suffix = _excel_col(idx)
            out.append({
                "id": f"{ref}-{suffix.lower()}" if lettered else ref,
                "name": f"{s['name']} {suffix}" if lettered else s["name"],
                "kind": s.get("kind", "monster"),
                "ref": ref,
                "init_mod": int(s.get("init_mod", 0)),
                "initiative": None,            # sættes ved initiativ-kast
                "hp_max": s.get("hp_max"),
                "current_hp": s.get("hp_max"),
                "conditions": [],
            })
    return out


def seed_positions(combatants: list[dict], tokens: list[dict]) -> None:
    """Sæt `col`/`row` på hver combatant (in-place) fra den matchende opstillings-
    token på kortet. Binder væsen-token ↔ combatant via ref + instans-bogstav:
    en combatant med id `kriger-a` tager token'en {ref:kriger, label:A}. Er der
    intet bogstav-match (fx DM'en labelede anderledes), tildeles den næste ledige
    token af samme ref. Tokens forbruges, så to combatants aldrig deler position;
    combatants uden token får ingen position (bliver "uden for brættet").
    """
    pool: dict[str, list[dict]] = {}
    for t in tokens:
        if t.get("kind") in ("pc", "monster", "npc") and t.get("ref"):
            pool.setdefault(t["ref"], []).append(t)
    for c in combatants:
        toks = pool.get(c["ref"])
        if not toks:
            continue
        letter = c["id"][len(c["ref"]) + 1:] if c["id"].startswith(c["ref"] + "-") else ""
        tok = next((t for t in toks
                    if (t.get("label") or "").strip().lower() == letter), None) or toks[0]
        toks.remove(tok)
        c["col"], c["row"] = int(tok.get("col", 0)), int(tok.get("row", 0))


def default_roller(init_mod: int) -> int:
    """Standard-initiativkast: 1d20 + init-modifier (bruger dice.py)."""
    return dice.roll(f"1d20{init_mod:+d}")["total"]


def roll_initiative(combatants: list[dict], roller=None, only_missing: bool = False) -> None:
    """Sæt `initiative` på hver combatant (in-place). `roller(init_mod)->int`
    injiceres (default = 1d20+mod via dice.py) så det kan testes deterministisk.
    only_missing=True ruller kun for dem uden en initiativ endnu — bruges når
    spillerne selv har indtastet deres PC'ers initiativ."""
    roller = roller or default_roller
    for c in combatants:
        if only_missing and c.get("initiative") is not None:
            continue
        c["initiative"] = roller(c.get("init_mod", 0))


def turn_order(combatants: list[dict]) -> list[str]:
    """Combatant-id'er sorteret efter tur-rækkefølge: højeste initiativ først,
    derefter højeste init-modifier (SRD-tiebreak: den med bedst Dex/init går
    først), til sidst navn for en stabil, deterministisk orden."""
    ordered = sorted(
        combatants,
        key=lambda c: (-(c.get("initiative") or 0), -(c.get("init_mod") or 0), c["name"]),
    )
    return [c["id"] for c in ordered]


def advance(round_no: int, turn_index: int, n: int) -> tuple[int, int]:
    """Ryk til næste tur. Når rækken (n combatants) er gennemløbet, starter en
    ny runde forfra. Tom encounter (n=0) rører ikke tælleren."""
    if n <= 0:
        return round_no, turn_index
    if turn_index + 1 >= n:
        return round_no + 1, 0
    return round_no, turn_index + 1
