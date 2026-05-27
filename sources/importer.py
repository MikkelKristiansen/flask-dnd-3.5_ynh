"""One-time seeder: Python dicts → srd35.db

Run:  python importer.py
Idempotent — safe to run multiple times (drops and recreates tables).
"""
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("DND_DB_PATH",
                              str(Path(__file__).parent / "srd35.db")))

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
DROP TABLE IF EXISTS spells;
CREATE TABLE spells (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    level_druid INTEGER,
    level_cleric INTEGER,
    level_wizard INTEGER,
    level_ranger INTEGER,
    level_paladin INTEGER,
    school TEXT,
    cast_time TEXT,
    range TEXT,
    target TEXT,
    duration TEXT,
    save TEXT,
    spell_resistance TEXT,
    description TEXT
);

DROP TABLE IF EXISTS skills;
CREATE TABLE skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ability TEXT NOT NULL,
    trained_only INTEGER NOT NULL,
    description TEXT
);

DROP TABLE IF EXISTS feats;
CREATE TABLE feats (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    prerequisites TEXT,
    benefit TEXT,
    normal TEXT,
    special TEXT
);

DROP TABLE IF EXISTS conditions;
CREATE TABLE conditions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    summary TEXT NOT NULL,
    description TEXT NOT NULL
);

