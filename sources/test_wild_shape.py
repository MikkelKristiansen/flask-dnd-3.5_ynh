"""Tests for Wild Shape-formvalg — især plante-/elementar-typerne (data-drevet).

Engine er dækket indirekte; her sikres at type-gatingen + de nye planteformer
faktisk dukker op på de rigtige niveauer. Kør: python -m pytest test_wild_shape.py
"""
import db as db_module
import character as cm
import wild_shape as W

WS = cm.class_wild_shape("Druid")


def _form_ids(level):
    info = W.wild_shape_info(WS, level)
    return {f["id"] for f in W.eligible_forms(info, level, db_module)}


def test_plants_locked_until_level_12():
    assert "shambling_mound" not in _form_ids(11)   # plante-type låses op ved 12
    ids = _form_ids(12)
    assert {"shambling_mound", "assassin_vine"} <= ids


def test_elementals_locked_until_level_16():
    assert not any(i.startswith("elemental_") for i in _form_ids(15))
    assert any(i.startswith("elemental_") for i in _form_ids(16))


def test_shambling_mound_form_matches_srd():
    """Druide-12 i Shambling Mound: Large, AC 20, Slam +13 (2d6+5) med BAB 9."""
    c = cm.load_character("defaults/tjorn.yaml")
    c.level = 12
    c.combat = {**c.combat, "bab": 9}
    c.wild_shape = {"current_form": "shambling_mound"}
    form = W.build_wild_shape_form(c, WS, db_module)
    assert form["size"] == "large" and form["ac"]["ac"] == 20
    slam = form["attacks"][0]
    assert (slam["to_hit"], slam["damage"]) == (13, "2d6+5")
