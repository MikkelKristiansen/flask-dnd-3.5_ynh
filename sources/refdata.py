"""Statisk referencedata + regel-opslag for D&D 3.5 (racer, sprog, klasser, feats).

Ren data og små opslag/parsere uden runtime-afhængigheder: race-traits,
sprogtabeller, klassens hit die / skill points / klassefærdigheder, feat-hjælpere
og feat-prerequisite-parseren. Ingen karakter-tilstand — kun "hvordan ser
reglerne/racerne ud". Race- og klasse-data indlæses fra data/races.yaml og
data/classes.yaml ved import (kilden til sandheden); resten er små opslag og
parsere. Beregninger der bruger en konkret karakter bor i character.py (rules);
her er kildedataene de slår op i.

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


def _load_records(name: str, required: tuple = ()) -> dict:
    """Indlæs data/<name>.yaml som mapping ``id → felt-dict``, valideret.

    Fejler tydeligt ved import (app-start) hvis filen er forkert formet eller en
    blok mangler påkrævede felter — så en YAML-tastefejl fanges før deploy i
    stedet for at give stille forkert opførsel.
    """
    data = _load_yaml(name)
    if not isinstance(data, dict):
        raise ValueError(
            f"data/{name}.yaml: forventede en mapping (id: felter), "
            f"fik {type(data).__name__}")
    for key, fields in data.items():
        if not isinstance(fields, dict):
            raise ValueError(
                f"data/{name}.yaml: '{key}' skal være en blok af felter, "
                f"ikke {type(fields).__name__}")
        missing = [f for f in required if f not in fields]
        if missing:
            raise ValueError(
                f"data/{name}.yaml: '{key}' mangler påkrævede felter: "
                f"{', '.join(missing)}")
    return data


_CLASSES: dict[str, dict] = _load_records("classes")


def class_data(cls: str) -> dict:
    """Klasse-data (hit_die, skill_points, class_skills, languages, …) eller {}."""
    return _CLASSES.get(cls.lower(), {})


def hit_die(cls: str) -> int:
    return class_data(cls).get("hit_die", 8)


def skill_points_per_level(cls: str, int_modifier: int, race: str = "") -> int:
    race_bonus = race_data(race).get("skill_point_bonus_per_level", 0)
    return max(1, base_skill_points(cls) + int_modifier + race_bonus)


def is_feat_level(level: int) -> bool:
    return level == 1 or level % 3 == 0


def is_ability_level(level: int) -> bool:
    return level % 4 == 0


def class_skills(cls: str) -> set[str]:
    return set(class_data(cls).get("class_skills", []))


# ---------------------------------------------------------------------------
# Race-data — bruges KUN af karaktergeneratoren ved oprettelse. Motoren har
# ingen mekanisk race-logik (scores gemmes som endelige tal, racial_traits er
# fri tekst); disse data lader generatoren lægge ability-justeringer på, sætte
# size/speed, lægge racial skill-bonusser i skills' misc, og pre-udfylde
# racial_traits i samme format som de håndskrevne karakterer bruger.
# ---------------------------------------------------------------------------
_RACES: dict[str, dict] = _load_records("races", required=("size", "speed"))


def race_data(race: str) -> dict:
    """Race-data (size, speed, ability-justeringer, skill-bonusser, traits) eller {}."""
    return _RACES.get(race.lower(), {})


def race_ids() -> list[str]:
    """Race-id'er i den rækkefølge de står i data/races.yaml (til generator-listen)."""
    return list(_RACES.keys())


def race_bio(race: str) -> dict:
    """Racens højde/vægt/alder-tabeldata (adulthood, age_dice, height/weight) eller {}."""
    return race_data(race).get("bio", {})


# Standardsprog i SRD. Druidic er hemmeligt (kun druider) og er IKKE i "any"-puljen
# — det gives kun gennem klassen.
STANDARD_LANGUAGES = [
    "Abyssal", "Aquan", "Auran", "Celestial", "Common", "Draconic", "Dwarven",
    "Elven", "Giant", "Gnoll", "Gnome", "Goblin", "Halfling", "Ignan",
    "Infernal", "Orc", "Sylvan", "Terran", "Undercommon",
]

