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


def test_rider_breakdowns():
    """Rytter-angreb bærer hit_parts/dmg_parts der summer til tallene (til hover)."""
    gained = [
        {"name": "Rake", "label": "rake 2d4", "rider_type": "extra_attacks", "rider_count": 2},
        {"name": "Rend", "label": "rend 2d6", "rider_type": "two_hit"},
    ]
    W._attach_riders(gained, bab=3, str_mod=4, size="medium")
    rake = gained[0]["rider"]["rolls"][0]
    # rake: til-hit = BAB + STR (størrelse 0 for medium), skade = terning + 1×STR
    assert rake["to_hit"] == 7 and rake["damage"] == "2d4+4" and rake["count"] == 2
    assert sum(p["value"] for p in rake["hit_parts"]) == rake["to_hit"]
    assert [p for p in rake["dmg_parts"] if "value" in p][0]["value"] == 4
    rend = gained[1]["rider"]["rolls"][0]
    # rend: ingen til-hit, skade = terning + 1,5×STR (floor(4·1.5)=6)
    assert "to_hit" not in rend and rend["damage"] == "2d6+6"
    assert rend["dmg_parts"][1]["label"] == "STR ×1.5" and rend["dmg_parts"][1]["value"] == 6