DROP TABLE IF EXISTS druid_levels;
CREATE TABLE druid_levels (
    level       INTEGER PRIMARY KEY,
    hd          TEXT NOT NULL,
    skill_points INTEGER NOT NULL,
    bab         INTEGER NOT NULL,
    fort        INTEGER NOT NULL,
    ref         INTEGER NOT NULL,
    will        INTEGER NOT NULL,
    spells_0    INTEGER NOT NULL,
    spells_1    INTEGER NOT NULL,
    spells_2    INTEGER NOT NULL,
    spells_3    INTEGER NOT NULL,
    spells_4    INTEGER NOT NULL,
    spells_5    INTEGER NOT NULL,
    spells_6    INTEGER NOT NULL,
    spells_7    INTEGER NOT NULL,
    spells_8    INTEGER NOT NULL,
    spells_9    INTEGER NOT NULL,
    features    TEXT NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Spell data
# ---------------------------------------------------------------------------

SPELLS: list[dict] = [
    # ── Level 0 (orisons) ─────────────────────────────────────────────────
    {
        "id": "detect_magic",
        "name": "Detect Magic",
        "level_druid": 0, "level_cleric": None, "level_wizard": 0,
        "school": "Divination",
        "cast_time": "1 standard action",
        "range": "60 ft",
        "target": "Cone-shaped emanation",
        "duration": "Concentration, up to 1 min./level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "You detect magical auras. The amount of information revealed "
            "depends on how long you study a particular area or subject."
        ),
    },
    {
        "id": "guidance",
        "name": "Guidance",
        "level_druid": 0, "level_cleric": 0, "level_wizard": None,
        "school": "Divination",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "1 minute or until discharged",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes",
        "description": (
            "This spell imbues the subject with a touch of divine guidance. "
            "The creature gets a +1 competence bonus on a single attack roll, "
            "saving throw, or skill check. It must choose to use the bonus "
            "before making the roll to which it applies."
        ),
    },
    {
        "id": "light",
        "name": "Light",
        "level_druid": 0, "level_cleric": 0, "level_wizard": 0,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Object touched",
        "duration": "10 min./level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "This spell causes an object to glow like a torch, shedding bright "
            "light in a 20-foot radius (and dim light for an additional 20 feet) "
            "from the point you touch."
        ),
    },
    {
        "id": "purify_food_drink",
        "name": "Purify Food and Drink",
        "level_druid": 0, "level_cleric": 0, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "10 ft",
        "target": "1 cu. ft./level of contaminated food and water",
        "duration": "Instantaneous",
        "save": "Will negates (object)",
        "spell_resistance": "No",
        "description": (
            "This spell makes spoiled, rotten, diseased, poisonous, or otherwise "
            "contaminated food and water pure and suitable for eating and drinking. "
            "This spell does not prevent subsequent natural decay or spoilage."
        ),
    },
    {
        "id": "flare",
        "name": "Flare",
        "level_druid": 0, "level_cleric": None, "level_wizard": 0,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "One creature",
        "duration": "Instantaneous",
        "save": "Fortitude negates",
        "spell_resistance": "Yes",
        "description": (
            "This cantrip creates a burst of light. If you cause the flash to "
            "appear in front of a single creature, that creature must succeed on "
            "a Fortitude saving throw or be dazzled for 1 minute."
        ),
    },
    {
        "id": "know_direction",
        "name": "Know Direction",
        "level_druid": 0, "level_cleric": None, "level_wizard": None,
        "school": "Divination",
        "cast_time": "1 standard action",
        "range": "Personal",
        "target": "You",
        "duration": "Instantaneous",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "You instantly know the direction of north from your current position. "
            "The spell is effective in any environment in which 'north' exists, "
            "but it may not work in extraplanar settings."
        ),
    },
    {
        "id": "resistance",
        "name": "Resistance",
        "level_druid": 0, "level_cleric": 0, "level_wizard": 0,
        "school": "Abjuration",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "1 minute",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes",
        "description": (
            "You imbue the subject with magical energy that protects it from harm, "
            "granting it a +1 resistance bonus on saving throws."
        ),
    },
    {
        "id": "virtue",
        "name": "Virtue",
        "level_druid": 0, "level_cleric": 0, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "1 minute",
        "save": "Fortitude negates (harmless)",
        "spell_resistance": "Yes",
        "description": (
            "With a touch, you infuse a creature with a surge of strength. "
            "The subject gains 1 temporary hit point."
        ),
    },
    # ── Level 1 ────────────────────────────────────────────────────────────
    {
        "id": "entangle",
        "name": "Entangle",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Long (400 ft + 40 ft/level)",
        "target": "Plants in a 40-ft.-radius spread",
        "duration": "1 min./level",
        "save": "Reflex partial",
        "spell_resistance": "No",
        "description": (
            "Grasses, weeds, bushes, and even trees wrap, twist, and entwine about "
            "creatures in the area of effect, holding them fast. Any creature in the "
            "area when the spell is cast must make a Reflex saving throw. Those who "
            "fail are entangled. A creature that enters the spell's area of effect "
            "must also make a Reflex saving throw."
        ),
    },
    {
        "id": "faerie_fire",
        "name": "Faerie Fire",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "Long (400 ft + 40 ft/level)",
        "target": "Creatures and objects within a 5-ft.-radius burst",
        "duration": "1 min./level",
        "save": "None",
        "spell_resistance": "Yes",
        "description": (
            "A pale glow surrounds and outlines the subjects. Outlined subjects "
            "shed light as candles. Outlined creatures do not benefit from the "
            "concealment normally provided by darkness, blur, displacement, "
            "or invisibility."
        ),
    },
    {
        "id": "speak_with_animals",
        "name": "Speak with Animals",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Divination",
        "cast_time": "1 standard action",
        "range": "Personal",
        "target": "You",
        "duration": "1 min./level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "You can comprehend and communicate with animals. You are able to ask "
            "questions of and receive answers from animals, although the spell "
            "doesn't make them more friendly or cooperative than normal."
        ),
    },
    {
        "id": "cure_light_wounds",
        "name": "Cure Light Wounds",
        "level_druid": 1, "level_cleric": 1, "level_wizard": None,
        "school": "Conjuration (Healing)",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "Instantaneous",
        "save": "Will half (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "When laying your hand upon a living creature, you channel positive "
            "energy that cures 1d8 points of damage +1 point per caster level "
            "(maximum +5)."
        ),
    },
    {
        "id": "goodberry",
        "name": "Goodberry",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "2d4 fresh berries touched",
        "duration": "One day/level",
        "save": "None",
        "spell_resistance": "Yes",
        "description": (
            "Casting goodberry upon a handful of freshly picked berries makes 2d4 "
            "of them magical. Each magical berry provides nourishment as if it were "
            "a normal meal. A harmed creature that eats a goodberry recovers 1 hit "
            "point (no more than 8 hit points per 24 hours)."
        ),
    },
    {
        "id": "longstrider",
        "name": "Longstrider",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Personal",
        "target": "You",
        "duration": "1 hour/level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "This spell increases your base land speed by 10 feet. "
            "It has no effect on other modes of movement."
        ),
    },
    {
        "id": "magic_fang",
        "name": "Magic Fang",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Living creature touched",
        "duration": "1 min./level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "Magic fang gives one natural weapon of the subject a +1 enhancement "
            "bonus on attack and damage rolls. The spell can affect a slam attack, "
            "fist, bite, or other natural weapon."
        ),
    },
    {
        "id": "obscuring_mist",
        "name": "Obscuring Mist",
        "level_druid": 1, "level_cleric": 1, "level_wizard": 1,
        "school": "Conjuration (Creation)",
        "cast_time": "1 standard action",
        "range": "20 ft",
        "target": "Cloud spreads in 20-ft. radius from you",
        "duration": "1 min./level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "A misty vapor arises around you. The vapor obscures all sight, "
            "including darkvision, beyond 5 feet. A creature 5 feet away has "
            "concealment (20% miss chance). Creatures farther away have total "
            "concealment (50% miss chance)."
        ),
    },
    {
        "id": "produce_flame",
        "name": "Produce Flame",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "0 ft",
        "target": "Flame in your palm",
        "duration": "1 min./level",
        "save": "None",
        "spell_resistance": "Yes",
        "description": (
            "Flames as bright as a torch appear in your open hand. In addition to "
            "providing illumination, the flames can be hurled or used to touch "
            "enemies. A strike with a melee touch attack deals 1d6 + 1/level "
            "(max +5) points of fire damage."
        ),
    },
    {
        "id": "summon_natures_ally_i",
        "name": "Summon Nature's Ally I",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Conjuration (Summoning)",
        "cast_time": "1 round",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "One summoned creature",
        "duration": "1 round/level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "This spell summons a nature creature to fight on your behalf. "
            "It appears where you designate and acts immediately, on your turn. "
            "It attacks your opponents to the best of its ability."
        ),
    },
    {
        "id": "calm_animals",
        "name": "Calm Animals",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Enchantment (Compulsion)",
        "cast_time": "1 standard action",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "Animals within 30 ft of each other",
        "duration": "1 min./level",
        "save": "Will negates",
        "spell_resistance": "Yes",
        "description": (
            "This spell soothes and quiets animals, rendering them docile and "
            "harmless. The total Hit Dice of animals you can affect is 2d4 + your "
            "caster level. Only animals (creatures with the animal type) can be "
            "affected. If the spell is successful, the animals cease hostile action "
            "and become docile for the duration."
        ),
    },
    {
        "id": "charm_animal",
        "name": "Charm Animal",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Enchantment (Charm)",
        "cast_time": "1 standard action",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "One animal",
        "duration": "1 hour/level",
        "save": "Will negates",
        "spell_resistance": "Yes",
        "description": (
            "This spell makes an animal regard you as its trusted friend and ally. "
            "If the creature is currently being threatened or attacked by you or your "
            "allies, it receives a +5 bonus on its saving throw. The spell does not "
            "enable you to control the charmed animal as if it were an automaton; "
            "it perceives your words and actions in the most favorable way."
        ),
    },
    {
        "id": "detect_animals_plants",
        "name": "Detect Animals or Plants",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Divination",
        "cast_time": "1 standard action",
        "range": "Long (400 ft + 40 ft/level)",
        "target": "Cone-shaped emanation",
        "duration": "Concentration, up to 10 min./level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "You can detect a particular kind of animal or plant in a cone emanating "
            "out from you. You must think of a specific kind of animal or plant when "
            "using the spell. The amount of information revealed depends on how long "
            "you study a particular area: 1st round, presence or absence; 2nd round, "
            "number and location of the strongest aura; 3rd round, exact number and "
            "locations of all such creatures."
        ),
    },
    {
        "id": "detect_snares_pits",
        "name": "Detect Snares and Pits",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Divination",
        "cast_time": "1 standard action",
        "range": "60 ft",
        "target": "Cone-shaped emanation",
        "duration": "Concentration, up to 10 min./level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "You can detect simple pits, deadfalls, and snares as well as magical "
            "traps constructed to harm those who enter an area. The spell does not "
            "detect complex mechanical traps. It detects traps set to harm those in "
            "the area of the spell. Rangers and druids can identify the type and "
            "location of each trap on a successful Wilderness Lore or Survival check."
        ),
    },
    {
        "id": "endure_elements",
        "name": "Endure Elements",
        "level_druid": 1, "level_cleric": 1, "level_wizard": 1,
        "school": "Abjuration",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "24 hours",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "A creature protected by endure elements suffers no harm from being in a "
            "hot or cold environment. It can exist comfortably in conditions between "
            "–50 and 140 degrees Fahrenheit without taking nonlethal damage. "
            "The spell doesn't protect against fire or cold damage, only environmental "
            "extremes."
        ),
    },
    {
        "id": "hide_from_animals",
        "name": "Hide from Animals",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Abjuration",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "One creature/level touched",
        "duration": "10 min./level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes",
        "description": (
            "Animals cannot sense the warded creatures. Even extraordinary or "
            "supernatural sensory capabilities such as blindsense, scent, and "
            "tremorsense cannot detect or locate warded creatures. If a warded "
            "creature touches an animal or attacks any creature, the spell ends "
            "for that character."
        ),
    },
    {
        "id": "jump",
        "name": "Jump",
        "level_druid": 1, "level_cleric": None, "level_wizard": 1,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "1 min./level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "The subject gets a bonus on Jump checks. The bonus is +10 (caster level "
            "1–4), +20 (5th–9th), or +30 (10th+). The spell does not affect whether "
            "the subject makes a running jump or a standing jump."
        ),
    },
    {
        "id": "magic_stone",
        "name": "Magic Stone",
        "level_druid": 1, "level_cleric": 1, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Up to three pebbles touched",
        "duration": "30 minutes or until discharged",
        "save": "Will negates (harmless, object)",
        "spell_resistance": "Yes (harmless, object)",
        "description": (
            "You transmute as many as three pebbles, which can be hurled or slung at "
            "opponents. If hurled, they have a range increment of 20 feet. Each stone "
            "that hits deals 1d6+1 points of bludgeoning damage. Against undead "
            "creatures this damage is doubled."
        ),
    },
    {
        "id": "pass_without_trace",
        "name": "Pass without Trace",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "One creature/level touched",
        "duration": "1 hour/level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "The subject or subjects can move through any type of terrain and leave "
            "neither footprints nor scent. Tracking the subjects is impossible by "
            "nonmagical means."
        ),
    },
    {
        "id": "shillelagh",
        "name": "Shillelagh",
        "level_druid": 1, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "One touched club or quarterstaff",
        "duration": "1 min./level",
        "save": "Will negates (object)",
        "spell_resistance": "Yes (object)",
        "description": (
            "Your own nonmagical club or quarterstaff becomes a +1 weapon and deals "
            "damage as if it were two size categories larger (a Medium club deals 2d6; "
            "a Medium quarterstaff deals 2d6/2d6). Only you can wield the weapon "
            "effectively for the duration of the spell."
        ),
    },
    # ── Level 2 ────────────────────────────────────────────────────────────
    {
        "id": "barkskin",
        "name": "Barkskin",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Living creature touched",
        "duration": "10 min./level",
        "save": "None",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "Barkskin toughens a creature's skin. The effect grants a +2 enhancement "
            "bonus to the creature's existing natural armor bonus. This enhancement "
            "bonus increases by 1 for every three caster levels above 3rd, "
            "to a maximum of +5 at 12th level."
        ),
    },
    {
        "id": "summon_natures_ally_ii",
        "name": "Summon Nature's Ally II",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Conjuration (Summoning)",
        "cast_time": "1 round",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "One summoned creature",
        "duration": "1 round/level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "This spell summons a more powerful nature creature to fight on your "
            "behalf. It appears where you designate and acts immediately, on your "
            "turn. The creature remains for 1 round per caster level."
        ),
    },
    {
        "id": "bear_endurance",
        "name": "Bear's Endurance",
        "level_druid": 2, "level_cleric": 2, "level_wizard": 2,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "1 min./level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "The affected creature gains greater vitality and stamina. The spell "
            "grants the subject a +4 enhancement bonus to Constitution, which adds "
            "the usual benefits to hit points, Fortitude saving throws, and so on."
        ),
    },
    {
        "id": "bull_strength",
        "name": "Bull's Strength",
        "level_druid": 2, "level_cleric": 2, "level_wizard": 2,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "1 min./level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "The subject becomes stronger. The spell grants a +4 enhancement bonus "
            "to Strength, adding the usual benefits to melee attack rolls, melee "
            "damage rolls, and other uses of the Strength modifier."
        ),
    },
    {
        "id": "cat_grace",
        "name": "Cat's Grace",
        "level_druid": 2, "level_cleric": None, "level_wizard": 2,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "1 min./level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "The transmuted creature becomes more graceful, agile, and coordinated. "
            "The spell grants a +4 enhancement bonus to Dexterity, adding the usual "
            "benefits to AC, Reflex saving throws, and other uses of the DEX modifier."
        ),
    },
    {
        "id": "flame_blade",
        "name": "Flame Blade",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "0 ft",
        "target": "Sword-like beam",
        "duration": "1 min./level",
        "save": "None",
        "spell_resistance": "Yes",
        "description": (
            "A 3-foot-long, blazing beam of red-hot fire springs forth from your "
            "hand. Attacks with the flame blade are melee touch attacks. "
            "The blade deals 1d8 fire damage +1 per two caster levels (max +10)."
        ),
    },
    {
        "id": "heat_metal",
        "name": "Heat Metal",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "Metal equipment of one creature per two levels",
        "duration": "7 rounds",
        "save": "Will negates (object)",
        "spell_resistance": "Yes (object)",
        "description": (
            "Heat metal makes metal extremely warm. Unattended, nonmagical metal "
            "gets no saving throw. An item in a creature's possession uses the "
            "creature's saving throw bonus unless its own bonus is higher."
        ),
    },
    {
        "id": "hold_animal",
        "name": "Hold Animal",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Enchantment (Compulsion)",
        "cast_time": "1 standard action",
        "range": "Medium (100 ft + 10 ft/level)",
        "target": "One animal",
        "duration": "1 round/level",
        "save": "Will negates",
        "spell_resistance": "Yes",
        "description": (
            "The subject becomes paralyzed and freezes in place. It is aware and "
            "breathes normally but cannot take any actions, even speech. "
            "A winged creature who is held cannot flap its wings and falls."
        ),
    },
    {
        "id": "owl_wisdom",
        "name": "Owl's Wisdom",
        "level_druid": 2, "level_cleric": 2, "level_wizard": 2,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "1 min./level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "The transmuted creature becomes wiser. The spell grants a +4 "
            "enhancement bonus to Wisdom, adding the usual benefits to "
            "Wisdom-based skills and Will saving throws."
        ),
    },
    {
        "id": "reduce_animal",
        "name": "Reduce Animal",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "One willing animal of Small, Medium, Large, or Huge size",
        "duration": "1 hour/level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "This spell causes a touched animal to shrink by one size category. "
            "A Large animal becomes Medium, a Medium animal becomes Small, etc. "
            "The size change has all the normal effects."
        ),
    },
    {
        "id": "animal_messenger",
        "name": "Animal Messenger",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Enchantment (Compulsion)",
        "cast_time": "1 standard action",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "One Tiny animal",
        "duration": "One day/level",
        "save": "None",
        "spell_resistance": "Yes",
        "description": (
            "You compel a Tiny animal to go to a spot you designate. The most "
            "common use for this spell is to send a message to an associate. The "
            "animal travels to the spot you designate at its normal movement rate. "
            "You can attach a small item or note to the animal. The animal avoids "
            "combat and dangerous situations."
        ),
    },
    {
        "id": "animal_trance",
        "name": "Animal Trance",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Enchantment (Compulsion)",
        "cast_time": "1 standard action",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "Animals or magical beasts with Intelligence 1 or 2",
        "duration": "Concentration",
        "save": "Will negates",
        "spell_resistance": "Yes",
        "description": (
            "Your swaying motions and music (or singing, or chanting) compel animals "
            "and magical beasts to do nothing but watch you. Only one animal or "
            "magical beast can be fascinated at a time, with a maximum total of 2d6 "
            "HD of creatures affected. The fascinated creature stands or sits quietly, "
            "watching you for as long as you concentrate on the spell."
        ),
    },
    {
        "id": "chill_metal",
        "name": "Chill Metal",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "Metal equipment of one creature per two levels",
        "duration": "7 rounds",
        "save": "Will negates (object)",
        "spell_resistance": "Yes (object)",
        "description": (
            "Chill metal makes metal extremely cold. Unattended, nonmagical metal "
            "gets no saving throw. Chilled metal deals cold damage each round: "
            "round 1 — 0; round 2 — 1d4; rounds 3–5 — 2d4; round 6 — 1d4; "
            "round 7 — 0. A creature in contact with chilled metal can drop it "
            "as a free action."
        ),
    },
    {
        "id": "delay_poison",
        "name": "Delay Poison",
        "level_druid": 2, "level_cleric": 2, "level_wizard": None,
        "school": "Conjuration (Healing)",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "1 hour/level",
        "save": "Fortitude negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "The subject becomes temporarily immune to poison. Any poison in its "
            "system or any poison to which it is exposed during the spell's duration "
            "does not affect the subject until the spell's duration has expired. "
            "Delay poison does not cure any damage that poison may have already done."
        ),
    },
    {
        "id": "fire_trap",
        "name": "Fire Trap",
        "level_druid": 2, "level_cleric": None, "level_wizard": 4,
        "school": "Abjuration",
        "cast_time": "10 minutes",
        "range": "Touch",
        "target": "Object touched",
        "duration": "Permanent until discharged",
        "save": "Reflex half",
        "spell_resistance": "Yes",
        "description": (
            "Fire trap wards a chest or other closeable container. When someone "
            "other than you opens the object, the trap explodes with a burst of "
            "flame dealing 1d4 + 1/level points of fire damage (max +20). "
            "The DC for the Reflex save is 10 + spell level + your Wis modifier. "
            "This spell has a material component cost of 25 gp."
        ),
    },
    {
        "id": "flaming_sphere",
        "name": "Flaming Sphere",
        "level_druid": 2, "level_cleric": None, "level_wizard": 2,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "Medium (100 ft + 10 ft/level)",
        "target": "5-ft.-diameter sphere",
        "duration": "1 round/level",
        "save": "Reflex negates",
        "spell_resistance": "Yes",
        "description": (
            "A burning globe of fire rolls in whichever direction you point and burns "
            "those it strikes. It moves 30 feet per round. As part of this movement, "
            "it can ascend or jump over walls. It rolls over barriers less than 4 feet "
            "tall. The sphere deals 2d6 points of fire damage to any creature it "
            "strikes. After rolling, the sphere can detonate on your command."
        ),
    },
    {
        "id": "fog_cloud",
        "name": "Fog Cloud",
        "level_druid": 2, "level_cleric": None, "level_wizard": 2,
        "school": "Conjuration (Creation)",
        "cast_time": "1 standard action",
        "range": "Medium (100 ft + 10 ft/level)",
        "target": "Fog spreads in 20-ft. radius, 20 ft. high",
        "duration": "10 min./level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "A bank of fog billows out from the point you designate. The fog obscures "
            "all sight, including darkvision, beyond 5 feet. A creature within 5 feet "
            "has concealment (20% miss chance). Creatures farther away have total "
            "concealment (50% miss chance). A moderate wind disperses the fog in "
            "4 rounds; a strong wind disperses it in 1 round."
        ),
    },
    {
        "id": "gust_of_wind",
        "name": "Gust of Wind",
        "level_druid": 2, "level_cleric": None, "level_wizard": 2,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "60 ft",
        "target": "Line-shaped gust of severe wind emanating from you",
        "duration": "1 round",
        "save": "Fortitude negates",
        "spell_resistance": "Yes",
        "description": (
            "This spell creates a severe blast of air (approximately 50 mph) that "
            "originates from you, affecting all creatures in its path. A Tiny or "
            "smaller creature is knocked down and rolled 1d4×10 feet. A Small "
            "creature is knocked down. A Medium creature is unable to move forward. "
            "Larger creatures are unaffected. The gust also automatically extinguishes "
            "unprotected flames and may extinguish protected flames."
        ),
    },
    {
        "id": "resist_energy",
        "name": "Resist Energy",
        "level_druid": 2, "level_cleric": 2, "level_wizard": 2,
        "school": "Abjuration",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "10 min./level",
        "save": "Fortitude negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "This abjuration grants a creature limited protection from damage of "
            "whichever one of five energy types you select: acid, cold, electricity, "
            "fire, or sonic. The subject gains energy resistance 10 against the "
            "energy type chosen, increasing to 20 at caster level 7th and 30 at "
            "caster level 11th."
        ),
    },
    {
        "id": "soften_earth_stone",
        "name": "Soften Earth and Stone",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "10-ft. square/level; see text",
        "duration": "Instantaneous",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "When this spell is cast, all natural, undressed earth or stone in the "
            "spell's area is softened. Wet earth becomes thick mud. Dry earth becomes "
            "loose sand or dirt. Hard stone becomes soft clay, easily molded or "
            "shaped, crumbling if weight is placed on it. Any creature on a surface "
            "of wet earth must make a DC 15 Reflex save or be mired down."
        ),
    },
    {
        "id": "spider_climb",
        "name": "Spider Climb",
        "level_druid": 2, "level_cleric": None, "level_wizard": 2,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "10 min./level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "The subject can climb and travel on vertical surfaces or even traverse "
            "ceilings as well as a spider does. The affected creature must have its "
            "hands free to climb in this manner. The subject gains a climb speed of "
            "20 feet; furthermore, it need not make Climb checks to traverse a "
            "vertical or horizontal surface."
        ),
    },
    {
        "id": "summon_swarm",
        "name": "Summon Swarm",
        "level_druid": 2, "level_cleric": None, "level_wizard": 2,
        "school": "Conjuration (Summoning)",
        "cast_time": "1 round",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "One swarm of bats, rats, or spiders",
        "duration": "Concentration + 2 rounds",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "You summon a swarm of bats, rats, or spiders (your choice), which "
            "immediately fills the designated area. Any creature vulnerable to the "
            "swarm type you choose takes damage equal to the swarm's attack each "
            "round. The swarm attacks any creature within its area."
        ),
    },
    {
        "id": "tree_shape",
        "name": "Tree Shape",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Personal",
        "target": "You",
        "duration": "1 hour/level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "By means of this spell, you are able to assume the form of a Large "
            "living tree or shrub or a Large dead tree trunk with a small number of "
            "limbs. The closest inspection cannot reveal that the tree in question "
            "is actually a magically concealed creature. Your hit points and saving "
            "throws are unchanged while in this form."
        ),
    },
    {
        "id": "warp_wood",
        "name": "Warp Wood",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "1 Small wooden object/level, all within 30 ft of each other",
        "duration": "Instantaneous",
        "save": "Will negates (object)",
        "spell_resistance": "Yes (object)",
        "description": (
            "You cause wood to bend and warp, permanently destroying its straightness, "
            "form, and strength. A warped door springs open (or shut) and cannot "
            "easily be opened. Warped ranged weapons are useless. A warped melee "
            "weapon causes a –4 penalty on attack rolls. You may warp as many as "
            "1 Small or smaller objects per caster level; use the size modifiers from "
            "the item's weight to determine how many 'objects' a larger item counts as."
        ),
    },
    {
        "id": "wood_shape",
        "name": "Wood Shape",
        "level_druid": 2, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "One touched piece of wood no larger than 10 cu. ft. + 1 cu. ft./level",
        "duration": "Instantaneous",
        "save": "Will negates (object)",
        "spell_resistance": "Yes (object)",
        "description": (
            "Wood shape enables you to form one existing piece of wood into any shape "
            "that suits your purpose. While it is possible to make crude furniture, "
            "doors, and so forth, fine detail isn't possible. There is a 30% chance "
            "that any shape that includes moving parts simply doesn't work."
        ),
    },
    # ── Level 3 ────────────────────────────────────────────────────────────
    {
        "id": "call_lightning",
        "name": "Call Lightning",
        "level_druid": 3, "level_cleric": None, "level_wizard": None,
        "school": "Evocation",
        "cast_time": "1 round",
        "range": "Medium (100 ft + 10 ft/level)",
        "target": "One or more 5-ft.-wide, 30-ft.-long vertical lines of lightning",
        "duration": "1 min./level",
        "save": "Reflex half",
        "spell_resistance": "Yes",
        "description": (
            "Immediately upon completing the spell, and once per round thereafter, "
            "you may call down a 5-foot-wide, 30-foot-long vertical bolt of "
            "lightning that deals 3d6 points of electricity damage."
        ),
    },
    {
        "id": "cure_moderate_wounds",
        "name": "Cure Moderate Wounds",
        "level_druid": 3, "level_cleric": 2, "level_wizard": None,
        "school": "Conjuration (Healing)",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "Instantaneous",
        "save": "Will half (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "When laying your hand upon a living creature, you channel positive "
            "energy that cures 2d8 points of damage +1 point per caster level "
            "(maximum +10)."
        ),
    },
    {
        "id": "plant_growth",
        "name": "Plant Growth",
        "level_druid": 3, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "See text",
        "target": "See text",
        "duration": "Instantaneous",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "Plant growth has different effects depending on the version chosen. "
            "Overgrowth: Causes normal vegetation within long range (400 ft) to "
            "become thick and overgrown. Enrichment: Raises plant productivity "
            "within a half-mile to one third above normal."
        ),
    },
    {
        "id": "poison",
        "name": "Poison",
        "level_druid": 3, "level_cleric": 4, "level_wizard": None,
        "school": "Necromancy",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Living creature touched",
        "duration": "Instantaneous; see text",
        "save": "Fortitude negates",
        "spell_resistance": "Yes",
        "description": (
            "Calling upon the venomous powers of natural predators, you infect the "
            "subject with a horrible poison. The poison deals 1d10 points of "
            "Constitution damage immediately and another 1d10 points 1 minute later."
        ),
    },
    {
        "id": "protection_energy",
        "name": "Protection from Energy",
        "level_druid": 3, "level_cleric": 3, "level_wizard": 3,
        "school": "Abjuration",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "10 min./level or until discharged",
        "save": "Fortitude negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "Protection from energy grants temporary immunity to the type of energy "
            "you specify (acid, cold, electricity, fire, or sonic). "
            "When the spell absorbs 12 points per caster level (maximum 120 points) "
            "of energy damage, it is discharged."
        ),
    },
    {
        "id": "sleet_storm",
        "name": "Sleet Storm",
        "level_druid": 3, "level_cleric": None, "level_wizard": 3,
        "school": "Conjuration (Creation)",
        "cast_time": "1 standard action",
        "range": "Long (400 ft + 40 ft/level)",
        "target": "Cylinder (40-ft. radius, 20 ft. high)",
        "duration": "1 round/level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "Driving sleet blocks all sight within it and causes the ground in the "
            "area to be icy. A character moving through the area falls unless he "
            "succeeds on a DC 10 Balance check for each square of movement."
        ),
    },
    {
        "id": "spike_growth",
        "name": "Spike Growth",
        "level_druid": 3, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Medium (100 ft + 10 ft/level)",
        "target": "One 20-ft.-radius area",
        "duration": "1 hour/level",
        "save": "Reflex partial",
        "spell_resistance": "Yes",
        "description": (
            "Any ground-covering vegetation in the spell's area becomes very "
            "hard and sharply pointed without changing its appearance. "
            "The spikes deal 1d4 points of piercing damage for each 5 feet of "
            "movement through the area."
        ),
    },
    {
        "id": "stone_shape",
        "name": "Stone Shape",
        "level_druid": 3, "level_cleric": 3, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Stone or stone object touched, up to 10 cu. ft. + 1 cu. ft./level",
        "duration": "Instantaneous",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "You can form an existing piece of stone into any shape that suits your "
            "purpose. While it's possible to make crude coffers, doors, and so forth "
            "with stone shape, fine detail isn't possible."
        ),
    },
    {
        "id": "summon_natures_ally_iii",
        "name": "Summon Nature's Ally III",
        "level_druid": 3, "level_cleric": None, "level_wizard": None,
        "school": "Conjuration (Summoning)",
        "cast_time": "1 round",
        "range": "Close (25 ft + 5 ft/2 levels)",
        "target": "One summoned creature",
        "duration": "1 round/level",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "This spell summons a more powerful nature creature to fight on your "
            "behalf. It appears where you designate and acts immediately, on your turn."
        ),
    },
    {
        "id": "water_breathing",
        "name": "Water Breathing",
        "level_druid": 3, "level_cleric": 3, "level_wizard": 3,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Living creatures touched",
        "duration": "2 hours/level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "The transmuted creatures can breathe water freely. Divide the duration "
            "evenly among all the creatures you touch. The spell does not make "
            "creatures unable to breathe air."
        ),
    },
    {
        "id": "wind_wall",
        "name": "Wind Wall",
        "level_druid": 3, "level_cleric": 3, "level_wizard": 3,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "Medium (100 ft + 10 ft/level)",
        "target": "Wall up to 10 ft./level long and 5 ft./level high (S)",
        "duration": "1 round/level",
        "save": "None; see text",
        "spell_resistance": "Yes",
        "description": (
            "An invisible vertical curtain of wind appears, 2 feet thick. "
            "Small flying creatures cannot pass through the wall. Arrows and bolts "
            "are deflected upward and miss; other ranged weapons have a 30% miss chance."
        ),
    },
    # ── Level 4 ────────────────────────────────────────────────────────────
    {
        "id": "flame_strike",
        "name": "Flame Strike",
        "level_druid": 4, "level_cleric": 5, "level_wizard": None,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "Medium (100 ft + 10 ft/level)",
        "target": "Cylinder (10-ft. radius, 40 ft. high)",
        "duration": "Instantaneous",
        "save": "Reflex half",
        "spell_resistance": "Yes",
        "description": (
            "A flame strike produces a vertical column of divine fire dealing "
            "1d6 points of damage per caster level (maximum 15d6). Half the damage "
            "is fire damage, the other half is divine power not subject to fire "
            "protection spells."
        ),
    },
    {
        "id": "ice_storm",
        "name": "Ice Storm",
        "level_druid": 4, "level_cleric": None, "level_wizard": 4,
        "school": "Evocation",
        "cast_time": "1 standard action",
        "range": "Long (400 ft + 40 ft/level)",
        "target": "Cylinder (20-ft. radius, 40 ft. high)",
        "duration": "1 full round",
        "save": "None",
        "spell_resistance": "Yes",
        "description": (
            "Great magical hailstones pound down, dealing 3d6 bludgeoning and 2d6 "
            "cold damage to every creature in the area. The hail also causes the "
            "ground in the area to be difficult terrain."
        ),
    },
    {
        "id": "freedom_movement",
        "name": "Freedom of Movement",
        "level_druid": 4, "level_cleric": 4, "level_wizard": None,
        "school": "Abjuration",
        "cast_time": "1 standard action",
        "range": "Personal or touch",
        "target": "You or creature touched",
        "duration": "10 min./level",
        "save": "Will negates (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "This spell enables you or a creature you touch to move and attack "
            "normally for the duration of the spell, even under the influence of "
            "magic that usually impedes movement, such as paralysis, solid fog, "
            "slow, and web."
        ),
    },
    {
        "id": "reincarnate",
        "name": "Reincarnate",
        "level_druid": 4, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "10 minutes",
        "range": "Touch",
        "target": "Dead creature touched",
        "duration": "Instantaneous",
        "save": "None",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "With this spell, you bring back a dead creature in another body, "
            "provided that its death occurred no more than one week before the "
            "casting of the spell and the subject's soul is free and willing to return."
        ),
    },
    # ── Level 5 ────────────────────────────────────────────────────────────
    {
        "id": "animal_growth",
        "name": "Animal Growth",
        "level_druid": 5, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "1 standard action",
        "range": "Medium (100 ft + 10 ft/level)",
        "target": "Up to one animal per two levels",
        "duration": "1 min./level",
        "save": "Fortitude negates",
        "spell_resistance": "Yes",
        "description": (
            "One animal per two levels doubles in size and eight times its normal "
            "weight, changing size by one category. The animal gets +8 Strength and "
            "+4 Constitution, but -2 Dexterity and -1 on attacks and AC."
        ),
    },
    {
        "id": "commune_nature",
        "name": "Commune with Nature",
        "level_druid": 5, "level_cleric": None, "level_wizard": None,
        "school": "Divination",
        "cast_time": "10 minutes",
        "range": "Personal",
        "target": "You",
        "duration": "Instantaneous",
        "save": "None",
        "spell_resistance": "No",
        "description": (
            "You become one with nature, sensing information about the land "
            "around you. In natural settings, the spell operates in a radius of "
            "1 mile per caster level."
        ),
    },
    {
        "id": "cure_critical_wounds",
        "name": "Cure Critical Wounds",
        "level_druid": 5, "level_cleric": 4, "level_wizard": None,
        "school": "Conjuration (Healing)",
        "cast_time": "1 standard action",
        "range": "Touch",
        "target": "Creature touched",
        "duration": "Instantaneous",
        "save": "Will half (harmless)",
        "spell_resistance": "Yes (harmless)",
        "description": (
            "When laying your hand upon a living creature, you channel positive "
            "energy that cures 4d8 points of damage +1 point per caster level "
            "(maximum +20)."
        ),
    },
    {
        "id": "awaken",
        "name": "Awaken",
        "level_druid": 5, "level_cleric": None, "level_wizard": None,
        "school": "Transmutation",
        "cast_time": "24 hours",
        "range": "Touch",
        "target": "Animal or tree touched",
        "duration": "Instantaneous",
        "save": "Will negates",
        "spell_resistance": "Yes",
        "description": (
            "You awaken a tree or animal to humanlike sentience. The awakened "
            "animal or tree is friendly toward you. An awakened tree has "
            "characteristics as a treant. An awakened animal gains 3d6 Intelligence "
            "and +1d3 Charisma."
        ),
    },
]

