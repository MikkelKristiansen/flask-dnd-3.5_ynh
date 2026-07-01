"""Endpoint-tests for Summon Nature's Ally-app-laget (Fase 3b-3d + 4).

Dækker det der hidtil kun var verificeret manuelt via test-klienten: kast,
spontant offer, fjern-ved-Brugt, HP pr. væsen og effekter pr. summon — plus
klasse-gating og guards. Bruger de rigtige defaults-karakterer (druide tjorn,
cleric aelred) kopieret til en tmp-mappe; app.CHARACTERS_DIR monkeypatches dertil.

Kør: python -m pytest test_summon_api.py   (fra sources/)
"""
import pathlib

import pytest
from ruamel.yaml import YAML

import app as app_module
import character as char_module

YAML_RW = YAML()
DEFAULTS = pathlib.Path(__file__).parent / "defaults"


def _write(src_name, dst_dir, slug, mutate):
    """Læs en defaults-karakter, muter den, og skriv til tmp-mappen som <slug>.yaml."""
    data = YAML_RW.load((DEFAULTS / src_name).read_text())
    mutate(data)
    with (dst_dir / f"{slug}.yaml").open("w") as f:
        YAML_RW.dump(data, f)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test-klient med en SNA-klar druide (tjorn) + en cleric (aelred) i tmp."""
    def druid(d):
        # SNA I i et level-1-slot (index 3) + Augment Summoning-feat; ryd dagsstand.
        d["spells_prepared"][1].append("summon_natures_ally_i")
        d["feats"].append("augment_summoning")
        d["spells_active"] = {}
        d["spells_used"] = {}
        d["summons"] = []

    def cleric(d):
        d["spells_active"] = {}
        d["spells_used"] = {}

    _write("tjorn.yaml", tmp_path, "druid", druid)
    _write("aelred.yaml", tmp_path, "cleric", cleric)
    monkeypatch.setattr(app_module, "CHARACTERS_DIR", tmp_path)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _load(slug):
    return char_module.load_character(str(app_module.CHARACTERS_DIR / f"{slug}.yaml"))


# ── Fase 3b: kast ───────────────────────────────────────────────────────────

def test_cast_creates_summon_and_marks_active(client):
    r = client.post("/api/summon", json={"char": "druid", "mode": "cast",
                    "level": 1, "spell_index": 3, "creature": "wolf"})
    body = r.get_json()
    assert body["ok"] is True and body["count"] == 1   # SNA I → altid 1 væsen
    char = _load("druid")
    assert len(char.summons) == 1
    s = char.summons[0]
    assert s["creature"] == "wolf" and s["spell_level"] == 1 and s["spell_index"] == 3
    assert s["augment"] is True                       # snapshot fra feats
    assert s["hp_current"] == [17]                    # fuld HP (wolf 13 + Augment +4)
    assert 3 in char.spells_active[1]                 # spellet er "I brug"


def test_cast_guards(client):
    # Ikke-SNA-slot (index 0 = produce_flame).
    assert client.post("/api/summon", json={"char": "druid", "level": 1,
           "spell_index": 0, "creature": "wolf"}).get_json()["error"]
    # Forkert-niveau-væsen (dire_wolf er SNA III).
    assert client.post("/api/summon", json={"char": "druid", "level": 1,
           "spell_index": 3, "creature": "dire_wolf"}).get_json()["error"]
    # Dobbelt-kast af samme instans afvises.
    client.post("/api/summon", json={"char": "druid", "level": 1,
                "spell_index": 3, "creature": "wolf"})
    assert client.post("/api/summon", json={"char": "druid", "level": 1,
           "spell_index": 3, "creature": "wolf"}).get_json()["error"]


# ── Fase 3c: fjern ved "Brugt" ──────────────────────────────────────────────

def test_used_removes_summon(client):
    client.post("/api/summon", json={"char": "druid", "level": 1,
                "spell_index": 3, "creature": "wolf"})
    r = client.post("/api/spells", json={"char": "druid", "level": 1,
                    "spell_index": 3, "state": "used"})
    assert r.get_json()["is_summon"] is True          # reload-flag
    char = _load("druid")
    assert char.summons == []                         # fanen forsvinder
    assert 3 in char.spells_used[1]


def test_non_summon_spell_no_reload(client):
    # Alm. spell uden bundet væsen → intet reload-flag, summons urørt.
    r = client.post("/api/spells", json={"char": "druid", "level": 1,
                    "spell_index": 0, "state": "used"})
    assert r.get_json()["is_summon"] is False


# ── Fase 3d: HP + effekter pr. summon ───────────────────────────────────────

def test_summon_hp_adjust_and_clamp(client):
    client.post("/api/summon", json={"char": "druid", "level": 1,
                "spell_index": 3, "creature": "wolf"})
    # −5 fra fuld (17) → 12.
    r = client.post("/api/summon_hp", json={"char": "druid", "spell_level": 1,
                    "spell_index": 3, "creature_index": 0, "delta": -5})
    assert r.get_json()["hp_current"] == [12]
    # Op igen klampes til hp_max (ikke over 17).
    r = client.post("/api/summon_hp", json={"char": "druid", "spell_level": 1,
                    "spell_index": 3, "creature_index": 0, "delta": 99})
    assert r.get_json()["hp_current"] == [17]


def test_condition_and_buff_on_summon(client):
    client.post("/api/summon", json={"char": "druid", "level": 1,
                "spell_index": 3, "creature": "wolf"})
    base = {"char": "druid", "target": "summon", "spell_level": 1, "spell_index": 3}
    client.post("/api/conditions", json={**base, "condition_id": "entangled", "action": "add"})
    client.post("/api/buffs", json={**base, "action": "add",
                "buff": {"name": "Bless", "note": "+1 attack", "affects": ["attack"]}})
    s = _load("druid").summons[0]
    assert s["conditions"] == ["entangled"]
    assert [b["name"] for b in s["buffs"]] == ["Bless"]
    # Remove igen.
    client.post("/api/conditions", json={**base, "condition_id": "entangled", "action": "remove"})
    client.post("/api/buffs", json={**base, "action": "remove", "index": 0})
    s = _load("druid").summons[0]
    assert not s.get("conditions") and not s.get("buffs")


# ── Fase 4: spontant offer ──────────────────────────────────────────────────

def test_sacrifice_druid(client):
    # Ofre cure_light_wounds (index 1) til SNA I → eagle.
    r = client.post("/api/summon", json={"char": "druid", "mode": "sacrifice",
                    "level": 1, "spell_index": 1, "creature": "eagle"})
    assert r.get_json()["ok"] is True
    char = _load("druid")
    assert char.summons[0]["creature"] == "eagle"
    assert 1 in char.spells_active[1]
    # "Brugt" på det ofrede slot fjerner væsenet (bundet, selvom ikke-SNA-spell).
    client.post("/api/spells", json={"char": "druid", "level": 1,
                "spell_index": 1, "state": "used"})
    assert _load("druid").summons == []


def test_sacrifice_rejected_for_non_druid(client):
    # Cleric (intet spontaneous_summon-flag) afvises server-side.
    r = client.post("/api/summon", json={"char": "cleric", "mode": "sacrifice",
                    "level": 1, "spell_index": 0, "creature": "eagle"})
    assert "klassen" in r.get_json()["error"]


def test_sacrifice_rejects_sna_spell_itself(client):
    # Selve SNA-spellet skal kastes med "Kast", ikke ofres.
    r = client.post("/api/summon", json={"char": "druid", "mode": "sacrifice",
                    "level": 1, "spell_index": 3, "creature": "eagle"})
    assert r.get_json()["error"]
