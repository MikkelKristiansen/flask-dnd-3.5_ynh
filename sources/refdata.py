"""Statisk referencedata + regel-opslag for D&D 3.5 (racer, sprog, klasser, feats).

Ren data og små opslag/parsere uden runtime-afhængigheder: race-traits,
sprogtabeller, klassens hit die / skill points / klassefærdigheder, feat-hjælpere
og feat-prerequisite-parseren. Ingen karakter-tilstand — kun "hvordan ser
reglerne/racerne ud". Race-data indlæses fra data/races.yaml ved import (kilden
til sandheden); resten er små opslag og parsere. Beregninger der bruger en konkret
karakter bor i character.py (rules); her er kildedataene de slår op i.

character.py re-eksporterer disse navne (façade), så char_module.race_data /
hit_die / feat_id m.fl. virker uændret.
"""
import re
from pathlib import Path

from ruamel.yaml import YAML

_DATA_DIR = Path(__file__).parent / "data"


def _load_yaml(name: str):
    """Indlæs data/<name>.yaml (race-/klassedata) → Python-struktur."""
    yaml = YAML(typ="safe")
    return yaml.load(_DATA_DIR / f"{name}.yaml") or {}


_HIT_DIE = {
    "barbarian": 12, "fighter": 10, "paladin": 10,
    "ranger": 8, "cleric": 8, "druid": 8, "monk": 8,
    "bard": 6, "rogue": 6, "sorcerer": 4, "wizard": 4,
}
_SKILL_POINTS = {
    "rogue": 8, "ranger": 6, "bard": 6,
    "druid": 4, "barbarian": 4, "monk": 4,
    "fighter": 2, "paladin": 2, "cleric": 2, "sorcerer": 2, "wizard": 2,
}
_CLASS_SKILLS: dict[str, set[str]] = {
    "druid": {
        "concentration", "craft", "diplomacy", "handle_animal", "heal",
        "knowledge_nature", "knowledge_geography", "listen",
        "profession", "profession_herbalist", "ride",
        "spellcraft", "spot", "survival", "swim",
    },
    "cleric": {
        "concentration", "craft", "diplomacy", "heal",
        "knowledge_arcana", "knowledge_history", "knowledge_planes",
        "knowledge_religion", "profession", "spellcraft",
    },
    "ranger": {
        "climb", "concentration", "craft", "handle_animal", "heal",
        "hide", "jump", "knowledge_dungeoneering", "knowledge_geography",
        "knowledge_nature", "listen", "move_silently", "profession",
        "ride", "search", "spot", "survival", "swim", "use_rope",
    },
    "rogue": {
        "appraise", "balance", "bluff", "climb", "craft", "decipher_script",
        "diplomacy", "disable_device", "disguise", "escape_artist", "forgery",
        "gather_information", "hide", "intimidate", "jump", "knowledge_local",
        "listen", "move_silently", "open_lock", "perform", "profession",
        "search", "sense_motive", "sleight_of_hand", "spot", "swim", "tumble",
        "use_magic_device", "use_rope",
    },
}


def hit_die(cls: str) -> int:
    return _HIT_DIE.get(cls.lower(), 8)


def skill_points_per_level(cls: str, int_modifier: int, race: str = "") -> int:
    race_bonus = race_data(race).get("skill_point_bonus_per_level", 0)
    return max(1, _SKILL_POINTS.get(cls.lower(), 2) + int_modifier + race_bonus)


def is_feat_level(level: int) -> bool:
    return level == 1 or level % 3 == 0


def is_ability_level(level: int) -> bool:
    return level % 4 == 0


def class_skills(cls: str) -> set[str]:
    return _CLASS_SKILLS.get(cls.lower(), set())


# ---------------------------------------------------------------------------
# Race-data — bruges KUN af karaktergeneratoren ved oprettelse. Motoren har
# ingen mekanisk race-logik (scores gemmes som endelige tal, racial_traits er
# fri tekst); disse data lader generatoren lægge ability-justeringer på, sætte
# size/speed, lægge racial skill-bonusser i skills' misc, og pre-udfylde
# racial_traits i samme format som de håndskrevne karakterer bruger.
# ---------------------------------------------------------------------------
_RACES: dict[str, dict] = _load_yaml("races")