# ---------------------------------------------------------------------------
# Skill data
# ---------------------------------------------------------------------------

SKILLS: list[dict] = [
    {"id": "appraise",           "name": "Appraise",             "ability": "int", "trained_only": 0,
     "description": "You can appraise common or well-known objects with a DC 12 Appraise check. Rare or exotic items require a DC 15–25 check. Failure means you estimate the value at 50%–150% of its actual value (DM determines). A magnifying glass gives a +2 circumstance bonus on checks for small or detailed items."},
    {"id": "balance",            "name": "Balance",              "ability": "dex", "trained_only": 0,
     "description": "You can walk on a precarious surface. A successful check lets you move at half speed along the surface. On a failure by 4 or less you can't move; on a failure by 5 or more you fall. DC 10 for a 2–6 inch wide surface; DC 15 for 7–11 inches; DC 20 for 1–6 inches; DC 25 for less than 1 inch. Being attacked while balancing forces a new check (DC = attack roll if hit)."},
    {"id": "bluff",              "name": "Bluff",                "ability": "cha", "trained_only": 0,
     "description": "Bluff is opposed by the target's Sense Motive check. A successful Bluff can convince someone that something false is true, send a secret message, feint in combat, or imply a meaning other than the one actually stated. A feint in combat (DC = defender's BAB + Wis mod) lets you deny the target their Dex bonus to AC for your next attack."},
    {"id": "climb",              "name": "Climb",                "ability": "str", "trained_only": 0,
     "description": "With a successful Climb check you can advance up, down, or across a slope, wall, or other steep incline at one-quarter your normal speed as a move action. A DC 0 slope is not steep enough to require a check. DC 5 for a rope with a wall, DC 15 for a dungeon wall, DC 25 for a smooth surface. You need both hands free to climb. Failure by 4 or less means no progress; failure by 5 or more means you fall."},
    {"id": "concentration",      "name": "Concentration",        "ability": "con", "trained_only": 0,
     "description": "You must make a Concentration check whenever you might be distracted while engaged in an activity requiring your full attention (such as spellcasting). If you fail, the distraction interrupts the activity. Spellcasting in combat: DC 10 + damage taken (if hurt) or DC 10 + spell level (to cast defensively). Also used to avoid losing a spell when grappled, pinned, or subject to violent motion."},
    {"id": "craft",              "name": "Craft",                "ability": "int", "trained_only": 0,
     "description": "You are skilled in a craft (alchemy, armorsmithing, bowmaking, etc.). A Craft check represents a week of work. The DC and the item's price in silver pieces determine progress. You can also use Craft to evaluate items of that type (DC 15). Druids and rangers may craft items from natural materials without needing Craft tools as a bonus."},
    {"id": "decipher_script",    "name": "Decipher Script",      "ability": "int", "trained_only": 1,
     "description": "You can decipher writing in an unfamiliar language or a message written in an incomplete or archaic form. DC 20 for a simple message, DC 25 for standard text, DC 30 for intricate, obscure, or ancient writing. Takes 1 minute per page. Failure by 5+ gives a false reading."},
    {"id": "diplomacy",          "name": "Diplomacy",            "ability": "cha", "trained_only": 0,
     "description": "Use Diplomacy to persuade others to agree with your point of view or to change their attitude toward you or someone else. The DC depends on the target's starting attitude: Hostile (DC 25+5), Unfriendly (DC 20), Indifferent (DC 15), Friendly (DC 10), Helpful (DC 5). Improving attitude by two steps or more requires beating a much higher DC. A Diplomacy check takes at least 1 full minute."},
    {"id": "disable_device",     "name": "Disable Device",       "ability": "int", "trained_only": 1,
     "description": "You can disarm traps and other small mechanical devices. DC 20 for simple devices (takes 1 round), DC 21–30 for tricky devices (1d4 rounds), DC 30+ for very tricky devices (2d4 rounds). Working without thieves' tools imposes a –2 penalty. If you exceed the DC by 10 or more, you can move the device to a new location or reset it after disarming."},
    {"id": "disguise",           "name": "Disguise",             "ability": "cha", "trained_only": 0,
     "description": "You can change your appearance and voice. The check is opposed by an observer's Spot check. Disguising as a different gender (−2), race (−2), or age category (−2 per step) applies penalties. Using a disguise kit gives a +2 circumstance bonus. A disguise takes 1d3×10 minutes to apply. A character who is not disguising themselves doesn't need a check, but a creature that has reason to be suspicious gets a Spot check."},
    {"id": "escape_artist",      "name": "Escape Artist",        "ability": "dex", "trained_only": 0,
     "description": "Escape from restraints: DC 20 for rope bonds (opposed by binder's Use Rope +10), DC 30 for manacles, DC 35 for masterwork manacles. Squeeze through tight space: DC 30 for a tight squeeze (move at 1/4 speed), DC 35 for extremely tight squeeze. Escape from a net or entangle spell: DC 20. Escape from a grapple: opposed by opponent's grapple check. Using rope bonds: takes 1 minute; tight spaces: 1 minute per 5 feet."},
    {"id": "forgery",            "name": "Forgery",              "ability": "int", "trained_only": 0,
     "description": "You can falsify documents, including handwriting. Forging a document takes 1 minute per page. The check is opposed by the reader's Forgery check (to notice it). Familiarity with the handwriting being forged gives a +4 bonus to the forger. Dissimilarity between the forged and original script gives the reader a +4 bonus."},
    {"id": "gather_information", "name": "Gather Information",   "ability": "cha", "trained_only": 0,
     "description": "By spending 1d4+1 hours canvassing a settlement and speaking with locals, you can gather rumors, legends, and other information about a topic (DC 10). The DM sets the DC based on how obscure or secret the information is. You can improve your result by spending more coin: for every 1 gp spent, add +1 to the roll (up to the DM's discretion)."},
    {"id": "handle_animal",      "name": "Handle Animal",        "ability": "cha", "trained_only": 1,
     "description": "Use Handle Animal to drive, command, and train animals. Push an animal to perform a trick beyond its training: DC 25. Command an animal to perform a trained trick: DC 10. Push an untrained animal: DC 15. Teach an animal a new trick: DC 15–20 (1 week). Train an animal for a general purpose: DC 15–20 (varies). Wild empathy (druids and rangers) works like Diplomacy against animals, rolling 1d20 + class level + Cha modifier."},
    {"id": "heal",               "name": "Heal",                 "ability": "wis", "trained_only": 0,
     "description": "First aid (DC 15, standard action): stabilize a dying character and prevent further damage loss. Long-term care (DC 15, 8 hours, requires healer's kit): doubles natural healing rate. Treat wounds from caltrops, spike growth, or spike stones (DC 15): removes the penalty. Treat poison (DC = poison's save DC): patient uses your Heal check result instead of their own save. Treat disease (DC = disease's save DC): patient uses your Heal check. Diagnose illness: DC 15."},
    {"id": "hide",               "name": "Hide",                 "ability": "dex", "trained_only": 0,
     "description": "Your Hide check is opposed by Spot checks of anyone who might notice you. You can hide behind cover (at least 1/4 obscured) or with concealment. While hiding you can move at half speed without penalty; moving faster imposes a −5 penalty. Sniping: after making a ranged attack, immediately re-hide with a −20 penalty. Size modifiers: Fine +16, Diminutive +12, Tiny +8, Small +4, Large −4, Huge −8, Gargantuan −12, Colossal −16."},
    {"id": "intimidate",         "name": "Intimidate",           "ability": "cha", "trained_only": 0,
     "description": "Coerce or threaten a creature into temporary cooperation. Demoralizing in combat (DC 10 + target's HD + Wis mod, standard action): the target is shaken for 1 round plus 1 round per 5 you exceed the DC. Influencing attitude: as Diplomacy but only to Unfriendly→Friendly and only lasts d6×10 minutes. Creatures with 4+ more HD than you are immune to combat demoralization."},
    {"id": "jump",               "name": "Jump",                 "ability": "str", "trained_only": 0,
     "description": "A running jump (at least 20 ft run-up) requires DC 4 per foot for long jump, DC 4 × height in feet for high jump. Without run-up, double the DC. A successful high jump lets you reach up to 8 feet above the jump's apex. Failure by 4 or less lands short; failure by 5+ means you fall. DC is halved if the character is in a gravity-reduced environment or benefits from a speed spell. Each point of encumbrance penalty also applies here."},
    {"id": "knowledge_arcana",   "name": "Knowledge (Arcana)",   "ability": "int", "trained_only": 1,
     "description": "Covers ancient mysteries, magic traditions, arcane symbols, cryptic phrases, constructs, dragons, and magical beasts. A DC 10 check lets you recall a relevant legend or piece of information. Higher DCs apply to more obscure or esoteric knowledge. You can also identify spells being cast (DC 15 + spell level) and recognize magic items you've encountered (DC 20)."},
    {"id": "knowledge_dungeoneering", "name": "Knowledge (Dungeoneering)", "ability": "int", "trained_only": 1,
     "description": "Covers aberrations, cave systems, underground geography, dungeon hazards (oozes, fungi, slimes), and subterranean ecosystems. DC 10 for common dungeon knowledge, DC 15–20 for obscure or specific creatures. Useful for identifying creature types, their abilities, and natural habits found underground."},
    {"id": "knowledge_geography","name": "Knowledge (Geography)","ability": "int", "trained_only": 1,
     "description": "Covers lands, terrain, climate, people, and fauna across the world. Useful for navigation, knowing about distant cultures, and identifying regional hazards. DC 10 for major kingdoms and capital cities, DC 15–20 for lesser-known regions. Also allows identification of animals, vermin, and magical creatures tied to geography."},
    {"id": "knowledge_history",  "name": "Knowledge (History)",  "ability": "int", "trained_only": 1,
     "description": "Covers wars, colonies, migrations, and founding of civilizations. Also covers legendary heroes, famous dynasties, and ancient empires. Useful for identifying historical artifacts and understanding context. DC 10 for widely-known history, DC 20–30 for obscure or ancient lore."},
    {"id": "knowledge_local",    "name": "Knowledge (Local)",    "ability": "int", "trained_only": 1,
     "description": "Covers legends, personalities, inhabitants, laws, customs, traditions, and humanoids of a particular region. DC 10 to know about well-known local figures or laws, DC 15–25 for rumors, criminal guilds, or hidden factions. Useful for navigating social situations in a specific area."},
    {"id": "knowledge_nature",   "name": "Knowledge (Nature)",   "ability": "int", "trained_only": 1,
     "description": "Covers animals, fey, giants, monstrous humanoids, plants, seasons and cycles, weather, and vermin. DC 10 to identify common natural creatures or phenomena, DC 15–20 for rare species or unusual natural events. Druids and rangers treat this as a class skill. A successful check can also reveal a creature's vulnerabilities or special abilities."},
    {"id": "knowledge_nobility", "name": "Knowledge (Nobility)",  "ability": "int", "trained_only": 1,
     "description": "Covers lineages, heraldry, family trees, mottoes, personalities, and customs of noble houses. DC 10 for well-known noble families, DC 20+ for obscure titles or noble secrets. Useful for court intrigue, recognizing insignia, and knowing the proper protocols and forms of address."},
    {"id": "knowledge_planes",   "name": "Knowledge (The Planes)","ability": "int", "trained_only": 1,
     "description": "Covers the Inner Planes, Outer Planes, the Astral Plane, the Ethereal Plane, outsiders, and planar travel. DC 10 to know basic planar geography, DC 15–25 for specific planar denizens or portals. Essential for identifying extraplanar creatures, spells that interact with planes, and navigating non-material realms."},
    {"id": "knowledge_religion", "name": "Knowledge (Religion)",  "ability": "int", "trained_only": 1,
     "description": "Covers gods and goddesses, mythic history, ecclesiastic tradition, holy symbols, and undead. DC 10 for widely-worshipped deities, DC 15–20 for obscure cults or divine mysteries. Also used to identify undead creatures and their weaknesses. Clerics and paladins treat this as a class skill."},
    {"id": "listen",             "name": "Listen",               "ability": "wis", "trained_only": 0,
     "description": "Make a Listen check to hear things. DC 0 for a person speaking loudly nearby, DC 5 for a whispered conversation 5 ft away, DC 10+ for further distances or other obstructions. Each 10 feet of distance adds +2 to DC; a door adds +5; a stone wall adds +15. While asleep your Listen check takes a −10 penalty."},
    {"id": "move_silently",      "name": "Move Silently",        "ability": "dex", "trained_only": 0,
     "description": "Move Silently is opposed by Listen checks of anyone who might hear you. Moving at half speed or less gives no penalty; moving at full speed imposes a −5 penalty; running or charging imposes a −20 penalty. Armor check penalty applies. Success allows you to move without being heard by nearby creatures."},
    {"id": "open_lock",          "name": "Open Lock",            "ability": "dex", "trained_only": 1,
     "description": "Pick or open a lock. DC 20 for a simple lock (1 round), DC 25 for an average lock, DC 30 for a good lock, DC 40 for an amazing lock. Requires thieves' tools; without them you take a −2 penalty and can only attempt DC 20 locks. Masterwork thieves' tools give a +2 circumstance bonus. An open lock check takes a full-round action."},
    {"id": "perform",            "name": "Perform",              "ability": "cha", "trained_only": 0,
     "description": "You can practice a form of performance (acting, comedy, dance, keyboard, oratory, percussion, sing, string, wind). Result: 10 or less = barely adequate; 11–14 = routine; 15–19 = memorable; 20–24 = masterful; 25–29 = extraordinary; 30+ = legendary. Bards use Perform as a class skill for their bardic music and spellcasting abilities."},
    {"id": "profession",         "name": "Profession",           "ability": "wis", "trained_only": 1,
     "description": "You are skilled in a livelihood (herbalist, innkeeper, scribe, shepherd, etc.). A Profession check (DC 10) lets you earn half your check result in gold pieces per week of work. You can also use a Profession check to know specific facts about your trade. Each Profession is a separate skill."},
    {"id": "profession_herbalist","name": "Profession (Herbalist)","ability": "wis", "trained_only": 1,
     "description": "Specialized knowledge of herbs, plants, and their medicinal, culinary, and alchemical uses. DC 10 to identify common herbs and their effects, DC 15–20 for rare or exotic plants. Can be used to gather herbs in the wild (combined with Survival) and to assess the quality of herbal preparations."},
    {"id": "ride",               "name": "Ride",                 "ability": "dex", "trained_only": 0,
     "description": "You can ride a mount. Guide with knees (DC 5, free action): keep control hands-free. Stay in saddle (DC 5): avoid falling. Fight with a war-trained mount (DC 10): direct your mount in combat as a move action instead of standard. Soft fall (DC 15): reduce falling damage. Leap (DC 15): have your mount jump while mounted. Fast mount/dismount (DC 20): mount or dismount as a free action."},
    {"id": "search",             "name": "Search",               "ability": "int", "trained_only": 0,
     "description": "Examine an area to find secret doors, hidden compartments, or concealed traps. DC 10 to find a simple hidden object, DC 20 for a typical secret door or compartment, DC 25+ for a well-hidden trap. Searching a 5-foot square is a full-round action. Elves get a free Search check when passing within 5 ft of a secret or concealed door."},
    {"id": "sense_motive",       "name": "Sense Motive",         "ability": "wis", "trained_only": 0,
     "description": "Hunch (DC 20): you can tell something is off about a person or situation without knowing exactly what. Sense enchantment (DC 25 or 15 for charm/compulsion): detect whether a person is under a magical influence. Discern secret message (DC = sender's Bluff): detect that a Bluffed message has a hidden meaning. Opposed by Bluff for deception."},
    {"id": "sleight_of_hand",    "name": "Sleight of Hand",      "ability": "dex", "trained_only": 1,
     "description": "Palm a coin or small object (DC 10), or pick a pocket or conceal a dagger (DC 20). Observers get an opposed Spot check; if they beat yours, they notice the attempt. A distracted target: −4 to their Spot. Trying to pass a large object (like a sword) unnoticed: −4 to your check. Armor check penalty applies."},
    {"id": "speak_language",     "name": "Speak Language",       "ability": "none","trained_only": 1,
     "description": "Speak Language is not used like a normal skill. Each rank lets you speak and read/write an additional language fluently. Common languages: Abyssal, Aquan, Auran, Celestial, Common, Draconic, Druidic (secret), Dwarven, Elven, Giant, Gnome, Goblin, Gnoll, Halfling, Ignan, Infernal, Orc, Sylvan, Terran, Undercommon. Druidic can only be taken by druids."},
    {"id": "spellcraft",         "name": "Spellcraft",           "ability": "int", "trained_only": 1,
     "description": "Identify a spell being cast (DC 15 + spell level, requires detect magic). Identify a spell from its school (DC 15 + spell level). Learn a spell from a spellbook or scroll (DC 15 + spell level). Prepare a spell from another's spellbook (DC 15). Identify a magic item (DC 25 + caster level, requires detect magic). Determine if an item is magical (DC 15). Counterspell: identify a spell to counter it (DC 15 + spell level)."},
    {"id": "spot",               "name": "Spot",                 "ability": "wis", "trained_only": 0,
     "description": "Spot is used to notice things — hidden creatures, approaching enemies, details in a scene. Opposed by Hide when looking for hidden creatures. DC increases with distance: +1 per 10 ft; −4 if distracted; −5 if the target is not moving. The check can also reveal concealed objects (DC set by DM) or give you more initiative information."},
    {"id": "survival",           "name": "Survival",             "ability": "wis", "trained_only": 0,
     "description": "Get along in the wild (DC 10): find food and water for yourself; DC 15: for one other. Follow tracks (DC varies): 10 for soft ground, 15 for normal, 20 for hard. Predict weather (DC 15): 24 hours ahead; DC 20: 48 hours. Avoid getting lost (DC 15). Keep from becoming lost in fog or storm (DC 15). Gain a +2 bonus on Fortitude saves against severe weather."},
    {"id": "swim",               "name": "Swim",                 "ability": "str", "trained_only": 0,
     "description": "Make a Swim check once per round to swim at one-quarter speed (DC 10 for calm water, DC 15 for rough water, DC 20 for stormy). A successful check at DC 15 lets you swim at half speed; DC 20 at full speed. Failure by 4 or less means no progress; failure by 5 or more means you go underwater. Armor check penalty applies; encumbered characters subtract the penalty from their check."},
    {"id": "tumble",             "name": "Tumble",               "ability": "dex", "trained_only": 1,
     "description": "Fall safely (DC 15): reduce damage from a fall of any height by 1d6. Move through a threatened square (DC 15): avoid an attack of opportunity. Move through an enemy's space (DC 25): move through without provoking an AoO. Tumble at full speed takes a −10 penalty to the DC. Armor check penalty applies. DC increases by 2 for each opponent beyond the first in a given move."},
    {"id": "use_magic_device",   "name": "Use Magic Device",     "ability": "cha", "trained_only": 1,
     "description": "Activate a magic item that you normally couldn't use. Activate blindly (DC 25): if you don't know what a device does. Decipher written spell (DC 25 + spell level): read a scroll or spellbook. Use a scroll (DC varies): cast the spell on the scroll (DC 20 + caster level). Use a wand (DC 20): if you lack the class ability. Emulate a class feature (DC 20): pretend to have it for the item's purpose. Failure by 10+ triggers a mishap."},
    {"id": "use_rope",           "name": "Use Rope",             "ability": "dex", "trained_only": 0,
     "description": "Tie a firm knot (DC 10, takes 1 minute). Make rope difficult to escape (DC 15, takes 2 minutes; escapee's DC = your check +10). Bind a character (DC 15): target's Escape Artist DC = your check result. Splice rope (DC 15): join two ropes. Tie a special knot (DC 15–20): e.g. bowline, cleat hitch. Throw a rope to a hook (DC 10 + 2 per 10 ft above head height). Secure a grappling hook: DC 10."},
]

