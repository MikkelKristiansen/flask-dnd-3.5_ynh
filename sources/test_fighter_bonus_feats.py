"""Tests for fighter-bonus-feats ved level-up (se briefs/BRIEF-fighter-bonus-feats.md).

Verificerer:
  (a) levelup_info["bonus_feat_level"] følger class_levels-data ("Bonus Feat" i
      features) — sand for fighter på 2/4/6/8, falsk på 3/5/7/9. Ikke-fighter
      (uden "Bonus Feat" i data) skal aldrig give True.
  (b) persistence.save_character kan tilføje TO feats på ét niveau (new_feats),
      med dedup på tværs af listen.

Kør: python -m pytest test_fighter_bonus_feats.py   (fra sources/)
"""
import pathlib

import pytest
from ruamel.yaml import YAML

import character as char_module
import character_view
import db as db_module

YAML_RW = YAML()
DEFAULTS = pathlib.Path(__file__).parent / "defaults"


def _make_char(tmp_path, slug, cls, level, feats=None):
    """Skriv en minimal karakter til tmp_path og returnér stien."""
    data = YAML_RW.load((DEFAULTS / "aelred.yaml").read_text())
    data["class"] = cls
    data["level"] = level
    data["name"] = slug.capitalize()
    data.pop("domains", None)
    data.pop("domain_spells_prepared", None)
    data.pop("domain_spells_used", None)
    data.pop("spells_prepared", None)
    data.pop("spells_used", None)
    data.pop("class_features", None)
    if feats is not None:
        data["feats"] = list(feats)
    path = tmp_path / f"{slug}.yaml"
    with path.open("w") as f:
        YAML_RW.dump(data, f)
    return path


# ── (a) bonus_feat_level-flag ────────────────────────────────────────────────

@pytest.mark.parametrize("level,expect_bonus,expect_general", [
    (1, True,  False),   # new_level 2: fighter Bonus Feat, ikke generel feat-niveau
    (2, False, True),    # new_level 3: generel feat-niveau, ingen bonus
    (3, True,  False),   # new_level 4: bonus
    (4, False, False),   # new_level 5: hverken/eller
    (5, True,  True),    # new_level 6: BÅDE bonus og generel
    (6, False, False),   # new_level 7: hverken/eller
    (7, True,  False),   # new_level 8: bonus
])
def test_fighter_bonus_feat_level(tmp_path, level, expect_bonus, expect_general):
    """Fighter får bonus_feat_level på 2,4,6,8 (og feat_level på 3,6,9 som hidtil)."""
    path = _make_char(tmp_path, "figh", "Fighter", level=level)
    char = char_module.load_character(str(path))
    v = character_view.build_character_view(char, db_module)
    info = v["levelup_info"]
    assert info["bonus_feat_level"] is expect_bonus
    assert info["feat_level"] is expect_general


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 7])
def test_non_fighter_never_gets_bonus_feat_level(tmp_path, level):
    """Cleric har ikke 'Bonus Feat' i class_levels-data → altid False."""
    path = _make_char(tmp_path, "clr", "Cleric", level=level)
    char = char_module.load_character(str(path))
    v = character_view.build_character_view(char, db_module)
    assert v["levelup_info"]["bonus_feat_level"] is False


def test_fighter_bonus_feat_flag_in_all_feats_json(tmp_path):
    """all_feats_json markerer fighter_bonus-puljen, så UI'et kan filtrere på den."""
    path = _make_char(tmp_path, "figh2", "Fighter", level=1)
    char = char_module.load_character(str(path))
    v = character_view.build_character_view(char, db_module)
    by_id = {f["id"]: f for f in v["all_feats_json"]}
    assert by_id["dodge"]["fighter_bonus"] is True
    # Toughness er ikke en kampfeat — skal ikke være markeret.
    assert by_id.get("toughness", {}).get("fighter_bonus", False) is False


# ── (b) to feats på ét niveau via persistence ────────────────────────────────

def test_save_character_new_feats_list_adds_both(tmp_path):
    path = _make_char(tmp_path, "figh3", "Fighter", level=1, feats=[])
    char_module.save_character(str(path), {
        "new_feats": ["dodge", "combat_reflexes"],
    })
    char = char_module.load_character(str(path))
    assert set(char.feats) >= {"dodge", "combat_reflexes"}
    assert len(char.feats) == 2


def test_save_character_new_feats_dedup_across_list(tmp_path):
    """Samme feat valgt to gange på ét niveau (fx generel + bonus-sektion) → kun én gang."""
    path = _make_char(tmp_path, "figh4", "Fighter", level=1, feats=[])
    char_module.save_character(str(path), {
        "new_feats": ["dodge", "dodge"],
    })
    char = char_module.load_character(str(path))
    assert char.feats == ["dodge"]


def test_save_character_new_feats_dedup_against_existing(tmp_path):
    """Featen findes allerede fra et tidligere niveau → tilføjes ikke igen."""
    path = _make_char(tmp_path, "figh5", "Fighter", level=1, feats=["dodge"])
    char_module.save_character(str(path), {
        "new_feats": ["dodge", "combat_reflexes"],
    })
    char = char_module.load_character(str(path))
    assert char.feats.count("dodge") == 1
    assert "combat_reflexes" in char.feats


def test_save_character_new_feat_and_new_feats_combine(tmp_path):
    """Bagudkompatibilitet: 'new_feat' (enkelt) + 'new_feats' (liste) må gerne kombineres."""
    path = _make_char(tmp_path, "figh6", "Fighter", level=1, feats=[])
    char_module.save_character(str(path), {
        "new_feat": "dodge",
        "new_feats": ["combat_reflexes"],
    })
    char = char_module.load_character(str(path))
    assert set(char.feats) == {"dodge", "combat_reflexes"}