def race_data(race: str) -> dict:
    """Race-data (size, speed, ability-justeringer, skill-bonusser, traits) eller {}."""
    return _RACES.get(race.lower(), {})


def race_ids() -> list[str]:
    """Race-id'er i den rækkefølge de står i data/races.yaml (til generator-listen)."""
    return list(_RACES.keys())


# Standardsprog i SRD. Druidic er hemmeligt (kun druider) og er IKKE i "any"-puljen
# — det gives kun gennem klassen.
STANDARD_LANGUAGES = [
    "Abyssal", "Aquan", "Auran", "Celestial", "Common", "Draconic", "Dwarven",
    "Elven", "Giant", "Gnoll", "Gnome", "Goblin", "Halfling", "Ignan",
    "Infernal", "Orc", "Sylvan", "Terran", "Undercommon",
]

# Klasse-sprog: 'automatic' gives gratis (tæller ikke mod Int-bonus), 'bonus' kan
# vælges som et af bonussprogene. Klasser uden særlige sprog står ikke her.
_CLASS_LANGUAGES: dict[str, dict] = {
    "druid":  {"automatic": ["Druidic"], "bonus": ["Sylvan"]},
    "cleric": {"automatic": [], "bonus": ["Abyssal", "Celestial", "Infernal"]},
    "wizard": {"automatic": [], "bonus": ["Draconic"]},
}


def class_languages(cls: str) -> dict:
    """Klassens sprog ({'automatic': [...], 'bonus': [...]}) eller tomt."""
    return _CLASS_LANGUAGES.get(cls.lower(), {"automatic": [], "bonus": []})


def race_bonus_languages(race: str) -> list[str]:
    """Racens bonussprog-liste ('any' → alle standardsprog)."""
    bonus = race_data(race).get("languages", {}).get("bonus", [])
    return list(STANDARD_LANGUAGES) if bonus == "any" else list(bonus)


def automatic_languages(race: str, cls: str) -> list[str]:
    """Sprog karakteren altid kan (race + klasse), uden at bruge Int-bonus."""
    langs = list(race_data(race).get("languages", {}).get("automatic", []))
    for lang in _CLASS_LANGUAGES.get(cls.lower(), {}).get("automatic", []):
        if lang not in langs:
            langs.append(lang)
    return langs


def bonus_language_pool(race: str, cls: str) -> list[str]:
    """De bonussprog man må vælge imellem (race + klasse), minus de automatiske.

    Human ('bonus': 'any') må vælge et hvilket som helst standardsprog.
    """
    race_bonus = race_data(race).get("languages", {}).get("bonus", [])
    pool = list(STANDARD_LANGUAGES) if race_bonus == "any" else list(race_bonus)
    for lang in _CLASS_LANGUAGES.get(cls.lower(), {}).get("bonus", []):
        if lang not in pool:
            pool.append(lang)
    auto = set(automatic_languages(race, cls))
    return [lang for lang in pool if lang not in auto]


def bonus_language_count(int_modifier: int) -> int:
    """Antal bonussprog = Int-mod (aldrig negativt)."""
    return max(0, int_modifier)


def apply_racial_adjustments(base_scores: dict, race: str) -> dict:
    """Læg racens ability-justeringer på basis-scores → endelige scores."""
    adj = race_data(race).get("ability_adjust", {})
    return {k: int(base_scores.get(k, 10)) + adj.get(k, 0)
            for k in ("str", "dex", "con", "int", "wis", "cha")}


def level1_feat_count(race: str) -> int:
    """Antal feats spilleren selv vælger ved level 1 (1 + evt. race-bonus-feat)."""
    return 1 + race_data(race).get("bonus_feats", 0)


def class_bonus_feats(cls: str) -> list[str]:
    """Feats klassen giver gratis ved level 1 (tæller ikke mod de valgte)."""
    return ["track"] if cls.lower() == "ranger" else []


# Feats hvor man vælger et specifikt våben (gemmes som {id, weapon} i stedet for
# en ren id-streng). Bruges af generatoren, level-up og visningen.
WEAPON_CHOICE_FEATS = {"weapon_focus", "weapon_specialization", "improved_critical"}