# ---------------------------------------------------------------------------
# Feat data
# ---------------------------------------------------------------------------

FEATS: list[dict] = [
    {
        "id": "alertness",
        "name": "Alertness",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You get a +2 bonus on all Listen checks and Spot checks.",
        "normal": None,
        "special": "The master of a familiar gains the benefit of Alertness whenever the familiar is within arm's reach.",
    },
    {
        "id": "augment_summoning",
        "name": "Augment Summoning",
        "type": "General",
        "prerequisites": "Spell Focus (Conjuration)",
        "benefit": "Each creature you conjure with any summon spell gains a +4 enhancement bonus to Strength and Constitution for the duration of the spell that summoned it.",
        "normal": None,
        "special": None,
    },
    {
        "id": "blind_fight",
        "name": "Blind-Fight",
        "type": "General",
        "prerequisites": "None",
        "benefit": "In melee, every time you miss because of concealment, you can reroll your miss chance percentile roll one time to see if you actually hit. An invisible attacker gets no advantages related to hitting you in melee.",
        "normal": None,
        "special": None,
    },
    {
        "id": "cleave",
        "name": "Cleave",
        "type": "General",
        "prerequisites": "Str 13, Power Attack",
        "benefit": "If you deal a creature enough damage to make it drop, you get an immediate, extra melee attack against another creature within reach. You can use this ability once per round.",
        "normal": None,
        "special": None,
    },
    {
        "id": "combat_casting",
        "name": "Combat Casting",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You get a +4 bonus on Concentration checks made to cast a spell or use a spell-like ability while on the defensive or while you are grappling or pinned.",
        "normal": None,
        "special": None,
    },
    {
        "id": "diehard",
        "name": "Diehard",
        "type": "General",
        "prerequisites": "Endurance",
        "benefit": "When reduced to between -1 and -9 hit points, you automatically become stable. When reduced to negative hit points, you may choose to act as if you were disabled, rather than dying.",
        "normal": "A character without this feat who is reduced to between -1 and -9 hit points is unconscious and dying.",
        "special": None,
    },
    {
        "id": "dodge",
        "name": "Dodge",
        "type": "General",
        "prerequisites": "Dex 13",
        "benefit": "During your action, you designate an opponent and receive a +1 dodge bonus to Armor Class against attacks from that opponent. You can select a new opponent on any action.",
        "normal": None,
        "special": None,
    },
    {
        "id": "endurance",
        "name": "Endurance",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You gain a +4 bonus on Swim checks to resist nonlethal damage, Constitution checks to continue running or hold your breath, forced march checks, and Fortitude saves vs. nonlethal damage from starvation, thirst, or environment.",
        "normal": None,
        "special": "A ranger automatically gains Endurance as a bonus feat at 3rd level.",
    },
    {
        "id": "extra_turning",
        "name": "Extra Turning",
        "type": "General",
        "prerequisites": "Ability to turn or rebuke undead",
        "benefit": "Each time you take this feat, you can use your ability to turn or rebuke undead four more times per day than normal.",
        "normal": None,
        "special": "You can gain this feat multiple times. Its effects stack.",
    },
    {
        "id": "extra_wild_shape",
        "name": "Extra Wild Shape",
        "type": "General",
        "prerequisites": "Wild shape class ability",
        "benefit": "You can use your wild shape ability two additional times per day.",
        "normal": None,
        "special": None,
    },
    {
        "id": "great_fortitude",
        "name": "Great Fortitude",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You get a +2 bonus on all Fortitude saving throws.",
        "normal": None,
        "special": None,
    },
    {
        "id": "improved_initiative",
        "name": "Improved Initiative",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You get a +4 bonus on initiative checks.",
        "normal": None,
        "special": None,
    },
    {
        "id": "iron_will",
        "name": "Iron Will",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You get a +2 bonus on all Will saving throws.",
        "normal": None,
        "special": None,
    },
    {
        "id": "lightning_reflexes",
        "name": "Lightning Reflexes",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You get a +2 bonus on all Reflex saving throws.",
        "normal": None,
        "special": None,
    },
    {
        "id": "mobility",
        "name": "Mobility",
        "type": "General",
        "prerequisites": "Dex 13, Dodge",
        "benefit": "You get a +4 dodge bonus to Armor Class against attacks of opportunity caused when you move out of or within a threatened area.",
        "normal": None,
        "special": None,
    },
    {
        "id": "natural_spell",
        "name": "Natural Spell",
        "type": "General",
        "prerequisites": "Wis 13, wild shape ability",
        "benefit": "You can complete the verbal and somatic components of spells while using your wild shape ability. You substitute various sounds and gestures for the normal verbal and somatic components of a spell.",
        "normal": None,
        "special": None,
    },
    {
        "id": "power_attack",
        "name": "Power Attack",
        "type": "General",
        "prerequisites": "Str 13",
        "benefit": "On your action, before making attack rolls for a round, you may choose to subtract a number from all melee attack rolls and add the same number to all melee damage rolls. This number may not exceed your base attack bonus.",
        "normal": None,
        "special": None,
    },
    {
        "id": "run",
        "name": "Run",
        "type": "General",
        "prerequisites": "None",
        "benefit": "When running, you move five times your normal speed (light/no armor) or four times your speed (heavy armor). If you make a jump after a running start, you gain a +4 bonus on your Jump check. You retain your Dexterity bonus to AC while running.",
        "normal": "You move four times your speed while running (light/no armor) or three times your speed (heavy armor), and you lose your Dexterity bonus to AC.",
        "special": None,
    },
    {
        "id": "skill_focus",
        "name": "Skill Focus",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You get a +3 bonus on all checks involving the chosen skill.",
        "normal": None,
        "special": "You can gain this feat multiple times. Each time it applies to a new skill.",
    },
    {
        "id": "spell_focus",
        "name": "Spell Focus",
        "type": "General",
        "prerequisites": "None",
        "benefit": "Add +1 to the Difficulty Class for all saving throws against spells from the school of magic you select.",
        "normal": None,
        "special": "You can gain this feat multiple times. Each time it applies to a new school of magic.",
    },
    {
        "id": "spell_focus_conjuration",
        "name": "Spell Focus (Conjuration)",
        "type": "General",
        "prerequisites": "None",
        "benefit": "Add +1 to the Difficulty Class for all saving throws against Conjuration spells you cast.",
        "normal": None,
        "special": "This is the Conjuration-specific version of Spell Focus.",
    },
    {
        "id": "spell_penetration",
        "name": "Spell Penetration",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You get a +2 bonus on caster level checks made to overcome a creature's spell resistance.",
        "normal": None,
        "special": None,
    },
    {
        "id": "spring_attack",
        "name": "Spring Attack",
        "type": "General",
        "prerequisites": "Dex 13, Dodge, Mobility, BAB +4",
        "benefit": "When using the attack action with a melee weapon, you can move both before and after the attack, provided that your total distance moved is not greater than your speed.",
        "normal": None,
        "special": None,
    },
    {
        "id": "toughness",
        "name": "Toughness",
        "type": "General",
        "prerequisites": "None",
        "benefit": "You gain +3 hit points.",
        "normal": None,
        "special": "A character may gain this feat multiple times. Its effects stack.",
    },
    {
        "id": "weapon_focus",
        "name": "Weapon Focus",
        "type": "Fighter",
        "prerequisites": "Proficiency with selected weapon, BAB +1",
        "benefit": "You gain a +1 bonus on all attack rolls you make using the selected weapon.",
        "normal": None,
        "special": "You can gain this feat multiple times. Each time it applies to a new weapon.",
    },
]

