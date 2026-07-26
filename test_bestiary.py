"""Tests for DM-bestiaret: db.get_monster + bestiary.monster_view mod den
seedede skelet-reference. Kræver at srd35.db er bygget (importer.py)."""
import bestiary
import db


def test_skeleton_seeded_and_shaped():
    row = db.get_monster("skelet")
    assert row is not None, "skelet mangler i srd35.db — kør importer.py"
    v = bestiary.monster_view(row)
    assert v["name"] == "Skelet (menneske)"
    assert v["type"] == "undead"
    assert v["hp_max"] == 6
    assert v["ac"] == {"ac": 15, "touch": 11, "flat_footed": 14,
                       "note": "+1 Dex, +2 naturlig, +2 tungt stålskjold"}
    assert v["saves"] == {"fort": 0, "ref": 1, "will": 2}


def test_missing_ability_score_shows_dash():
    # Udøde har hverken Con eller Int → "—", ikke en falsk +0.
    v = bestiary.monster_view(db.get_monster("skelet"))
    mods = {a["key"]: a["mod"] for a in v["abilities"]}
    assert mods["con"] == "—" and mods["int"] == "—"
    assert mods["str"] == "+1" and mods["cha"] == "-5"


def test_attacks_and_feats_decoded_to_lists():
    v = bestiary.monster_view(db.get_monster("skelet"))
    assert [a["name"] for a in v["attacks"]] == ["Krumsabel", "Klo"]
    assert v["feats"] == ["Improved Initiative"]


def test_unknown_monster_is_none():
    assert db.get_monster("findes-ikke") is None
