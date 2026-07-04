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


# Familiarer (Wizard/Sorcerer): creature-id → mester-bonus (data/familiars.yaml).
# Statblokken bor i animals.yaml; her kun det familiar-specifikke (bonus til mesteren).
_FAMILIARS: dict[str, dict] = _load_records("familiars")


def familiar_ids() -> list[str]:
    """Gyldige familiar-creature-id'er i data-rækkefølge (til vælgeren)."""
    return list(_FAMILIARS.keys())


def familiar_data(creature_id: str) -> dict:
    """Familiar-bonus-data (note, modifiers, hp_bonus) for et creature-id eller {}."""
    return _FAMILIARS.get((creature_id or "").lower(), {})


def familiar_benefit_modifiers(creature_id: str) -> list[dict]:
    """Mester-bonussens modifiers (saves/skills) — flyder ind i mesterens effekt-motor."""
    return list(familiar_data(creature_id).get("modifiers") or [])


def familiar_hp_bonus(creature_id: str) -> int:
    """Fast maks-HP-bonus familiaren giver mesteren (toad +3; ellers 0)."""
    return int(familiar_data(creature_id).get("hp_bonus") or 0)


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


# ---------------------------------------------------------------------------
# Monk-helpers: rene opslags-/formelfunktioner uden karaktertilstand
# ---------------------------------------------------------------------------

def monk_unarmed_damage(level: int, size: str) -> str:
    """Monkens unarmed strike-skade som streng (fx '1d8') ud fra level og størrelse.

    Slår op i classes.yaml unarmed_damage-tabellen. Bruger 'small'-kolonnen hvis
    size == 'small', ellers 'medium'. YAML-nøgler kan være int eller str — begge
    håndteres. Returnerer skaden ved den højeste tærskel ≤ level.
    """
    table = class_data("monk").get("unarmed_damage", {})
    col_key = "small" if size.lower() == "small" else "medium"
    col = table.get(col_key, {})
    # Konvertér nøgler til int (YAML loader dem sommetider som str)
    thresholds = {int(k): v for k, v in col.items()}
    best = "1d4"  # fallback
    for thr in sorted(thresholds):
        if level >= thr:
            best = str(thresholds[thr])
    return best


