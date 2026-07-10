"""Tests for at party'ets ledsagere (animal companion / familiar / mount) føres
ind i DM-encounteren som egne combatants.

Kør: python -m pytest test_dm_companions.py   (fra sources/)

Dækker: feltmapning statblok → combatant-kilde, og at en rigtig druide-companion
(defaults/tjorn.yaml → "Varg") dukker op med auto-rulbar init + HP, mens et party
uden ledsagere (eller en ukendt slug) intet bidrager.
"""
from pathlib import Path

import db
import dm_party
import dm_encounter as E


def test_companion_combatant_maps_statblock():
    # initiative-feltet fra statblokken er den fulde init-modifier (kan auto-rulles).
    stat = {"name": "Varg", "kind": "companion", "initiative": 3,
            "hp_max": 26, "hp_current": 20}
    c = dm_party._companion_combatant("tjorn", stat)
    assert c["ref"] == "tjorn-companion"        # bundet til ejeren → unikt id
    assert c["name"] == "Varg"
    assert c["kind"] == "companion"
    assert c["init_mod"] == 3
    assert c["hp_max"] == 26 and c["hp_current"] == 20


def test_companion_kind_defaults_when_missing():
    c = dm_party._companion_combatant("x", {"name": "N", "hp_max": 5})
    assert c["kind"] == "companion" and c["init_mod"] == 0


def test_real_druid_companion_enters_party(monkeypatch):
    # defaults/tjorn.yaml er en level-3 druide med companion "Varg" (ulv).
    monkeypatch.setattr(dm_party, "CHARACTERS_DIR", Path("defaults"))
    comps = dm_party.party_companions(["tjorn"], db)
    assert len(comps) == 1
    v = comps[0]
    assert v["name"] == "Varg" and v["kind"] == "companion"
    assert v["ref"] == "tjorn-companion"
    assert isinstance(v["init_mod"], int)
    assert v["hp_max"] > 0


def test_party_without_companions_yields_nothing(monkeypatch):
    monkeypatch.setattr(dm_party, "CHARACTERS_DIR", Path("defaults"))
    # aelred/faelyn har ingen companion; ukendt-slug findes ikke → springes tavst over.
    assert dm_party.party_companions(["aelred", "faelyn", "ukendt"], db) == []


def test_companion_becomes_trackable_combatant(monkeypatch):
    # Ende-til-ende: ledsager-kilden folder ud til en combatant med egen init + HP,
    # og init auto-rulles (som encounter_start gør for alt der ikke er en PC).
    monkeypatch.setattr(dm_party, "CHARACTERS_DIR", Path("defaults"))
    comps = dm_party.party_companions(["tjorn"], db)
    sources = [{"ref": c["ref"], "count": 1, "name": c["name"], "kind": c["kind"],
                "init_mod": c["init_mod"], "hp_max": c["hp_max"]} for c in comps]
    combs = E.build_combatants(sources)
    E.roll_initiative([c for c in combs if c["kind"] != "pc"],
                      roller=lambda mod: 10 + mod)
    assert len(combs) == 1
    varg = combs[0]
    assert varg["kind"] == "companion"
    assert varg["initiative"] == 10 + comps[0]["init_mod"]   # blev auto-rullet
    assert varg["current_hp"] == varg["hp_max"] > 0          # egen HP-pulje
