"""Test for Rogue Sneak Attack-visningen (beregnet klasseevne, ikke fast skade).

Sneak attack = +1d6 ved lvl 1, +1d6 pr. 2 levels (max 10d6 ved lvl 19). Betinget
skade, så den vises og påføres af spilleren. Kør: python -m pytest test_rogue.py
"""
import pathlib

import pytest
from ruamel.yaml import YAML

import app as app_module

YAML_RW = YAML()
DEFAULTS = pathlib.Path(__file__).parent / "defaults"


@pytest.fixture
def client(tmp_path, monkeypatch):
    def rogue(d):
        d["class"] = "Rogue"; d["level"] = 5
    data = YAML_RW.load((DEFAULTS / "aelred.yaml").read_text())
    rogue(data)
    (tmp_path / "rogue.yaml").write_text("")
    with (tmp_path / "rogue.yaml").open("w") as f:
        YAML_RW.dump(data, f)
    # ikke-rogue kontrol
    cleric = YAML_RW.load((DEFAULTS / "aelred.yaml").read_text())
    with (tmp_path / "cleric.yaml").open("w") as f:
        YAML_RW.dump(cleric, f)
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", tmp_path)
    return app_module.app.test_client()


@pytest.mark.parametrize("level,dice", [(1, 1), (2, 1), (3, 2), (5, 3), (19, 10), (20, 10)])
def test_sneak_dice_formula(level, dice):
    assert (level + 1) // 2 == dice


def test_rogue_panel_shows_sneak_attack(client):
    h = client.get("/karakter/rogue").get_data(as_text=True)
    assert ">Rogue<" in h and "Sneak Attack" in h and "+3d6 skade" in h   # lvl 5 → 3d6


def test_non_rogue_has_no_panel(client):
    h = client.get("/karakter/cleric").get_data(as_text=True)
    assert "Sneak Attack" not in h