# ---------------------------------------------------------------------------
# Condition data (SRD 3.5)
# ---------------------------------------------------------------------------

CONDITIONS: list[dict] = [
    {
        "id": "blinded",
        "name": "Blinded",
        "summary": "–2 AC, lose DEX bonus, –4 attacks & Spot/Search",
        "description": (
            "The character cannot see. He takes a –2 penalty to Armor Class, loses "
            "his Dexterity bonus to AC (if any), moves at half speed, and takes a "
            "–4 penalty on Search checks and on most Strength- and Dexterity-based "
            "skill checks. All checks and activities that rely on vision automatically "
            "fail. All opponents are considered to have total concealment (50% miss "
            "chance) to the blinded character. Characters who remain blinded for a "
            "long time grow accustomed to these drawbacks and can overcome some of them."
        ),
    },
    {
        "id": "confused",
        "name": "Confused",
        "summary": "Random action each round (d%: babble/do nothing/attack nearest/act normally)",
        "description": (
            "A confused character's actions are determined by rolling d% at the "
            "beginning of his turn: 01–10 Attack caster. 11–20 Act normally. "
            "21–50 Do nothing but babble incoherently. 51–70 Flee from caster. "
            "71–100 Attack nearest creature. A confused character who can't carry "
            "out the indicated action does nothing but babble incoherently. Attackers "
            "are not at any special advantage when attacking a confused character."
        ),
    },
    {
        "id": "cowering",
        "name": "Cowering",
        "summary": "Frozen with fear, –2 AC, loses DEX bonus, no actions",
        "description": (
            "The character is frozen in fear and can take no actions. A cowering "
            "character takes a –2 penalty to Armor Class and loses his Dexterity "
            "bonus (if any)."
        ),
    },
    {
        "id": "dazzled",
        "name": "Dazzled",
        "summary": "–1 on attack rolls and sight-based Perception checks",
        "description": (
            "The creature is unable to see well because of overstimulation of the "
            "eyes. A dazzled creature takes a –1 penalty on attack rolls and "
            "sight-based Perception checks."
        ),
    },
    {
        "id": "deafened",
        "name": "Deafened",
        "summary": "–4 on Initiative, 20% spell failure chance, can't use Listen",
        "description": (
            "A deafened character cannot hear. He takes a –4 penalty on initiative "
            "checks, automatically fails Listen checks, and has a 20% chance of "
            "spell failure when casting spells with verbal components. Characters who "
            "remain deafened for a long time grow accustomed to these drawbacks and "
            "can overcome some of them."
        ),
    },
    {
        "id": "disabled",
        "name": "Disabled",
        "summary": "0 HP: one action/round, strenuous actions deal 1 damage",
        "description": (
            "A character with 0 hit points, or one who has negative hit points but "
            "has become stable and conscious, is disabled. A disabled character may "
            "take a single move or standard action each turn (but not both, nor can "
            "she take full-round actions). She moves at half speed. Taking a standard "
            "action (or any other strenuous action) deals 1 point of damage after the "
            "action is complete."
        ),
    },
    {
        "id": "entangled",
        "name": "Entangled",
        "summary": "–2 attacks, –4 DEX, can't move (or half speed), spells need Concentration",
        "description": (
            "The character is ensnared. Being entangled impedes movement, but does "
            "not entirely prevent it unless the bonds are anchored to an immobile "
            "object or tethered by an opposing force. An entangled creature moves at "
            "half speed, cannot run or charge, and takes a –2 penalty on all attack "
            "rolls and a –4 penalty to Dexterity. An entangled character who "
            "attempts to cast a spell must make a Concentration check (DC 15) or "
            "lose the spell."
        ),
    },
    {
        "id": "exhausted",
        "name": "Exhausted",
        "summary": "–6 STR & DEX, half speed; rest 1 hour to become Fatigued",
        "description": (
            "An exhausted character moves at half his normal speed and takes a –6 "
            "penalty to Strength and Dexterity. After 1 hour of complete rest, an "
            "exhausted character becomes fatigued. A fatigued character becomes "
            "exhausted by doing something else that would normally cause fatigue."
        ),
    },
    {
        "id": "fascinated",
        "name": "Fascinated",
        "summary": "Standing/sitting quietly, –4 Spot & Listen, no actions",
        "description": (
            "A fascinated creature is entranced by a supernatural or spell effect. "
            "The creature stands or sits quietly, taking no actions other than to pay "
            "attention to the fascinating effect, for as long as the effect lasts. It "
            "takes a –4 penalty on skill checks made as reactions, such as Listen "
            "and Spot checks. Any potential threat, such as a hostile creature "
            "approaching, allows the fascinated creature a new saving throw."
        ),
    },
    {
        "id": "fatigued",
        "name": "Fatigued",
        "summary": "–2 STR & DEX, can't run or charge; rest 8 hours to recover",
        "description": (
            "A fatigued character can neither run nor charge and takes a –2 penalty "
            "to Strength and Dexterity. Doing anything that would normally cause "
            "fatigue causes the fatigued character to become exhausted. After 8 hours "
            "of complete rest, fatigued characters are no longer fatigued."
        ),
    },
    {
        "id": "flat_footed",
        "name": "Flat-Footed",
        "summary": "Loses DEX bonus to AC, can't make AoO",
        "description": (
            "A character who has not yet acted during a combat is flat-footed, not "
            "yet reacting normally to the situation. A flat-footed character loses "
            "his Dexterity bonus to AC (if any) and cannot make attacks of opportunity."
        ),
    },
    {
        "id": "frightened",
        "name": "Frightened",
        "summary": "Flees from source, –2 attacks/saves/checks while in sight",
        "description": (
            "A frightened creature flees from the source of its fear as best it can. "
            "If unable to flee, it may fight. A frightened creature takes a –2 "
            "penalty on all attack rolls, saving throws, skill checks, and ability "
            "checks. A frightened creature can use special abilities, including spells, "
            "to flee; indeed, it must use such means if they are the only way to "
            "escape. Frightened is like shaken, except that the creature must flee "
            "if possible."
        ),
    },
    {
        "id": "grappled",
        "name": "Grappled",
        "summary": "–4 DEX, –4 attack (light weapons), no move, spells need Concentration",
        "description": (
            "Engaging a creature in grapple imposes a –4 penalty to Dexterity on "
            "both the grappler and the target. A grappling character may only make "
            "attacks with light weapons or natural attacks at –4. Casting spells "
            "requires a Concentration check (DC 20)."
        ),
    },
    {
        "id": "helpless",
        "name": "Helpless",
        "summary": "DEX 0, coup de grace possible; adjacent enemies get +4 attack",
        "description": (
            "A helpless character is paralyzed, held, bound, sleeping, unconscious, "
            "or otherwise completely at an opponent's mercy. A helpless target is "
            "treated as having a Dexterity of 0 (–5 modifier). Melee attacks against "
            "a helpless character get a +4 bonus (equivalent to attacking a prone "
            "target). Ranged attacks gets no special bonus. A helpless character is "
            "also subject to a coup de grace."
        ),
    },
    {
        "id": "nauseated",
        "name": "Nauseated",
        "summary": "Only one move action/round, no attack/spell/other",
        "description": (
            "Experiencing stomach distress. Nauseated creatures are unable to attack, "
            "cast spells, concentrate on spells, or do anything else requiring "
            "attention. The only action such a character can take is a single move "
            "action per turn."
        ),
    },
    {
        "id": "panicked",
        "name": "Panicked",
        "summary": "Drops held items, flees; –2 attacks/saves/checks",
        "description": (
            "A panicked creature must drop anything it holds and flee at top speed "
            "from the source of its fear, as well as any other dangers it encounters, "
            "along a random path. It can't take any other actions. In addition, the "
            "creature takes a –2 penalty on all saving throws, skill checks, and "
            "ability checks. If cornered, a panicked creature cowers and does not "
            "attack, typically using the total defense action."
        ),
    },
    {
        "id": "paralyzed",
        "name": "Paralyzed",
        "summary": "STR & DEX 0, helpless; adjacent foes get +4 melee, coup de grace",
        "description": (
            "A paralyzed character is frozen in place and unable to move or act. A "
            "paralyzed character has effective Dexterity and Strength scores of 0 "
            "and is helpless, but can take purely mental actions. A winged creature "
            "flying in the air at the time becomes paralyzed and falls. A paralyzed "
            "swimmer can't swim and may drown. A creature can move through a space "
            "occupied by a paralyzed creature — ally or not. Each square occupied by "
            "a paralyzed creature is considered difficult terrain."
        ),
    },
    {
        "id": "prone",
        "name": "Prone",
        "summary": "–4 melee attacks, +4 AC vs ranged, –4 AC vs melee",
        "description": (
            "The character is on the ground. An attacker who is prone has a –4 "
            "penalty on melee attack rolls and cannot use a ranged weapon (except for "
            "a crossbow). A defender who is prone gains a +4 bonus to Armor Class "
            "against ranged attacks, but takes a –4 penalty to AC against melee "
            "attacks. Standing up is a move-equivalent action that provokes an attack "
            "of opportunity."
        ),
    },
    {
        "id": "shaken",
        "name": "Shaken",
        "summary": "–2 on attacks, saves, checks, and ability checks",
        "description": (
            "A shaken character takes a –2 penalty on attack rolls, saving throws, "
            "skill checks, and ability checks. Shaken is a less severe state of "
            "fear than frightened or panicked."
        ),
    },
    {
        "id": "sickened",
        "name": "Sickened",
        "summary": "–2 on attacks, damage, saves, skill checks, ability checks",
        "description": (
            "The character takes a –2 penalty on all attack rolls, weapon damage "
            "rolls, saving throws, skill checks, and ability checks."
        ),
    },
    {
        "id": "staggered",
        "name": "Staggered",
        "summary": "Only one action/round (move or standard, not both)",
        "description": (
            "A character whose nonlethal damage exactly equals his current hit points "
            "is staggered. A staggered character may take a single move action or "
            "standard action each round (but not both, nor can he take full-round "
            "actions). A character whose nonlethal damage exceeds his current hit "
            "points becomes unconscious."
        ),
    },
    {
        "id": "stunned",
        "name": "Stunned",
        "summary": "No actions, drops held items, –2 AC, loses DEX bonus",
        "description": (
            "A stunned creature drops everything held, can't take actions, takes a "
            "–2 penalty to AC, and loses its Dexterity bonus to AC (if any). "
            "Attackers can make coup de grace attempts against stunned defenders."
        ),
    },
    {
        "id": "unconscious",
        "name": "Unconscious",
        "summary": "Helpless, unaware; at negative HP: dying unless stable",
        "description": (
            "Unconscious creatures are knocked out and helpless. Unconsciousness can "
            "result from having current hit points between –1 and –9 (but not yet "
            "dead), or from nonlethal damage in excess of current hit points."
        ),
    },
]

