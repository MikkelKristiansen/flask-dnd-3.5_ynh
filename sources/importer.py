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
    trained_only INTEGER NOT NULL
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
    {"id": "appraise",           "name": "Appraise",             "ability": "int", "trained_only": 0},
    {"id": "balance",            "name": "Balance",              "ability": "dex", "trained_only": 0},
    {"id": "bluff",              "name": "Bluff",                "ability": "cha", "trained_only": 0},
    {"id": "climb",              "name": "Climb",                "ability": "str", "trained_only": 0},
    {"id": "concentration",      "name": "Concentration",        "ability": "con", "trained_only": 0},
    {"id": "craft",              "name": "Craft",                "ability": "int", "trained_only": 0},
    {"id": "decipher_script",    "name": "Decipher Script",      "ability": "int", "trained_only": 1},
    {"id": "diplomacy",          "name": "Diplomacy",            "ability": "cha", "trained_only": 0},
    {"id": "disable_device",     "name": "Disable Device",       "ability": "int", "trained_only": 1},
    {"id": "disguise",           "name": "Disguise",             "ability": "cha", "trained_only": 0},
    {"id": "escape_artist",      "name": "Escape Artist",        "ability": "dex", "trained_only": 0},
    {"id": "forgery",            "name": "Forgery",              "ability": "int", "trained_only": 0},
    {"id": "gather_information", "name": "Gather Information",   "ability": "cha", "trained_only": 0},
    {"id": "handle_animal",      "name": "Handle Animal",        "ability": "cha", "trained_only": 1},
    {"id": "heal",               "name": "Heal",                 "ability": "wis", "trained_only": 0},
    {"id": "hide",               "name": "Hide",                 "ability": "dex", "trained_only": 0},
    {"id": "intimidate",         "name": "Intimidate",           "ability": "cha", "trained_only": 0},
    {"id": "jump",               "name": "Jump",                 "ability": "str", "trained_only": 0},
    {"id": "knowledge_arcana",   "name": "Knowledge (Arcana)",   "ability": "int", "trained_only": 1},
    {"id": "knowledge_dungeoneering", "name": "Knowledge (Dungeoneering)", "ability": "int", "trained_only": 1},
    {"id": "knowledge_geography","name": "Knowledge (Geography)","ability": "int", "trained_only": 1},
    {"id": "knowledge_history",  "name": "Knowledge (History)",  "ability": "int", "trained_only": 1},
    {"id": "knowledge_local",    "name": "Knowledge (Local)",    "ability": "int", "trained_only": 1},
    {"id": "knowledge_nature",   "name": "Knowledge (Nature)",   "ability": "int", "trained_only": 1},
    {"id": "knowledge_nobility", "name": "Knowledge (Nobility)", "ability": "int", "trained_only": 1},
    {"id": "knowledge_planes",   "name": "Knowledge (The Planes)","ability": "int", "trained_only": 1},
    {"id": "knowledge_religion", "name": "Knowledge (Religion)", "ability": "int", "trained_only": 1},
    {"id": "listen",             "name": "Listen",               "ability": "wis", "trained_only": 0},
    {"id": "move_silently",      "name": "Move Silently",        "ability": "dex", "trained_only": 0},
    {"id": "open_lock",          "name": "Open Lock",            "ability": "dex", "trained_only": 1},
    {"id": "perform",            "name": "Perform",              "ability": "cha", "trained_only": 0},
    {"id": "profession",         "name": "Profession",           "ability": "wis", "trained_only": 1},
    {"id": "profession_herbalist","name": "Profession (Herbalist)","ability": "wis", "trained_only": 1},
    {"id": "ride",               "name": "Ride",                 "ability": "dex", "trained_only": 0},
    {"id": "search",             "name": "Search",               "ability": "int", "trained_only": 0},
    {"id": "sense_motive",       "name": "Sense Motive",         "ability": "wis", "trained_only": 0},
    {"id": "sleight_of_hand",    "name": "Sleight of Hand",      "ability": "dex", "trained_only": 1},
    {"id": "speak_language",     "name": "Speak Language",       "ability": "none","trained_only": 1},
    {"id": "spellcraft",         "name": "Spellcraft",           "ability": "int", "trained_only": 1},
    {"id": "spot",               "name": "Spot",                 "ability": "wis", "trained_only": 0},
    {"id": "survival",           "name": "Survival",             "ability": "wis", "trained_only": 0},
    {"id": "swim",               "name": "Swim",                 "ability": "str", "trained_only": 0},
    {"id": "tumble",             "name": "Tumble",               "ability": "dex", "trained_only": 1},
    {"id": "use_magic_device",   "name": "Use Magic Device",     "ability": "cha", "trained_only": 1},
    {"id": "use_rope",           "name": "Use Rope",             "ability": "dex", "trained_only": 0},
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
        "spells_0": 3, "spells_1": 1, "spells_2": 0, "spells_3": 0,
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
        "spells_0": 4, "spells_1": 2, "spells_2": 0, "spells_3": 0,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Woodland Stride"]),
    },
    {
        "level": 3, "hd": "d8", "skill_points": 4, "bab": 2,
        "fort": 3, "ref": 1, "will": 3,
        "spells_0": 4, "spells_1": 2, "spells_2": 1, "spells_3": 0,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Trackless Step"]),
    },
    {
        "level": 4, "hd": "d8", "skill_points": 4, "bab": 3,
        "fort": 4, "ref": 1, "will": 4,
        "spells_0": 5, "spells_1": 3, "spells_2": 2, "spells_3": 0,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Resist Nature's Lure (+4 saves vs. fey & nature spells)"]),
    },
    {
        "level": 5, "hd": "d8", "skill_points": 4, "bab": 3,
        "fort": 4, "ref": 1, "will": 4,
        "spells_0": 5, "spells_1": 3, "spells_2": 2, "spells_3": 1,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Wild Shape 1/day (Small or Medium animal)"]),
    },
    {
        "level": 6, "hd": "d8", "skill_points": 4, "bab": 4,
        "fort": 5, "ref": 2, "will": 5,
        "spells_0": 5, "spells_1": 3, "spells_2": 3, "spells_3": 2,
        "spells_4": 0, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Wild Shape 2/day", "Wild Shape (Large)"]),
    },
    {
        "level": 7, "hd": "d8", "skill_points": 4, "bab": 5,
        "fort": 5, "ref": 2, "will": 5,
        "spells_0": 6, "spells_1": 4, "spells_2": 3, "spells_3": 2,
        "spells_4": 1, "spells_5": 0, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([]),
    },
    {
        "level": 8, "hd": "d8", "skill_points": 4, "bab": 6,
        "fort": 6, "ref": 2, "will": 6,
        "spells_0": 6, "spells_1": 4, "spells_2": 3, "spells_3": 3,
        "spells_4": 2, "spells_5": 0, "spells_6": 0, "spells_7": 0,
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
        "spells_0": 6, "spells_1": 4, "spells_2": 4, "spells_3": 3,
        "spells_4": 2, "spells_5": 1, "spells_6": 0, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps(["Venom Immunity (immune to all poisons)"]),
    },
    {
        "level": 10, "hd": "d8", "skill_points": 4, "bab": 7,
        "fort": 7, "ref": 3, "will": 7,
        "spells_0": 6, "spells_1": 4, "spells_2": 4, "spells_3": 3,
        "spells_4": 3, "spells_5": 2, "spells_6": 0, "spells_7": 0,
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
        "spells_0": 6, "spells_1": 5, "spells_2": 4, "spells_3": 4,
        "spells_4": 3, "spells_5": 2, "spells_6": 1, "spells_7": 0,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([]),
    },
    {
        "level": 12, "hd": "d8", "skill_points": 4, "bab": 9,
        "fort": 8, "ref": 4, "will": 8,
        "spells_0": 6, "spells_1": 5, "spells_2": 4, "spells_3": 4,
        "spells_4": 3, "spells_5": 3, "spells_6": 2, "spells_7": 0,
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
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 4,
        "spells_4": 4, "spells_5": 3, "spells_6": 2, "spells_7": 1,
        "spells_8": 0, "spells_9": 0,
        "features": json.dumps([]),
    },
    {
        "level": 14, "hd": "d8", "skill_points": 4, "bab": 10,
        "fort": 9, "ref": 4, "will": 9,
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 4,
        "spells_4": 4, "spells_5": 3, "spells_6": 3, "spells_7": 2,
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
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 5,
        "spells_4": 4, "spells_5": 4, "spells_6": 3, "spells_7": 2,
        "spells_8": 1, "spells_9": 0,
        "features": json.dumps([]),
    },
    {
        "level": 16, "hd": "d8", "skill_points": 4, "bab": 12,
        "fort": 10, "ref": 5, "will": 10,
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 5,
        "spells_4": 4, "spells_5": 4, "spells_6": 3, "spells_7": 3,
        "spells_8": 2, "spells_9": 0,
        "features": json.dumps([
            "Wild Shape 7/day",
            "Wild Shape (Elemental 4/day)",
        ]),
    },
    {
        "level": 17, "hd": "d8", "skill_points": 4, "bab": 12,
        "fort": 10, "ref": 5, "will": 10,
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 5,
        "spells_4": 5, "spells_5": 4, "spells_6": 4, "spells_7": 3,
        "spells_8": 2, "spells_9": 1,
        "features": json.dumps([]),
    },
    {
        "level": 18, "hd": "d8", "skill_points": 4, "bab": 13,
        "fort": 11, "ref": 6, "will": 11,
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 5,
        "spells_4": 5, "spells_5": 4, "spells_6": 4, "spells_7": 3,
        "spells_8": 3, "spells_9": 2,
        "features": json.dumps(["Wild Shape 8/day"]),
    },
    {
        "level": 19, "hd": "d8", "skill_points": 4, "bab": 14,
        "fort": 11, "ref": 6, "will": 11,
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 5,
        "spells_4": 5, "spells_5": 5, "spells_6": 4, "spells_7": 4,
        "spells_8": 3, "spells_9": 3,
        "features": json.dumps([]),
    },
    {
        "level": 20, "hd": "d8", "skill_points": 4, "bab": 15,
        "fort": 12, "ref": 6, "will": 12,
        "spells_0": 6, "spells_1": 5, "spells_2": 5, "spells_3": 5,
        "spells_4": 5, "spells_5": 5, "spells_6": 4, "spells_7": 4,
        "spells_8": 4, "spells_9": 4,
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
            "INSERT OR REPLACE INTO skills (id, name, ability, trained_only) "
            "VALUES (:id, :name, :ability, :trained_only)",
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
