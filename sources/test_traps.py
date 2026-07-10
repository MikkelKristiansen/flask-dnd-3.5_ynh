"""Tests for fælde-data-laget: db.get_trap + traps.trap_view.

Kør: python -m pytest test_traps.py   (fra sources/)

Kræver et seedet srd35.db (python importer.py) med traps-tabellen.
"""
import db
import traps


def test_get_trap_attack_based():
    t = db.get_trap("basic-arrow-trap")
    assert t is not None
    assert t["name"] == "Basic Arrow Trap"
    assert t["attack"] == "+10 ranged (1d6/×3, arrow)"
    assert t["save"] is None                       # angrebs-baseret → ingen save
    assert t["search_dc"] == 20 and t["disable_dc"] == 20


def test_get_trap_save_based():
    t = db.get_trap("camouflaged-pit-trap")
    assert t["save"] == "DC 20 Reflex save avoids"
    assert t["attack"] is None                     # save-baseret → intet angreb
    assert t["effect"] == "10 ft. deep (1d6, fall)"


def test_get_trap_unknown_is_none():
    assert db.get_trap("findes-ikke") is None


def test_get_all_traps_sorted_by_name():
    names = [t["name"] for t in db.get_all_traps()]
    assert "Basic Arrow Trap" in names and "Camouflaged Pit Trap" in names
    assert names == sorted(names)


def test_trap_view_shapes_row():
    v = traps.trap_view(db.get_trap("basic-arrow-trap"))
    assert v["name"] == "Basic Arrow Trap"
    assert v["cr"] == "1" and v["trap_type"] == "mechanical"
    assert v["trigger"] == "proximity" and v["reset"] == "manual"


def test_trap_view_name_falls_back_to_id():
    v = traps.trap_view({"id": "mystisk-faelde"})
    assert v["name"] == "mystisk-faelde"           # intet name → id
    assert v["attack"] is None                      # manglende felter → None