# ---------------------------------------------------------------------------
# Druid level progression (SRD 3.5 PHB)
# Spell slots are base slots WITHOUT Wisdom bonus.
# Wisdom bonus spells are added by the app based on WIS modifier.
# ---------------------------------------------------------------------------

import json

DRUID_LEVELS: list[dict] = [
    # level, hd, skill_pts, bab, fort, ref, will, 0-9 spells per day, features
    {
        "level": 1, "hd": "d8", "skill_points": 4, "bab": 0,
        "fort": 2, "ref": 0, "will": 2,
        "spells_0": 3, "spells_1": 2, "spells_2": 0, "spells_3": 0,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([
            "Animal Companion",
            "Nature Sense (+2 Knowledge Nature & Survival)",
            "Wild Empathy",
            "Spontaneous Casting (Summon Nature's Ally)",
        ]),
    },
    {
        "level": 2, "hd": "d8", "skill_points": 4, "bab": 1,
        "fort": 3, "ref": 0, "will": 3,
        "spells_0": 4, "spells_1": 3, "spells_2": 0, "spells_3": 0,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Woodland Stride"]),
    },
    {
        "level": 3, "hd": "d8", "skill_points": 4, "bab": 2,
        "fort": 3, "ref": 1, "will": 3,
        "spells_0": 4, "spells_1": 3, "spells_2": 2, "spells_3": 0,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Trackless Step"]),
    },
    {
        "level": 4, "hd": "d8", "skill_points": 4, "bab": 3,
        "fort": 4, "ref": 1, "will": 4,
        "spells_0": 5, "spells_1": 4, "spells_2": 3, "spells_3": 0,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Resist Nature's Lure (+4 saves vs. fey & nature spells)"]),
    },
    {
        "level": 5, "hd": "d8", "skill_points": 4, "bab": 3,
        "fort": 4, "ref": 1, "will": 4,
        "spells_0": 5, "spells_1": 4, "spells_2": 3, "spells_3": 2,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Wild Shape 1/day (Small or Medium animal)"]),
    },
    {
        "level": 6, "hd": "d8", "skill_points": 4, "bab": 4,
        "fort": 5, "ref": 2, "will": 5,
        "spells_0": 5, "spells_1": 4, "spells_2": 4, "spells_3": 3,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Wild Shape 2/day", "Wild Shape (Large)"]),
    },
    {
        "level": 7, "hd": "d8", "skill_points": 4, "bab": 5,
        "fort": 5, "ref": 2, "will": 5,
        "spells_0": 6, "spells_1": 5, "spells_2": 4, "spells_3": 3,
        "spells_4": 2, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([]),
    },
    {
        "level": 8, "hd": "d8", "skill_points": 4, "bab": 6,
        "fort": 6, "ref": 2, "will": 6,
        "spells_0": 6, "spells_1": 5, "spells_2": 4, "spells_3": 4,
        "spells_4": 3, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([
            "Wild Shape 3/day",
            "Wild Shape (Tiny)",
            "Wild Shape (Plant)",
        ]),
    },
    {
        "level": 9, "hd": "d8", "skill_points": 4, "bab": 6,
        "fort": 6, "ref": 3, "will": 6,
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 4,
        "spells_4": 3, "spells_5": 2, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Venom Immunity (immune to all poisons)"]),
    },
    {
        "level": 10, "hd": "d8", "skill_points": 4, "bab": 7,
        "fort": 7, "ref": 3, "will": 7,
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 4,
        "spells_4": 4, "spells_5": 3, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([
            "Wild Shape 4/day",
            "Wild Shape (Huge)",
            "Wild Shape (Elemental 1/day)",
        ]),
    },
    {
        "level": 11, "hd": "d8", "skill_points": 4, "bab": 8,
        "fort": 7, "ref": 3, "will": 7,
        "spells_0": 6, "spells_1": 6, "spells_2": 5, "spells_3": 5,
        "spells_4": 4, "spells_5": 3, "spells_6": 2, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([]),
    },
    {
        "level": 12, "hd": "d8", "skill_points": 4, "bab": 9,
        "fort": 8, "ref": 4, "will": 8,
        "spells_0": 6, "spells_1": 6, "spells_2": 5, "spells_3": 5,
        "spells_4": 4, "spells_5": 4, "spells_6": 3, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([
            "Wild Shape 5/day",
            "Wild Shape (Elemental 2/day)",
            "Thousand Faces (alter self at will)",
        ]),
    },
    {
        "level": 13, "hd": "d8", "skill_points": 4, "bab": 9,
        "fort": 8, "ref": 4, "will": 8,
        "spells_0": 6, "spells_1": 6, "spells_2": 6, "spells_3": 5,
        "spells_4": 5, "spells_5": 4, "spells_6": 3, "spells_7": 2,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([]),
    },
    {
        "level": 14, "hd": "d8", "skill_points": 4, "bab": 10,
        "fort": 9, "ref": 4, "will": 9,
        "spells_0": 6, "spells_1": 6, "spells_2": 6, "spells_3": 5,
        "spells_4": 5, "spells_5": 4, "spells_6": 4, "spells_7": 3,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([
            "Wild Shape 6/day",
            "Wild Shape (Elemental 3/day)",
            "Timeless Body (no aging penalties)",
        ]),
    },
    {
        "level": 15, "hd": "d8", "skill_points": 4, "bab": 11,
        "fort": 9, "ref": 5, "will": 9,
        "spells_0": 6, "spells_1": 6, "spells_2": 6, "spells_3": 6,
        "spells_4": 5, "spells_5": 5, "spells_6": 4, "spells_7": 3,
        "spells_8": 2, "spells_9": 0,
        "features": json.dumps([]),
    },
    {
        "level": 16, "hd": "d8", "skill_points": 4, "bab": 12,
        "fort": 10, "ref": 5, "will": 10,
        "spells_0": 6, "spells_1": 6, "spells_2": 6, "spells_3": 6,
        "spells_4": 5, "spells_5": 5, "spells_6": 4, "spells_7": 4,
        "spells_8": 3, "spells_9": 0,
        "features": json.dumps([
            "Wild Shape 7/day",
            "Wild Shape (Elemental 4/day)",
        ]),
    },
    {
        "level": 17, "hd": "d8", "skill_points": 4, "bab": 12,
        "fort": 10, "ref": 5, "will": 10,
        "spells_0": 6, "spells_1": 6, "spells_2": 6, "spells_3": 6,
        "spells_4": 6, "spells_5": 5, "spells_6": 5, "spells_7": 4,
        "spells_8": 3, "spells_9": 2,
        "features": json.dumps([]),
    },
    {
        "level": 18, "hd": "d8", "skill_points": 4, "bab": 13,
        "fort": 11, "ref": 6, "will": 11,
        "spells_0": 6, "spells_1": 6, "spells_2": 6, "spells_3": 6,
        "spells_4": 6, "spells_5": 5, "spells_6": 5, "spells_7": 4,
        "spells_8": 4, "spells_9": 3,
        "features": json.dumps(["Wild Shape 8/day"]),
    },
    {
        "level": 19, "hd": "d8", "skill_points": 4, "bab": 14,
        "fort": 11, "ref": 6, "will": 11,
        "spells_0": 6, "spells_1": 6, "spells_2": 6, "spells_3": 6,
        "spells_4": 6, "spells_5": 6, "spells_6": 5, "spells_7": 5,
        "spells_8": 4, "spells_9": 4,
        "features": json.dumps([]),
    },
    {
        "level": 20, "hd": "d8", "skill_points": 4, "bab": 15,
        "fort": 12, "ref": 6, "will": 12,
        "spells_0": 6, "spells_1": 6, "spells_2": 6, "spells_3": 6,
        "spells_4": 6, "spells_5": 6, "spells_6": 5, "spells_7": 5,
        "spells_8": 5, "spells_9": 5,
        "features": json.dumps(["A Thousand Faces", "Wild Shape (Huge Elemental)"]),
    },
]

