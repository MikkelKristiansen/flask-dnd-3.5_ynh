-- SRD v3.5 skema. Kilden til sandheden for tabelstruktur.
-- Data ligger i data/<tabel>.yaml og indlæses af importer.py.
DROP TABLE IF EXISTS spells;
CREATE TABLE spells (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    level_druid INTEGER,
    level_cleric INTEGER,
    level_wizard INTEGER,
    level_bard INTEGER,
    level_ranger INTEGER,
    level_paladin INTEGER,
    school TEXT,
    cast_time TEXT,
    range TEXT,
    target TEXT,
    duration TEXT,
    -- 1 = spell der kun rammer casteren selv og har varighed (ikke instant).
    -- Får tre tilstande på arket (Ledig/I brug/Brugt) i stedet for to.
    self_duration INTEGER,
    save TEXT,
    spell_resistance TEXT,
    components TEXT,
    target_label TEXT,
    description TEXT
);

DROP TABLE IF EXISTS skills;
CREATE TABLE skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ability TEXT NOT NULL,
    trained_only INTEGER NOT NULL,
    armor_check INTEGER NOT NULL DEFAULT 0,  -- 0 ingen · 1 normal ACP · 2 dobbelt (Swim)
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
    special TEXT,
    fighter_bonus INTEGER       -- 1 = må vælges som fighter-bonus-feat (nullable)
);

DROP TABLE IF EXISTS conditions;
CREATE TABLE conditions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    summary TEXT NOT NULL,
    description TEXT NOT NULL
);

-- Oprydning: tidligere var der én tabel pr. klasse (druid_levels osv.); nu samlet
-- i class_levels. DROP'sne fjerner de gamle tabeller fra eksisterende databaser.
DROP TABLE IF EXISTS druid_levels;
DROP TABLE IF EXISTS cleric_levels;
DROP TABLE IF EXISTS ranger_levels;
DROP TABLE IF EXISTS rogue_levels;

-- Én tabel for alle klassers level-progression. Tilføj en klasse = append rækker
-- (med class:) til data/class_levels.yaml — ingen schema- eller importer-ændring.
DROP TABLE IF EXISTS class_levels;
CREATE TABLE class_levels (
    class       TEXT NOT NULL,
    level       INTEGER NOT NULL,
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
    -- Antal spells KENDT pr. niveau (spontane castere: sorcerer/bard). Fast
    -- SRD-opslagstabel, IKKE Cha-afhængig (modsat wizards Int-formel). Nullable:
    -- NULL = klassen bruger ikke "spells known" (behandles som 0). Kun sorcerer/
    -- bard-rækker fylder disse; øvrige klasser udelader feltet.
    spells_known_0 INTEGER,
    spells_known_1 INTEGER,
    spells_known_2 INTEGER,
    spells_known_3 INTEGER,
    spells_known_4 INTEGER,
    spells_known_5 INTEGER,
    spells_known_6 INTEGER,
    spells_known_7 INTEGER,
    spells_known_8 INTEGER,
    spells_known_9 INTEGER,
    features    TEXT NOT NULL,
    PRIMARY KEY (class, level)
);

DROP TABLE IF EXISTS domains;
CREATE TABLE domains (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    granted_power TEXT NOT NULL
);

DROP TABLE IF EXISTS domain_spells;
CREATE TABLE domain_spells (
    domain_id TEXT NOT NULL,
    level     INTEGER NOT NULL,
    spell_id  TEXT NOT NULL,
    PRIMARY KEY (domain_id, level)
);

-- Angreb en spell kan lave (Produce Flame, Magic Stone …). 0..n rækker pr. spell.
-- Skade udregnes (gemmes aldrig):
--   base_damage + min(floor(niveau*dmg_per_level/dmg_per_level_div), max) + dmg_bonus.
DROP TABLE IF EXISTS spell_attacks;
CREATE TABLE spell_attacks (
    spell_id          TEXT NOT NULL,   -- FK til spells.id
    label             TEXT NOT NULL,   -- visningsnavn på angrebsrækken
    kind              TEXT NOT NULL,   -- melee | ranged | melee_touch | ranged_touch
    mode_group        TEXT,            -- tilstands-gruppe: rækker m/ samme (spell_id, mode_group) er ét angreb i flere tilstande (Produce Flame: touch)
    base_damage       TEXT NOT NULL,   -- terningen, fx "1d6"
    dmg_per_level     INTEGER,         -- skade-bonus pr. casterniveau (Produce Flame 1)
    dmg_per_level_div INTEGER,         -- del niveauet med dette først (tom=1); Flame Blade 2 = +1 pr. 2 niveauer
    dmg_per_level_max INTEGER,         -- cap på niveau-bonus (Produce Flame 5)
    dmg_bonus         INTEGER,         -- flad skade-bonus (Magic Stone +1)
    to_hit            INTEGER,         -- flad til-hit-bonus (Magic Stone +1)
    crit              TEXT,            -- default x2
    dmg_type          TEXT,            -- skadetype
    range_ft          INTEGER,         -- rækkevidde for kastet/ranged
    charges           INTEGER,         -- antal ladninger (Magic Stone 3); tom = ubegrænset
    alt_note          TEXT             -- fx "2d6+2 mod udøde"
);

