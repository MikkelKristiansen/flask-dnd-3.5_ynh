"""Tests for paladin-pakken: Smite Evil + Lay on Hands (app-laget).

Caps (SRD): Lay on Hands-pulje = level × Cha-bonus (kræver Cha 12+), Smite Evil
= 1/dag + 1 pr. 5 levels (max 5). Begge nulstilles ved "Ny dag".

Kør: python -m pytest test_paladin.py   (fra sources/)
"""
import pathlib

import pytest
from ruamel.yaml import YAML

import app as app_module
import character as char_module
import character_view

YAML_RW = YAML()
DEFAULTS = pathlib.Path(__file__).parent / "defaults"


def _write(dst_dir, slug, mutate):
    data = YAML_RW.load((DEFAULTS / "aelred.yaml").read_text())
    mutate(data)
    with (dst_dir / f"{slug}.yaml").open("w") as f:
        YAML_RW.dump(data, f)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Paladin (lvl 6, Cha 14, såret) + en ikke-paladin (cleric) i tmp."""
    def paladin(d):
        d["class"] = "Paladin"; d["level"] = 6
        d["ability_scores"]["cha"] = 14          # +2 → pulje 12, smite +2
        d["hp"]["current"] = 10; d["hp"]["max"] = 50
    _write(tmp_path, "pal", paladin)
    _write(tmp_path, "cleric", lambda d: None)
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", tmp_path)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _load(slug):
    return char_module.load_character(str(app_module.CHARACTERS_DIR / f"{slug}.yaml"))


# ── Caps-formel (ren funktion) ──────────────────────────────────────────────

class _Lvl:
    def __init__(self, level): self.level = level


@pytest.mark.parametrize("level,cha_mod,lay,smite", [
    (1, 1, 1, 1), (2, 2, 4, 1), (5, 2, 10, 2), (6, 2, 12, 2),
    (20, 5, 100, 5), (3, 0, 0, 1), (2, -1, 0, 1),
])
def test_paladin_caps(level, cha_mod, lay, smite):
    assert character_view._paladin_caps(_Lvl(level), cha_mod) == (lay, smite)


# ── Smite Evil ──────────────────────────────────────────────────────────────

def test_smite_decrements_and_caps(client):
    assert client.post("/api/paladin", json={"char": "pal", "action": "smite"}
                       ).get_json() == {"ok": True, "smite_remaining": 1}
    assert _load("pal").smite_used == 1
    # Anden = sidste; tredje må ikke gå under 0.
    client.post("/api/paladin", json={"char": "pal", "action": "smite"})
    r = client.post("/api/paladin", json={"char": "pal", "action": "smite"}).get_json()
    assert r["smite_remaining"] == 0
    assert _load("pal").smite_used == 2          # capped på 2/dag (lvl 6)


# ── Lay on Hands ────────────────────────────────────────────────────────────

def test_lay_on_hands_heals_self_and_caps(client):
    r = client.post("/api/paladin", json={"char": "pal", "action": "lay_on_hands",
                                          "amount": 8}).get_json()
    assert r["hp_current"] == 18 and r["lay_remaining"] == 4
    # Bed om mere end resten (4) → cappes til 4.
    r = client.post("/api/paladin", json={"char": "pal", "action": "lay_on_hands",
                                          "amount": 10}).get_json()
    assert r["hp_current"] == 22 and r["lay_remaining"] == 0
    # Tom pulje afvises.
    assert "error" in client.post("/api/paladin", json={"char": "pal",
                     "action": "lay_on_hands", "amount": 1}).get_json()


def test_newday_resets_paladin_resources(client):
    client.post("/api/paladin", json={"char": "pal", "action": "smite"})
    client.post("/api/paladin", json={"char": "pal", "action": "lay_on_hands", "amount": 5})
    client.post("/api/newday", json={"char": "pal"})
    char = _load("pal")
    assert char.smite_used == 0 and char.lay_on_hands_used == 0


def test_non_paladin_rejected(client):
    assert client.post("/api/paladin", json={"char": "cleric", "action": "smite"}
                       ).status_code == 400


# ── Special Mount ───────────────────────────────────────────────────────────

import companion as companion_module  # noqa: E402
import db as db_module  # noqa: E402


@pytest.mark.parametrize("cls,level,ok", [
    ("Paladin", 5, True), ("Paladin", 4, False), ("Paladin", 20, True),
    ("Cleric", 20, False), ("Druid", 9, False),
])
def test_mount_eligible(cls, level, ok):
    assert companion_module.mount_eligible(cls, level) is ok


def test_mount_advancement_heavy_warhorse():
    """Paladin-5 heavy warhorse matcher SRD: 6 HD, Str 19, Int 6, NA 8, AC 18,
    HP 45, BAB 4, saves 8/6/3, hooves +7 (1d6+4) + bite +2 (1d4+2)."""
    animal = db_module.get_animal("heavy_warhorse")
    st = companion_module.advance_companion(animal, companion_module.mount_deltas(5), db_module)
    assert st["total_hd"] == 6
    assert st["abilities"]["str"] == 19 and st["abilities"]["int"] == 6
    assert st["natural_armor"] == 8 and st["ac"]["ac"] == 18
    assert st["hp_max"] == 45 and st["bab"] == 4
    assert st["saves"] == {"fort": 8, "ref": 6, "will": 3}
    hoof, bite = st["attacks"]
    assert (hoof["to_hit"], hoof["damage"]) == (7, "1d6+4")
    assert (bite["to_hit"], bite["damage"]) == (2, "1d4+2")
    assert "Empathic Link" in st["specials"]


def test_mount_specials_accumulate():
    """Specials akkumulerer: en level-15 mount har stadig empathic link + de øvrige."""
    s = companion_module.mount_deltas(15)["specials"]
    assert "Empathic Link" in s and "Improved Speed (+10 ft.)" in s
    assert any("Spell Resistance" in x for x in s)
    # Str-bonus følger tabellen (+4 ved 15-20), Int sættes til 9.
    assert companion_module.mount_deltas(15)["str_bonus"] == 4
    assert companion_module.mount_deltas(15)["int_set"] == 9


def test_summon_and_dismiss_mount(client):
    """Paladin (lvl 6) tilkalder en heavy warhorse → gemmes med kind='mount'."""
    r = client.post("/api/companion", json={"char": "pal", "action": "summon",
                    "animal": "heavy_warhorse", "name": "Brunhilde"}).get_json()
    assert r == {"ok": True}
    comp = _load("pal").companion
    assert comp["kind"] == "mount" and comp["animal"] == "heavy_warhorse"
    assert comp["hp_current"] == 45            # 6 HD heavy warhorse
    # Afsked rydder den.
    client.post("/api/companion", json={"char": "pal", "action": "dismiss"})
    assert not _load("pal").companion


def test_paladin_cannot_summon_non_mount(client):
    """En paladin kan kun tilkalde warhorse/warpony som mount, ikke en wolf."""
    r = client.post("/api/companion", json={"char": "pal", "action": "summon",
                    "animal": "wolf"}).get_json()
    assert "error" in r


def test_warhorse_not_a_companion_option():
    """Warhorse/warpony må ikke kunne vælges som almindelig animal companion."""
    assert db_module.get_animal("heavy_warhorse")["companion_ok"] == 0
    assert db_module.get_animal("warpony")["companion_ok"] == 0