# ---------------------------------------------------------------------------
# INSERT templates
# ---------------------------------------------------------------------------

SPELL_INSERT = """
INSERT OR REPLACE INTO spells
    (id, name, level_druid, level_cleric, level_wizard, level_ranger, level_paladin,
     school, cast_time, range, target, duration, save, spell_resistance, description)
VALUES
    (:id, :name, :level_druid, :level_cleric, :level_wizard, :level_ranger, :level_paladin,
     :school, :cast_time, :range, :target, :duration, :save, :spell_resistance, :description)
"""

FEAT_INSERT = """
INSERT OR REPLACE INTO feats (id, name, type, prerequisites, benefit, normal, special)
VALUES (:id, :name, :type, :prerequisites, :benefit, :normal, :special)
"""

CONDITION_INSERT = """
INSERT OR REPLACE INTO conditions (id, name, summary, description)
VALUES (:id, :name, :summary, :description)
"""

DRUID_LEVEL_INSERT = """
INSERT OR REPLACE INTO druid_levels
    (level, hd, skill_points, bab, fort, ref, will,
     spells_0, spells_1, spells_2, spells_3, spells_4,
     spells_5, spells_6, spells_7, spells_8, spells_9, features)
VALUES
    (:level, :hd, :skill_points, :bab, :fort, :ref, :will,
     :spells_0, :spells_1, :spells_2, :spells_3, :spells_4,
     :spells_5, :spells_6, :spells_7, :spells_8, :spells_9, :features)
"""


