"""Tests for forbrugsvarer (Del B2): charges + brug (buff-add + øjeblikkelig-rul).

Skriver karakterfilen med safe-YAML (kommentar-fri) så app'ens rt-save + reload er
ren. Kører /api/inventory action=use gennem Flask-klienten.
"""
import pathlib

import pytest
from ruamel.yaml import YAML

import app as app_module
import character as char_module

YAML_SAFE = YAML(typ="safe")
DEFAULTS = pathlib.Path(__file__).parent / "defaults"


@pytest.fixture
def use_client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", tmp_path)

    def make(inventory):
        data = YAML_SAFE.load((DEFAULTS / "aelred.yaml").read_text())
        data["name"] = "Consum"
        data["inventory"] = inventory
        data["buffs"] = []
        with (tmp_path / "consum.yaml").open("w") as f:
            YAML_SAFE.dump(data, f)
        return app_module.app.test_client()

    return make, tmp_path


def _use(client, index):
    return client.post("/api/inventory",
                       json={"char": "consum", "action": "use", "index": index}).get_json()


def _reload(tmp):
    return char_module.load_character(str(tmp / "consum.yaml"))


def test_inv_row_marks_consumable(use_client):
    make, _ = use_client
    client = make([{"ref": "magic_items/wand_of_magic_missile", "state": "backpack", "charges": 50}])
    rows = client.post("/api/inventory", json={"char": "consum", "action": "update",
                                               "index": 0, "notes": "x"}).get_json()["inventory"]
    assert rows[0]["consumable"] is True and rows[0]["charges"] == 50


def test_single_use_potion_rolls_and_is_removed(use_client):
    make, tmp = use_client
    client = make([{"ref": "magic_items/potion_of_cure_light_wounds", "state": "backpack", "charges": 1}])
    used = _use(client, 0)["used"]
    assert used["roll_expr"] == "1d8+1" and used["removed"] is True
    assert len(_reload(tmp).inventory) == 0


def test_wand_decrements_and_stays(use_client):
    make, tmp = use_client
    client = make([{"ref": "magic_items/wand_of_magic_missile", "state": "backpack", "charges": 50}])
    used = _use(client, 0)["used"]
    assert used["roll_expr"] == "1d4+1" and used["charges_left"] == 49
    inv = _reload(tmp).inventory
    assert len(inv) == 1 and inv[0].charges == 49


def test_buff_potion_adds_active_buff(use_client):
    make, tmp = use_client
    client = make([{"ref": "magic_items/potion_of_bulls_strength", "state": "backpack", "charges": 1}])
    used = _use(client, 0)["used"]
    assert used["buff_added"] == "Bull's Strength"
    char = _reload(tmp)
    assert len(char.inventory) == 0
    assert any(b.get("spell_id") == "bull_strength" for b in char.buffs)


def test_empty_wand_rejected(use_client):
    make, _ = use_client
    client = make([{"ref": "magic_items/wand_of_magic_missile", "state": "backpack", "charges": 0}])
    assert _use(client, 0).get("error") == "tom"


def test_non_consumable_rejected(use_client):
    make, _ = use_client
    client = make([{"ref": "magic_items/cloak_of_resistance_1", "state": "worn"}])
    assert _use(client, 0).get("error") == "ikke en forbrugsvare"


# ── Wand-kataloget (SRD's wand-tabel) ────────────────────────────────────────

def test_wand_cl_variant_skalerer(use_client):
    """CL-varianterne har hver sin række, og caster_level styrer skaleringen —
    det er GENSTANDENS CL, ikke brugerens niveau. Karakteren her er 1. niveau;
    wanden er CL 9, så 5 missiler er beviset på at wandens CL bliver brugt."""
    make, _ = use_client
    client = make([{"ref": "magic_items/wand_of_magic_missile_cl9", "state": "backpack", "charges": 50}])
    assert _use(client, 0)["used"]["roll_expr"] == "5d4+5"


def test_wand_uden_spell_er_ikke_forbrugsvare(use_client):
    """De seks wands hvis spell mangler i data/spells.yaml er rene opslag:
    character_view sætter ikke consumable, så 🧪 Brug-knappen vises slet ikke."""
    make, _ = use_client
    client = make([{"ref": "magic_items/wand_of_searing_light", "state": "backpack"}])
    rows = client.post("/api/inventory", json={"char": "consum", "action": "update",
                                               "index": 0, "notes": "x"}).get_json()["inventory"]
    assert rows[0]["consumable"] is False
    assert _use(client, 0).get("error") == "ikke en forbrugsvare"


def test_alle_wands_har_levende_spell_id():
    """Der er ingen fremmednøgle på magic_items.spell_id: et forkert id fejler TAVST
    (wanden tæller ned uden at kaste noget). data/spells.yaml er inkonsistent omkring
    genitiv-s — bear_endurance uden s, eagles_splendor med — så det er let at ramme
    forbi. Denne test er hele sikkerhedsnettet."""
    import db
    døde = [(m["id"], m["spell_id"]) for m in db.get_all_magic_items()
            if m.get("spell_id") and db.get_spell(m["spell_id"]) is None]
    assert døde == [], f"magic_items peger på spells der ikke findes: {døde}"
