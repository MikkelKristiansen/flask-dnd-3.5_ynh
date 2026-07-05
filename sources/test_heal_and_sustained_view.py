"""Integrationstests: rulbar healing + vedvarende save-spells i selve view-laget.

Kør: python -m pytest test_heal_and_sustained_view.py   (fra sources/)

Dækker de to sammenbyggede briefs (BRIEF-heal-cast.md + BRIEF-sustained-save-
duration.md) ende-til-ende gennem build_character_view, ikke bare de rene
spells.py-funktioner: at ⚡ Kast · helbred rent faktisk dukker op på en forberedt
cure-spell, og at Flaming Sphere bliver tre-tilstand UDEN engangs-⚡-Kast og med
en runde-tæller i Spell-effekter.
"""
import db
import character as char_module
import character_view as cv


def _cleric(level=3):
    ch = char_module.load_character("defaults/tjorn.yaml")
    ch.cls, ch.level = "Cleric", level
    return ch


def test_prepared_cure_light_wounds_gets_green_heal_cast_button():
    ch = _cleric(level=3)
    ch.spells_prepared = {1: ["cure_light_wounds"]}
    ch.spells_active = {}
    ch.spells_used = {}
    entry = cv.build_character_view(ch, db)["spell_data"][1][0]
    assert entry["three_state"] is False
    assert entry["cast"]["kind"] == "heal"
    assert entry["cast"]["roll_expr"] == "1d8+3"
    assert entry["cast"]["button_label"] == "⚡ Kast · helbred"


def test_flaming_sphere_becomes_three_state_with_no_cast_button():
    ch = _cleric(level=3)
    ch.spells_prepared = {2: ["flaming_sphere"]}
    ch.spells_active = {}
    ch.spells_used = {}
    entry = cv.build_character_view(ch, db)["spell_data"][2][0]
    assert entry["three_state"] is True
    assert entry["cast"] is None   # vedvarende spell bruger toggle, ikke engangs-kast


def test_active_flaming_sphere_shows_up_in_spell_effects_with_tracker():
    ch = _cleric(level=3)
    ch.spells_prepared = {2: ["flaming_sphere"]}
    ch.spells_active = {2: [0]}
    ch.spells_used = {}
    ch.spell_durations = {}
    view = cv.build_character_view(ch, db)
    effects = view["spell_effects"]
    assert len(effects) == 1
    assert effects[0]["damage"] == "2d6"
    assert effects[0]["tracker"] == {"left": 3, "max": 3, "unit": "round"}


def test_instantaneous_fireball_keeps_its_engangs_cast_button():
    # Kontrol: en øjeblikkelig E-spell (ingen runde-varighed) er IKKE tre-tilstand
    # og beholder sin eksisterende engangs-⚡-Kast — kun vedvarende spells gates væk.
    ch = _cleric(level=5)
    ch.spells_prepared = {3: ["fireball"]}
    ch.spells_active = {}
    ch.spells_used = {}
    entry = cv.build_character_view(ch, db)["spell_data"][3][0]
    assert entry["three_state"] is False
    assert entry["cast"]["kind"] == "save"
