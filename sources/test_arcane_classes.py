"""Tests for Fase 1 af spellcaster-arbejdet: bard, sorcerer, wizard.

Verificerer:
  (a) Klasserne kan genereres ende-til-ende via /karakter/<slug> (HTTP 200, navn i HTML).
  (b) Spell-slot-tal stemmer med SRD-tabellen for udvalgte levels.
  (c) cast_ability bruges korrekt (CHA for bard/sorcerer, INT for wizard → bonus slots).
  (d) Cleric/druid-slot-adfærd er uændret (wis bruges stadig).

Kør: python -m pytest test_arcane_classes.py   (fra sources/)
"""
import pathlib

import pytest
from ruamel.yaml import YAML

import app as app_module
import character as char_module
import db as db_module
import refdata

YAML_RW = YAML()
DEFAULTS = pathlib.Path(__file__).parent / "defaults"


def _make_char(tmp_path, slug, cls, level=1, **ability_overrides):
    """Skriv en minimal karakter til tmp_path og returnér stien."""
    data = YAML_RW.load((DEFAULTS / "aelred.yaml").read_text())
    data["class"] = cls
    data["level"] = level
    data["name"] = slug.capitalize()
    # Nulstil klasse-specifikke felter der ikke passer til arcane casters
    data.pop("domains", None)
    data.pop("domain_spells_prepared", None)
    data.pop("domain_spells_used", None)
    data.pop("spells_prepared", None)
    data.pop("spells_used", None)
    data.pop("class_features", None)
    for ability, score in ability_overrides.items():
        data["ability_scores"][ability] = score
    path = tmp_path / f"{slug}.yaml"
    with path.open("w") as f:
        YAML_RW.dump(data, f)
    return path


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Bard lvl 1, sorcerer lvl 1, wizard lvl 1 + cleric som kontrol."""
    _make_char(tmp_path, "bard1",     "Bard",     level=1,  cha=16)
    _make_char(tmp_path, "sorc1",     "Sorcerer", level=1,  cha=16)
    _make_char(tmp_path, "wiz1",      "Wizard",   level=1,  int=16)
    _make_char(tmp_path, "sorc5",     "Sorcerer", level=5,  cha=16)
    _make_char(tmp_path, "wiz5",      "Wizard",   level=5,  int=16)
    _make_char(tmp_path, "bard10",    "Bard",     level=10, cha=18)
    _make_char(tmp_path, "sorc10",    "Sorcerer", level=10, cha=18)
    _make_char(tmp_path, "wiz10",     "Wizard",   level=10, int=18)
    _make_char(tmp_path, "sorc20",    "Sorcerer", level=20, cha=20)
    _make_char(tmp_path, "wiz20",     "Wizard",   level=20, int=20)
    _make_char(tmp_path, "bard20",    "Bard",     level=20, cha=20)
    _make_char(tmp_path, "cleric1",   "Cleric",   level=1,  wis=16)
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", tmp_path)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


# ── (a) Ende-til-ende-generering ─────────────────────────────────────────────

@pytest.mark.parametrize("slug,expected_text", [
    ("bard1",   "Bard"),
    ("sorc1",   "Sorcerer"),
    ("wiz1",    "Wizard"),
])
def test_class_renders_ok(client, slug, expected_text):
    """Karakter-arket loader uden fejl og viser klassenavnet."""
    r = client.get(f"/karakter/{slug}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert expected_text in html


# ── (b) Spell-slot-tal mod SRD ───────────────────────────────────────────────

def _slots_no_bonus(cls, level):
    """Basis-spell-slots (ingen ability-bonus) for klasse/level fra DB."""
    data = db_module.get_class_level(cls.lower(), level)
    assert data is not None, f"Ingen class_level-data for {cls} level {level}"
    # WIS 10 = mod 0 → ingen bonus
    return char_module.spell_slots_total(data, 10)


@pytest.mark.parametrize("cls,level,expected", [
    # Bard: kun spells 0-6; level 1 = 2×lvl0
    ("Bard",     1,  {0: 2}),
    # Bard: level 10 = 3/3/3/2 + 0-slot for lvl4 udelades (base=0)
    ("Bard",    10,  {0: 3, 1: 3, 2: 3, 3: 2}),
    # Bard: level 20 = 4/4/4/4/4/4/4
    ("Bard",    20,  {0: 4, 1: 4, 2: 4, 3: 4, 4: 4, 5: 4, 6: 4}),
    # Sorcerer: level 1 = 5/3
    ("Sorcerer", 1,  {0: 5, 1: 3}),
    # Sorcerer: level 10 = 6/6/6/6/5/3
    ("Sorcerer", 10, {0: 6, 1: 6, 2: 6, 3: 6, 4: 5, 5: 3}),
    # Sorcerer: level 20 = 6 i alle 10 niveauer
    ("Sorcerer", 20, {0: 6, 1: 6, 2: 6, 3: 6, 4: 6, 5: 6, 6: 6, 7: 6, 8: 6, 9: 6}),
    # Wizard: level 1 = 3/1
    ("Wizard",   1,  {0: 3, 1: 1}),
    # Wizard: level 10 = 4/4/4/3/3/2
    ("Wizard",  10,  {0: 4, 1: 4, 2: 4, 3: 3, 4: 3, 5: 2}),
    # Wizard: level 20 = 4 i alle 10 niveauer
    ("Wizard",  20,  {0: 4, 1: 4, 2: 4, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4}),
])
def test_base_spell_slots(cls, level, expected):
    """Basis-slots uden ability-bonus matcher SRD-tabellen."""
    assert _slots_no_bonus(cls, level) == expected


# ── (c) cast_ability bruges korrekt ──────────────────────────────────────────

def test_cast_ability_bard_is_cha():
    assert refdata.class_data("bard").get("cast_ability") == "cha"


def test_cast_ability_sorcerer_is_cha():
    assert refdata.class_data("sorcerer").get("cast_ability") == "cha"


def test_cast_ability_wizard_is_int():
    assert refdata.class_data("wizard").get("cast_ability") == "int"


def test_sorcerer_high_cha_gets_bonus_slots():
    """Sorcerer CHA 20 (mod +5) ved level 1 → bonus på lvl 1-5."""
    data = db_module.get_class_level("sorcerer", 1)
    slots = char_module.spell_slots_total(data, 20)   # CHA 20
    # Base: {0:5, 1:3}; CHA-mod +5 → bonus på lvl1 (+1), lvl2-5 (men base=0 → ikke medregnet)
    assert slots[1] > 3   # bonus pga. CHA
    assert slots[0] == 5  # cantrips: aldrig bonus


def test_wizard_high_int_gets_bonus_slots():
    """Wizard INT 18 (mod +4) ved level 5 → bonus på lvl 1-3 (base>0 krævet).

    Wizard level 5 har base: 4/3/2/1 → bonus slår igennem på lvl 1-3.
    Level 4 har base=0 → bonus slots tæller ikke med (SRD-regel: min. 1 base).
    """
    data = db_module.get_class_level("wizard", 5)
    base_slots = char_module.spell_slots_total(data, 10)   # INT 10, ingen bonus
    bonus_slots = char_module.spell_slots_total(data, 18)  # INT 18, +4 mod
    assert bonus_slots[1] > base_slots[1]
    assert bonus_slots[3] > base_slots[3]   # lvl 3 har base=1 → bonus inkluderes
    assert 4 not in bonus_slots              # lvl 4 base=0 → udelades (korrekt)


def test_bard_high_cha_gets_bonus_slots():
    """Bard CHA 18 (mod +4) ved level 10 → bonus på lvl 1-4."""
    data = db_module.get_class_level("bard", 10)
    base_slots = char_module.spell_slots_total(data, 10)
    bonus_slots = char_module.spell_slots_total(data, 18)
    assert bonus_slots[1] > base_slots[1]
    assert bonus_slots[3] > base_slots[3]


# ── (d) Cleric/druid-slot-adfærd er uændret ──────────────────────────────────

def test_cleric_still_uses_wis(client):
    """Cleric-arket loader stadig korrekt (wis er default cast_ability)."""
    r = client.get("/karakter/cleric1")
    assert r.status_code == 200
    assert "Cleric" in r.get_data(as_text=True)


def test_cleric_cast_ability_is_wis():
    assert refdata.class_data("cleric").get("cast_ability") == "wis"


def test_druid_cast_ability_is_wis():
    assert refdata.class_data("druid").get("cast_ability") == "wis"


def test_paladin_cast_ability_is_wis():
    assert refdata.class_data("paladin").get("cast_ability") == "wis"


def test_ranger_cast_ability_is_wis():
    assert refdata.class_data("ranger").get("cast_ability") == "wis"


def test_cleric_wis_bonus_slots_unchanged():
    """Cleric WIS 18 (mod +4) ved level 5: slot-beregning som før (wis-drevet)."""
    data = db_module.get_class_level("cleric", 5)
    base = char_module.spell_slots_total(data, 10)
    with_wis = char_module.spell_slots_total(data, 18)
    assert with_wis[1] > base[1]
    assert with_wis[3] > base[3]


# ── Fase 2: level_bard-kolonne og spell-data ─────────────────────────────────

def test_level_bard_column_exists():
    """level_bard-kolonnen skal eksistere i spells-tabellen."""
    import sqlite3, os
    db_path = os.environ.get("DND_DB_PATH", str(pathlib.Path(__file__).parent / "srd35.db"))
    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(spells)")]
    conn.close()
    assert "level_bard" in cols, "level_bard mangler i spells-tabellen"


def test_level_bard_has_entries():
    """level_bard-kolonnen skal have mindst 16 L0- og 26 L1-spells."""
    import sqlite3, os
    db_path = os.environ.get("DND_DB_PATH", str(pathlib.Path(__file__).parent / "srd35.db"))
    conn = sqlite3.connect(db_path)
    n0 = conn.execute("SELECT count(*) FROM spells WHERE level_bard=0").fetchone()[0]
    n1 = conn.execute("SELECT count(*) FROM spells WHERE level_bard=1").fetchone()[0]
    conn.close()
    assert n0 == 16, f"Forventede 16 bard L0-spells, fik {n0}"
    assert n1 == 26, f"Forventede 26 bard L1-spells, fik {n1}"


def test_magic_missile_is_wizard_1():
    spell = db_module.get_spell("magic_missile")
    assert spell is not None, "magic_missile ikke fundet"
    assert spell["level_wizard"] == 1


def test_sleep_is_wizard_1_and_bard_1():
    spell = db_module.get_spell("sleep")
    assert spell is not None, "sleep ikke fundet"
    assert spell["level_wizard"] == 1
    assert spell["level_bard"] == 1


def test_acid_splash_is_wizard_0():
    spell = db_module.get_spell("acid_splash")
    assert spell is not None, "acid_splash ikke fundet"
    assert spell["level_wizard"] == 0


def test_daze_is_bard_0_and_wizard_0():
    spell = db_module.get_spell("daze")
    assert spell is not None, "daze ikke fundet"
    assert spell["level_bard"] == 0
    assert spell["level_wizard"] == 0


# ── Spot-verifikation: print for manuel kontrol ───────────────────────────────

def test_spot_check_levels(capsys):
    """Printer slots for level 1/5/10/20 — sammenlign manuelt med SRD."""
    for cls in ("Bard", "Sorcerer", "Wizard"):
        for lvl in (1, 5, 10, 20):
            data = db_module.get_class_level(cls.lower(), lvl)
            slots = char_module.spell_slots_total(data, 10)
            print(f"{cls:10} lvl {lvl:2}: {slots}")
    captured = capsys.readouterr()
    # Spot-tjek: wizarden har 4/3/2/1 ved level 5
    assert "Wizard" in captured.out
    assert "Sorcerer" in captured.out
    assert "Bard" in captured.out


# ── Fase 3: arkan casting-model (DC, cast_type, spontan-visning, known) ───────

def test_spell_save_dc_formula():
    """DC = 10 + spell-niveau + caster-mod + Spell Focus-bonus."""
    assert char_module.spell_save_dc(1, 3) == 14
    assert char_module.spell_save_dc(0, 3) == 13
    assert char_module.spell_save_dc(1, 3, 1) == 15


def test_spell_focus_matches_base_school():
    """Spell Focus (Evocation) gælder 'Evocation [Force]' o.l. — basis-skolen, ikke
    den fulde school-streng (regressionstest for subskole/deskriptor-match)."""
    feats = [{"id": "spell_focus", "school": "Evocation"}]
    assert char_module.spell_focus_bonus(feats, "Evocation [Force]") == 1
    assert char_module.spell_focus_bonus(feats, "Evocation [Cold]") == 1
    assert char_module.spell_focus_bonus(feats, "Conjuration (Creation) [Force]") == 0
    assert char_module.spell_focus_bonus(feats, "Divination") == 0


def test_greater_spell_focus_stacks():
    """Spell Focus + Greater Spell Focus i samme skole giver +2."""
    feats = [{"id": "spell_focus", "school": "Necromancy"},
             {"id": "greater_spell_focus", "school": "Necromancy"}]
    assert char_module.spell_focus_bonus(feats, "Necromancy") == 2


@pytest.mark.parametrize("cls,expected", [
    ("Sorcerer", "spontaneous"),
    ("Bard", "spontaneous"),
    ("Wizard", "spellbook"),
    ("Cleric", None),
    ("Druid", None),
])
def test_cast_type(cls, expected):
    assert char_module.class_cast_type(cls) == expected


@pytest.mark.parametrize("cls,expected", [
    ("sorcerer", "level_wizard"),   # deler wizard-listen
    ("bard", "level_bard"),
    ("wizard", "level_wizard"),
    ("cleric", "level_cleric"),
    ("fighter", None),
])
def test_spell_list_column(cls, expected):
    assert db_module.spell_list_column(cls) == expected


def test_sorcerer_shows_spontaneous_view(client):
    """Sorcerer-arket viser den spontane 'Kendte'-visning, ikke forberedelse."""
    html = client.get("/karakter/sorc1").get_data(as_text=True)
    assert "✨ Kendte" in html
    assert "📖 Forberedte" not in html


def test_prepared_caster_unchanged(client):
    """Cleric beholder forberedelses-visningen (ingen spontan 'Kendte')."""
    html = client.get("/karakter/cleric1").get_data(as_text=True)
    assert "📖 Forberedte" in html
    assert "✨ Kendte" not in html


def test_bard_shows_spontaneous_view(client):
    """Bard er spontan og læser sin egen liste (level_bard) i 'Lær nye'."""
    html = client.get("/karakter/bard1").get_data(as_text=True)
    assert "✨ Kendte" in html
    assert "📖 Forberedte" not in html


def test_wizard_shows_spellbook_view(client):
    """Wizard-arket har Forberedte + Spellbog (forbereder FRA bogen), ikke
    'Alle tilgængelige' eller den spontane 'Kendte'."""
    html = client.get("/karakter/wiz1").get_data(as_text=True)
    assert "📖 Forberedte" in html
    assert "📕 Spellbog" in html
    assert "Alle tilgængelige" not in html
    assert "✨ Kendte" not in html


def test_spells_known_round_trip(tmp_path):
    """spells_known + spells_known_used overlever save/load."""
    path = _make_char(tmp_path, "sknown", "Sorcerer", level=4, cha=16)
    char_module.save_character(str(path), {
        "spells_known": {0: ["detect_magic", "light"], 1: ["magic_missile"]},
        "spells_known_used": {1: 2, 0: 0},
    })
    c = char_module.load_character(str(path))
    assert c.spells_known == {0: ["detect_magic", "light"], 1: ["magic_missile"]}
    assert c.spells_known_used == {1: 2}   # 0-værdier persisteres ikke