def monk_fast_movement(level: int) -> int:
    """Monkens Fast Movement-bonus i ft (kun unarmored/let last). Cap 60 ft.

    +10 ft pr. 3 levels: level 3 = +10, 6 = +20, 9 = +30, 12 = +40, 15 = +50, 18 = +60.
    """
    return min((level // 3) * 10, 60)


def monk_flurry_penalty(level: int) -> int:
    """Flurry of Blows-straf til til-hit (negativ int). Gælder ALLE angreb ved flurry.

    −2 ved level 1-4, −1 ved level 5-8, 0 ved level 9+.
    """
    if level >= 9:
        return 0
    if level >= 5:
        return -1
    return -2


def monk_greater_flurry(level: int) -> bool:
    """True hvis monken har Greater Flurry (level 11+): 2 ekstra angreb i stedet for 1."""
    return level >= 11


def monk_ac_bonus(level: int) -> int:
    """Monkens ekstra AC-bonus (uover Wis-delen) når unarmored, skalerer med level.

    +1 ved level 5, +2 ved 10, +3 ved 15, +4 ved 20. Formel: level // 5.
    """
    return level // 5


def monk_ki_strike(level: int) -> str:
    """Beskrivelse af Ki Strike-typen monken kan overvinde DR med.

    Tom streng hvis under level 4. Ellers: 'magisk' (4+), 'magisk, lovlig' (10+),
    'magisk, lovlig, adamant' (16+).
    """
    if level >= 16:
        return "magisk, lovlig, adamant"
    if level >= 10:
        return "magisk, lovlig"
    if level >= 4:
        return "magisk"
    return ""


def monk_evasion(level: int) -> str:
    """Monkens evasion-evne som streng til visning.

    Tom streng ved level 1. 'Evasion' ved level 2-8. 'Improved Evasion' ved level 9+.
    """
    if level >= 9:
        return "Improved Evasion"
    if level >= 2:
        return "Evasion"
    return ""


def class_starting_gold(cls: str) -> str:
    """Klassens start-guld-terning som streng (fx '6d4*10'), eller '' hvis ukendt."""
    return str(class_data(cls).get("starting_gold", ""))


def class_age_group(cls: str) -> str:
    """Klassens SRD startalders-gruppe ('fast'/'medium'/'slow'), default 'medium'."""
    return str(class_data(cls).get("age_group", "medium"))


def class_speed_bonus(cls: str) -> int:
    """Klassens speed-bonus i ft (barbar: Fast Movement +10), default 0."""
    return int(class_data(cls).get("speed_bonus", 0))


def class_weapon_proficiency(cls: str) -> dict | None:
    """Klassens våben-proficiency {categories: [...], weapons: [id, …]} eller None.

    None betyder "ingen proficiency-data" → kalderen håndhæver ikke (ingen straf).
    """
    return class_data(cls).get("weapon_proficiency")


def class_armor_proficiency(cls: str) -> dict | None:
    """Klassens rustnings-proficiency {types, shields, tower_shield} eller None.

    None betyder "ingen proficiency-data" → kalderen håndhæver ikke (ingen straf).
    """
    return class_data(cls).get("armor_proficiency")


# ── Startkit (anbefalede køb pr. klasse — data/starting_kits.yaml) ──────────
_STARTING_KITS: dict[str, list] = (_load_yaml("starting_kits") or {}).get("kits", {}) or {}


def _flatten(seq) -> list:
    """Fladgør én/flere niveauers indlejrede lister (YAML-ankre bliver til lister)."""
    out: list = []
    for x in seq or []:
        out.extend(_flatten(x)) if isinstance(x, list) else out.append(x)
    return out


def starting_kit_ids(cls: str) -> set:
    """Anbefalede start-køb (bare katalog-id'er) for en klasse — tom hvis ukendt."""
    return set(_flatten(_STARTING_KITS.get((cls or "").lower(), [])))


# Feats hvor man vælger et specifikt våben (gemmes som {id, weapon} i stedet for
# en ren id-streng). Bruges af generatoren, level-up og visningen.
WEAPON_CHOICE_FEATS = {"weapon_focus", "greater_weapon_focus", "weapon_specialization",
                       "greater_weapon_specialization", "improved_critical"}

# Feats hvor man i stedet vælger en troldskole (gemmes som {id, school}). Spell
# Focus/Greater Spell Focus gælder hver én skole og kan tages flere gange (SRD).
SCHOOL_CHOICE_FEATS = {"spell_focus", "greater_spell_focus"}

# De otte troldskoler (SRD). Bruges til skole-valgs-feats og spell-DC-bonus.
SPELL_SCHOOLS = ["Abjuration", "Conjuration", "Divination", "Enchantment",
                 "Evocation", "Illusion", "Necromancy", "Transmutation"]


def feat_id(entry) -> str:
    """Feat-id'et, uanset om posten er en streng eller en {id, ...}-dict."""
    return str(entry["id"] if isinstance(entry, dict) else entry)


def feat_weapon(entry) -> str:
    """Det valgte våben for en feat-post, eller "" hvis ingen."""
    return str(entry.get("weapon", "")) if isinstance(entry, dict) else ""


def feat_school(entry) -> str:
    """Den valgte troldskole for en feat-post, eller "" hvis ingen."""
    return str(entry.get("school", "")) if isinstance(entry, dict) else ""


def feat_label(entry, feat_row: dict | None = None) -> str:
    """Visningsnavn + evt. valgt våben/skole, fx 'Weapon Focus (Longsword)'
    eller 'Spell Focus (Conjuration)'."""
    name = (feat_row or {}).get("name") or feat_id(entry)
    choice = feat_weapon(entry) or feat_school(entry)
    return f"{name} ({choice})" if choice else name


def spell_focus_bonus(feat_entries, school: str) -> int:
    """+1 til spell-DC pr. Spell Focus / Greater Spell Focus i spellets skole.

    En caster med begge feats i samme skole får +2. Spellets school-felt i DB'en
    bærer ofte subskole/deskriptorer ('Evocation [Force]', 'Conjuration (Creation)')
    — Spell Focus gælder basis-skolen, så vi matcher på dens første ord. Ingen af de
    8 skolenavne er præfiks af et andet, så startswith er entydigt.
    """
    base = (school or "").strip().lower()
    if not base:
        return 0
    bonus = 0
    for e in feat_entries:
        fs = feat_school(e).lower()
        if fs and feat_id(e) in SCHOOL_CHOICE_FEATS and base.startswith(fs):
            bonus += 1
    return bonus


def class_cast_type(cls: str) -> str | None:
    """Klassens casting-model: 'spontaneous' (sorcerer/bard), 'spellbook' (wizard)
    eller None for forberedte/ikke-castere. Data-drevet (cast_type i classes.yaml)."""
    return class_data(cls).get("cast_type")


def owned_feat_tokens(feat_entries, name_by_id: dict) -> set:
    """Ejer-tokens til prereq-tjek: alle bare feat-id'er plus kvalificerede
    labels ('spell focus (conjuration)') for valg-feats. Så navne-baserede
    prerequisites som Augment Summonings stadig matcher det valgte."""
    tokens: set = set()
    for e in feat_entries:
        fid = feat_id(e)
        tokens.add(fid)
        choice = feat_weapon(e) or feat_school(e)
        if choice:
            name = name_by_id.get(fid, fid)
            tokens.add(f"{name} ({choice})".lower())
    return tokens


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
    ws = class_data(cls).get("wild_shape") or {}
    from_level = ws.get("from_level", class_data(cls).get("wild_shape_from_level"))
    return from_level is not None and level >= from_level


def class_wild_shape(cls: str) -> dict | None:
    """Klassens fulde wild shape-progression (data), eller None hvis ingen."""
    return class_data(cls).get("wild_shape")


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
        # Kvalificeret valg-feat ejet direkte (fx "spell focus (conjuration)")?
        if low in owned:
            continue
        # En valg-feat med specifikt valg ('spell focus (conjuration)') som IKKE er
        # ejet (var den, fangede linjen ovenfor) → kræver præcis det valg, ikke opfyldt.
        m_choice = re.match(r"^(.*?)\s*\(.+\)$", low)
        if m_choice and feat_name_to_id.get(m_choice.group(1).strip()) \
                in (WEAPON_CHOICE_FEATS | SCHOOL_CHOICE_FEATS):
            unmet.append(clause)
            continue
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


# Summon-tabeller (dokument-formet: spellniveau → væsner, derfor her og ikke i
# SQLite). To FAMILIER deler samme motor og adskilles kun af et spell-præfiks og
# deres væsen-liste:
#   • sna = Summon Nature's Ally (druide/ranger) — rene væsen-id'er.
#   • sm  = Summon Monster (cleric/arkane) — entries kan være {base, template},
#           fordi de fleste SM-væsner er celestial/fiendish-udgaver af eksisterende
#           katalog-dyr (skabelonen lægges på ved kast, jf. creature_template.py).
_SUMMON_LISTS: dict = _load_yaml("summon_lists")
_SUMMON_MONSTER_LISTS: dict = _load_yaml("summon_monster_lists")

# familie → (spell-id-præfiks, niveau-tabel). Ny familie tilføjes her alene.
_SUMMON_FAMILIES: dict = {
    "sna": ("summon_natures_ally_", _SUMMON_LISTS),
    "sm":  ("summon_monster_",      _SUMMON_MONSTER_LISTS),
}


def summon_family(spell_id: str) -> str | None:
    """Hvilken summon-familie et spell-id tilhører ('sna'/'sm'), ellers None."""
    for fam, (prefix, _table) in _SUMMON_FAMILIES.items():
        if spell_id.startswith(prefix):
            return fam
    return None


def summon_entries(family: str, spell_level: int) -> list[dict]:
    """Normaliserede summon-kandidater for en familie + spellniveau.

    Returnerer [{"base": <katalog-id>, "template": <'celestial'|'fiendish'|None>}].
    SNA-listens rene id'er normaliseres til template=None; SM-listens dict-entries
    bevarer deres skabelon. Tom liste hvis familien/niveauet ikke (endnu) findes.
    """
    _prefix, table = _SUMMON_FAMILIES.get(family, (None, {}))
    entries = []
    for e in (table.get(spell_level) or []):
        if isinstance(e, dict):
            entries.append({"base": e["base"], "template": e.get("template")})
        else:
            entries.append({"base": e, "template": None})
    return entries


def summon_creatures(spell_level: int) -> list[str]:
    """Bagudkompatibel SNA-hjælper: væsen-id'er for Summon Nature's Ally af niveauet."""
    return [e["base"] for e in summon_entries("sna", spell_level)]


# Summon N (SNA og Summon Monster): vælg ÉT væsen fra niveau-N-listen, ELLER flere
# svagere væsner af SAMME slags fra en lavere liste. SRD-fast: én liste ned → 1d3,
# to lister ned → 1d4+1. Offset = hvor mange lister ned man går.
_SUMMON_COUNT_BY_OFFSET = {0: "1", 1: "1d3", 2: "1d4+1"}


def summon_tiers(family: str, spell_level: int) -> list[dict]:
    """De 'spor' et Summon-spell af et niveau tilbyder — stærkeste først.

    Hvert spor: {"offset", "list_level", "count", "entries"}. offset 0 = niveau-N-
    listen (1 væsen); offset 1/2 = liste N-1/N-2 (1d3 / 1d4+1 væsner af samme slags).
    Kun spor med et gyldigt (>=1) listeniveau og mindst ét væsen tages med.
    """
    tiers = []
    for offset, count in _SUMMON_COUNT_BY_OFFSET.items():
        list_level = spell_level - offset
        if list_level < 1:
            continue
        entries = summon_entries(family, list_level)
        if entries:
            tiers.append({"offset": offset, "list_level": list_level,
                          "count": count, "entries": entries})
    return tiers


def summon_count_expr(family: str, spell_level: int, base: str,
                      template: str | None) -> str | None:
    """Antals-udtrykket ('1'/'1d3'/'1d4+1') for et valgt væsen ved et cast-niveau.

    Slår væsenet op i sporene for cast-niveauet og returnerer sporets antal-udtryk;
    None hvis væsenet ikke findes i noget spor (ugyldigt valg → afvises af kalderen).
    """
    for tier in summon_tiers(family, spell_level):
        if any(e["base"] == base and e["template"] == template for e in tier["entries"]):
            return tier["count"]
    return None


# Celestial/Fiendish-skabeloner (Summon Monster). Dokument-formet (definitioner +
# HD-skalering); selve overlay-logikken ligger i creature_template.py, så data
# forbliver ren og fortolkes ét sted.
_CREATURE_TEMPLATES: dict = _load_yaml("creature_templates")


def creature_templates() -> dict:
    """Rå skabelon-data ({templates: {...}, scaling: {...}}) — se creature_template.py."""
    return _CREATURE_TEMPLATES


# Kampindstillinger ("Kampindstillinger"-panelet, Lag A). Dokument-formet
# (id → {label, feat?, scope, modifiers, note}), som races/classes — indlæst
# direkte, ikke via importer.py/SQLite. Selve toggle-mekanikken (feat-gate,
# view-model) bor i combat_options.py; her er kun kildedataene.
_COMBAT_OPTIONS: dict = _load_records("combat_options")


def combat_options() -> dict:
    """Rå kamp-toggle-data ({id: {label, feat?, scope, modifiers, note}})."""
    return _COMBAT_OPTIONS