def feat_id(entry) -> str:
    """Feat-id'et, uanset om posten er en streng eller en {id, weapon}-dict."""
    return str(entry["id"] if isinstance(entry, dict) else entry)


def feat_weapon(entry) -> str:
    """Det valgte våben for en feat-post, eller "" hvis ingen."""
    return str(entry.get("weapon", "")) if isinstance(entry, dict) else ""


def feat_label(entry, feat_row: dict | None = None) -> str:
    """Visningsnavn: feat-navn + evt. valgt våben, fx 'Weapon Focus (Longsword)'."""
    name = (feat_row or {}).get("name") or feat_id(entry)
    wpn = feat_weapon(entry)
    return f"{name} ({wpn})" if wpn else name


def class_needs_domains(cls: str) -> bool:
    return cls.lower() == "cleric"


def base_skill_points(cls: str) -> int:
    """Klassens skill points pr. level før INT/race (til generatorens budget-preview)."""
    return _SKILL_POINTS.get(cls.lower(), 2)


# ---------------------------------------------------------------------------
# Feat-prerequisite-tjek til generatoren. Prerequisites er fri tekst i db'en
# (fx "Dex 15", "Str 13, Power Attack", "Spell Focus (Conjuration)", "BAB +4",
# "Ability to turn or rebuke undead", "Wild shape class ability"). Vi parser
# klausul-for-klausul og tjekker de typer vi kan verificere; ukendte klausuler
# behandles som rådgivende (ikke-blokerende) for at undgå falske afvisninger.
# ---------------------------------------------------------------------------
_ABILITY_PREREQ_RE = re.compile(r"^(str|dex|con|int|wis|cha)\s+(\d+)$", re.I)
_BAB_PREREQ_RE = re.compile(r"(?:base attack bonus|bab)\s*\+?(\d+)", re.I)
_LEVEL_PREREQ_RE = re.compile(r"level\s+(\d+)", re.I)  # fx "Fighter level 4"


def class_can_turn_undead(cls: str) -> bool:
    return cls.lower() == "cleric"


def class_has_wild_shape(cls: str, level: int) -> bool:
    return cls.lower() == "druid" and level >= 5


def feat_prereq_unmet(prereq_text: str, owned_feat_ids, scores: dict,
                      cls: str, level: int, bab: int,
                      feat_name_to_id: dict) -> list[str]:
    """Returnér de prerequisite-klausuler der IKKE er opfyldt (tom liste = OK).

    owned_feat_ids er de feats karakteren VIL have (valgte + klassens gratis) — så
    en feat-kæde som Dodge→Mobility er gyldig når begge vælges samtidig ved level 1.
    """
    if not prereq_text or prereq_text.strip().lower() == "none":
        return []
    owned = set(owned_feat_ids)
    unmet = []
    for clause in prereq_text.split(","):
        clause = clause.strip()
        if not clause:
            continue
        m = _ABILITY_PREREQ_RE.match(clause)
        if m:
            if int(scores.get(m.group(1).lower(), 10)) < int(m.group(2)):
                unmet.append(clause)
            continue
        m = _BAB_PREREQ_RE.search(clause)
        if m:
            if bab < int(m.group(1)):
                unmet.append(clause)
            continue
        m = _LEVEL_PREREQ_RE.search(clause)
        if m:
            if level < int(m.group(1)):
                unmet.append(clause)
            continue
        low = clause.lower()
        if "turn" in low and "undead" in low:
            if not class_can_turn_undead(cls):
                unmet.append(clause)
            continue
        if "wild shape" in low:
            if not class_has_wild_shape(cls, level):
                unmet.append(clause)
            continue
        if low.startswith("proficiency"):
            continue  # kan ikke verificeres her — rådgivende
        fid = feat_name_to_id.get(low)
        if fid is not None:
            if fid not in owned:
                unmet.append(clause)
            continue
        # ukendt klausul → rådgivende, blokér ikke
    return unmet


def spell_like_dc(spell_level: int, cha_modifier: int, extra: int = 0) -> int:
    """Save-DC for en spell-like ability: 10 + spell level + Cha-modifier.

    Gnomens SLA'er er Cha-baserede (SRD). `extra` rummer fx gnomens +1 til
    DC for illusionsskoler.
    """
    return 10 + spell_level + cha_modifier + extra