def seed() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    for spell in SPELLS:
        row = {
            "id": spell["id"],
            "name": spell["name"],
            "level_druid": spell.get("level_druid"),
            "level_cleric": spell.get("level_cleric"),
            "level_wizard": spell.get("level_wizard"),
            "level_ranger": spell.get("level_ranger"),
            "level_paladin": spell.get("level_paladin"),
            "school": spell.get("school"),
            "cast_time": spell.get("cast_time"),
            "range": spell.get("range"),
            "target": spell.get("target"),
            "duration": spell.get("duration"),
            "save": spell.get("save"),
            "spell_resistance": spell.get("spell_resistance"),
            "description": spell.get("description"),
        }
        conn.execute(SPELL_INSERT, row)

    for skill in SKILLS:
        conn.execute(
            "INSERT OR REPLACE INTO skills (id, name, ability, trained_only, description) "
            "VALUES (:id, :name, :ability, :trained_only, :description)",
            skill,
        )

    for feat in FEATS:
        row = {k: feat.get(k) for k in ("id", "name", "type", "prerequisites", "benefit", "normal", "special")}
        conn.execute(FEAT_INSERT, row)

    for condition in CONDITIONS:
        conn.execute(CONDITION_INSERT, condition)

    for dl in DRUID_LEVELS:
        conn.execute(DRUID_LEVEL_INSERT, dl)

    conn.commit()
    conn.close()

    print(f"Database seeded at {DB_PATH}")
    print(f"  {len(SPELLS)} spells, {len(SKILLS)} skills, {len(FEATS)} feats")
    print(f"  {len(CONDITIONS)} conditions, {len(DRUID_LEVELS)} druid levels")


if __name__ == "__main__":
    seed()
