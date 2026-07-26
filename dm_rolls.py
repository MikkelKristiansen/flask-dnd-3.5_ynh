"""dm_rolls — fold aktive conditions ind i én monster-combatants terningkast.

Ét ansvar: tag et (trykt) monster-statblok + combatantens aktive condition-id'er
og producér de FÆRDIGE rul-udtryk (til-hit / skade / saves) som kamp-konsollen
gør klikbare — med condition-straffene allerede lagt oveni.

Alt tungt arbejde genbruges fra spillersidens effekt-motor:
  * conditions → flad modifier-liste via ``effects.collect_active_effects``
    (samme katalog spillerne bruger; conditions bor i effects-tabellen som
    kind: condition med targets attack/damage/save_all/str/dex/…).
  * stacking + melee/ranged-scoping via ``effects.resolve_target``.

Den ENESTE ekstra logik her er en oversættelse der er nødvendig FORDI monstre er
en "trykt hybrid": deres til-hit/skade/saves er færdige tal, ikke udregnet fra
ability-scores. En condition der sænker Str/Dex/Con/Wis (fatigued, exhausted …)
kaskaderer derfor ikke af sig selv — vi omsætter ability-straffen til det tilsvarende
modifier-skift via monsterets egne scores og lægger det på det trykte tal.

Ingen Flask, ingen tilfældighed (kun udtryk bygges — dice.py ruller senere).
"""
from __future__ import annotations

import re

import effects

# Targets der påvirker de tal en DM RULLER for monsteret (til-hit/skade/saves).
# Bruges kun til at afgøre om en aktiv condition faktisk ændrede noget (så UI'en
# kan markere "modificeret"); ac/init/skill_all foldes ikke ind her.
_COMBAT_TARGETS = {
    "attack", "attack_melee", "attack_ranged",
    "damage", "damage_melee", "damage_ranged",
    "save_all", "save_fort", "save_ref", "save_will",
    "str", "dex", "con", "wis",
}


def _ability_mod(score: int) -> int:
    """3.5 ability-modifier. Score klampes til ≥0 (som effekt-motoren)."""
    return (max(0, score) - 10) // 2


def _mod_delta(score, penalty: int) -> int:
    """Skift i ability-modifier når `penalty` (≤0) lægges til en score.
    fx Str 15 (+2) − 2 = Str 13 (+1) → delta −1. None-score (fx udød uden Con) → 0."""
    if score is None or not penalty:
        return 0
    return _ability_mod(int(score) + penalty) - _ability_mod(int(score))


def _is_ranged(notes: str) -> bool:
    """Afstandsangreb ud fra våben-noten (data bruger 'kastet'/'afstand'; alt
    andet, inkl. 'nærkamp' og tom note, regnes som nærkamp)."""
    n = (notes or "").lower()
    return "kast" in n or "afstand" in n or "ranged" in n


def _fold_damage(expr: str, delta: int) -> str:
    """Læg `delta` til modifier-leddet i et skade-udtryk (NdX±M). Bevarer terningen;
    '1d6+1' med −2 → '1d6-1', og et led der går i nul udelades ('1d6')."""
    m = re.fullmatch(r"(\d*d\d+)([+-]\d+)?", (expr or "").replace(" ", "").lower())
    if not m:
        return expr                                   # ikke-standard → rør ikke
    mod = int(m.group(2) or 0) + delta
    return m.group(1) + (f"{mod:+d}" if mod else "")


def _crit_mult(crit: str) -> int:
    """Multiplikator fra crit-feltet: 'x3'→3, 'x4'→4, ellers 2 (trusselsområder
    som '18-20' er ×2)."""
    c = (crit or "").lower()
    return 3 if "x3" in c else (4 if "x4" in c else 2)


def combatant_rolls(m: dict, condition_ids: list[str], db) -> dict:
    """Byg klikbare rul-udtryk for én combatant ud fra dens statblok-view `m`
    (bestiary.monster_view) + aktive `condition_ids`.

    Returnerer:
        {"attacks": [{name, hit_bonus, hit_expr, dmg_expr, crit_mult, crit_range}],
         "saves": {"fort"|"ref"|"will": {"val": int, "expr": "1d20±N"}},
         "modified": bool,          # ændrede en aktiv condition tallene?
         "sources": [condition-navne der bidrog]}
    """
    mods, sources = effects.collect_active_effects([], condition_ids or [], db)

    # Direkte combat-targets (stacker som utypede straffe; melee/ranged deler alias).
    d_atk_melee = effects.resolve_target(mods, "attack", "attack_melee")
    d_atk_ranged = effects.resolve_target(mods, "attack", "attack_ranged")
    d_dmg_melee = effects.resolve_target(mods, "damage", "damage_melee")
    d_dmg_ranged = effects.resolve_target(mods, "damage", "damage_ranged")
    s_fort = effects.resolve_target(mods, "save_all", "save_fort")
    s_ref = effects.resolve_target(mods, "save_all", "save_ref")
    s_will = effects.resolve_target(mods, "save_all", "save_will")

    # Ability-straffe → modifier-skift via monsterets EGNE scores (trykt hybrid).
    scores = {a["key"]: a.get("score") for a in m.get("abilities", [])}
    str_d = _mod_delta(scores.get("str"), effects.resolve_target(mods, "str"))
    dex_d = _mod_delta(scores.get("dex"), effects.resolve_target(mods, "dex"))
    con_d = _mod_delta(scores.get("con"), effects.resolve_target(mods, "con"))
    wis_d = _mod_delta(scores.get("wis"), effects.resolve_target(mods, "wis"))

    attacks = []
    for at in m.get("attacks", []):
        try:
            base = int(str(at.get("bonus", "0")).replace("+", "") or 0)
        except ValueError:
            base = 0
        if _is_ranged(at.get("notes", "")):
            hit = base + d_atk_ranged + dex_d
            dmg_delta = d_dmg_ranged                  # ranged: normalt ingen Str-til-skade
        else:
            hit = base + d_atk_melee + str_d
            dmg_delta = d_dmg_melee + str_d
        dmg = at.get("damage")
        attacks.append({
            "name": at.get("name", "Angreb"),
            "hit_bonus": hit,
            "hit_expr": f"1d20{hit:+d}",
            "dmg_expr": _fold_damage(dmg, dmg_delta) if dmg else "",
            "crit_mult": _crit_mult(at["crit"]) if at.get("crit") else None,
            "crit_range": at.get("crit"),
        })

    sv = m.get("saves", {})
    saves = {
        "fort": _save(sv.get("fort", 0), s_fort + con_d),
        "ref": _save(sv.get("ref", 0), s_ref + dex_d),
        "will": _save(sv.get("will", 0), s_will + wis_d),
    }

    # "Modificeret" = mindst én aktiv condition rørte et combat-tal (ikke bare AC/init).
    applied = [s["name"] for s in sources
               if any(md.get("target") in _COMBAT_TARGETS for md in s.get("modifiers", []))]
    return {"attacks": attacks, "saves": saves,
            "modified": bool(applied), "sources": applied}


def _save(base, delta: int) -> dict:
    total = int(base) + delta
    return {"val": total, "expr": f"1d20{total:+d}"}