DROP TABLE IF EXISTS armor;
CREATE TABLE armor (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    armor_bonus   INTEGER NOT NULL,
    max_dex       INTEGER,                    -- NULL = ingen Dex-grænse
    armor_check   INTEGER NOT NULL DEFAULT 0, -- ACP (negativ); anvendes på Str/Dex-skills
    spell_failure INTEGER NOT NULL DEFAULT 0, -- arcane spell failure % (kun arcane casters; gemt til senere)
    druid_ok      INTEGER NOT NULL DEFAULT 1, -- 0 = forbudt for druider (metal); jf. _DRUID_PROHIBITED_ARMOR
    type          TEXT NOT NULL,              -- light | medium | heavy | shield
    cost_cp       INTEGER,                    -- pris i kobber (1 gp = 100 cp)
    weight        REAL NOT NULL DEFAULT 0,    -- pund (Medium); Small ×½, Large ×2 udregnes
    description   TEXT                        -- SRD-beskrivelse (særlige egenskaber); NULL = ingen særtekst
);

DROP TABLE IF EXISTS weapons;
CREATE TABLE weapons (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,              -- simple | martial | exotic
    weapon_class TEXT NOT NULL,              -- unarmed | light | one-handed | two-handed | ranged
    cost_cp      INTEGER,                    -- pris i kobber (1 gp = 100 cp); NULL = — / special
    dmg_s        TEXT,                       -- skade, Small-version
    dmg_m        TEXT,                       -- skade, Medium-version (a/b for dobbeltvåben)
    critical     TEXT,                       -- fx "19–20/x2"
    range_ft     INTEGER,                    -- range increment i fod; NULL = ren nærkamp
    weight       REAL NOT NULL DEFAULT 0,    -- pund (Medium-version)
    damage_type  TEXT,                       -- bludgeoning | piercing | slashing | kombinationer
    hands        INTEGER,                    -- hænder våbnet kræver; NULL = udled af weapon_class (kun sat hvor ranged afviger)
    metal        INTEGER,                    -- 0 = ikke-metal (træ/læder): kan ikke laves af cold iron / forsølves; NULL = metal (default)
    ranged_str   TEXT,                       -- ranged Str-til-skade: composite | penalty_only | full | none | NULL(=none)
    thrown       INTEGER,                    -- 1 = kastbart håndvåben (kan bruges i BÅDE nærkamp og kast) → ⇄-skift på arket; NULL = nej
    description  TEXT                        -- SRD-beskrivelse (særlige egenskaber); NULL = ingen særtekst
);

DROP TABLE IF EXISTS items;
CREATE TABLE items (
    id       TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,   -- adventuring_gear | substance | tool | clothing | food | ammunition
    cost_cp       INTEGER,    -- pris i kobber; NULL = variabel / —
    weight        REAL NOT NULL DEFAULT 0,    -- pund (Medium-version)
    small_quarter INTEGER NOT NULL DEFAULT 0, -- 1 = vejer ¼ for Small (SRD fodnote 1); 0 = uændret
    bundle        INTEGER,    -- antal enheder som vægt/pris dækker (ammo: 10/20/5); NULL = per styk
    description   TEXT        -- SRD-beskrivelse (særlige egenskaber); NULL = ingen særtekst
);

