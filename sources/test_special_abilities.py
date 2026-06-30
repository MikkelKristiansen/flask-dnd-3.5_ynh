"""Tests for special-evne-resolveren (natural abilities ved wild shape).

Dækker token-parsing, slug-udledning og overførsels-reglen (animal: kun Ex
special attacks; elemental: alt). Kør: python -m pytest test_special_abilities.py
"""
import db as db_module
import character as cm
import special_abilities as sa
import wild_shape as W

WS = cm.class_wild_shape("Druid")


def test_split_tokens_is_paren_aware():
    # Kommaet inde i parentesen må IKKE splitte token'et.
    assert sa._split_tokens("Poison (Fort DC 14, 1d6 Con)") == ["Poison (Fort DC 14, 1d6 Con)"]
    assert sa._split_tokens("Air mastery, whirlwind (Reflex DC 28)") == \
        ["Air mastery", "whirlwind (Reflex DC 28)"]
    assert sa._split_tokens(None) == []


def test_slug_strips_numbers_and_punctuation():
    assert sa._slug("rake 2d4+4") == "rake"
    assert sa._slug("Improved grab") == "improved_grab"
    assert sa._slug("Low-light vision") == "low_light_vision"
    assert sa._slug("Whirlwind (Reflex DC 28)") == "whirlwind"


def test_animal_form_gains_only_ex_special_attacks():
    """Wolverine: Rage (Ex attack) kobles på; scent/low-light er reference (RAW)."""
    r = sa.resolve_form_abilities("Rage", "Low-light vision, scent", "animal", db_module)
    gained = {e["slug"] for e in r["gained"]}
    reference = {e["slug"] for e in r["reference"]}
    assert gained == {"rage"}
    assert reference == {"low_light_vision", "scent"}
    assert r["gained"][0]["buff_id"] == "rage"  # aktiverbar


def test_su_sp_attacks_not_gained_on_animal_form():
    r = sa.resolve_form_abilities("Spell-like abilities", None, "animal", db_module)
    assert r["gained"] == []
    assert r["reference"][0]["slug"] == "spell_like_abilities"


def test_elemental_form_gains_everything():
    r = sa.resolve_form_abilities(
        "Air mastery, whirlwind (Reflex DC 28)", "Darkvision 60 ft.", "elemental", db_module)
    assert r["reference"] == []
    assert {e["slug"] for e in r["gained"]} == {"air_mastery", "whirlwind", "darkvision"}


def test_form_label_keeps_creature_specific_numbers():
    r = sa.resolve_form_abilities("Improved grab, constrict 2d8+6", None, "animal", db_module)
    labels = {e["label"] for e in r["gained"]}
    assert "constrict 2d8+6" in labels  # form-specifikke tal bevares i labelen


def test_build_form_exposes_natural_abilities():
    c = cm.load_character("defaults/tjorn.yaml")
    c.level = 5
    c.combat = {**c.combat, "bab": 3}
    c.wild_shape = {"current_form": "badger"}
    form = W.build_wild_shape_form(c, WS, db_module)
    na = form["natural_abilities"]
    assert any(e["slug"] == "rage" for e in na["gained"])
    assert all("special_attacks" != k for k in form)  # gamle rå felter er væk
