"""Unit-tests for Summon Familiar (Wizard/Sorcerer) — bygget på companion-motoren.

Kør: python -m pytest test_familiar.py   (fra sources/)

Dækker: eligibility, SRD-avancement (naturlig rustning/Int/specials), HP = ½ mester,
og at typens MESTER-bonus (rat +2 Fort, toad +3 HP) faktisk rammer mesterens tal.
"""
import db
import familiar as fam
import character as char_module
import character_view as cv


def _wizard(level=5, hp_max=30, familiar_id=None):
    ch = char_module.load_character("defaults/tjorn.yaml")
    ch.cls, ch.level, ch.hp_max = "Wizard", level, hp_max
    ch.companion = {"kind": "familiar", "animal": familiar_id, "name": "F"} if familiar_id else {}
    return ch


def test_eligibility():
    assert fam.familiar_eligible("Wizard", 1)
    assert fam.familiar_eligible("Sorcerer", 3)
    assert not fam.familiar_eligible("Druid", 10)
    assert not fam.familiar_eligible("Wizard", 0)


def test_advancement_table_matches_srd():
    # level 1-2 → na +1 / Int 6; 3-4 → +2 / 7; 19-20 → +10 / 15.
    assert fam.familiar_deltas(1)["na_bonus"] == 1 and fam.familiar_deltas(1)["int_set"] == 6
    assert fam.familiar_deltas(4)["na_bonus"] == 2 and fam.familiar_deltas(4)["int_set"] == 7
    assert fam.familiar_deltas(20)["na_bonus"] == 10 and fam.familiar_deltas(20)["int_set"] == 15


def test_specials_accumulate():
    s1 = fam.familiar_deltas(1)["specials"]
    assert "Alertness" in s1 and "Share Spells" in s1 and "Deliver Touch Spells" not in s1
    s5 = fam.familiar_deltas(5)["specials"]
    assert "Deliver Touch Spells" in s5 and "Speak with Master" in s5
    assert "Scry on Familiar" in fam.familiar_deltas(13)["specials"]


def test_familiar_hp_is_half_master():
    ch = _wizard(hp_max=30, familiar_id="owl")
    assert fam.build_familiar(ch, db)["hp_max"] == 15
    ch2 = _wizard(hp_max=41, familiar_id="rat")   # ulige → rundet ned
    assert fam.build_familiar(ch2, db)["hp_max"] == 20


def test_build_returns_none_without_familiar():
    assert fam.build_familiar(_wizard(), db) is None                 # ingen companion
    ch = _wizard(); ch.companion = {"kind": "companion", "animal": "wolf"}
    assert fam.build_familiar(ch, db) is None                        # forkert kind


def _fort(ch):
    v = cv.build_character_view(ch, db)
    return next(s for s in v["saves"] if s["name"] == "Fortitude")["val"]


def test_rat_familiar_gives_master_plus2_fort():
    base = _fort(_wizard())
    assert _fort(_wizard(familiar_id="rat")) == base + 2


def test_toad_familiar_gives_master_plus3_hp():
    base = cv.build_character_view(_wizard(), db)["hp_max_eff"]
    assert cv.build_character_view(_wizard(familiar_id="toad"), db)["hp_max_eff"] == base + 3


def test_familiar_uses_companion_tab_without_tricks():
    ch = _wizard(familiar_id="owl")
    st = fam.build_familiar(ch, db)
    assert st["kind"] == "familiar" and st["tricks"] == []
    assert "Speak with Master" in st["specials"]           # mester-level 5