def class_languages(cls: str) -> dict:
    """Klassens sprog ({'automatic': [...], 'bonus': [...]}) eller tomt.

    'automatic' gives gratis (tæller ikke mod Int-bonus), 'bonus' kan vælges som
    et af bonussprogene. Klasser uden særlige sprog har intet 'languages'-felt.
    """
    return class_data(cls).get("languages", {"automatic": [], "bonus": []})


def race_bonus_languages(race: str) -> list[str]:
    """Racens bonussprog-liste ('any' → alle standardsprog)."""
    bonus = race_data(race).get("languages", {}).get("bonus", [])
    return list(STANDARD_LANGUAGES) if bonus == "any" else list(bonus)


def automatic_languages(race: str, cls: str) -> list[str]:
    """Sprog karakteren altid kan (race + klasse), uden at bruge Int-bonus."""
    langs = list(race_data(race).get("languages", {}).get("automatic", []))
    for lang in class_languages(cls).get("automatic", []):
        if lang not in langs:
            langs.append(lang)
    return langs


def bonus_language_pool(race: str, cls: str) -> list[str]:
    """De bonussprog man må vælge imellem (race + klasse), minus de automatiske.

    Human ('bonus': 'any') må vælge et hvilket som helst standardsprog.
    """
    race_bonus = race_data(race).get("languages", {}).get("bonus", [])
    pool = list(STANDARD_LANGUAGES) if race_bonus == "any" else list(race_bonus)
    for lang in class_languages(cls).get("bonus", []):
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
    return list(class_data(cls).get("bonus_feats", []))


def class_bonus_feat_choices(cls: str) -> int:
    """Antal feats spilleren vælger fra klassens bonus-feat-pulje (0 for de fleste)."""
    return int(class_data(cls).get("bonus_feat_choices", 0))


def class_bonus_feat_pool(cls: str) -> list | None:
    """Eksplicit liste af feat-id'er klassens bonus-feat vælges fra (monk), eller
    None hvis klassen bruger den brede fighter-bonus-pulje (fighter_bonus-flaget)."""
    pool = class_data(cls).get("bonus_feat_pool")
    return list(pool) if isinstance(pool, list) else None


def class_bonus_feat_ignore_prereqs(cls: str) -> bool:
    """True hvis klassens bonus-feat gives uden at opfylde prerequisites (monk)."""
    return bool(class_data(cls).get("bonus_feat_ignore_prereqs", False))


def class_ac_ability(cls: str) -> str:
    """Ability hvis modifier lægges til AC når unarmored (monk: 'wis'), ellers ''."""
    return str(class_data(cls).get("ac_ability", ""))


def class_starting_gold(cls: str) -> str:
    """Klassens start-guld-terning som streng (fx '6d4*10'), eller '' hvis ukendt."""
    return str(class_data(cls).get("starting_gold", ""))


def class_age_group(cls: str) -> str:
    """Klassens SRD startalders-gruppe ('fast'/'medium'/'slow'), default 'medium'."""
    return str(class_data(cls).get("age_group", "medium"))


def class_speed_bonus(cls: str) -> int:
    """Klassens speed-bonus i ft (barbar: Fast Movement +10), default 0."""
    return int(class_data(cls).get("speed_bonus", 0))


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
    return bool(class_data(cls).get("needs_domains", False))


def base_skill_points(cls: str) -> int:
    """Klassens skill points pr. level før INT/race (til generatorens budget-preview)."""
    return class_data(cls).get("skill_points", 2)


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
    return bool(class_data(cls).get("turn_undead", False))


def class_has_wild_shape(cls: str, level: int) -> bool:
    from_level = class_data(cls).get("wild_shape_from_level")
    return from_level is not None and level >= from_level


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