DROP TABLE IF EXISTS animals;
-- Væsen-katalog: BÅDE animal companions OG summonbare væsner (Summon Nature's
-- Ally). companion_ok skelner de to roller; hit_die rummer ikke-d8-væsner.
CREATE TABLE animals (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    size              TEXT NOT NULL,              -- tiny | small | medium | large | huge
    base_hd           INTEGER NOT NULL,          -- antal hit dice (uden bonus-HD)
    type              TEXT,                       -- animal (default/NULL) | magical_beast | elemental | fey | outsider
                                                  --   driver BAB: animal/elemental ¾·HD, magical_beast/outsider 1·HD, fey ½·HD
    hit_die           INTEGER,                   -- terningtype pr. HD: 6 (fey) | 10 (magical beast); NULL = 8 (dyr/elementaler)
    good_saves        TEXT,                       -- JSON-liste, fx ["fort","ref"]; NULL = udled af type
                                                  --   (animal/magical_beast: fort+ref · fey: ref+will · elemental: pr. element)
    str               INTEGER NOT NULL,
    dex               INTEGER NOT NULL,
    con               INTEGER NOT NULL,
    int               INTEGER NOT NULL,
    wis               INTEGER NOT NULL,
    cha               INTEGER NOT NULL,
    natural_armor     INTEGER NOT NULL DEFAULT 0, -- basis naturlig rustning (avancement lægger til)
    speed             TEXT NOT NULL,              -- fri tekst, fx "50 ft." eller "10 ft., fly 80 ft."
    attacks           TEXT NOT NULL,              -- JSON: [{name, damage, group:primary|secondary, count?}]
    special_attacks   TEXT,                       -- fri tekst, fx "Trip" / "Poison"; NULL = ingen
    special_qualities TEXT,                       -- fri tekst, fx "Low-light vision, scent"
    skills            TEXT NOT NULL,              -- JSON: [{id, misc, note?}] (misc = total − basis-abilitymod)
    feats             TEXT NOT NULL,              -- JSON: liste af feat-navne (strenge)
    companion_ok      INTEGER                     -- 1/NULL = kan vælges som animal companion; 0 = kun summonbar
);

-- Mekaniske effekter: buffs & tilstande oversat til modifiers, så de ændrer de
-- faktiske tal (ability scores kaskaderer; direkte bonusser lægges på pr. tal).
-- modifiers/riders gemmes som JSON-tekst og afkodes i db._effect_row.
--   modifier = {target, type, value, only_vs?, note?}
--     target: str|dex|con|int|wis|cha (kaskaderer) · ac|ac_touch|attack|damage
--             · save_fort|save_ref|save_will|save_all · skill:<id> · speed · init · hp_temp
--     type:   enhancement morale dodge luck insight deflection natural competence
--             resistance size circumstance sacred profane untyped penalty
--   rider    = ikke-numerisk effekt (flag/tekst), fx "mister Dex til AC".
DROP TABLE IF EXISTS effects;
CREATE TABLE effects (
    id              TEXT PRIMARY KEY,           -- = buffens spell_id eller tilstandens id
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL,              -- buff | condition
    source_spell_id TEXT,                       -- FK til spells.id for SRD-beskrivelse (kan være NULL)
    modifiers       TEXT NOT NULL DEFAULT '[]', -- JSON: liste af modifier-objekter
    riders          TEXT NOT NULL DEFAULT '[]', -- JSON: liste af ikke-numeriske ryttere
    -- Picker-metadata: hvor/hvordan effekten tilbydes i effekt-vælgeren.
    picker          TEXT,                       -- buff | damage | NULL (NULL = vises ikke i picker)
    note            TEXT,                       -- kort virkningstekst i vælgeren
    affects         TEXT NOT NULL DEFAULT '[]', -- JSON: hvilke sektioner buffen markerer (attack/save/...)
    editable        INTEGER NOT NULL DEFAULT 0, -- 1 = spørg om en værdi ved tilføjelse (ability-skade)
    negative        INTEGER NOT NULL DEFAULT 0, -- 1 = gem værdien negativ (skade)
    prompt          TEXT                        -- spørgsmålstekst når editable
);

-- Special-evner (natural abilities): forklarings-katalog for væsners special attacks
-- og special qualities. Slug'en matcher det ledende navn i animals' fritekst-felter
-- (fx "Rage", "Improved grab"), så wild_shape kan slå en forklaring + Ex/Su/Sp-art op.
DROP TABLE IF EXISTS special_abilities;
CREATE TABLE special_abilities (
    id          TEXT PRIMARY KEY,  -- slug, fx 'rage', 'improved_grab', 'low_light_vision'
    name        TEXT NOT NULL,     -- visningsnavn, fx 'Rage'
    kind        TEXT,              -- ex | su | sp (afgør overførsel ved wild shape)
    category    TEXT,              -- attack | quality (informativt; feltet i animals afgør reelt)
    buff_id     TEXT,              -- valgfri FK til effects.id: aktiverbar stat-buff (fx rage)
    rider_type  TEXT,              -- engangs-angrebsrytter: extra_attacks | two_hit |
                                   -- on_charge | on_hit | on_grapple | trample (NULL = ingen)
    rider_count INTEGER,           -- antal ekstra angreb (extra_attacks, fx rake = 2)
    description TEXT               -- SRD/OGL-forklaring
);
