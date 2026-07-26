"""dm_party — kompakte PC-statblokke til DM-play-visningens sidebjælke.

Ét ansvar: oversæt en liste PC-slugs → en let "kampglans"-model pr. karakter
(HP, AC, saves, initiativ, speed, conditions). Genbruger `build_character_view`
så tallene er præcis de samme som på det fulde ark, men PLUKKER kun de felter
sidebjælken viser — hele ark-modellen (spell-kataloger, angreb, level-up …)
ryger aldrig ud i DM-templaten.

Ingen Flask, ingen HTML. En PC der ikke kan loades springes ikke over, men
markeres `broken` så DM'en ser hvem der mangler i stedet for en tavs udeladelse.
"""
from __future__ import annotations

import character as char_module
import companion as companion_module
import familiar as familiar_module
from character_view import build_character_view
from paths import CHARACTERS_DIR, PORTRAIT_EXTS, PORTRAITS_DIR, _safe_slug


def _has_portrait(slug: str) -> bool:
    safe = _safe_slug(slug)
    return bool(safe) and any(
        (PORTRAITS_DIR / f"{safe}.{ext}").exists() for ext in PORTRAIT_EXTS)


def _pc_statblock(slug: str, path, db) -> dict:
    """Kompakt statblok for én PC. Tal plukkes fra build_character_view, så de
    matcher det fulde ark (inkl. aktive effekter)."""
    char = char_module.load_character(str(path))
    v = build_character_view(char, db)
    ac = v["ac"]
    return {
        "slug": slug,
        "name": char.name or slug,
        "has_portrait": _has_portrait(slug),
        "hp_current": char.hp_current,
        "hp_max": v["hp_max_eff"],
        "dead": char.hp_current <= 0,
        "ac": ac["ac"],
        "touch": ac["touch"],
        "flat_footed": ac["flat_footed"],
        # saves er en liste af delta_row-dicts i rækkefølgen Fort/Ref/Will.
        "saves": [{"name": s["name"], "val": s["val"]} for s in v["saves"]],
        "init": v["initiative"]["val"],
        "speed": v["speed"]["val"],
        "conditions": list(char.conditions),
    }


def party_view(slugs: list[str], db) -> list[dict]:
    """Statblokke for hvert party-medlem, i den givne rækkefølge. En PC der ikke
    kan loades får `{broken: True}` frem for at forsvinde fra sidebjælken."""
    out = []
    for slug in slugs:
        path = CHARACTERS_DIR / f"{_safe_slug(slug)}.yaml"
        try:
            if not path.exists():
                raise FileNotFoundError(slug)
            out.append(_pc_statblock(slug, path, db))
        except Exception:
            out.append({"slug": slug, "name": slug, "broken": True})
    return out


def _companion_combatant(owner_slug: str, stat: dict) -> dict:
    """Companion/familiar-statblok → let combatant-kilde (samme form som PC/monster-
    kilderne i encounteren). `initiative` fra statblokken er den fulde init-modifier,
    så den kan auto-rulles som et monster. `ref` bindes til ejeren (en PC har højst
    én ledsager), så id'et bliver unikt i encounteren."""
    return {
        "owner": owner_slug,
        "ref": f"{_safe_slug(owner_slug)}-companion",
        "name": stat["name"],
        "kind": stat.get("kind") or "companion",
        "init_mod": stat.get("initiative", 0),
        "hp_max": stat["hp_max"],
        "hp_current": stat.get("hp_current"),
    }


def party_companions(slugs: list[str], db) -> list[dict]:
    """Kampklare ledsagere (animal companion / familiar / mount) for party'et.

    Genbruger de samme motorer som karakterarket (`build_familiar`/`build_companion`),
    så tallene matcher arket. En PC uden (gyldig) ledsager bidrager ingenting — og en
    PC der slet ikke kan loades springes tavst over (den fremgår allerede `broken` i
    party_view, så DM'en får ikke to fejl for samme karakter)."""
    out = []
    for slug in slugs:
        path = CHARACTERS_DIR / f"{_safe_slug(slug)}.yaml"
        if not path.exists():
            continue
        try:
            char = char_module.load_character(str(path))
            stat = (familiar_module.build_familiar(char, db)
                    or companion_module.build_companion(char, db))
        except Exception:
            continue
        if stat:
            out.append(_companion_combatant(slug, stat))
    return out
