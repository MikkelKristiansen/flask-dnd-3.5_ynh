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
    assert r["gained"][0]["buff_id"] == "animal_rage"  # aktiverbar (≠ barbar-rage)


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
    rage = next(e for e in na["gained"] if e["slug"] == "rage")
    assert rage["activatable"] and not rage["active"]
    assert all("special_attacks" != k for k in form)  # gamle rå felter er væk


def test_active_rage_applies_to_form_scores_and_ac():
    """Rage tændt → +4 Str/+4 Con og −2 AC slår igennem i formen."""
    c = cm.load_character("defaults/tjorn.yaml")
    c.level = 5
    c.combat = {**c.combat, "bab": 3}
    c.wild_shape = {"current_form": "badger"}
    off = W.build_wild_shape_form(c, WS, db_module)

    c.wild_shape = {"current_form": "badger", "active_abilities": ["rage"]}
    on = W.build_wild_shape_form(c, WS, db_module)

    assert on["abilities"]["str"] == off["abilities"]["str"] + 4
    assert on["abilities"]["con"] == off["abilities"]["con"] + 4
    assert on["ac"]["ac"] == off["ac"]["ac"] - 2
    # +4 Str = +2 mod → primær-klo-angreb rammer +2 og slår +2 mere i skade
    assert on["attacks"][0]["to_hit"] == off["attacks"][0]["to_hit"] + 2
    rage = next(e for e in on["natural_abilities"]["gained"] if e["slug"] == "rage")
    assert rage["active"]


def _wild_form(form_id, level=12, bab=9):
    c = cm.load_character("defaults/tjorn.yaml")
    c.level = level
    c.combat = {**c.combat, "bab": bab}
    c.wild_shape = {"current_form": form_id}
    return W.build_wild_shape_form(c, WS, db_module)


def _ability(form, slug):
    return next(e for e in form["natural_abilities"]["gained"] if e["slug"] == slug)


def test_rake_rider_rolls_use_form_str_and_bab():
    """Dire tiger: rake = 2 ekstra angreb, til-hit BAB+Str+størrelse, skade 2d4+Str."""
    rake = _ability(_wild_form("dire_tiger"), "rake")
    roll = rake["rider"]["rolls"][0]
    # dire_tiger Str 27 (+8), Large (−1), BAB 9 → til-hit +16; skade 2d4+8; ×2.
    assert roll["to_hit"] == 16 and roll["damage"] == "2d4+8" and roll["count"] == 2


def test_rend_rider_adds_1_5_str_and_has_no_to_hit():
    rend = _ability(_wild_form("dire_ape"), "rend")
    roll = rend["rider"]["rolls"][0]
    # dire_ape Str 23 (+6) → 2d6 + floor(1.5*6)=+9; rend er automatisk (intet til-hit).
    assert roll["damage"] == "2d6+9" and "to_hit" not in roll


def test_note_only_rider_has_trigger_but_no_rolls():
    pounce = _ability(_wild_form("dire_tiger"), "pounce")
    assert pounce["rider"]["rolls"] == []
    assert "charger" in pounce["rider"]["trigger"]


def test_form_skills_use_form_scores_and_size():
    """Skills i form bruger formens fysiske scores; Hide får størrelses-mod (×4)."""
    import models
    from character import size_mod_attack
    c = cm.load_character("defaults/tjorn.yaml")
    c.level = 12
    c.combat = {**c.combat, "bab": 9}
    c.skills = [models.Skill(id="climb", ranks=5, misc=0),
                models.Skill(id="hide", ranks=4, misc=1)]
    c.wild_shape = {"current_form": "dire_tiger"}        # Large-form
    form = W.build_wild_shape_form(c, WS, db_module)
    ab = form["abilities"]
    smod = lambda score: (score - 10) // 2
    sk = {s["name"]: s["total"] for s in form["skills"]}
    assert sk["Climb"] == 5 + smod(ab["str"])            # Str-skill: ranks + form-Str-mod
    # Hide (Dex): ranks + form-Dex-mod + misc + størrelses-mod (Large = −4)
    assert sk["Hide"] == 4 + smod(ab["dex"]) + 1 + size_mod_attack("large") * 4
