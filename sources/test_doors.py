"""Tests for dør-data-laget: db.get_door + doors.door_view.

Kør: python -m pytest test_doors.py   (fra sources/)

Kræver et seedet srd35.db (python importer.py) med doors-tabellen.
"""
import db
import doors


def test_get_door_unlocked():
    d = db.get_door("iron-door")
    assert d is not None
    assert d["name"] == "Jerndør"
    assert d["hardness"] == 10 and d["hp"] == 60
    assert d["open_lock_dc"] is None                # ulåst → intet Open Lock-DC


def test_get_door_locked():
    d = db.get_door("locked-iron-door")
    assert d["open_lock_dc"] == 30
    assert "God lås" in d["note"]


def test_get_door_unknown_is_none():
    assert db.get_door("findes-ikke") is None


def test_get_all_doors_sorted_by_name():
    names = [d["name"] for d in db.get_all_doors()]
    assert "Jerndør" in names and "Simpel trædør" in names
    assert names == sorted(names)


def test_door_view_shapes_row():
    v = doors.door_view(db.get_door("simple-wooden-door"))
    assert v["name"] == "Simpel trædør"
    assert v["material"] == "wood" and v["thickness"] == "1 in."
    assert v["hardness"] == 5 and v["hp"] == 10


def test_door_view_name_falls_back_to_id():
    v = doors.door_view({"id": "mystisk-dor"})
    assert v["name"] == "mystisk-dor"               # intet name → id
    assert v["material"] is None                     # manglende felter → None
