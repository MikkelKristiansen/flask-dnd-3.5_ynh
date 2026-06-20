-- SRD v3.5 skema. Kilden til sandheden for tabelstruktur.
-- Data ligger i data/<tabel>.yaml og indlæses af importer.py.
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

DROP TABLE IF EXISTS cleric_levels;
CREATE TABLE cleric_levels (
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

DROP TABLE IF EXISTS ranger_levels;
CREATE TABLE ranger_levels (
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
    weight        REAL NOT NULL DEFAULT 0     -- pund (Medium); Small ×½, Large ×2 udregnes
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
    damage_type  TEXT                        -- bludgeoning | piercing | slashing | kombinationer
);

DROP TABLE IF EXISTS items;
CREATE TABLE items (
    id       TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,   -- adventuring_gear | substance | tool | clothing | food | ammunition
    cost_cp       INTEGER,    -- pris i kobber; NULL = variabel / —
    weight        REAL NOT NULL DEFAULT 0,    -- pund (Medium-version)
    small_quarter INTEGER NOT NULL DEFAULT 0  -- 1 = vejer ¼ for Small (SRD fodnote 1); 0 = uændret
);
