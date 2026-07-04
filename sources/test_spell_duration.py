"""Unit-tests for kategori F: varigheds-parser + utility-udledning.

Kør: python -m pytest test_spell_duration.py   (fra sources/)

spell_duration parser spells.yaml's prosa-varighed til et tal der skalerer med
casterniveau. Den gætter ALDRIG: uparsbar tekst → computed=None, rå tekst som note.
spell_is_utility identificerer kategori F som residual (intet angreb/effekt/summon).
"""
import db
from spells import spell_duration, spell_is_utility, derive_active_utility


def _dur(text, cl=5):
    return spell_duration({"duration": text}, cl)


# ── Skalerende varighed (N unit/level) ──────────────────────────────────────

def test_min_per_level_scales():
    d = _dur("10 min./level", cl=5)
    assert d["value"] == 50 and d["unit"] == "min"
    assert d["computed"] == "50 min" and d["per_level"] is True


def test_round_per_level_dismissible():
    d = _dur("1 round/level (D)", cl=2)
    assert d["computed"] == "2 runder"
    assert d["dismissible"] is True


def test_hour_per_level_singular_label():
    d = _dur("1 hour/level", cl=1)
    assert d["computed"] == "1 time"


def test_day_per_level_word_one_normalized():
    # SRD's "One day/level" normaliseres til "1 day/level" og skalerer.
    d = _dur("One day/level", cl=3)
    assert d["value"] == 3 and d["unit"] == "day"
    assert d["computed"] == "3 dage" and d["per_level"] is True


# ── Fast varighed (uden /level) ─────────────────────────────────────────────

def test_fixed_hours():
    d = _dur("24 hours")
    assert d["value"] == 24 and d["unit"] == "hour"
    assert d["computed"] == "24 timer" and d["per_level"] is False


# ── Koncentration ───────────────────────────────────────────────────────────

def test_concentration_up_to_scales_and_flags():
    d = _dur("Concentration, up to 1 min./level (D)", cl=4)
    assert d["concentration"] is True and d["dismissible"] is True
    assert d["computed"] == "4 min"


def test_pure_concentration_has_no_number():
    d = _dur("Concentration")
    assert d["concentration"] is True and d["computed"] is None


# ── Markører uden varigt tal ────────────────────────────────────────────────

def test_instantaneous():
    d = _dur("Instantaneous")
    assert d["instantaneous"] is True and d["computed"] is None


def test_permanent():
    d = _dur("Permanent (D)")
    assert d["permanent"] is True and d["dismissible"] is True


def test_see_text_is_special_no_guess():
    d = _dur("See text")
    assert d["special"] is True and d["computed"] is None


def test_empty_duration_returns_none():
    assert spell_duration({"duration": ""}, 5) is None
    assert spell_duration({}, 5) is None


# ── Utility-identifikation (residual) mod ægte data ─────────────────────────

def test_fly_is_utility():
    assert spell_is_utility("fly", db) is True


def test_magic_missile_is_not_utility():        # kategori B (har spell_attacks)
    assert spell_is_utility("magic_missile", db) is False


def test_fireball_is_not_utility():             # kategori E (save-række)
    assert spell_is_utility("fireball", db) is False


def test_mage_armor_is_not_utility():           # kategori A (effekt-post)
    assert spell_is_utility("mage_armor", db) is False


def test_derive_active_utility_lists_active_fly():
    from character import load_character
    c = load_character("defaults/tjorn.yaml")
    c.spells_prepared = {3: ["fly"]}
    c.spells_active = {3: [0]}
    c.spells_used = {}
    rows = derive_active_utility(c, db)
    assert len(rows) == 1
    assert rows[0]["label"] == "Fly"
    assert rows[0]["computed"] == f"{c.level} min"      # 1 min./level


def test_derive_skips_instantaneous_utility():
    from character import load_character
    c = load_character("defaults/tjorn.yaml")
    c.spells_prepared = {1: ["knock"]}      # Instantaneous utility → ingen varighed
    c.spells_active = {1: [0]}
    c.spells_used = {}
    assert derive_active_utility(c, db) == []
