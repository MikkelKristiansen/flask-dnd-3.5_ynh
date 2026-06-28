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
    assert app_module._paladin_caps(_Lvl(level), cha_mod) == (lay, smite)


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
